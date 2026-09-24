"""Fotograf okuma: format, bit derinligi, EXIF yonu, ICC ve alpha.

Tasarim kararlari
-----------------
* Okuma sonucu her zaman float32 0..1 RGB/RGBA'dir; 16-bit girisler
  yolda 8-bit'e dusurulmez.
* EXIF Orientation okunur ve piksellere *uygulanir*; sonrasinda goruntu
  gorsel olarak dik olur ve yon etiketi 1 kabul edilir.
* ICC profili varsa sRGB'ye donusturulur; yoksa sRGB varsayilir ve bu
  varsayim ImageMetadata.assumed_srgb ile kaydedilir.
* Bozuk/desteklenmeyen dosya ImageLoadError firlatir; cagiran katman
  tek dosya hatasinin toplu islemi durdurmasina izin vermez.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageCms, ImageFile, UnidentifiedImageError

from luma_atelier.imaging import pixels as px

log = logging.getLogger(__name__)

# Kismen bozuk JPEG'lerde elde olani goster, tamamen reddetme
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Pillow'un decompression-bomb esigi. 200 MP profesyonel fotograflar icin
# bile fazlasiyla yeterli, kotu niyetli dosyalari eler.
Image.MAX_IMAGE_PIXELS = 400_000_000

SUPPORTED_INPUT_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".tif", ".tiff", ".bmp"}
)
"""Dogrulanmis giris uzantilari. Matris docs/FORMAT_SUPPORT.md icinde."""


class ImageLoadError(Exception):
    """Dosya okunamadi. Mesaj kullaniciya gosterilecek Turkce metindir."""

    def __init__(self, message: str, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


@dataclass(frozen=True)
class ImageMetadata:
    """Yuklenen dosyanin kaynak ozellikleri."""

    path: Path
    width: int
    height: int
    source_bit_depth: int
    has_alpha: bool
    source_format: str
    exif_orientation: int = 1
    orientation_applied: bool = False
    icc_profile: bytes | None = None
    icc_description: str = ""
    assumed_srgb: bool = True
    icc_applied: bool = False
    """Gomulu profil gercekten sRGB'ye cevrildi mi?

    Profilin *okunmus* olmasi uygulandigi anlamina gelmez. 16-bit
    TIFF'ler tifffile ile okunuyordu ve donusum atlaniyordu: ProPhoto
    profilli bir dosyada olculen sapma kanal basina 69/255'e kadar
    cikiyordu. Bu alan, uygulamanin yapmadigi bir seyi yapmis gibi
    bildirmesini engeller.
    """
    exif_bytes: bytes | None = None
    exif_tags: dict[int, Any] = field(default_factory=dict)

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1_000_000.0


@dataclass(frozen=True)
class LoadedImage:
    """Calisma tamponuyla birlikte kaynak bilgisi."""

    pixels: np.ndarray  # float32 (Y, X, 3|4), 0..1, sRGB kodlu
    metadata: ImageMetadata

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def has_alpha(self) -> bool:
        return self.pixels.shape[2] == 4


# EXIF Orientation -> uygulanacak geometrik donusum
_ORIENTATION_OPS: dict[int, str] = {
    1: "none",
    2: "flip_h",
    3: "rot180",
    4: "flip_v",
    5: "transpose",
    6: "rot270",   # saat yonunde 90
    7: "transverse",
    8: "rot90",    # saat yonunun tersine 90
}


def apply_orientation(arr: np.ndarray, orientation: int) -> np.ndarray:
    """EXIF yon etiketini piksellere uygular.

    Telefonla dikey cekilmis fotograflarin yan yatmasini onler.
    Bilinmeyen etiketlerde goruntu degistirilmeden dondurulur.
    """
    op = _ORIENTATION_OPS.get(int(orientation), "none")
    if op == "none":
        return arr
    if op == "flip_h":
        out = arr[:, ::-1]
    elif op == "flip_v":
        out = arr[::-1, :]
    elif op == "rot180":
        out = arr[::-1, ::-1]
    elif op == "rot90":
        out = np.rot90(arr, k=1)
    elif op == "rot270":
        out = np.rot90(arr, k=-1)
    elif op == "transpose":
        out = np.swapaxes(arr, 0, 1)
    elif op == "transverse":
        out = np.rot90(arr, k=-1)[:, ::-1]
    else:
        return arr
    return np.ascontiguousarray(out)


#: Pillow'un renk yonetiminin dogrudan cevirebildigi modlar disinda
#: kalanlar; bunlar dizi uzerinde kafesle cevrilir.
_HIGH_DEPTH_MODES = frozenset({"I;16", "I;16B", "I;16L", "I", "F"})


def _read_icc(im: Image.Image) -> tuple[bytes | None, str]:
    blob = im.info.get("icc_profile")
    if not blob:
        return None, ""
    try:
        prof = ImageCms.getOpenProfile(io.BytesIO(blob))
        return blob, (ImageCms.getProfileDescription(prof) or "").strip()
    except Exception:  # noqa: BLE001 - bozuk profil dosyayi reddetmemeli
        log.warning("ICC profili çözümlenemedi, sRGB varsayılıyor")
        return None, ""


def _convert_to_srgb(im: Image.Image, blob: bytes) -> Image.Image:
    """Gomulu profili sRGB'ye donusturur.

    Basarisiz olursa goruntu oldugu gibi birakilir ve renk kaymasi
    olabilecegi log'a yazilir.
    """
    try:
        src = ImageCms.getOpenProfile(io.BytesIO(blob))
        dst = ImageCms.createProfile("sRGB")
        mode = im.mode
        if mode in ("I;16", "I;16B", "I;16L", "I", "F"):
            return im  # yuksek bit derinligi: donusum yerine sRGB varsay
        if mode not in ("RGB", "RGBA", "L", "LA", "CMYK", "YCbCr"):
            return im
        out_mode = "RGBA" if mode in ("RGBA", "LA") else "RGB"
        return ImageCms.profileToProfile(
            im, src, dst, outputMode=out_mode, renderingIntent=0
        ) or im
    except Exception as exc:  # noqa: BLE001
        log.warning("ICC -> sRGB dönüşümü başarısız (%s); profil yok sayılıyor", exc)
        return im


def _pil_to_working(im: Image.Image) -> tuple[np.ndarray, int]:
    """Pillow goruntusunu float32 calisma tamponuna cevirir.

    Ikinci deger kaynak bit derinligidir (8, 16 veya 32).
    """
    mode = im.mode
    if mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(im)
        if arr.dtype in (np.int32, np.uint32):
            arr = np.clip(arr, 0, 65535).astype(np.uint16)
        return px.ensure_working(px.from_uint16(arr)), 16
    if mode == "F":
        return px.ensure_working(np.asarray(im, dtype=np.float32)), 32
    if mode not in ("RGB", "RGBA"):
        wants_alpha = mode in ("LA", "PA", "RGBa", "La") or (
            mode == "P" and "transparency" in im.info
        )
        im = im.convert("RGBA" if wants_alpha else "RGB")
    arr = np.asarray(im)
    if arr.dtype == np.uint16:
        return px.ensure_working(px.from_uint16(arr)), 16
    return px.ensure_working(px.from_uint8(arr)), 8



#: Yuksek bit derinlikli goruntulerde ICC donusumu icin kafes boyutu.
#: 51 = 255 / 5 oldugu icin 52 noktali kafesin tum dugumleri 8-bit'te
#: birebir temsil edilir; kafes konumunda yuvarlama hatasi olmaz.
ICC_LUT_SIZE = 52


def _icc_lut(blob: bytes) -> "Lut3D | None":
    """Gomulu profilden sRGB'ye goturen 3B kafes uretir.

    Neden kafes: Pillow'un renk yonetimi 16-bit RGB goruntuyu dogrudan
    donusturemiyor (boyle bir mod yok). Kafes lcms ile 8-bit'te
    ornekleniyor, sonra float veriye trilineer interpolasyonla
    uygulaniyor. Boylece **pikselin kendi hassasiyeti korunur**;
    yalnizca esleme egrisi 8-bit adimlarla orneklenmis olur. Donusum
    hic yapilmadiginda olculen hata 69/255 iken, bu yolla 1-2/255
    mertebesine iner.
    """
    from luma_atelier.imaging.lut3d import Lut3D

    size = ICC_LUT_SIZE
    step = 255 // (size - 1)
    axis = np.arange(size, dtype=np.uint8) * step
    r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")
    grid = np.stack([r, g, b], axis=-1).reshape(size, size * size, 3)
    try:
        src = ImageCms.getOpenProfile(io.BytesIO(blob))
        dst = ImageCms.createProfile("sRGB")
        probe = Image.fromarray(grid.astype(np.uint8), "RGB")
        mapped = ImageCms.profileToProfile(probe, src, dst, outputMode="RGB",
                                           renderingIntent=0)
    except Exception as exc:  # noqa: BLE001 - bozuk profil dosyayi reddetmemeli
        log.warning("ICC kafesi kurulamadi (%s); sRGB varsayiliyor", exc)
        return None
    if mapped is None:
        return None
    table = (np.asarray(mapped, np.float32) / 255.0).reshape(size, size,
                                                             size, 3)
    return Lut3D(name="ICC -> sRGB", size=size, table=table)


def _convert_array_to_srgb(work: np.ndarray,
                           blob: bytes) -> tuple[np.ndarray, bool]:
    """Calisma dizisini gomulu profilden sRGB'ye cevirir.

    Returns:
        (dizi, donusum uygulandi mi)
    """
    from luma_atelier.imaging.lut3d import apply_lut3d

    lut = _icc_lut(blob)
    if lut is None:
        return work, False
    if lut.is_identity:
        # Profil zaten sRGB: bos yere islem yapma
        return work, True
    return apply_lut3d(work, lut, 1.0), True


def _load_tiff(path: Path) -> tuple[np.ndarray, int, bool] | None:
    """16-bit TIFF'i tifffile ile okur (Pillow bazi varyantlari dusurur).

    Basarisiz olursa None doner ve Pillow yoluna gecilir.
    """
    try:
        import tifffile
    except ImportError:
        return None
    try:
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            arr = page.asarray()
    except Exception as exc:  # noqa: BLE001
        log.debug("tifffile TIFF okuyamadi (%s); Pillow denenecek", exc)
        return None

    if arr.ndim == 2:
        arr = arr[..., None]
    if arr.ndim != 3 or arr.shape[2] not in (1, 2, 3, 4):
        return None

    has_alpha = arr.shape[2] in (2, 4)
    if arr.dtype == np.uint8:
        work, depth = px.from_uint8(arr), 8
    elif arr.dtype == np.uint16:
        work, depth = px.from_uint16(arr), 16
    elif arr.dtype in (np.float32, np.float64):
        work, depth = arr.astype(np.float32), 32
    else:
        return None

    if arr.shape[2] == 1:
        work = work.repeat(3, axis=2)
    elif arr.shape[2] == 2:  # gri + alpha
        work = np.dstack([work[..., 0:1].repeat(3, axis=2), work[..., 1:2]])
    return px.ensure_working(work), depth, has_alpha


def load_image(path: str | Path, *, apply_exif_orientation: bool = True) -> LoadedImage:
    """Fotografi diskten okuyup calisma tamponu ve metadata dondurur.

    Raises:
        ImageLoadError: dosya yok, desteklenmiyor, bozuk veya cozulemedi.
    """
    p = Path(path)
    if not p.exists():
        raise ImageLoadError(f"Dosya bulunamadı: {p.name}", p)
    if not p.is_file():
        raise ImageLoadError(f"Bu bir dosya değil: {p.name}", p)
    try:
        if p.stat().st_size == 0:
            raise ImageLoadError(f"Dosya boş: {p.name}", p)
    except OSError as exc:
        raise ImageLoadError(f"Dosya okunamadı: {p.name} ({exc.strerror})", p) from exc

    suffix = p.suffix.lower()
    tiff_result = _load_tiff(p) if suffix in (".tif", ".tiff") else None

    try:
        with Image.open(p) as im:
            im.load()
            source_format = (im.format or suffix.lstrip(".")).upper()
            exif_tags: dict[int, Any] = {}
            orientation = 1
            exif_bytes: bytes | None = im.info.get("exif")
            try:
                raw = im.getexif()
                exif_tags = {int(k): v for k, v in raw.items()}
                orientation = int(exif_tags.get(274, 1) or 1)
            except Exception:  # noqa: BLE001 - bozuk EXIF dosyayi reddetmemeli
                log.debug("EXIF okunamadi: %s", p.name)

            icc_blob, icc_desc = _read_icc(im)

            icc_applied = False
            if tiff_result is not None:
                work, depth, _ = tiff_result
                if icc_blob:
                    work, icc_applied = _convert_array_to_srgb(work, icc_blob)
            elif icc_blob and im.mode in _HIGH_DEPTH_MODES:
                # Pillow bu modlarda renk donusumu yapamaz; kafesle cevir
                work, depth = _pil_to_working(im)
                work, icc_applied = _convert_array_to_srgb(work, icc_blob)
            else:
                src = _convert_to_srgb(im, icc_blob) if icc_blob else im
                work, depth = _pil_to_working(src)
                icc_applied = bool(icc_blob) and src is not im
    except ImageLoadError:
        raise
    except UnidentifiedImageError as exc:
        raise ImageLoadError(f"Dosya bicimi taninmadi veya bozuk: {p.name}", p) from exc
    except Image.DecompressionBombError as exc:
        raise ImageLoadError(f"Fotoğraf guvenlik sinirindan büyük: {p.name}", p) from exc
    except MemoryError as exc:
        raise ImageLoadError(f"Fotoğraf bellege sigmadi: {p.name}", p) from exc
    except OSError as exc:
        raise ImageLoadError(f"Dosya okunamadı: {p.name} ({exc})", p) from exc

    if work.size == 0:
        raise ImageLoadError(f"Fotoğraf boş gorunuyor: {p.name}", p)

    applied = False
    if apply_exif_orientation and orientation != 1:
        work = apply_orientation(work, orientation)
        applied = True

    meta = ImageMetadata(
        path=p,
        width=int(work.shape[1]),
        height=int(work.shape[0]),
        source_bit_depth=depth,
        has_alpha=work.shape[2] == 4,
        source_format=source_format,
        exif_orientation=orientation,
        orientation_applied=applied,
        icc_profile=icc_blob,
        icc_description=icc_desc,
        # Profil okunmus ama uygulanamamissa goruntu yine sRGB
        # varsayilmistir; kullaniciya boyle bildirilmeli.
        assumed_srgb=icc_blob is None or not icc_applied,
        icc_applied=icc_applied,
        exif_bytes=exif_bytes,
        exif_tags=exif_tags,
    )
    return LoadedImage(pixels=work, metadata=meta)


def probe_image(path: str | Path) -> ImageMetadata | None:
    """Pikselleri okumadan hizli bilgi alir; kitaplik taramasi icin.

    Basarisizsa None doner (tarama tek bozuk dosyada durmasin).
    """
    p = Path(path)
    try:
        with Image.open(p) as im:
            orientation = 1
            try:
                orientation = int(im.getexif().get(274, 1) or 1)
            except Exception:  # noqa: BLE001
                pass
            w, h = im.size
            if orientation in (5, 6, 7, 8):
                w, h = h, w
            blob = im.info.get("icc_profile")
            depth = 16 if im.mode in ("I;16", "I;16B", "I;16L", "I") else 8
            return ImageMetadata(
                path=p,
                width=w,
                height=h,
                source_bit_depth=depth,
                has_alpha=im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info,
                source_format=(im.format or p.suffix.lstrip(".")).upper(),
                exif_orientation=orientation,
                icc_profile=blob,
                assumed_srgb=blob is None,
            )
    except Exception:  # noqa: BLE001 - tarama dayanikli olmali
        return None

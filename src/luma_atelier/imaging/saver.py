"""Fotograf yazma: JPEG, PNG, WebP ve 16-bit TIFF.

Guvenlik kurallari
------------------
* Once gecici dosyaya yazilir, basarili biterse nihai ada tasinir.
  Iptal edilen veya coken export yarim dosya birakmaz.
* Kaynak dosyanin uzerine yazmak varsayilan degildir; cagiran katman
  acikca izin vermelidir.
* Cikti dosyasina dogru ICC profili yazilir.
* Formatin desteklemedigi ozellik (orn. JPEG'de alpha) sessizce
  atlanmaz; RGB'ye dusurulurken kullanicinin sectigi dolgu rengi
  kullanilir.
"""
from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile

from luma_atelier.imaging import pixels as px

log = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """Desteklenen cikti formatlari."""

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    TIFF = "tiff"

    @property
    def extension(self) -> str:
        return {
            OutputFormat.JPEG: ".jpg",
            OutputFormat.PNG: ".png",
            OutputFormat.WEBP: ".webp",
            OutputFormat.TIFF: ".tif",
        }[self]

    @property
    def label(self) -> str:
        return {
            OutputFormat.JPEG: "JPEG",
            OutputFormat.PNG: "PNG",
            OutputFormat.WEBP: "WebP",
            OutputFormat.TIFF: "TIFF",
        }[self]

    @property
    def supports_alpha(self) -> bool:
        return self in (OutputFormat.PNG, OutputFormat.WEBP, OutputFormat.TIFF)

    @property
    def supports_quality(self) -> bool:
        """PNG/TIFF kayipsizdir; sahte kalite slider'i gosterilmez."""
        return self in (OutputFormat.JPEG, OutputFormat.WEBP)

    @property
    def supports_16bit(self) -> bool:
        return self is OutputFormat.TIFF


class ImageSaveError(Exception):
    """Yazma basarisiz. Mesaj kullaniciya gosterilecek Turkce metindir."""


@dataclass(frozen=True)
class SaveOptions:
    """Tek bir dosya yazma isleminin tum secenekleri."""

    fmt: OutputFormat = OutputFormat.JPEG
    quality: int = 92
    bit_depth: int = 8
    """8 veya 16. 16 yalnizca TIFF'te gecerlidir."""
    flatten_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    """Alpha desteklemeyen formatta saydam alanin dolgu rengi (0..1)."""
    keep_alpha: bool = True
    icc_profile: bytes | None = None
    exif_bytes: bytes | None = None
    strip_metadata: bool = False
    png_compress_level: int = 6
    webp_lossless: bool = False
    overwrite: bool = False
    """False iken var olan dosyanin uzerine yazilmaz; guvenli ad uretilir."""


@dataclass(frozen=True)
class SaveResult:
    path: Path
    bytes_written: int
    fmt: OutputFormat
    bit_depth: int
    had_alpha: bool
    renamed_from_conflict: bool = False


def unique_path(path: Path) -> tuple[Path, bool]:
    """Cakisma varsa "ad (2).jpg" seklinde guvenli yeni ad uretir."""
    if not path.exists():
        return path, False
    stem, suffix, parent = path.stem, path.suffix, path.parent
    for i in range(2, 10_000):
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate, True
    raise ImageSaveError(f"Uygun boş dosya adı bulunamadı: {path.name}")


def _prepare_array(img: np.ndarray, opt: SaveOptions) -> tuple[np.ndarray, bool]:
    """Calisma tamponunu hedef formatin kabul ettigi diziye cevirir."""
    work = px.ensure_working(img)
    has_alpha = work.shape[2] == 4

    if has_alpha and not (opt.fmt.supports_alpha and opt.keep_alpha):
        work = px.composite_over(work, opt.flatten_color)
        has_alpha = False

    work = np.clip(work, 0.0, 1.0)
    if opt.bit_depth == 16 and opt.fmt.supports_16bit:
        return px.to_uint16(work), has_alpha
    return px.to_uint8(work), has_alpha


def _pil_mode(arr: np.ndarray) -> str:
    channels = arr.shape[2]
    if arr.dtype == np.uint16:
        return "RGBA" if channels == 4 else "RGB"
    return "RGBA" if channels == 4 else "RGB"


def _write_tiff(path: Path, arr: np.ndarray, opt: SaveOptions) -> None:
    """TIFF yazma - 16-bit icin tifffile, aksi halde Pillow."""
    import tifffile

    extratags = []
    if opt.icc_profile and not opt.strip_metadata:
        # TIFF etiketi 34675 = InterColourProfile
        extratags.append((34675, 7, len(opt.icc_profile), opt.icc_profile, True))
    photometric = "rgb"
    extrasamples = ("unassoc",) if arr.shape[2] == 4 else None
    tifffile.imwrite(
        path,
        arr,
        photometric=photometric,
        extrasamples=extrasamples,
        compression="adobe_deflate",
        extratags=extratags,
        metadata=None,
    )


#: Kodlayici tamponu icin piksel basina emniyet payi. Saf gurultude
#: gercek JPEG ~2 bayt/piksele ulasabiliyor; 4 kat pay guvenli sinirdir.
_ENCODER_HEADROOM = 4
#: Ust veri ve basliklar icin sabit ek pay
_ENCODER_EXTRA_BYTES = 1 << 20


@contextmanager
def _encoder_buffer(pixel_count: int):
    """Pillow'un kodlayici tamponunu gecici olarak buyutur.

    Bkz. modul icindeki aciklama: `optimize`/`progressive` acikken
    yetersiz tampon yuksek entropili goruntulerde yazmayi cokertir.
    """
    previous = ImageFile.MAXBLOCK
    ImageFile.MAXBLOCK = max(
        previous,
        pixel_count * _ENCODER_HEADROOM + _ENCODER_EXTRA_BYTES,
    )
    try:
        yield
    finally:
        ImageFile.MAXBLOCK = previous


def _write_pillow(path: Path, arr: np.ndarray, opt: SaveOptions) -> None:
    im = Image.fromarray(arr, mode=_pil_mode(arr))
    params: dict[str, object] = {}
    if opt.icc_profile and not opt.strip_metadata:
        params["icc_profile"] = opt.icc_profile
    if opt.exif_bytes and not opt.strip_metadata and opt.fmt in (
        OutputFormat.JPEG,
        OutputFormat.WEBP,
    ):
        params["exif"] = opt.exif_bytes

    if opt.fmt is OutputFormat.JPEG:
        params.update(
            quality=int(np.clip(opt.quality, 1, 100)),
            subsampling=0 if opt.quality >= 90 else 2,
            optimize=True,
            progressive=True,
        )
        with _encoder_buffer(im.width * im.height):
            im.save(path, format="JPEG", **params)
    elif opt.fmt is OutputFormat.PNG:
        params.update(compress_level=int(np.clip(opt.png_compress_level, 0, 9)))
        im.save(path, format="PNG", **params)
    elif opt.fmt is OutputFormat.WEBP:
        if opt.webp_lossless:
            params.update(lossless=True, quality=100, method=4)
        else:
            params.update(quality=int(np.clip(opt.quality, 1, 100)), method=4)
        with _encoder_buffer(im.width * im.height):
            im.save(path, format="WEBP", **params)
    else:
        raise ImageSaveError(f"Bu yol {opt.fmt.label} için kullanılmaz")


def save_image(
    img: np.ndarray, path: str | Path, options: SaveOptions | None = None
) -> SaveResult:
    """Calisma tamponunu diske yazar.

    Once ayni klasorde gecici dosyaya yazar, basarili olursa nihai ada
    tasir. Boylece iptal veya hata yarim dosya birakmaz.

    Raises:
        ImageSaveError: klasor yok, yazma izni yok, disk dolu veya
            kodlayici hata verdi.
    """
    opt = options or SaveOptions()
    target = Path(path)
    renamed = False

    if target.suffix.lower() not in (opt.fmt.extension, ".jpeg", ".tiff"):
        target = target.with_suffix(opt.fmt.extension)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImageSaveError(
            f"Hedef klasör olusturulamadi: {target.parent} ({exc.strerror})"
        ) from exc

    if not opt.overwrite:
        target, renamed = unique_path(target)

    arr, had_alpha = _prepare_array(img, opt)

    tmp_fd, tmp_name = -1, ""
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.stem}-", suffix=opt.fmt.extension + ".part",
            dir=str(target.parent),
        )
        os.close(tmp_fd)
        tmp_fd = -1
        tmp_path = Path(tmp_name)

        if opt.fmt is OutputFormat.TIFF:
            _write_tiff(tmp_path, arr, opt)
        else:
            _write_pillow(tmp_path, arr, opt)

        size = tmp_path.stat().st_size
        if size == 0:
            raise ImageSaveError(f"Kodlayici boş dosya uretti: {target.name}")

        os.replace(tmp_path, target)  # ayni birimde atomik
    except ImageSaveError:
        _cleanup(tmp_name)
        raise
    except PermissionError as exc:
        _cleanup(tmp_name)
        raise ImageSaveError(
            f"Yazma izni yok: {target.parent}. Başka bir klasör seçin."
        ) from exc
    except OSError as exc:
        _cleanup(tmp_name)
        if getattr(exc, "errno", None) == 28:
            raise ImageSaveError("Diskte yeterli yer yok.") from exc
        raise ImageSaveError(f"Dosya yazilamadi: {target.name} ({exc})") from exc
    except Exception as exc:  # noqa: BLE001 - kodlayici hatalari
        _cleanup(tmp_name)
        raise ImageSaveError(f"Kaydetme başarısız: {target.name} ({exc})") from exc
    finally:
        if tmp_fd != -1:
            os.close(tmp_fd)

    return SaveResult(
        path=target,
        bytes_written=size,
        fmt=opt.fmt,
        bit_depth=16 if arr.dtype == np.uint16 else 8,
        had_alpha=had_alpha,
        renamed_from_conflict=renamed,
    )


def _cleanup(tmp_name: str) -> None:
    if not tmp_name:
        return
    try:
        Path(tmp_name).unlink(missing_ok=True)
    except OSError:
        log.debug("Gecici dosya silinemedi: %s", tmp_name)

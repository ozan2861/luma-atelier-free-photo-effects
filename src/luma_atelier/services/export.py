"""Tam cozunurluklu disa aktarma ve toplu kuyruk.

Tasarim kararlari
-----------------
* **Orijinal asla degismez.** Cikti her zaman ayri bir dosyadir; hedef
  klasor kaynakla ayni olsa bile ad sablonu cakismayi onler ve cakisma
  politikasi kullanicinindir.
* **Onizlemeyle ayni motor.** Render yolu duzenleyicinin kullandiginin
  aynisidir: once geometri kaynaga, sonra olcekleme, sonra efekt yigini.
  Sira farkli olsa tam boy cikti onizlemeden farkli gorunurdu.
* **Yeniden boyutlandirma geometriden sonra.** Kullanici "uzun kenar
  2048" dediginde *cikti* fotografin uzun kenarini kastediyor, kirpma
  oncesi kaynagi degil.
* **Hata izolasyonu.** Kuyrukta bir dosyanin cokmesi digerlerini
  durdurmaz; basarisizlar ayri listelenir ve yeniden denenebilir.
* **Iptal yarim dosya birakmaz.** `save_image` gecici dosyaya yazip
  yeniden adlandirir; iptal kontrolu yazma *baslamadan* once yapilir.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.effects.base import RenderContext
from luma_atelier.imaging.loader import ImageMetadata, load_image
from luma_atelier.imaging.recipe import Recipe
from luma_atelier.imaging.saver import (
    ImageSaveError,
    OutputFormat,
    SaveOptions,
    save_image,
    unique_path,
)

log = logging.getLogger(__name__)

#: Cok buyuk cikti istenirse uyarma esigi (piksel)
LARGE_OUTPUT_PIXELS = 80_000_000


class ResizeMode(str, Enum):
    """Cikti boyutlandirma kipi."""

    NONE = "none"
    LONG_EDGE = "long_edge"
    WIDTH = "width"
    HEIGHT = "height"
    PERCENT = "percent"

    @property
    def label(self) -> str:
        return {
            ResizeMode.NONE: "Orijinal boyut",
            ResizeMode.LONG_EDGE: "Uzun kenar",
            ResizeMode.WIDTH: "Genişlik",
            ResizeMode.HEIGHT: "Yükseklik",
            ResizeMode.PERCENT: "Yüzde",
        }[self]

    @property
    def needs_value(self) -> bool:
        return self is not ResizeMode.NONE


class MetadataPolicy(str, Enum):
    """Cikti dosyasina hangi ust verinin yazilacagi."""

    KEEP = "keep"
    STRIP_GPS = "strip_gps"
    STRIP_ALL = "strip_all"

    @property
    def label(self) -> str:
        return {
            MetadataPolicy.KEEP: "Tümünü koru",
            MetadataPolicy.STRIP_GPS: "Konumu (GPS) kaldır",
            MetadataPolicy.STRIP_ALL: "Tüm üst veriyi kaldır",
        }[self]

    @property
    def description(self) -> str:
        return {
            MetadataPolicy.KEEP:
                "Çekim bilgisi, tarih ve konum çıktıya yazılır.",
            MetadataPolicy.STRIP_GPS:
                "Çekim bilgisi korunur, konum bilgisi silinir. "
                "Fotoğrafı paylaşırken güvenli seçimdir.",
            MetadataPolicy.STRIP_ALL:
                "Hiçbir üst veri yazılmaz; yalnızca renk profili kalır.",
        }[self]


class ConflictPolicy(str, Enum):
    """Hedefte ayni adda dosya varsa ne yapilacagi."""

    RENAME = "rename"
    OVERWRITE = "overwrite"
    SKIP = "skip"

    @property
    def label(self) -> str:
        return {
            ConflictPolicy.RENAME: "Yeni ad ver",
            ConflictPolicy.OVERWRITE: "Üzerine yaz",
            ConflictPolicy.SKIP: "Atla",
        }[self]


#: Ad sablonunda kullanilabilecek alanlar
NAME_TOKENS: tuple[tuple[str, str], ...] = (
    ("{ad}", "Kaynak dosya adı (uzantısız)"),
    ("{sayac}", "Sıra numarası (001, 002, ...)"),
    ("{genislik}", "Çıktı genişliği"),
    ("{yukseklik}", "Çıktı yüksekliği"),
    ("{tarih}", "Bugünün tarihi (2026-09-17)"),
    ("{gorunum}", "Uygulanan hazır görünümün adı"),
)

#: Windows dosya adinda yasak karakterler
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
#: Windows'ta ayrilmis cihaz adlari
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class ExportSettings:
    """Bir disa aktarma isinin tum secenekleri."""

    folder: Path = Path()
    fmt: OutputFormat = OutputFormat.JPEG
    quality: int = 92
    bit_depth: int = 8
    resize: ResizeMode = ResizeMode.NONE
    resize_value: int = 2048
    name_template: str = "{ad}-luma"
    metadata: MetadataPolicy = MetadataPolicy.STRIP_GPS
    conflict: ConflictPolicy = ConflictPolicy.RENAME
    embed_icc: bool = True
    webp_lossless: bool = False
    png_compress_level: int = 6

    def effective_bit_depth(self) -> int:
        """Bicim 16 bit desteklemiyorsa 8'e duser."""
        return self.bit_depth if self.fmt.supports_16bit else 8

    def output_size(self, width: int, height: int) -> tuple[int, int]:
        """Verilen kadraj boyutunun cikti boyutu."""
        if self.resize is ResizeMode.NONE or self.resize_value <= 0:
            return (width, height)
        value = self.resize_value
        if self.resize is ResizeMode.PERCENT:
            factor = max(0.01, value / 100.0)
        elif self.resize is ResizeMode.LONG_EDGE:
            factor = value / max(1, max(width, height))
        elif self.resize is ResizeMode.WIDTH:
            factor = value / max(1, width)
        else:
            factor = value / max(1, height)
        return (max(1, int(round(width * factor))),
                max(1, int(round(height * factor))))


@dataclass(frozen=True)
class ExportJob:
    """Kuyruktaki tek is."""

    source: Path
    recipe: Recipe = field(default_factory=Recipe)
    preset_name: str = ""
    #: Zaten yuklu piksel varsa yeniden okunmaz (acik fotograf icin)
    pixels: np.ndarray | None = None
    metadata: ImageMetadata | None = None


@dataclass(frozen=True)
class ExportResult:
    """Tek isin sonucu."""

    job: ExportJob
    path: Path | None = None
    width: int = 0
    height: int = 0
    bit_depth: int = 8
    bytes_written: int = 0
    elapsed_ms: float = 0.0
    skipped: bool = False
    renamed: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and (self.path is not None or self.skipped)


# ============================================================ AD URETIMI
def safe_stem(text: str, fallback: str = "foto") -> str:
    """Windows'ta gecerli bir dosya govdesi uretir.

    Yasak karakterler, sondaki nokta/bosluk ve ayrilmis cihaz adlari
    (CON, NUL, ...) temizlenir. Bos kalirsa `fallback` kullanilir.
    """
    cleaned = _ILLEGAL.sub("_", text).strip().rstrip(". ")
    if not cleaned:
        return fallback
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:150]


def build_name(template: str, *, source: Path, index: int, width: int,
               height: int, preset: str = "") -> str:
    """Ad sablonunu doldurur (uzantisiz)."""
    values = {
        "{ad}": source.stem,
        "{sayac}": f"{index:03d}",
        "{genislik}": str(width),
        "{yukseklik}": str(height),
        "{tarih}": time.strftime("%Y-%m-%d"),
        "{gorunum}": preset or "duzenleme",
    }
    out = template or "{ad}"
    for token, value in values.items():
        out = out.replace(token, str(value))
    return safe_stem(out, fallback=safe_stem(source.stem))


def preview_names(template: str, sources: list[Path], settings: ExportSettings,
                  limit: int = 3) -> list[str]:
    """Kullaniciya gosterilecek ornek cikti adlari."""
    out: list[str] = []
    for i, source in enumerate(sources[:limit], start=1):
        stem = build_name(template, source=source, index=i,
                          width=0, height=0)
        out.append(stem + settings.fmt.extension)
    return out


# =========================================================== TEK DOSYA
def render_for_export(pixels: np.ndarray, recipe: Recipe,
                      settings: ExportSettings) -> np.ndarray:
    """Tam kalitede render eder.

    Sira duzenleyicinin onizleme yolunun **aynisidir**:
    geometri -> olcekleme -> efekt yigini. Efektlerin piksel cinsinden
    parametreleri `RenderContext.scale` ile uyarlanir; boylece kucultulmus
    ciktida da ayni karakter korunur.
    """
    working = px.ensure_working(pixels)
    geometry = recipe.geometry
    base = np.ascontiguousarray(geometry.apply(working)) \
        if not geometry.is_identity else working

    full_h, full_w = base.shape[:2]
    target_w, target_h = settings.output_size(full_w, full_h)
    scale = 1.0
    if (target_w, target_h) != (full_w, full_h):
        # Kucultmede INTER_AREA, buyutmede INTER_CUBIC dogru secim
        interp = (cv2.INTER_AREA if target_w < full_w else cv2.INTER_CUBIC)
        base = cv2.resize(base, (target_w, target_h), interpolation=interp)
        scale = target_w / max(1, full_w)

    ctx = RenderContext(full_width=full_w, full_height=full_h, scale=scale,
                        seed=recipe.seed, quality="final", purpose="export")
    return recipe.without_geometry().apply(base, ctx)


def export_one(job: ExportJob, settings: ExportSettings, *,
               index: int = 1,
               is_cancelled=None) -> ExportResult:  # noqa: ANN001
    """Tek fotografi render edip yazar. **Hicbir kosulda yukselmez.**

    Hatalar `ExportResult.error` icinde Turkce olarak doner; kuyruk
    calismaya devam eder.
    """
    started = time.perf_counter()

    def cancelled() -> bool:
        return bool(is_cancelled and is_cancelled())

    try:
        pixels, metadata = _source_for(job)
    except Exception as exc:  # noqa: BLE001 - bozuk dosya kuyrugu durdurmasin
        log.warning("Dışa aktarma için okunamadı: %s (%s)", job.source, exc)
        return ExportResult(job=job, error=_read_error(job.source, exc))

    if cancelled():
        return ExportResult(job=job, error="İptal edildi")

    try:
        rendered = render_for_export(pixels, job.recipe, settings)
    except Exception as exc:  # noqa: BLE001
        log.exception("Disa aktarma render'i basarisiz: %s", job.source)
        return ExportResult(job=job,
                            error=f"İşlenemedi: {type(exc).__name__}")

    if cancelled():
        return ExportResult(job=job, error="İptal edildi")

    height, width = rendered.shape[:2]
    stem = build_name(settings.name_template, source=job.source, index=index,
                      width=width, height=height, preset=job.preset_name)
    target = settings.folder / f"{stem}{settings.fmt.extension}"

    if target.exists() and settings.conflict is ConflictPolicy.SKIP:
        return ExportResult(job=job, path=target, width=width, height=height,
                            skipped=True,
                            elapsed_ms=(time.perf_counter() - started) * 1000)

    if _same_file(target, job.source):
        return ExportResult(
            job=job,
            error="Çıktı kaynak dosyanın üzerine yazacaktı; ad şablonunu "
                  "veya klasörü değiştirin.")

    options = SaveOptions(
        fmt=settings.fmt,
        quality=settings.quality,
        bit_depth=settings.effective_bit_depth(),
        icc_profile=_output_profile(metadata, settings.embed_icc),
        exif_bytes=_exif_for(metadata, settings.metadata),
        strip_metadata=settings.metadata is MetadataPolicy.STRIP_ALL,
        png_compress_level=settings.png_compress_level,
        webp_lossless=settings.webp_lossless,
        overwrite=settings.conflict is ConflictPolicy.OVERWRITE,
    )

    if cancelled():
        return ExportResult(job=job, error="İptal edildi")

    try:
        saved = save_image(rendered, target, options)
    except ImageSaveError as exc:
        return ExportResult(job=job, error=str(exc))
    except OSError as exc:
        return ExportResult(job=job, error=_write_error(target, exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("Beklenmeyen yazma hatasi: %s", target)
        return ExportResult(job=job,
                            error=f"Yazılamadı: {type(exc).__name__}")

    return ExportResult(
        job=job, path=saved.path, width=width, height=height,
        bit_depth=saved.bit_depth, bytes_written=saved.bytes_written,
        renamed=saved.renamed_from_conflict,
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )


def _source_for(job: ExportJob) -> tuple[np.ndarray, ImageMetadata]:
    """Isin piksellerini ve ust verisini verir; gerekirse diskten okur."""
    if job.pixels is not None and job.metadata is not None:
        return job.pixels, job.metadata
    loaded = load_image(job.source)
    return loaded.pixels, loaded.metadata



def _output_profile(metadata: "ImageMetadata",
                    embed: bool) -> bytes | None:
    """Cikti dosyasina gomulecek renk profili.

    Kaynak genis gamutlu bir profil tasiyorsa yukleyici pikselleri
    sRGB'ye cevirir. O durumda kaynagin profilini geri gommek dosyayi
    **iki kez** yanlis yapardi: sRGB pikseller Adobe RGB etiketiyle
    gosterilirdi. Donusum yapildiysa sRGB etiketi yazilir.

    Profil okunamadiysa (veya hic yoksa) pikseller zaten sRGB
    varsayilmistir; o zaman da sRGB etiketi dogru olandir.
    """
    if not embed:
        return None
    if metadata.icc_profile is not None and not metadata.icc_applied:
        # Donusum yapilamadi: pikseller kaynak profilinde kaldi
        return metadata.icc_profile
    return _srgb_profile()


_SRGB_CACHE: bytes | None = None


def _srgb_profile() -> bytes | None:
    """Gomulecek sRGB profili (bir kez uretilir)."""
    global _SRGB_CACHE
    if _SRGB_CACHE is None:
        try:
            from PIL import ImageCms
            _SRGB_CACHE = ImageCms.ImageCmsProfile(
                ImageCms.createProfile("sRGB")).tobytes()
        except Exception:  # noqa: BLE001 - profil yoksa etiketsiz yazilir
            log.warning("sRGB profili uretilemedi; cikti etiketsiz kalacak")
            _SRGB_CACHE = b""
    return _SRGB_CACHE or None


def _exif_for(metadata: ImageMetadata,
              policy: MetadataPolicy) -> bytes | None:
    """Politikaya gore yazilacak EXIF blogunu secer."""
    if policy is MetadataPolicy.STRIP_ALL:
        return None
    raw = getattr(metadata, "exif_bytes", None)
    if not raw:
        return None
    if policy is MetadataPolicy.KEEP:
        return raw
    return strip_gps(raw)


def strip_gps(exif_bytes: bytes) -> bytes | None:
    """EXIF blogundan GPS IFD'sini cikarir.

    Piexif ile yeniden kodlanir. Cozulemezse **tum EXIF dusurulur**:
    konumu sizdirmaktansa cekim bilgisini kaybetmek daha guvenlidir.
    """
    try:
        import piexif

        data = piexif.load(exif_bytes)
        data["GPS"] = {}
        for key in ("thumbnail",):
            data.pop(key, None)
        return piexif.dump(data)
    except Exception:  # noqa: BLE001
        log.warning("GPS temizlenemedi; tüm EXIF düşürüldü")
        return None


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and a.samefile(b)
    except OSError:
        return a.resolve() == b.resolve()


def _read_error(path: Path, exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"Dosya bulunamadı: {path.name}"
    if isinstance(exc, PermissionError):
        return f"Dosya okunamadı (izin yok): {path.name}"
    return f"Dosya açılamadı veya bozuk: {path.name}"


def _write_error(path: Path, exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return (f"'{path.parent.name}' klasörüne yazma izni yok. "
                f"Farklı bir klasör seçin.")
    if getattr(exc, "errno", None) == 28:
        return "Diskte yeterli boş alan yok."
    return f"Yazılamadı: {exc.strerror or exc}"


# ============================================================== KUYRUK
class ExportQueue(QObject):
    """Toplu disa aktarma kuyrugu.

    Isler tek bir calisan is parcaciginda **sirayla** islenir. Paralel
    calistirmak buyuk fotograflarda bellek kullanimini katlar ve diske
    yazma zaten sirali oldugu icin kayda deger hiz kazandirmaz.
    """

    started = Signal(int)                 # toplam is sayisi
    itemStarted = Signal(int, str)        # sira, dosya adi
    itemFinished = Signal(object)         # ExportResult
    progress = Signal(int, int)           # biten, toplam
    finished = Signal(object)             # ExportSummary
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._cancel = False
        self._running = False
        self._results: list[ExportResult] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, jobs: list[ExportJob], settings: ExportSettings) -> bool:
        """Kuyrugu baslatir. Zaten calisiyorsa False doner."""
        if self._running or not jobs:
            return False
        self._cancel = False
        self._running = True
        self._results = []
        self.started.emit(len(jobs))
        self._pool.start(_QueueTask(self, list(jobs), settings))
        return True

    def cancel(self) -> None:
        """Kuyrugu iptal eder; isleyen dosya tamamlandiktan sonra durur."""
        if self._running:
            self._cancel = True

    def is_cancelled(self) -> bool:
        return self._cancel

    def wait(self, timeout_ms: int = 60_000) -> bool:
        """Kuyruk bitene kadar bekler (testler ve kapanis icin)."""
        return self._pool.waitForDone(timeout_ms)

    # --------------------------------------------------- calisan geri cagri
    def _report_started(self, index: int, name: str) -> None:
        self.itemStarted.emit(index, name)

    def _report_done(self, result: ExportResult, done: int,
                     total: int) -> None:
        self._results.append(result)
        self.itemFinished.emit(result)
        self.progress.emit(done, total)

    def _report_finished(self, summary: ExportSummary) -> None:
        self._running = False
        if self._cancel:
            self.cancelled.emit()
        self.finished.emit(summary)


@dataclass(frozen=True)
class ExportSummary:
    """Kuyrugun sonucu."""

    results: tuple[ExportResult, ...] = ()
    cancelled: bool = False
    elapsed_ms: float = 0.0

    @property
    def succeeded(self) -> tuple[ExportResult, ...]:
        return tuple(r for r in self.results if r.ok and not r.skipped)

    @property
    def failed(self) -> tuple[ExportResult, ...]:
        return tuple(r for r in self.results if r.error)

    @property
    def skipped(self) -> tuple[ExportResult, ...]:
        return tuple(r for r in self.results if r.skipped)

    @property
    def total_bytes(self) -> int:
        return sum(r.bytes_written for r in self.succeeded)

    def message(self) -> str:
        """Durum cubugu icin tek satirlik ozet."""
        parts = [f"{len(self.succeeded)} fotoğraf yazıldı"]
        if self.skipped:
            parts.append(f"{len(self.skipped)} atlandı")
        if self.failed:
            parts.append(f"{len(self.failed)} başarısız")
        if self.cancelled:
            parts.append("iptal edildi")
        size_mb = self.total_bytes / (1024 * 1024)
        if size_mb >= 0.05:
            parts.append(f"{size_mb:.1f} MB")
        parts.append(f"{self.elapsed_ms / 1000:.1f} s")
        return "  ·  ".join(parts)

    def retry_jobs(self) -> list[ExportJob]:
        """Yeniden denenebilecek isler (yalnizca basarisizlar)."""
        return [r.job for r in self.failed]


class _QueueTask(QRunnable):
    """Kuyrugu arka planda sirayla isler."""

    def __init__(self, queue: ExportQueue, jobs: list[ExportJob],
                 settings: ExportSettings) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._queue = queue
        self._jobs = jobs
        self._settings = settings

    def run(self) -> None:
        started = time.perf_counter()
        total = len(self._jobs)
        results: list[ExportResult] = []
        try:
            self._settings.folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            message = _write_error(self._settings.folder / "x", exc)
            for job in self._jobs:
                results.append(ExportResult(job=job, error=message))
                self._queue._report_done(results[-1], len(results), total)
            self._queue._report_finished(ExportSummary(
                results=tuple(results), cancelled=False,
                elapsed_ms=(time.perf_counter() - started) * 1000))
            return

        for i, job in enumerate(self._jobs, start=1):
            if self._queue.is_cancelled():
                break
            self._queue._report_started(i, job.source.name)
            result = export_one(job, self._settings, index=i,
                                is_cancelled=self._queue.is_cancelled)
            results.append(result)
            self._queue._report_done(result, i, total)

        self._queue._report_finished(ExportSummary(
            results=tuple(results),
            cancelled=self._queue.is_cancelled(),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        ))


# ======================================================== TAHMIN YARDIMI
def estimate_bytes(width: int, height: int,
                   settings: ExportSettings) -> int:
    """Kaba dosya boyutu tahmini (kullaniciya bilgi icin).

    Gercek boyut icerige gore degisir; bu yalniz buyukluk mertebesi
    verir ve oyle sunulur.
    """
    pixels = max(1, width * height)
    depth = settings.effective_bit_depth()
    if settings.fmt is OutputFormat.JPEG:
        bits_per_pixel = 0.9 + 0.22 * (settings.quality / 100.0) ** 2 * 24
    elif settings.fmt is OutputFormat.WEBP:
        if settings.webp_lossless:
            bits_per_pixel = 11.0
        else:
            bits_per_pixel = 0.6 + 0.16 * (settings.quality / 100.0) ** 2 * 24
    elif settings.fmt is OutputFormat.PNG:
        bits_per_pixel = 13.0
    else:
        bits_per_pixel = depth * 3.0 * 0.85
    return int(pixels * bits_per_pixel / 8)


def format_bytes(count: int) -> str:
    """Insan okur boyut metni."""
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.0f} KB"
    if count < 1024 * 1024 * 1024:
        return f"{count / (1024 * 1024):.1f} MB"
    return f"{count / (1024 * 1024 * 1024):.2f} GB"

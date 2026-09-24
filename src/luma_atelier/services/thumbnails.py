"""Kucuk resim uretimi - arka planda, onbellekli, iptal edilebilir.

Kurallar
--------
* Goruntu isi hicbir zaman UI iş parçacığında yapilmaz.
* Yalnizca *gorunur* olan kucuk resimler oncelikli uretilir; ekran
  disindaki istekler kuyruga alinir ve gerekirse iptal edilir.
* Uretilen kucuk resimler diske onbelleklenir; ayni fotograf ikinci
  acilista yeniden islenmez.
* Onbellek boyutu sinirlidir; en eski kayitlar temizlenir.
"""
from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QImage, QPixmap

from luma_atelier.core.paths import cache_dir
from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.loader import ImageLoadError, load_image

log = logging.getLogger(__name__)

#: Kucuk resmin uzun kenari (piksel). Ekran olceklemesinde bulanik
#: gorunmemesi icin gosterim boyutunun iki katina yakin tutulur.
THUMB_LONG_EDGE = 320
#: Disk onbellegi ust siniri
CACHE_LIMIT_BYTES = 512 * 1024 * 1024
#: **Bellekteki** kucuk resimlerin ust siniri.
#:
#: Onceden sinir yoktu: 4000 fotograflik bir klasorde gezinmek sureci
#: olculen 1094 MB buyutuyordu ve bu bellek hic geri verilmiyordu.
#: 96 MB, 320 px'lik yaklasik 350 kucuk resme denk gelir; film seridi
#: ve izgara gorunumu icin fazlasiyla yeterli.
MEMORY_CACHE_BYTES = 96 * 1024 * 1024


@dataclass(frozen=True)
class ThumbRequest:
    path: Path
    #: Dosya degistiginde onbellek gecersiz olsun diye
    mtime: float
    size: int


class _Signals(QObject):
    #: Worker QImage yayar; QPixmap donusumu GUI is parcaciginda
    #: yapilir (Qt: QPixmap yalnizca GUI is parcaciginda kullanilir).
    ready = Signal(str, QImage)   # yol, kucuk resim
    failed = Signal(str, str)      # yol, Turkce hata mesaji


class _ThumbTask(QRunnable):
    """Tek bir kucuk resmi uretir."""

    def __init__(self, request: ThumbRequest, signals: _Signals,
                 cache_path: Path) -> None:
        super().__init__()
        self._req = request
        self._signals = signals
        self._cache_path = cache_path
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D102
        if self._cancelled:
            return
        key = str(self._req.path)
        try:
            if self._cache_path.exists():
                cached = QImage(str(self._cache_path))
                if not cached.isNull():
                    if not self._cancelled:
                        self._signals.ready.emit(key, cached)
                    return

            loaded = load_image(self._req.path)
            if self._cancelled:
                return
            thumb = _downscale(loaded.pixels, THUMB_LONG_EDGE)
            qim = _to_qimage(thumb)
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                # Once gecici ada yaz, sonra tasi: yarim PNG onbellege girmesin
                tmp = self._cache_path.with_suffix(".part")
                if qim.save(str(tmp), "PNG"):
                    tmp.replace(self._cache_path)
            except OSError:
                log.debug("Kucuk resim onbellege yazilamadi: %s", key)
            if not self._cancelled:
                self._signals.ready.emit(key, qim)
        except ImageLoadError as exc:
            if not self._cancelled:
                self._signals.failed.emit(key, str(exc))
        except Exception as exc:  # noqa: BLE001 - tek dosya tarama durdurmasin
            log.exception("Kucuk resim uretilemedi: %s", key)
            if not self._cancelled:
                self._signals.failed.emit(key, f"Küçük resim üretilemedi: {exc}")


def _downscale(img: np.ndarray, long_edge: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(1.0, long_edge / max(h, w))
    if scale >= 1.0:
        return img
    size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


def _to_qimage(arr: np.ndarray) -> QImage:
    work = np.clip(px.ensure_working(arr), 0.0, 1.0)
    if work.shape[2] == 4:
        u8 = np.ascontiguousarray(px.to_uint8(work))
        fmt = QImage.Format.Format_RGBA8888
    else:
        u8 = np.ascontiguousarray(px.to_uint8(work[..., :3]))
        fmt = QImage.Format.Format_RGB888
    h, w = u8.shape[:2]
    return QImage(u8.data, w, h, u8.strides[0], fmt).copy()


class _PruneTask(QRunnable):
    """Disk onbellegi budamasini arka planda calistirir."""

    def __init__(self, service: "ThumbnailService") -> None:
        super().__init__()
        self._service = service
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        try:
            self._service.prune_cache()
        except Exception:  # noqa: BLE001 - budama uygulamayi cokertmesin
            log.exception("Onbellek budamasi basarisiz")


class ThumbnailService(QObject):
    """Kucuk resim uretimini yoneten servis.

    Sinyaller:
        thumbnailReady(yol, QPixmap)
        thumbnailFailed(yol, mesaj)
    """

    thumbnailReady = Signal(str, QPixmap)
    thumbnailFailed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        # UI'ya nefes birakmak icin cekirdek sayisinin altinda kal
        self._pool.setMaxThreadCount(max(2, (QThreadPool.globalInstance()
                                             .maxThreadCount() or 4) - 2))
        self._signals = _Signals()
        self._signals.ready.connect(self._on_ready, Qt.ConnectionType.QueuedConnection)
        self._signals.failed.connect(self._on_failed, Qt.ConnectionType.QueuedConnection)
        #: LRU: en son kullanilan sonda durur
        self._memory: OrderedDict[str, QPixmap] = OrderedDict()
        self._memory_bytes = 0
        self._memory_limit = MEMORY_CACHE_BYTES
        self._cache_limit = CACHE_LIMIT_BYTES
        self._pending: dict[str, _ThumbTask] = {}
        self._cache_root = cache_dir() / "thumbs"

    # ------------------------------------------------------------- erisim
    def cached(self, path: str | Path) -> QPixmap | None:
        """Bellekte hazir kucuk resim varsa dondurur (anlik cizim icin)."""
        return self._touch(str(path))

    def _touch(self, key: str) -> QPixmap | None:
        """Kaydi LRU sirasinda one alir."""
        hit = self._memory.get(key)
        if hit is not None:
            self._memory.move_to_end(key)
        return hit

    def request(self, path: str | Path) -> QPixmap | None:
        """Kucuk resim ister. Hazirsa hemen dondurur, degilse kuyruga alir."""
        p = Path(path)
        key = str(p)
        hit = self._touch(key)
        if hit is not None:
            return hit
        if key in self._pending:
            return None
        try:
            stat = p.stat()
        except OSError:
            self.thumbnailFailed.emit(key, "Dosya bulunamadı")
            return None

        req = ThumbRequest(path=p, mtime=stat.st_mtime, size=stat.st_size)
        task = _ThumbTask(req, self._signals, self._cache_file(req))
        self._pending[key] = task
        self._pool.start(task)
        return None

    def cancel(self, path: str | Path) -> None:
        """Ekran disina cikan istegi iptal eder."""
        task = self._pending.pop(str(path), None)
        if task is not None:
            task.cancel()

    def cancel_all(self) -> None:
        for task in self._pending.values():
            task.cancel()
        self._pending.clear()

    def shutdown(self) -> None:
        """Kapanista bekleyen isleri durdurur."""
        self.cancel_all()
        self._pool.waitForDone(3000)

    # ----------------------------------------------------------- dahili
    def _cache_file(self, req: ThumbRequest) -> Path:
        digest = hashlib.sha256(
            f"{req.path}|{req.mtime}|{req.size}|{THUMB_LONG_EDGE}".encode()
        ).hexdigest()
        # Tek klasorde on binlerce dosya olmasin
        return self._cache_root / digest[:2] / f"{digest}.png"

    def _on_ready(self, key: str, image: QImage) -> None:
        # GUI is parcacigi: QPixmap burada uretilebilir.
        pixmap = QPixmap.fromImage(image)
        self._pending.pop(key, None)
        self._remember(key, pixmap)
        self.thumbnailReady.emit(key, pixmap)

    @staticmethod
    def _pixmap_bytes(pixmap: QPixmap) -> int:
        depth = max(8, pixmap.depth()) // 8
        return max(1, pixmap.width() * pixmap.height() * depth)

    def _remember(self, key: str, pixmap: QPixmap) -> None:
        """Kucuk resmi bellege alir ve siniri asmiyorsa saklar."""
        old = self._memory.pop(key, None)
        if old is not None:
            self._memory_bytes -= self._pixmap_bytes(old)
        self._memory[key] = pixmap
        self._memory_bytes += self._pixmap_bytes(pixmap)
        while self._memory_bytes > self._memory_limit and len(self._memory) > 1:
            _evicted_key, evicted = self._memory.popitem(last=False)
            self._memory_bytes -= self._pixmap_bytes(evicted)

    def memory_bytes(self) -> int:
        """Bellekteki kucuk resimlerin toplam boyutu (olcum ve test icin)."""
        return self._memory_bytes

    def _on_failed(self, key: str, message: str) -> None:
        self._pending.pop(key, None)
        self.thumbnailFailed.emit(key, message)

    # -------------------------------------------------------- onbellek
    def cache_size_bytes(self) -> int:
        try:
            return sum(f.stat().st_size
                       for f in self._cache_root.rglob("*.png") if f.is_file())
        except OSError:
            return 0

    def prune_cache_async(self) -> None:
        """Disk onbellegini arka planda sinirin altina indirir.

        Budama dosya sistemini geziyor; acilis sirasinda GUI is
        parcaciginda yapilmasi uygulamayi bekletirdi.
        """
        self._pool.start(_PruneTask(self))

    def set_cache_limit(self, limit_bytes: int) -> None:
        """Disk onbellegi ust sinirini ayarlar (Ayarlar ekranindan).

        Cok kucuk bir sinir onbellegi ise yaramaz hale getirirdi;
        16 MB alt sinir uygulanir.
        """
        self._cache_limit = max(16 * 1024 * 1024, int(limit_bytes))

    def cache_limit(self) -> int:
        return self._cache_limit

    def clear_memory_cache(self) -> None:
        """Bellekteki kucuk resimleri birakir; disk onbellegi ayridir."""
        self._memory.clear()
        self._memory_bytes = 0

    def prune_cache(self, limit: int | None = None) -> int:
        """Onbellegi sinirin altina indirir; en eski dosyalar once silinir.

        `limit` verilmezse Ayarlar ekranindan gelen gecerli sinir
        kullanilir; sabit kullanmak ayari etkisiz birakirdi.
        """
        limit = self._cache_limit if limit is None else limit
        try:
            files = [(f, f.stat()) for f in self._cache_root.rglob("*.png")
                     if f.is_file()]
        except OSError:
            return 0
        total = sum(s.st_size for _, s in files)
        if total <= limit:
            return 0
        files.sort(key=lambda item: item[1].st_atime)
        freed = 0
        for f, s in files:
            if total - freed <= limit:
                break
            try:
                f.unlink()
                freed += s.st_size
            except OSError:
                continue
        log.info("Kucuk resim onbelleginden %.1f MB temizlendi", freed / 1e6)
        return freed

    def clear_cache(self) -> None:
        import shutil
        self._memory.clear()
        self._memory_bytes = 0
        shutil.rmtree(self._cache_root, ignore_errors=True)

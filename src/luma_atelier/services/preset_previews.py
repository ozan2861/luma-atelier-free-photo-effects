"""Preset kucuk resimleri - kullanicinin **kendi fotografi** uzerinde.

Gereksinim: "Kucuk resimleri kullanicinin sectigi fotograf uzerinde
olustur; sabit ornek fotograf gosterme."

Strateji
--------
* Kaynak bir kez kucuk bir tabana (`BASE_LONG_EDGE`) indirilir; her
  preset bu taban uzerinde calisir. 120 preseti tam boyda islemek
  dakikalar surerdi.
* Yalnizca **gorunur** kartlar oncelikli uretilir. Gorunur alandan
  cikan istekler iptal edilir.
* Sonuclar bellekte onbelleklenir; ayni fotograf + ayni preset ikinci
  kez hesaplanmaz.
* Fotograf degisince onbellek temizlenir.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.effects.base import RenderContext
from luma_atelier.imaging.recipe import Recipe

log = logging.getLogger(__name__)

#: Preset onizlemelerinin uretildigi taban cozunurluk (uzun kenar).
#: Kart 148 px genislikte gosteriliyor; 2x yeterli keskinlik verir ve
#: 120 preset icin toplam maliyeti makul tutar.
BASE_LONG_EDGE = 320

#: Bellekte tutulacak en fazla onizleme. 120 preset x ~300 KB = 36 MB.
CACHE_LIMIT = 260


class _Signals(QObject):
    #: Worker QImage yayar; QPixmap donusumu GUI is parcaciginda.
    ready = Signal(str, QImage)
    failed = Signal(str, str)


class _PreviewTask(QRunnable):
    def __init__(self, preset_id: str, base: np.ndarray, recipe: Recipe,
                 full_size: tuple[int, int], signals: _Signals,
                 is_current) -> None:  # noqa: ANN001
        super().__init__()
        self._preset_id = preset_id
        self._base = base
        self._recipe = recipe
        self._full_size = full_size
        self._signals = signals
        self._is_current = is_current
        self.setAutoDelete(True)

    def _emit(self, signal, *args) -> bool:  # noqa: ANN001, ANN002
        """Sinyali guvenle yayar.

        Pencere kapanirken calisan is parcaciklari hala sonuc uretiyor
        olabilir; o anda sinyal nesnesi Qt tarafinda yok edilmis olur ve
        `emit` `RuntimeError` verir. Bu bir hata degil, normal kapanis
        yarisidir: sonucu sessizce birakmak dogru davranistir.
        """
        try:
            signal.emit(*args)
            return True
        except RuntimeError:
            log.debug("Onizleme sonucu birakildi (pencere kapanmis): %s",
                      self._preset_id)
            return False

    def run(self) -> None:  # noqa: D102
        if not self._is_current(self._preset_id):
            return
        try:
            full_w, full_h = self._full_size
            scale = self._base.shape[1] / max(1.0, float(full_w))
            ctx = RenderContext(
                full_width=full_w, full_height=full_h, scale=scale,
                seed=self._recipe.seed, quality="final", purpose="thumbnail",
            )
            out = self._recipe.apply(self._base, ctx)
            if not self._is_current(self._preset_id):
                return
            self._emit(self._signals.ready, self._preset_id,
                       _to_qimage(out))
        except RuntimeError:
            # Kapanis sirasinda Qt nesneleri yok edilmis olabilir
            log.debug("Onizleme kapanista iptal edildi: %s", self._preset_id)
        except Exception as exc:  # noqa: BLE001 - tek preset digerlerini engellemez
            log.exception("Preset onizlemesi uretilemedi: %s", self._preset_id)
            self._emit(self._signals.failed, self._preset_id, str(exc))


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


class PresetPreviewService(QObject):
    """Preset kucuk resimlerini uretir ve onbellekler.

    Sinyaller:
        previewReady(preset_id, QPixmap)
        previewFailed(preset_id, mesaj)
    """

    previewReady = Signal(str, QPixmap)
    previewFailed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        available = QThreadPool.globalInstance().maxThreadCount() or 4
        self._pool.setMaxThreadCount(max(2, min(6, available - 2)))
        self._signals = _Signals()
        self._signals.ready.connect(self._on_ready, Qt.ConnectionType.QueuedConnection)
        self._signals.failed.connect(self._on_failed,
                                     Qt.ConnectionType.QueuedConnection)

        self._base: np.ndarray | None = None
        self._full_size: tuple[int, int] = (0, 0)
        self._source_key: str = ""
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._pending: set[str] = set()
        self._generation = 0
        self._base_pixmap: QPixmap | None = None

    # -------------------------------------------------------------- kaynak
    def setSource(self, image: np.ndarray | None, key: str) -> None:  # noqa: N802
        """Onizlemelerin uretilecegi fotografi ayarlar.

        `key` fotografi tanimlar (genelde dosya yolu). Ayni fotograf
        yeniden verilirse onbellek korunur.
        """
        if key == self._source_key and image is not None:
            return
        self._generation += 1
        self._pending.clear()
        self._cache.clear()
        self._source_key = key

        if image is None:
            self._base = None
            self._base_pixmap = None
            self._full_size = (0, 0)
            return

        h, w = image.shape[:2]
        self._full_size = (w, h)
        scale = min(1.0, BASE_LONG_EDGE / max(h, w))
        if scale < 1.0:
            size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
            self._base = np.ascontiguousarray(
                cv2.resize(image, size, interpolation=cv2.INTER_AREA)
            )
        else:
            self._base = np.ascontiguousarray(image)
        # GUI is parcacigi (setSource oradan cagrilir): QPixmap guvenli
        self._base_pixmap = QPixmap.fromImage(_to_qimage(self._base))

    @property
    def has_source(self) -> bool:
        return self._base is not None

    def original_pixmap(self) -> QPixmap | None:
        """Islenmemis taban - "Orijinal" karti icin."""
        return self._base_pixmap

    # ------------------------------------------------------------- istekler
    def cached(self, preset_id: str) -> QPixmap | None:
        pixmap = self._cache.get(preset_id)
        if pixmap is not None:
            self._cache.move_to_end(preset_id)
        return pixmap

    def request(self, preset_id: str, recipe: Recipe) -> QPixmap | None:
        """Onizleme ister. Hazirsa hemen dondurur."""
        if self._base is None:
            return None
        hit = self.cached(preset_id)
        if hit is not None:
            return hit
        if preset_id in self._pending:
            return None
        self._pending.add(preset_id)
        generation = self._generation
        self._pool.start(_PreviewTask(
            preset_id, self._base, recipe, self._full_size, self._signals,
            lambda pid, g=generation: (g == self._generation
                                       and pid in self._pending),
        ))
        return None

    def cancel(self, preset_id: str) -> None:
        """Gorunur alandan cikan istegi iptal eder."""
        self._pending.discard(preset_id)

    def cancel_all(self) -> None:
        self._pending.clear()

    def shutdown(self) -> None:
        self.cancel_all()
        self._generation += 1
        self._pool.waitForDone(3000)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def cached_count(self) -> int:
        return len(self._cache)

    # --------------------------------------------------------------- dahili
    def _on_ready(self, preset_id: str, image: QImage) -> None:
        # GUI is parcacigi: QPixmap burada uretilebilir.
        pixmap = QPixmap.fromImage(image)
        self._pending.discard(preset_id)
        self._cache[preset_id] = pixmap
        self._cache.move_to_end(preset_id)
        while len(self._cache) > CACHE_LIMIT:
            self._cache.popitem(last=False)
        self.previewReady.emit(preset_id, pixmap)

    def _on_failed(self, preset_id: str, message: str) -> None:
        self._pending.discard(preset_id)
        self.previewFailed.emit(preset_id, message)

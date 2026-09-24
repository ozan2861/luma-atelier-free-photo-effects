"""Render servisi: arka planda onizleme ve tam boy uretimi.

Kurallar
--------
* Goruntu hesabi hicbir zaman UI is parcaciginda yapilmaz.
* Hizli kaydirici hareketinde eski gorevler **iptal** edilir; ekranda
  son istek kalir. Bunu bir "istek jetonu" (token) ile yaparız: sonuc
  geldiginde jeton guncel degilse sonuc atilir.
* Onizleme iki kademelidir: surukleme sirasinda dusuk cozunurluk ve
  "interactive" kalite, fare birakilinca tam onizleme cozunurlugu.
* Onizleme, %100 gorunum ve tam boy render **ayni** motoru ve ayni
  tarifi kullanir; tek fark `RenderContext.scale`.

Neden thread, process degil
---------------------------
Agir is NumPy ve OpenCV icinde gecer; her ikisi de hesap sirasinda GIL'i
birakir. Olculen deger: 9 MP pozlama zinciri sirasinda UI olay dongusu
bloke olmuyor. Process havuzu her istekte 100+ MB dizi kopyalamayi
gerektirirdi ve pratikte daha yavas olurdu.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.effects.base import RenderContext
from luma_atelier.imaging.recipe import Recipe

log = logging.getLogger(__name__)

#: Onizleme uzun kenari. Gereksinim: 1600-2048 arasi.
PREVIEW_LONG_EDGE = 1800
#: Surukleme sirasindaki dusuk kalite uzun kenari.
INTERACTIVE_LONG_EDGE = 1100
#: Karo, kenar paylariyla birlikte en fazla bu kadar piksel islenir.
#: Anamorfik cizgi 1200 px'e kadar erisebilir; pay sinirsiz buyuse
#: %100 gorunum her kaydirmada saniyelerce donardi. 12 MP, olculen
#: sureyi bu makinede ~1 saniyenin altinda tutuyor.
MAX_TILE_AREA = 12_000_000


@dataclass(frozen=True)
class RenderRequest:
    """Tek bir render istegi."""

    token: int
    source: np.ndarray
    recipe: Recipe
    long_edge: int
    quality: str          # "interactive" | "final"
    purpose: str          # "preview" | "export" | "thumbnail"
    full_width: int
    full_height: int


@dataclass(frozen=True)
class RenderResult:
    token: int
    image: np.ndarray
    scale: float
    elapsed_ms: float
    quality: str
    purpose: str
    failed_layers: tuple[str, ...] = ()
    """Render sirasinda atlanan katmanlar.

    Bos degilse kullaniciya bildirilmelidir: aksi halde bir efekt
    sessizce calismaz ve kullanici nedenini goremez.
    """


class _Signals(QObject):
    done = Signal(object)     # RenderResult
    failed = Signal(int, str)


class _TileSignals(QObject):
    #: jeton, bolge (x, y, w, h), pikseller, sure (ms)
    done = Signal(int, object, object, float)
    failed = Signal(int, str)


class _TileTask(QRunnable):
    """Karoyu arka planda uretir.

    Karo GUI is parcaciginda uretildiginde, genis yaricapli bir tarifte
    (bloom + halation) olculen 1.3 saniye dogrudan arayuzun donma
    suresiydi. Sonuc jetonla dogrulanir: kullanici kaydirmaya devam
    ettiyse eski karo ekrana basilmaz.
    """

    def __init__(self, token: int, service: RenderService,
                 source: np.ndarray, recipe: Recipe,
                 rect: tuple[int, int, int, int],
                 signals: _TileSignals, is_current) -> None:  # noqa: ANN001
        super().__init__()
        self._token = token
        self._service = service
        self._source = source
        self._recipe = recipe
        self._rect = rect
        self._signals = signals
        self._is_current = is_current
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        if not self._is_current(self._token):
            return
        t0 = time.perf_counter()
        try:
            tile = self._service.render_tile(self._source, self._recipe,
                                             self._rect)
            if not self._is_current(self._token):
                return
            self._signals.done.emit(self._token, self._rect, tile,
                                    (time.perf_counter() - t0) * 1000.0)
        except RuntimeError:
            # Kapanis sirasinda Qt nesneleri yok edilmis olabilir
            log.debug("Karo kapanista birakildi (token=%s)", self._token)
        except Exception as exc:  # noqa: BLE001 - karo yoksa onizleme kalir
            log.exception("Karo uretilemedi (token=%s)", self._token)
            if self._is_current(self._token):
                self._signals.failed.emit(self._token, str(exc))


class _RenderTask(QRunnable):
    def __init__(self, request: RenderRequest, signals: _Signals,
                 is_current) -> None:  # noqa: ANN001
        super().__init__()
        self._req = request
        self._signals = signals
        self._is_current = is_current
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        req = self._req
        # Kuyrukta beklerken gecersiz kaldiysa hic baslama
        if not self._is_current(req.token):
            return
        t0 = time.perf_counter()
        try:
            working, scale = _prepare_source(req.source, req.long_edge)
            if not self._is_current(req.token):
                return
            ctx = RenderContext(
                full_width=req.full_width, full_height=req.full_height,
                scale=scale, seed=req.recipe.seed,
                quality=req.quality, purpose=req.purpose,
            )
            failures: list[str] = []
            out = req.recipe.apply(working, ctx, failures=failures)
            if not self._is_current(req.token):
                return
            self._signals.done.emit(RenderResult(
                token=req.token, image=out, scale=scale,
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                quality=req.quality, purpose=req.purpose,
                failed_layers=tuple(dict.fromkeys(failures)),
            ))
        except Exception as exc:  # noqa: BLE001
            log.exception("Render basarisiz (token=%s)", req.token)
            if self._is_current(req.token):
                self._signals.failed.emit(req.token, f"Render başarısız: {exc}")


def _prepare_source(source: np.ndarray, long_edge: int) -> tuple[np.ndarray, float]:
    """Kaynagi hedef cozunurluge indirir ve olcek faktorunu dondurur."""
    h, w = source.shape[:2]
    longest = max(h, w)
    if long_edge <= 0 or longest <= long_edge:
        return source, 1.0
    scale = long_edge / float(longest)
    size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    small = cv2.resize(source, size, interpolation=cv2.INTER_AREA)
    return px.ensure_working(small), scale


class RenderService(QObject):
    """Onizleme ve export render'larini yoneten servis.

    Sinyaller:
        previewReady(RenderResult)
        renderFailed(token, mesaj)
    """

    previewReady = Signal(object)
    renderFailed = Signal(int, str)
    #: jeton, bolge, pikseller, sure (ms)
    tileReady = Signal(int, object, object, float)
    tileFailed = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._preview_long_edge = PREVIEW_LONG_EDGE
        self._pool = QThreadPool(self)
        # UI'ya nefes birak: tum cekirdekleri doldurma
        available = QThreadPool.globalInstance().maxThreadCount() or 4
        self._pool.setMaxThreadCount(max(2, min(6, available - 2)))
        self._signals = _Signals()
        self._signals.done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)
        self._signals.failed.connect(self._on_failed,
                                     Qt.ConnectionType.QueuedConnection)
        self._token = 0
        self._current_token = 0
        self._last_ms = 0.0

        # Karo istekleri ayri jeton sayaci kullanir: onizleme istegi
        # karoyu, karo istegi onizlemeyi iptal etmemeli.
        self._tile_signals = _TileSignals()
        self._tile_signals.done.connect(self._on_tile_done,
                                        Qt.ConnectionType.QueuedConnection)
        self._tile_signals.failed.connect(self._on_tile_failed,
                                          Qt.ConnectionType.QueuedConnection)
        self._tile_token = 0
        self._current_tile_token = 0

    @property
    def last_elapsed_ms(self) -> float:
        return self._last_ms

    @property
    def thread_count(self) -> int:
        return self._pool.maxThreadCount()

    def set_preview_long_edge(self, long_edge: int) -> None:
        """Onizleme uzun kenarini degistirir (Ayarlar ekranindan).

        Bekleyen istekler gecersiz kilinir; eski boyutta uretilmis
        bir sonuc yeni ayarla celisirdi.
        """
        value = int(max(640, min(6000, long_edge)))
        if value == self._preview_long_edge:
            return
        self._preview_long_edge = value
        self.cancel_pending()

    def preview_long_edge(self) -> int:
        return self._preview_long_edge

    def request_preview(
        self, source: np.ndarray, recipe: Recipe, *, interactive: bool = False,
        long_edge: int | None = None,
    ) -> int:
        """Onizleme ister. Onceki bekleyen istekler gecersiz olur.

        Returns:
            Istek jetonu. Sonuc bu jetonla gelir.
        """
        self._token += 1
        self._current_token = self._token
        h, w = source.shape[:2]
        edge = long_edge if long_edge is not None else (
            INTERACTIVE_LONG_EDGE if interactive else self._preview_long_edge
        )
        req = RenderRequest(
            token=self._token, source=source, recipe=recipe,
            long_edge=edge,
            quality="interactive" if interactive else "final",
            purpose="preview", full_width=w, full_height=h,
        )
        self._pool.start(_RenderTask(req, self._signals, self._is_current))
        return self._token

    def request_tile(self, source: np.ndarray, recipe: Recipe,
                     rect: tuple[int, int, int, int]) -> int:
        """Karoyu arka planda ister; sonuc `tileReady` ile gelir.

        Onceki bekleyen karo istegi gecersiz olur. Donen jeton, gelen
        sonucun hala istenen karo olup olmadigini dogrulamak icindir.
        """
        self._tile_token += 1
        self._current_tile_token = self._tile_token
        self._pool.start(_TileTask(
            self._tile_token, self, source, recipe, rect,
            self._tile_signals, self._is_current_tile,
        ))
        return self._tile_token

    def cancel_tile(self) -> None:
        """Bekleyen karo isteklerini gecersiz kilar."""
        self._current_tile_token = 0

    def _is_current_tile(self, token: int) -> bool:
        return token == self._current_tile_token

    def _on_tile_done(self, token: int, rect: object, image: object,
                      ms: float) -> None:
        if token != self._current_tile_token:
            return
        self.tileReady.emit(token, rect, image, ms)

    def _on_tile_failed(self, token: int, message: str) -> None:
        if token != self._current_tile_token:
            return
        self.tileFailed.emit(token, message)

    def render_tile(self, source: np.ndarray, recipe: Recipe,
                    rect: tuple[int, int, int, int], *,
                    margin: int = 96) -> np.ndarray:
        """Kaynagin bir bolgesini **tam cozunurlukte** render eder.

        %100 ve uzeri yakinlastirmada gercek pikselleri gostermek icin.
        Onizlemeyi buyutmek bulanik sonuc verirdi.

        `margin`: **taban** kenar payi. Blur/clarity gibi komsu piksel
        okuyan islemler karo sinirinda farkli sonuc uretmesin diye bolge
        genisletilerek islenir, sonra paylar kirpilir. Gercekte gereken
        pay tarife baglidir (bloom 400 px yaricapa, anamorfik 1200 px
        uzunluga kadar cikar); tarif bunu `tile_reach` ile bildirir ve
        pay ona gore buyutulur. Genisletilmis bolge `MAX_TILE_AREA`
        pikseli asarsa pay kirpilir: bu durumda karo sinirinda kucuk bir
        sapma kalir, ama uygulama saniyelerce kilitlenmez. Global
        istatistik gerektiren islemler bu yaklasimla tam dogru olmaz;
        suan boyle bir islem yok, eklenirse ayrica ele alinmali.
        """
        h, w = source.shape[:2]
        x, y, rw, rh = rect
        margin = self._tile_margin(recipe, (w, h), margin, int(rw), int(rh))
        x0 = max(0, int(x) - margin)
        y0 = max(0, int(y) - margin)
        x1 = min(w, int(x + rw) + margin)
        y1 = min(h, int(y + rh) + margin)
        if x1 <= x0 or y1 <= y0:
            return source[0:1, 0:1]

        crop = np.ascontiguousarray(source[y0:y1, x0:x1])
        # Karonun kadrajdaki konumu efektlere bildirilir: vignette,
        # tilt-shift, isik sizintisi, grain ve maskeler karoyu tum
        # fotograf sanmamali. Aksi halde %100 gorunum, tam boy
        # ciktidan farkli bir goruntu gosterir.
        ctx = RenderContext(
            full_width=w, full_height=h, scale=1.0, seed=recipe.seed,
            quality="final", purpose="detail",
            tile_origin=(x0, y0), tile_frame=(w, h),
        )
        rendered = recipe.apply(crop, ctx)

        # Kenar paylarini geri kes
        left = int(x) - x0
        top = int(y) - y0
        return np.ascontiguousarray(
            rendered[top:top + int(rh), left:left + int(rw)]
        )

    @staticmethod
    def _tile_margin(recipe: Recipe, frame: tuple[int, int], base: int,
                     rw: int, rh: int) -> int:
        """Tarifin gerektirdigi kenar payi, butceyle sinirli."""
        needed = int(np.ceil(recipe.tile_reach(frame)))
        margin = max(int(base), needed)
        if margin <= base:
            return margin
        # Butce: genisletilmis bolge bu kadar pikseli asmasin
        limit = margin
        while limit > base and (rw + 2 * limit) * (rh + 2 * limit) > MAX_TILE_AREA:
            limit -= 16
        limit = max(int(base), limit)
        if limit < margin:
            log.debug("Karo payi butceye kirpildi: %d -> %d", margin, limit)
        return limit

    def render_now(self, source: np.ndarray, recipe: Recipe, *,
                   long_edge: int = 0, purpose: str = "export") -> np.ndarray:
        """Bu is parcaciginda, tam kalitede render eder (export icin).

        Onizlemeyle **ayni** kodu calistirir; tek fark olcek.
        """
        working, scale = _prepare_source(source, long_edge)
        h, w = source.shape[:2]
        ctx = RenderContext(
            full_width=w, full_height=h, scale=scale,
            seed=recipe.seed, quality="final", purpose=purpose,
        )
        return recipe.apply(working, ctx)

    def cancel_pending(self) -> None:
        """Bekleyen tum istekleri gecersiz kilar."""
        self._current_token = self._token + 1
        self._token = self._current_token
        self.cancel_tile()
        self._pool.clear()

    def shutdown(self) -> None:
        self.cancel_pending()
        self._pool.waitForDone(3000)

    # ------------------------------------------------------------- dahili
    def _is_current(self, token: int) -> bool:
        return token == self._current_token

    def _on_done(self, result: object) -> None:
        if not isinstance(result, RenderResult):
            raise TypeError("result must be a RenderResult")
        if result.token != self._current_token:
            return  # kullanici bu arada baska bir sey yapti
        self._last_ms = result.elapsed_ms
        self.previewReady.emit(result)

    def _on_failed(self, token: int, message: str) -> None:
        if token == self._current_token:
            self.renderFailed.emit(token, message)

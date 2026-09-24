"""%100 gorunumun gercek kaynak ayrintisini gosterdigini kanitlar.

Karo boyutunu olcmek yetmez: tuvalin *cizdigi piksellerin* gercekten
kaynaktaki ince ayrintiyi tasidigi gosterilmeli. Bunun icin yuksek
frekansli (ince desenli) bir test goruntusu kullanilir. Onizleme bu
deseni kaybeder; tam cozunurluklu karo korur. Aradaki fark gradyan
enerjisiyle olculur.
"""
from __future__ import annotations

import time

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from luma_atelier.imaging.recipe import Recipe
from luma_atelier.services.render import RenderService
from luma_atelier.ui.widgets.image_canvas import CompareMode, ImageCanvas

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def fine_detail_source() -> np.ndarray:
    """Tek piksel genisliginde cizgiler iceren 2400x1600 goruntu.

    Bu desen yarim cozunurlukte *tamamen* kaybolur (Nyquist siniri);
    dolayisiyla karonun gercekten kaynaktan geldigini ayirt etmek icin
    kesin bir olcuttur.
    """
    h, w = 1600, 2400
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), np.float32)
    # Dikey tek piksel cizgiler
    img[..., 0] = ((xx % 2) == 0).astype(np.float32) * 0.9 + 0.05
    # Yatay tek piksel cizgiler
    img[..., 1] = ((yy % 2) == 0).astype(np.float32) * 0.9 + 0.05
    # Dama deseni
    img[..., 2] = (((xx + yy) % 2) == 0).astype(np.float32) * 0.9 + 0.05
    return np.ascontiguousarray(img)


def gradient_energy(arr: np.ndarray) -> float:
    """Komsu piksel farklarinin ortalamasi - ince ayrinti olcusu."""
    a = arr.astype(np.float32)
    if a.ndim == 3:
        a = a.mean(axis=2)
    dx = np.abs(np.diff(a, axis=1)).mean()
    dy = np.abs(np.diff(a, axis=0)).mean()
    return float(dx + dy)


def grab_canvas(canvas: ImageCanvas, app: QApplication) -> np.ndarray:
    """Tuvalin cizdigi pikselleri NumPy dizisi olarak alir."""
    app.processEvents()
    pixmap = canvas.grab()
    qimg = pixmap.toImage().convertToFormat(
        pixmap.toImage().Format.Format_RGB888
    )
    w, h = qimg.width(), qimg.height()
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=h * qimg.bytesPerLine())
    arr = arr.reshape(h, qimg.bytesPerLine())[:, : w * 3].reshape(h, w, 3)
    return arr.astype(np.float32) / 255.0


@pytest.fixture
def canvas_at_full(qapp: QApplication,
                   fine_detail_source: np.ndarray) -> ImageCanvas:
    """Onizleme gosteren, kaynagi 2400 px olan tuval."""
    import cv2

    canvas = ImageCanvas()
    canvas.resize(900, 600)
    canvas.show()
    qapp.processEvents()

    h, w = fine_detail_source.shape[:2]
    scale = 1800 / w
    preview = cv2.resize(fine_detail_source, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    canvas.setImage(preview, preview, source_size=(w, h))
    qapp.processEvents()
    return canvas


class TestHundredPercentView:
    def test_actual_pixels_reports_exactly_one_to_one(
        self, canvas_at_full: ImageCanvas
    ) -> None:
        canvas_at_full.zoomToActualPixels()
        assert canvas_at_full.effectiveZoom() == pytest.approx(1.0, abs=1e-6)

    def test_detail_tile_is_required_at_exactly_one_hundred(
        self, canvas_at_full: ImageCanvas
    ) -> None:
        """Tam %100'de karo *gerekli* olarak isaretlenmeli.

        Esik yanlis ayarlanmis olsaydi (orn. 1.02 yerine efektif zoom'a
        bakmak) tam %100 karonun disinda kalabilirdi.
        """
        canvas_at_full.zoomToActualPixels()
        assert canvas_at_full.needsDetailTile()

    def test_fit_view_does_not_need_a_tile(
        self, canvas_at_full: ImageCanvas
    ) -> None:
        canvas_at_full.zoomToFit()
        assert not canvas_at_full.needsDetailTile()

    def test_rendered_pixels_carry_real_source_detail(
        self, canvas_at_full: ImageCanvas, qapp: QApplication,
        fine_detail_source: np.ndarray,
    ) -> None:
        """Asil kanit: ekrana cizilen piksellerde ince desen var mi?

        Onizleme yarim cozunurlukte oldugu icin tek piksel cizgileri
        kaybeder. Karo olmadan ekranda bulanik bir yuzey, karo ile
        gercek desen gorunmeli.
        """
        canvas_at_full.zoomToActualPixels()
        qapp.processEvents()

        without_tile = grab_canvas(canvas_at_full, qapp)
        energy_without = gradient_energy(without_tile)

        # Gorunen bolgeyi tam cozunurlukte uret ve yerlestir
        service = RenderService()
        rect = canvas_at_full.visibleImageRect()
        tile = service.render_tile(
            fine_detail_source, Recipe(),
            (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())),
        )
        canvas_at_full.setDetailTile(tile, rect)
        qapp.processEvents()

        with_tile = grab_canvas(canvas_at_full, qapp)
        energy_with = gradient_energy(with_tile)
        service.shutdown()

        assert energy_with > energy_without * 3.0, (
            f"karo ayrinti getirmedi: karosuz {energy_without:.4f}, "
            f"karolu {energy_with:.4f}"
        )

    def test_tile_covers_the_visible_region(
        self, canvas_at_full: ImageCanvas, fine_detail_source: np.ndarray
    ) -> None:
        canvas_at_full.zoomToActualPixels()
        rect = canvas_at_full.visibleImageRect()
        # Gorunen bolge tuval boyutunda olmali (kaynak koordinatlarinda,
        # %100'de 1:1)
        assert rect.width() == pytest.approx(canvas_at_full.width(), abs=3)
        assert rect.height() == pytest.approx(canvas_at_full.height(), abs=3)

    def test_tile_pixel_count_matches_source_region(
        self, canvas_at_full: ImageCanvas, fine_detail_source: np.ndarray
    ) -> None:
        """Karo kaynak bolgeyle ayni piksel sayisinda olmali."""
        canvas_at_full.zoomToActualPixels()
        service = RenderService()
        rect = canvas_at_full.visibleImageRect()
        tile = service.render_tile(
            fine_detail_source, Recipe(),
            (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())),
        )
        service.shutdown()
        assert tile.shape[1] == int(rect.width())
        assert tile.shape[0] == int(rect.height())

    def test_tile_matches_source_pixels_exactly_with_empty_recipe(
        self, canvas_at_full: ImageCanvas, fine_detail_source: np.ndarray
    ) -> None:
        """Bos tarifte karo kaynagin birebir kopyasi olmali."""
        canvas_at_full.zoomToActualPixels()
        service = RenderService()
        rect = canvas_at_full.visibleImageRect()
        x, y = int(rect.x()), int(rect.y())
        w, h = int(rect.width()), int(rect.height())
        tile = service.render_tile(fine_detail_source, Recipe(), (x, y, w, h))
        service.shutdown()
        expected = fine_detail_source[y:y + h, x:x + w]
        assert np.array_equal(tile, expected)


class TestTileInvalidation:
    def test_pan_clears_tile_and_requests_new_view(
        self, canvas_at_full: ImageCanvas, qapp: QApplication
    ) -> None:
        """Kaydirma sonrasi karo gecersiz olmali ve yenisi istenmeli."""
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        canvas_at_full.zoomToActualPixels()
        canvas_at_full.setDetailTile(
            np.zeros((10, 10, 3), np.float32), canvas_at_full.visibleImageRect()
        )
        assert canvas_at_full._detail is not None

        seen: list[int] = []
        canvas_at_full.viewChanged.connect(lambda: seen.append(1))

        def send(kind, pos):  # noqa: ANN001, ANN202
            ev = QMouseEvent(kind, QPointF(pos), Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier)
            qapp.sendEvent(canvas_at_full, ev)

        send(QMouseEvent.Type.MouseButtonPress, QPoint(400, 300))
        send(QMouseEvent.Type.MouseMove, QPoint(340, 260))
        send(QMouseEvent.Type.MouseButtonRelease, QPoint(340, 260))

        assert canvas_at_full._detail is None, "kaydirma karoyu temizlemedi"
        assert seen, "kaydirma sonrasi viewChanged yayilmadi"

    def test_zoom_emits_view_changed(
        self, canvas_at_full: ImageCanvas
    ) -> None:
        seen: list[int] = []
        canvas_at_full.viewChanged.connect(lambda: seen.append(1))
        canvas_at_full.setZoom(3.0)
        assert seen

    def test_new_image_clears_tile(
        self, canvas_at_full: ImageCanvas, fine_detail_source: np.ndarray
    ) -> None:
        canvas_at_full.setDetailTile(
            np.zeros((10, 10, 3), np.float32), canvas_at_full.visibleImageRect()
        )
        canvas_at_full.setImage(fine_detail_source, fine_detail_source)
        assert canvas_at_full._detail is None


class TestTileInCompareModes:
    def test_tile_is_drawn_in_split_compare(
        self, canvas_at_full: ImageCanvas, qapp: QApplication,
        fine_detail_source: np.ndarray,
    ) -> None:
        """Karsilastirma modunda da gercek kalite gorunmeli."""
        canvas_at_full.setCompareMode(CompareMode.SPLIT)
        canvas_at_full.zoomToActualPixels()
        qapp.processEvents()

        before = grab_canvas(canvas_at_full, qapp)
        service = RenderService()
        rect = canvas_at_full.visibleImageRect()
        tile = service.render_tile(
            fine_detail_source, Recipe(),
            (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())),
        )
        canvas_at_full.setDetailTile(tile, rect)
        qapp.processEvents()
        after = grab_canvas(canvas_at_full, qapp)
        service.shutdown()

        # Sag yari (duzenlenmis taraf) ayrinti kazanmali
        half = before.shape[1] // 2
        assert (gradient_energy(after[:, half:])
                > gradient_energy(before[:, half:]) * 2.0)


class TestAsyncTileDelivery:
    """Karo GUI is parcaciginda uretilmemeli.

    Genis yaricapli bir tarifte (bloom + halation, 24 MP kaynak) karo
    uretimi olculen 1.3 saniye suruyor. Bu is GUI is parcaciginda
    yapilirsa kullanici her kaydirmada arayuzu donmus gorur.
    """

    def test_requested_tile_arrives_with_same_pixels(
        self, qapp: QApplication, fine_detail_source: np.ndarray,
    ) -> None:
        service = RenderService()
        rect = (600, 400, 320, 240)
        recipe = Recipe()
        expected = service.render_tile(fine_detail_source, recipe, rect)

        got: list[tuple] = []
        service.tileReady.connect(
            lambda t, r, img, ms: got.append((t, r, img)))
        token = service.request_tile(fine_detail_source, recipe, rect)

        deadline = time.time() + 10.0
        while not got and time.time() < deadline:
            qapp.processEvents()
        service.shutdown()

        assert got, "karo arka plandan hic gelmedi"
        received_token, received_rect, image = got[0]
        assert received_token == token
        assert received_rect == rect
        assert np.array_equal(image, expected)

    def test_superseded_tile_is_not_delivered(
        self, qapp: QApplication, fine_detail_source: np.ndarray,
    ) -> None:
        """Kullanici kaydirmaya devam ettiyse eski karo ekrana gelmemeli."""
        service = RenderService()
        recipe = Recipe()
        delivered: list[int] = []
        service.tileReady.connect(lambda t, r, img, ms: delivered.append(t))

        first = service.request_tile(fine_detail_source, recipe,
                                     (100, 100, 320, 240))
        second = service.request_tile(fine_detail_source, recipe,
                                      (700, 500, 320, 240))
        deadline = time.time() + 10.0
        while second not in delivered and time.time() < deadline:
            qapp.processEvents()
        # Gecikmis sonuc icin biraz daha bekle
        extra = time.time() + 0.5
        while time.time() < extra:
            qapp.processEvents()
        service.shutdown()

        assert second in delivered, "guncel karo gelmedi"
        assert first not in delivered, "gecersiz kalan karo ekrana basildi"

"""Tuval koordinat sistemi ve gorunum testleri.

Bu testler ozellikle onemli: maskeler (Faz 5) goruntu uzayinda saklanir
ve zoom/pan degistiginde kaymamalari gerekir. Donusum hatasi maskeleri
yanlis yere koyar.
"""
from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from luma_atelier.ui.widgets.image_canvas import (
    MAX_ZOOM,
    MIN_ZOOM,
    CompareMode,
    ImageCanvas,
    numpy_to_qimage,
)

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(qapp: QApplication, color_patches: np.ndarray) -> ImageCanvas:
    c = ImageCanvas()
    c.resize(800, 600)
    c.show()
    qapp.processEvents()
    c.setImage(color_patches, color_patches)
    qapp.processEvents()
    return c


class TestNumpyToQImage:
    def test_rgb_conversion_preserves_size(self, color_patches: np.ndarray) -> None:
        qim = numpy_to_qimage(color_patches)
        assert (qim.width(), qim.height()) == (720, 480)

    def test_alpha_is_kept(self, alpha_edge: np.ndarray) -> None:
        qim = numpy_to_qimage(alpha_edge)
        assert qim.hasAlphaChannel()

    def test_colour_is_correct(self) -> None:
        arr = np.zeros((8, 8, 3), np.float32)
        arr[..., 0] = 1.0
        qim = numpy_to_qimage(arr)
        c = qim.pixelColor(4, 4)
        assert (c.red(), c.green(), c.blue()) == (255, 0, 0)

    def test_buffer_is_owned_not_borrowed(self) -> None:
        """QImage NumPy tamponunu odunc alirsa serbest bellek okunur."""
        def make():  # noqa: ANN202
            arr = np.full((64, 64, 3), 0.5, np.float32)
            return numpy_to_qimage(arr)

        qim = make()
        import gc
        gc.collect()
        # Kaynak dizi yok edildikten sonra da dogru deger okunabilmeli
        assert qim.pixelColor(10, 10).red() == 128

    def test_out_of_range_values_are_clipped(self) -> None:
        arr = np.full((8, 8, 3), 3.5, np.float32)
        qim = numpy_to_qimage(arr)
        assert qim.pixelColor(2, 2).red() == 255


class TestCoordinateTransform:
    @pytest.mark.parametrize("point", [(0, 0), (400, 300), (799, 599),
                                       (-50, -50), (1200, 900)])
    def test_widget_to_image_roundtrip(self, canvas: ImageCanvas,
                                       point: tuple[int, int]) -> None:
        p = QPointF(*point)
        back = canvas.imageToWidget(canvas.widgetToImage(p))
        assert abs(back.x() - p.x()) < 1e-4
        assert abs(back.y() - p.y()) < 1e-4

    @pytest.mark.parametrize("zoom", [0.1, 0.5, 1.0, 2.0, 8.0])
    def test_roundtrip_holds_at_every_zoom(self, canvas: ImageCanvas,
                                           zoom: float) -> None:
        canvas.setZoom(zoom)
        p = QPointF(321.0, 187.0)
        back = canvas.imageToWidget(canvas.widgetToImage(p))
        assert abs(back.x() - p.x()) < 1e-3
        assert abs(back.y() - p.y()) < 1e-3

    def test_image_point_is_stable_across_pan(self, canvas: ImageCanvas) -> None:
        """Kaydirma goruntu uzayindaki bir noktayi degistirmemeli."""
        canvas.setZoom(3.0)
        target = QPointF(120.0, 90.0)          # goruntu uzayinda bir piksel
        widget_before = canvas.imageToWidget(target)
        canvas._pan += QPointF(40.0, -25.0)    # kaydir
        widget_after = canvas.imageToWidget(target)
        # Ekrandaki yeri degisir ...
        assert widget_before != widget_after
        # ... ama geri donusum ayni goruntu pikselini vermeli
        back = canvas.widgetToImage(widget_after)
        assert abs(back.x() - target.x()) < 1e-3
        assert abs(back.y() - target.y()) < 1e-3

    def test_zoom_keeps_focus_point_anchored(self, canvas: ImageCanvas) -> None:
        """Fare tekerlegiyle yakinlasinca imlecin gosterdigi piksel kaymamali."""
        focus = QPointF(250.0, 180.0)
        before = canvas.widgetToImage(focus)
        canvas.setZoom(4.0, focus)
        after = canvas.widgetToImage(focus)
        assert abs(before.x() - after.x()) < 1e-3
        assert abs(before.y() - after.y()) < 1e-3


class TestZoom:
    def test_fit_shows_whole_image(self, canvas: ImageCanvas) -> None:
        canvas.zoomToFit()
        w, h = canvas.imageSize
        assert w * canvas.zoom() <= canvas.width() + 1
        assert h * canvas.zoom() <= canvas.height() + 1

    def test_actual_pixels_is_one_to_one(self, canvas: ImageCanvas) -> None:
        canvas.zoomToActualPixels()
        assert canvas.zoom() == pytest.approx(1.0)

    def test_zoom_is_clamped(self, canvas: ImageCanvas) -> None:
        canvas.setZoom(1000.0)
        assert canvas.zoom() <= MAX_ZOOM
        canvas.setZoom(0.0001)
        assert canvas.zoom() >= MIN_ZOOM

    def test_fit_mode_clears_on_manual_zoom(self, canvas: ImageCanvas) -> None:
        canvas.zoomToFit()
        assert canvas.isFitMode()
        canvas.setZoom(2.0)
        assert not canvas.isFitMode()

    def test_resize_refits_while_in_fit_mode(self, canvas: ImageCanvas,
                                             qapp: QApplication) -> None:
        canvas.zoomToFit()
        first = canvas.zoom()
        canvas.resize(1200, 900)
        qapp.processEvents()
        assert canvas.zoom() != pytest.approx(first)
        w, h = canvas.imageSize
        assert w * canvas.zoom() <= canvas.width() + 1

    def test_zoom_in_out_are_inverse(self, canvas: ImageCanvas) -> None:
        canvas.setZoom(1.0)
        canvas.zoomIn()
        canvas.zoomOut()
        assert canvas.zoom() == pytest.approx(1.0, rel=1e-6)


class TestCompareModes:
    def test_modes_switch(self, canvas: ImageCanvas) -> None:
        for mode in CompareMode:
            canvas.setCompareMode(mode)
            assert canvas.compareMode() is mode

    def test_compare_refused_without_original(
        self, qapp: QApplication, color_patches: np.ndarray
    ) -> None:
        """Orijinal yoksa karsilastirma sessizce yanlis sonuc uretmemeli."""
        c = ImageCanvas()
        c.resize(400, 300)
        c.setImage(color_patches)  # orijinal verilmedi
        c.setCompareMode(CompareMode.SPLIT)
        assert c.compareMode() is CompareMode.OFF

    def test_side_by_side_halves_fit_scale(self, canvas: ImageCanvas) -> None:
        canvas.setCompareMode(CompareMode.OFF)
        canvas.zoomToFit()
        full = canvas.fitScale()
        canvas.setCompareMode(CompareMode.SIDE_BY_SIDE)
        assert canvas.fitScale() < full

    def test_split_ratio_is_within_bounds(self, canvas: ImageCanvas) -> None:
        assert 0.0 < canvas.splitRatio() < 1.0


class TestEmptyState:
    def test_no_image_reports_zero_size(self, qapp: QApplication) -> None:
        c = ImageCanvas()
        assert not c.hasImage
        assert c.imageSize == (0, 0)

    def test_clear_removes_image(self, canvas: ImageCanvas) -> None:
        canvas.clear()
        assert not canvas.hasImage

    def test_zoom_calls_are_safe_without_image(self, qapp: QApplication) -> None:
        c = ImageCanvas()
        c.zoomToFit()
        c.zoomIn()
        c.setZoom(2.0)
        assert c.zoom() > 0

    def test_new_image_of_different_size_refits(
        self, canvas: ImageCanvas, gradient_rgb: np.ndarray
    ) -> None:
        canvas.setZoom(5.0)
        canvas.setImage(gradient_rgb, gradient_rgb)
        assert canvas.isFitMode()
        assert canvas.imageSize == (gradient_rgb.shape[1], gradient_rgb.shape[0])

"""Tuval uzerindeki etkilesimli araclar: kirpma, firca, gradyan.

Tasarim
-------
Araclar tuvalin *uzerinde* calisir ama tuvalin kendisi araclari
bilmez. `CanvasOverlay` fare olaylarini yakalar, goruntu uzayina
cevirir ve sinyal olarak yayar; cizimi de kendisi yapar. Boylece
`ImageCanvas` yalnizca goruntuden ve gorunumden sorumlu kalir.

Tum koordinatlar **normalize goruntu uzayindadir** (0..1). Zoom ve pan
degistiginde araclar kaymaz.
"""
from __future__ import annotations

import logging
from enum import Enum

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from luma_atelier.imaging.geometry import Geometry, fit_crop_to_aspect
from luma_atelier.ui.theme.tokens import PALETTE, TYPE

log = logging.getLogger(__name__)

#: Kirpma tutamaginin yakalanma yaricapi (ekran pikseli)
HANDLE_GRAB = 14.0
#: Kirpma dikdortgeninin en kucuk normalize boyutu
MIN_CROP = 0.04


class CanvasTool(str, Enum):
    """Tuval araci."""

    NONE = "none"
    CROP = "crop"
    BRUSH = "brush"
    ERASER = "eraser"
    LINEAR = "linear"
    RADIAL = "radial"

    @property
    def label(self) -> str:
        return {
            CanvasTool.NONE: "Gezinme",
            CanvasTool.CROP: "Kırpma",
            CanvasTool.BRUSH: "Fırça",
            CanvasTool.ERASER: "Silgi",
            CanvasTool.LINEAR: "Doğrusal gradyan",
            CanvasTool.RADIAL: "Radyal gradyan",
        }[self]


class CanvasOverlay(QWidget):
    """Tuvalin uzerine yerlesen saydam etkilesim katmani.

    Sinyaller:
        cropChanged(tuple): normalize (x, y, w, h), surukleme sirasinda
        cropCommitted(tuple): surukleme bitti
        strokeStarted() / strokePoint(QPointF) / strokeFinished()
        gradientChanged(tuple, tuple) / gradientCommitted(tuple, tuple)
    """

    cropChanged = Signal(tuple)
    cropCommitted = Signal(tuple)
    strokeStarted = Signal()
    strokePoint = Signal(QPointF)
    strokeFinished = Signal()
    gradientChanged = Signal(tuple, tuple)
    gradientCommitted = Signal(tuple, tuple)

    def __init__(self, canvas, parent: QWidget | None = None) -> None:  # noqa: ANN001
        super().__init__(parent or canvas)
        self._canvas = canvas
        self._tool = CanvasTool.NONE
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        # Kirpma
        self._crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
        self._aspect: float | None = None
        self._drag_handle = ""
        self._drag_origin = QPointF()
        self._drag_crop = self._crop
        self._show_thirds = True

        # Firca
        self._brush_radius = 0.05
        self._cursor_pos: QPointF | None = None
        self._painting = False

        # Gradyan
        self._grad_start: tuple[float, float] = (0.5, 0.2)
        self._grad_end: tuple[float, float] = (0.5, 0.8)
        self._grad_dragging = ""

        # Maske gorunumu
        self._mask_preview: np.ndarray | None = None
        self._show_mask = False

    # ----------------------------------------------------------------- arac
    def tool(self) -> CanvasTool:
        return self._tool

    def setTool(self, tool: CanvasTool) -> None:  # noqa: N802
        self._tool = tool
        interactive = tool is not CanvasTool.NONE
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          not interactive)
        if tool is CanvasTool.CROP:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool in (CanvasTool.BRUSH, CanvasTool.ERASER):
            self.setCursor(Qt.CursorShape.BlankCursor)
        elif tool in (CanvasTool.LINEAR, CanvasTool.RADIAL):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    # ---------------------------------------------------------------- kirpma
    def setCrop(self, crop: tuple[float, float, float, float]) -> None:  # noqa: N802
        self._crop = crop
        self.update()

    def crop(self) -> tuple[float, float, float, float]:
        return self._crop

    def setAspect(self, aspect: float | None) -> None:  # noqa: N802
        self._aspect = aspect
        if aspect is not None and aspect > 0:
            iw, ih = self._canvas.sourceSize
            if iw and ih:
                self._crop = fit_crop_to_aspect(self._crop, aspect, iw / ih)
                self.cropChanged.emit(self._crop)
                self.cropCommitted.emit(self._crop)
        self.update()

    def setShowThirds(self, value: bool) -> None:  # noqa: N802
        self._show_thirds = value
        self.update()

    # ----------------------------------------------------------------- firca
    def setBrushRadius(self, radius: float) -> None:  # noqa: N802
        self._brush_radius = max(0.002, min(0.6, radius))
        self.update()

    def brushRadius(self) -> float:  # noqa: N802
        return self._brush_radius

    def setMaskPreview(self, mask: np.ndarray | None) -> None:  # noqa: N802
        """Maske gorunumu icin 0..1 maske dizisi."""
        self._mask_preview = mask
        self.update()

    def setShowMask(self, value: bool) -> None:  # noqa: N802
        self._show_mask = value
        self.update()

    # --------------------------------------------------------------- gradyan
    def setGradient(self, start: tuple[float, float],  # noqa: N802
                    end: tuple[float, float]) -> None:
        self._grad_start, self._grad_end = start, end
        self.update()

    def gradient(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return self._grad_start, self._grad_end

    # ------------------------------------------------------------ donusumler
    def _image_rect(self) -> QRectF:
        """Goruntunun ekrandaki dikdortgeni."""
        canvas = self._canvas
        iw, ih = canvas.imageSize
        if not iw or not ih:
            return QRectF()
        top_left = canvas.imageToWidget(QPointF(0, 0))
        bottom_right = canvas.imageToWidget(QPointF(float(iw), float(ih)))
        return QRectF(top_left, bottom_right)

    def _to_norm(self, pos: QPointF) -> tuple[float, float]:
        rect = self._image_rect()
        if rect.width() < 1 or rect.height() < 1:
            return (0.0, 0.0)
        return (float(np.clip((pos.x() - rect.left()) / rect.width(), 0, 1)),
                float(np.clip((pos.y() - rect.top()) / rect.height(), 0, 1)))

    def _from_norm(self, point: tuple[float, float]) -> QPointF:
        rect = self._image_rect()
        return QPointF(rect.left() + point[0] * rect.width(),
                       rect.top() + point[1] * rect.height())

    # -------------------------------------------------------------- olaylar
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        pos = event.position()

        if self._tool is CanvasTool.CROP:
            self._drag_handle = self._handle_at(pos)
            self._drag_origin = pos
            self._drag_crop = self._crop
            if not self._drag_handle:
                # Bos alana basmak yeni kirpma baslatir
                nx, ny = self._to_norm(pos)
                self._crop = (nx, ny, MIN_CROP, MIN_CROP)
                self._drag_handle = "br"
                self._drag_crop = self._crop
            self.update()
            return

        if self._tool in (CanvasTool.BRUSH, CanvasTool.ERASER):
            self._painting = True
            self.strokeStarted.emit()
            nx, ny = self._to_norm(pos)
            self.strokePoint.emit(QPointF(nx, ny))
            return

        if self._tool in (CanvasTool.LINEAR, CanvasTool.RADIAL):
            start_px = self._from_norm(self._grad_start)
            end_px = self._from_norm(self._grad_end)
            if (pos - start_px).manhattanLength() < HANDLE_GRAB * 1.5:
                self._grad_dragging = "start"
            elif (pos - end_px).manhattanLength() < HANDLE_GRAB * 1.5:
                self._grad_dragging = "end"
            else:
                self._grad_start = self._to_norm(pos)
                self._grad_end = self._to_norm(pos)
                self._grad_dragging = "end"
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        self._cursor_pos = pos

        if self._tool is CanvasTool.CROP and self._drag_handle:
            self._resize_crop(pos)
            self.cropChanged.emit(self._crop)
            self.update()
            return

        if self._painting:
            nx, ny = self._to_norm(pos)
            self.strokePoint.emit(QPointF(nx, ny))
            return

        if self._grad_dragging:
            point = self._to_norm(pos)
            if self._grad_dragging == "start":
                self._grad_start = point
            else:
                self._grad_end = point
            self.gradientChanged.emit(self._grad_start, self._grad_end)
            self.update()
            return

        if self._tool in (CanvasTool.BRUSH, CanvasTool.ERASER):
            self.update()   # firca imleci cizimi

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_handle:
            self._drag_handle = ""
            self.cropCommitted.emit(self._crop)
        if self._painting:
            self._painting = False
            self.strokeFinished.emit()
        if self._grad_dragging:
            self._grad_dragging = ""
            self.gradientCommitted.emit(self._grad_start, self._grad_end)
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._cursor_pos = None
        self.update()

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        """Firca boyutunu tekerlekle ayarlar; diger araclarda tuvale birakir."""
        if self._tool in (CanvasTool.BRUSH, CanvasTool.ERASER):
            steps = event.angleDelta().y() / 120.0
            self.setBrushRadius(self._brush_radius * (1.12 ** steps))
            event.accept()
            return
        event.ignore()

    # -------------------------------------------------------- kirpma yardim
    def _handle_at(self, pos: QPointF) -> str:
        x, y, w, h = self._crop
        rect = self._image_rect()
        if rect.width() < 1:
            return ""
        corners = {
            "tl": (x, y), "tr": (x + w, y),
            "bl": (x, y + h), "br": (x + w, y + h),
        }
        for name, point in corners.items():
            if (self._from_norm(point) - pos).manhattanLength() < HANDLE_GRAB * 1.6:
                return name
        edges = {
            "t": (x + w / 2, y), "b": (x + w / 2, y + h),
            "l": (x, y + h / 2), "r": (x + w, y + h / 2),
        }
        for name, point in edges.items():
            if (self._from_norm(point) - pos).manhattanLength() < HANDLE_GRAB * 1.4:
                return name
        # Ic alan: tasima
        nx, ny = self._to_norm(pos)
        if x <= nx <= x + w and y <= ny <= y + h:
            return "move"
        return ""

    def _resize_crop(self, pos: QPointF) -> None:
        nx, ny = self._to_norm(pos)
        x, y, w, h = self._drag_crop
        handle = self._drag_handle

        if handle == "move":
            ox, oy = self._to_norm(self._drag_origin)
            dx, dy = nx - ox, ny - oy
            x = float(np.clip(x + dx, 0.0, 1.0 - w))
            y = float(np.clip(y + dy, 0.0, 1.0 - h))
        else:
            left, top, right, bottom = x, y, x + w, y + h
            if "l" in handle:
                left = min(nx, right - MIN_CROP)
            if "r" in handle:
                right = max(nx, left + MIN_CROP)
            if "t" in handle:
                top = min(ny, bottom - MIN_CROP)
            if "b" in handle:
                bottom = max(ny, top + MIN_CROP)
            x, y = max(0.0, left), max(0.0, top)
            w, h = min(1.0, right) - x, min(1.0, bottom) - y

        crop = (x, y, max(MIN_CROP, w), max(MIN_CROP, h))
        if self._aspect is not None and self._aspect > 0:
            iw, ih = self._canvas.sourceSize
            if iw and ih:
                crop = fit_crop_to_aspect(crop, self._aspect, iw / ih)
        self._crop = crop

    # --------------------------------------------------------------- cizim
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if self._tool is CanvasTool.NONE and not self._show_mask:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._show_mask and self._mask_preview is not None:
            self._paint_mask(p)

        if self._tool is CanvasTool.CROP:
            self._paint_crop(p)
        elif self._tool in (CanvasTool.LINEAR, CanvasTool.RADIAL):
            self._paint_gradient(p)
        elif self._tool in (CanvasTool.BRUSH, CanvasTool.ERASER):
            self._paint_brush_cursor(p)
        p.end()

    def _paint_mask(self, p: QPainter) -> None:
        """Maskeyi kirmizi ortu olarak gosterir."""
        from PySide6.QtGui import QImage

        mask = self._mask_preview
        if mask is None or mask.size == 0:
            return
        h, w = mask.shape[:2]
        rgba = np.zeros((h, w, 4), np.uint8)
        colour = QColor(PALETTE.mask_overlay)
        rgba[..., 0] = colour.red()
        rgba[..., 1] = colour.green()
        rgba[..., 2] = colour.blue()
        rgba[..., 3] = np.clip(mask * 150.0, 0, 255).astype(np.uint8)
        rgba = np.ascontiguousarray(rgba)
        image = QImage(rgba.data, w, h, rgba.strides[0],
                       QImage.Format.Format_RGBA8888).copy()
        p.drawImage(self._image_rect(), image)

    def _paint_crop(self, p: QPainter) -> None:
        rect = self._image_rect()
        if rect.width() < 2:
            return
        x, y, w, h = self._crop
        crop_rect = QRectF(rect.left() + x * rect.width(),
                           rect.top() + y * rect.height(),
                           w * rect.width(), h * rect.height())

        # Disarisi karartilir
        shade = QColor(PALETTE.crop_shade)
        shade.setAlphaF(0.66)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shade)
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(),
                          crop_rect.top() - rect.top()))
        p.drawRect(QRectF(rect.left(), crop_rect.bottom(), rect.width(),
                          rect.bottom() - crop_rect.bottom()))
        p.drawRect(QRectF(rect.left(), crop_rect.top(),
                          crop_rect.left() - rect.left(), crop_rect.height()))
        p.drawRect(QRectF(crop_rect.right(), crop_rect.top(),
                          rect.right() - crop_rect.right(), crop_rect.height()))

        # Ucte bir rehberleri
        if self._show_thirds:
            guide = QColor(PALETTE.grid_line)
            guide.setAlphaF(0.30)
            p.setPen(QPen(guide, 1.0))
            for i in (1, 2):
                gx = crop_rect.left() + crop_rect.width() * i / 3.0
                gy = crop_rect.top() + crop_rect.height() * i / 3.0
                p.drawLine(QPointF(gx, crop_rect.top()),
                           QPointF(gx, crop_rect.bottom()))
                p.drawLine(QPointF(crop_rect.left(), gy),
                           QPointF(crop_rect.right(), gy))

        # Cerceve
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(PALETTE.text_primary), 1.4))
        p.drawRect(crop_rect)

        # Tutamaklar
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.text_primary))
        for cx, cy in ((crop_rect.left(), crop_rect.top()),
                       (crop_rect.right(), crop_rect.top()),
                       (crop_rect.left(), crop_rect.bottom()),
                       (crop_rect.right(), crop_rect.bottom())):
            p.drawRect(QRectF(cx - 5, cy - 5, 10, 10))

        # Boyut bilgisi
        iw, ih = self._canvas.sourceSize
        if iw and ih:
            out_w = int(round(iw * w))
            out_h = int(round(ih * h))
            f = QFont("Cascadia Mono")
            f.setPixelSize(TYPE.size_micro)
            p.setFont(f)
            text = f"{out_w} × {out_h}"
            box = QRectF(crop_rect.left() + 4, crop_rect.top() + 4, 120, 16)
            p.setBrush(QColor(0, 0, 0, 160))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(box.left(), box.top(),
                                     p.fontMetrics().horizontalAdvance(text) + 10,
                                     16), 3, 3)
            p.setPen(QColor(PALETTE.text_primary))
            p.drawText(QRectF(box.left() + 5, box.top(), box.width(), 16),
                       int(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter), text)

    def _paint_gradient(self, p: QPainter) -> None:
        start = self._from_norm(self._grad_start)
        end = self._from_norm(self._grad_end)
        p.setPen(QPen(QColor(PALETTE.accent), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)

        if self._tool is CanvasTool.LINEAR:
            p.drawLine(start, end)
            # Gradyanin yonune dik rehber cizgiler
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length = max(1e-3, float(np.hypot(dx, dy)))
            nx, ny = -dy / length * 80.0, dx / length * 80.0
            guide = QColor(PALETTE.accent)
            guide.setAlphaF(0.5)
            p.setPen(QPen(guide, 1.0, Qt.PenStyle.DashLine))
            for point in (start, end):
                p.drawLine(QPointF(point.x() - nx, point.y() - ny),
                           QPointF(point.x() + nx, point.y() + ny))
        else:
            radius = float(np.hypot(end.x() - start.x(), end.y() - start.y()))
            p.drawEllipse(start, radius, radius)

        p.setPen(QPen(QColor(PALETTE.bg_base), 1.5))
        for point, colour in ((start, PALETTE.accent),
                              (end, PALETTE.accent_hover)):
            p.setBrush(QColor(colour))
            p.drawEllipse(point, 7, 7)

    def _paint_brush_cursor(self, p: QPainter) -> None:
        if self._cursor_pos is None:
            return
        rect = self._image_rect()
        radius_px = self._brush_radius * rect.width()
        colour = QColor(PALETTE.danger if self._tool is CanvasTool.ERASER
                        else PALETTE.accent_hover)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(PALETTE.bg_base), 2.4))
        p.drawEllipse(self._cursor_pos, radius_px, radius_px)
        p.setPen(QPen(colour, 1.3))
        p.drawEllipse(self._cursor_pos, radius_px, radius_px)

"""Renk carki: gölge / orta ton / parlak alan renk secimi.

Klasik derecelendirme carki: merkez notr (etkisiz), disa dogru gidildikce
doygunluk artar, aci tonu belirler. Altindaki kaydirici siddeti verir.

Gorsel olarak carkin kendisi bir kez uretilip onbelleklenir; her
cizimde yeniden hesaplanmaz.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from luma_atelier.ui.theme.tokens import PALETTE, SPACE, TYPE
from luma_atelier.ui.widgets.parameter_slider import ParameterSlider, SliderSpec

#: Carkin ic boslugu (merkez notr bolge) - yaricapa oran
NEUTRAL_RADIUS = 0.06


def hsv_to_rgb(hue: float, sat: float, value: float = 1.0) -> tuple[float, float, float]:
    """0..360 ton, 0..1 doygunluk -> 0..1 RGB."""
    h = (hue % 360.0) / 60.0
    c = value * sat
    x = c * (1.0 - abs(h % 2.0 - 1.0))
    m = value - c
    if h < 1:
        r, g, b = c, x, 0.0
    elif h < 2:
        r, g, b = x, c, 0.0
    elif h < 3:
        r, g, b = 0.0, c, x
    elif h < 4:
        r, g, b = 0.0, x, c
    elif h < 5:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return (r + m, g + m, b + m)


class ColorWheel(QWidget):
    """Tek bir renk carki.

    Deger, `color` olarak 0..1 RGB uclusudur; merkez (0.5, 0.5, 0.5)
    notrdur ve hicbir etki yapmaz.

    Sinyaller:
        colorChanged(tuple): surukleme sirasinda
        editingFinished(tuple): surukleme bittiginde
    """

    colorChanged = Signal(tuple)
    editingFinished = Signal(tuple)

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ColorWheel")
        self._title = title
        self._hue = 0.0
        self._sat = 0.0
        self._dragging = False
        self._hover = False
        self._wheel_cache: QPixmap | None = None
        self._cache_size = 0

        self.setMinimumSize(96, 112)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{title}: merkez nötrdür.\n"
            "Sürükleyerek renk seçin, çift tıklama sıfırlar."
        )
        self.setAccessibleName(title or "Renk çarkı")

    # ---------------------------------------------------------------- deger
    def color(self) -> tuple[float, float, float]:
        """0..1 RGB. Notr merkez (0.5, 0.5, 0.5)."""
        r, g, b = hsv_to_rgb(self._hue, self._sat, 1.0)
        # Notrden sapma olarak esle: merkez 0.5
        return (0.5 + (r - 0.5) * self._sat,
                0.5 + (g - 0.5) * self._sat,
                0.5 + (b - 0.5) * self._sat)

    def setColor(self, color, *, notify: bool = False) -> None:  # noqa: ANN001, N802
        try:
            r, g, b = (float(c) for c in color)
        except (TypeError, ValueError):
            r = g = b = 0.5
        dr, dg, db = r - 0.5, g - 0.5, b - 0.5
        magnitude = max(abs(dr), abs(dg), abs(db))
        if magnitude < 1e-4:
            self._hue, self._sat = 0.0, 0.0
        else:
            # Ton acisini RGB sapmasindan geri hesapla
            mx = max(dr, dg, db)
            mn = min(dr, dg, db)
            chroma = mx - mn
            if chroma < 1e-6:
                hue = 0.0
            elif mx == dr:
                hue = ((dg - db) / chroma) % 6.0
            elif mx == dg:
                hue = ((db - dr) / chroma) + 2.0
            else:
                hue = ((dr - dg) / chroma) + 4.0
            self._hue = float(hue * 60.0)
            self._sat = float(np.clip(chroma * 2.0, 0.0, 1.0))
        self.update()
        if notify:
            self.colorChanged.emit(self.color())

    def isNeutral(self) -> bool:  # noqa: N802
        return self._sat < 1e-4

    def reset(self) -> None:
        if self.isNeutral():
            return
        self._hue, self._sat = 0.0, 0.0
        self.update()
        self.colorChanged.emit(self.color())
        self.editingFinished.emit(self.color())

    # ------------------------------------------------------------ yerlesim
    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, 138)

    def _wheel_rect(self) -> QRectF:
        label_h = 16.0 if self._title else 0.0
        side = min(self.width(), self.height() - label_h) - 6
        side = max(24.0, side)
        x = (self.width() - side) / 2.0
        return QRectF(x, label_h + 3.0, side, side)

    # ----------------------------------------------------------- etkilesim
    def _set_from_pos(self, pos: QPointF) -> None:
        r = self._wheel_rect()
        centre = r.center()
        dx = (pos.x() - centre.x()) / max(1.0, r.width() / 2.0)
        dy = (pos.y() - centre.y()) / max(1.0, r.height() / 2.0)
        dist = float(np.hypot(dx, dy))
        if dist < NEUTRAL_RADIUS:
            self._sat = 0.0
        else:
            self._sat = float(np.clip((dist - NEUTRAL_RADIUS)
                                      / (1.0 - NEUTRAL_RADIUS), 0.0, 1.0))
            self._hue = float(np.degrees(np.arctan2(-dy, dx)) % 360.0)
        self.update()
        self.colorChanged.emit(self.color())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._set_from_pos(event.position())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            self._set_from_pos(event.position())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            self._dragging = False
            self.editingFinished.emit(self.color())

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.reset()

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = False
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        hue_step = 3.0 if fine else 12.0
        sat_step = 0.02 if fine else 0.06
        if key == Qt.Key.Key_Left:
            self._hue = (self._hue - hue_step) % 360.0
        elif key == Qt.Key.Key_Right:
            self._hue = (self._hue + hue_step) % 360.0
        elif key == Qt.Key.Key_Up:
            self._sat = float(np.clip(self._sat + sat_step, 0.0, 1.0))
        elif key == Qt.Key.Key_Down:
            self._sat = float(np.clip(self._sat - sat_step, 0.0, 1.0))
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_Escape):
            self.reset()
            event.accept()
            return
        else:
            super().keyPressEvent(event)
            return
        self.update()
        self.colorChanged.emit(self.color())
        self.editingFinished.emit(self.color())
        event.accept()

    # ---------------------------------------------------------------- cizim
    def _wheel_pixmap(self, size: int) -> QPixmap:
        """Cark gorseli. Bir kez uretilir, boyut degisince yenilenir."""
        if self._wheel_cache is not None and self._cache_size == size:
            return self._wheel_cache

        n = max(8, size)
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        cx = cy = (n - 1) / 2.0
        dx = (xx - cx) / cx
        dy = (yy - cy) / cy
        dist = np.hypot(dx, dy)
        hue = (np.degrees(np.arctan2(-dy, dx)) % 360.0).astype(np.float32)
        sat = np.clip((dist - NEUTRAL_RADIUS) / (1.0 - NEUTRAL_RADIUS), 0.0, 1.0)

        # Vektorlestirilmis HSV -> RGB
        h = hue / 60.0
        c = sat
        x = c * (1.0 - np.abs(h % 2.0 - 1.0))
        m = 1.0 - c
        zeros = np.zeros_like(c)
        sector = h.astype(np.int32) % 6
        r = np.select([sector == 0, sector == 1, sector == 2, sector == 3,
                       sector == 4, sector == 5],
                      [c, x, zeros, zeros, x, c])
        g = np.select([sector == 0, sector == 1, sector == 2, sector == 3,
                       sector == 4, sector == 5],
                      [x, c, c, x, zeros, zeros])
        b = np.select([sector == 0, sector == 1, sector == 2, sector == 3,
                       sector == 4, sector == 5],
                      [zeros, zeros, x, c, c, x])
        rgb = np.dstack([r + m, g + m, b + m])

        # Disari kalan alani saydam yap
        alpha = np.clip((1.0 - dist) * n * 0.5, 0.0, 1.0)
        rgba = np.dstack([
            np.clip(rgb * 255.0, 0, 255).astype(np.uint8),
            (alpha * 255.0).astype(np.uint8),
        ])
        rgba = np.ascontiguousarray(rgba)
        image = QImage(rgba.data, n, n, rgba.strides[0],
                       QImage.Format.Format_RGBA8888).copy()
        self._wheel_cache = QPixmap.fromImage(image)
        self._cache_size = size
        return self._wheel_cache

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._title:
            f = QFont()
            f.setPixelSize(TYPE.size_caption)
            p.setFont(f)
            p.setPen(QColor(PALETTE.text_primary if (self._hover or self.hasFocus())
                            else PALETTE.text_secondary))
            p.drawText(QRectF(0, 0, self.width(), 16),
                       int(Qt.AlignmentFlag.AlignCenter), self._title)

        r = self._wheel_rect()
        size = int(min(r.width(), r.height()))
        if size < 8:
            p.end()
            return

        p.drawPixmap(r, self._wheel_pixmap(size), QRectF(0, 0, size, size))

        # Kenarlik
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(PALETTE.accent if self.hasFocus()
                             else PALETTE.border), 1.4))
        p.drawEllipse(r)

        # Secim gostergesi
        centre = r.center()
        radius = r.width() / 2.0
        d = NEUTRAL_RADIUS + self._sat * (1.0 - NEUTRAL_RADIUS)
        angle = np.radians(self._hue)
        pos = QPointF(centre.x() + float(np.cos(angle)) * d * radius,
                      centre.y() - float(np.sin(angle)) * d * radius)
        p.setPen(QPen(QColor(PALETTE.bg_base), 2.0))
        p.setBrush(QColor(*[int(c * 255) for c in
                            hsv_to_rgb(self._hue, self._sat)]))
        p.drawEllipse(pos, 6.0, 6.0)
        p.setPen(QPen(QColor(PALETTE.text_primary), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pos, 6.0, 6.0)

        # Merkez notr isareti
        p.setPen(QPen(QColor(PALETTE.text_muted), 1.0))
        p.drawEllipse(centre, radius * NEUTRAL_RADIUS, radius * NEUTRAL_RADIUS)
        p.end()


class ColorWheelGroup(QWidget):
    """Renk carki + siddet kaydiricisi.

    Derecelendirme panelinde her bolge (golge / orta ton / parlak alan)
    icin bir tane kullanilir.
    """

    valueChanged = Signal(tuple, float)
    editingFinished = Signal(tuple, float)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE.xxs)

        self.wheel = ColorWheel(title)
        self.strength = ParameterSlider(SliderSpec(
            key="amount", label="Şiddet", minimum=0.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0, suffix=" %",
            bipolar=False, tooltip=f"{title} renginin şiddeti",
        ))
        lay.addWidget(self.wheel)
        lay.addWidget(self.strength)

        self.wheel.colorChanged.connect(lambda _c: self._emit(False))
        self.wheel.editingFinished.connect(lambda _c: self._emit(True))
        self.strength.valueChanged.connect(lambda _v: self._emit(False))
        self.strength.editingFinished.connect(lambda _v: self._emit(True))

    def _emit(self, finished: bool) -> None:
        payload = (self.wheel.color(), self.strength.value())
        (self.editingFinished if finished else self.valueChanged).emit(*payload)

    def setValues(self, color, amount: float) -> None:  # noqa: ANN001, N802
        self.wheel.setColor(color)
        self.strength.setValue(float(amount), notify=False)

    def values(self) -> tuple[tuple[float, float, float], float]:
        return self.wheel.color(), self.strength.value()

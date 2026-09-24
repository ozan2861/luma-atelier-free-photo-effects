"""Etkilesimli ton egrisi editoru.

Kullanim
--------
* Egri uzerine tiklamak yeni kontrol noktasi ekler.
* Noktayi surukleyerek tasinir; uc noktalar yalnizca dikeyde hareket eder.
* Sag tiklama veya Delete secili noktayi siler (uc noktalar silinmez).
* Cift tiklama egriyi kimlige dondurur.
* Klavye: Tab ile noktalar arasinda gezinilir, ok tuslariyla tasinir.

Arka planda secili kanalin histogrami cizilir; kullanici hangi ton
araligina dokundugunu gorur.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from luma_atelier.imaging import curves
from luma_atelier.ui.theme.tokens import PALETTE, RADIUS, TYPE

#: Kontrol noktasinin yakalanma yaricapi (piksel)
GRAB_RADIUS = 11.0
#: Iki nokta bu kadar yakinsa yeni nokta eklenmez
MIN_POINT_GAP = 0.035
#: Maksimum kontrol noktasi. Daha fazlasi egriyi yonetilemez yapar.
MAX_POINTS = 16


class CurveEditor(QWidget):
    """Tek bir ton egrisini duzenleyen kare kontrol.

    Sinyaller:
        curveChanged(list): her degisimde (onizleme icin)
        editingFinished(list): surukleme bittiginde (gecmis icin)
    """

    curveChanged = Signal(list)
    editingFinished = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CurveEditor")
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip(
            "Eğriye tıklayarak nokta ekleyin, sürükleyerek taşıyın.\n"
            "Sağ tıklama noktayı siler. Çift tıklama eğriyi sıfırlar."
        )

        self._points: list[tuple[float, float]] = list(curves.IDENTITY_CURVE)
        self._selected = -1
        self._dragging = False
        self._hover = -1
        self._histogram: np.ndarray | None = None
        self._curve_color = QColor(PALETTE.text_primary)

    # ---------------------------------------------------------------- veri
    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def setPoints(self, points, *, notify: bool = False) -> None:  # noqa: ANN001, N802
        self._points = curves.normalise_points(points)
        self._selected = -1
        self.update()
        if notify:
            self.curveChanged.emit(self.points())

    def setCurveColor(self, color: str) -> None:  # noqa: N802
        """Kanal egrisi icin renk (kirmizi/yesil/mavi ayrimi)."""
        self._curve_color = QColor(color)
        self.update()

    def setHistogram(self, values: np.ndarray | None) -> None:  # noqa: N802
        """Arka planda gosterilecek 0..1 normalize histogram."""
        self._histogram = values
        self.update()

    def reset(self) -> None:
        if curves.is_identity(self._points):
            return
        self._points = list(curves.IDENTITY_CURVE)
        self._selected = -1
        self.update()
        self.curveChanged.emit(self.points())
        self.editingFinished.emit(self.points())

    def isIdentity(self) -> bool:  # noqa: N802
        return curves.is_identity(self._points)

    # ------------------------------------------------------------ yerlesim
    def _plot_rect(self) -> QRectF:
        side = min(self.width(), self.height()) - 2
        x = (self.width() - side) / 2.0
        y = (self.height() - side) / 2.0
        return QRectF(x + 0.5, y + 0.5, side - 1, side - 1)

    def _to_widget(self, point: tuple[float, float]) -> QPointF:
        r = self._plot_rect()
        return QPointF(r.left() + point[0] * r.width(),
                       r.bottom() - point[1] * r.height())

    def _to_curve(self, pos: QPointF) -> tuple[float, float]:
        r = self._plot_rect()
        x = (pos.x() - r.left()) / max(1.0, r.width())
        y = (r.bottom() - pos.y()) / max(1.0, r.height())
        return (float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0)))

    def _point_at(self, pos: QPointF) -> int:
        for i, p in enumerate(self._points):
            if (self._to_widget(p) - pos).manhattanLength() < GRAB_RADIUS * 1.6:
                w = self._to_widget(p)
                dx, dy = w.x() - pos.x(), w.y() - pos.y()
                if dx * dx + dy * dy <= GRAB_RADIUS * GRAB_RADIUS:
                    return i
        return -1

    def sizeHint(self):  # noqa: ANN201, N802
        from PySide6.QtCore import QSize
        return QSize(240, 240)

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return width

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    # ------------------------------------------------------------- etkilesim
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        index = self._point_at(pos)

        if event.button() == Qt.MouseButton.RightButton:
            if index > 0 and index < len(self._points) - 1:
                del self._points[index]
                self._selected = -1
                self.update()
                self.curveChanged.emit(self.points())
                self.editingFinished.emit(self.points())
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if index < 0:
            index = self._insert_point(self._to_curve(pos))
            if index < 0:
                return
        self._selected = index
        self._dragging = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.update()

    def _insert_point(self, point: tuple[float, float]) -> int:
        if len(self._points) >= MAX_POINTS:
            return -1
        x, _y = point
        for px_, _py in self._points:
            if abs(px_ - x) < MIN_POINT_GAP:
                return -1
        self._points.append(point)
        self._points = curves.normalise_points(self._points)
        for i, p in enumerate(self._points):
            if abs(p[0] - x) < 1e-6:
                return i
        return -1

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if not self._dragging:
            hover = self._point_at(pos)
            if hover != self._hover:
                self._hover = hover
                self.setCursor(Qt.CursorShape.SizeAllCursor if hover >= 0
                               else Qt.CursorShape.CrossCursor)
                self.update()
            return

        if self._selected < 0:
            return
        x, y = self._to_curve(pos)
        last = len(self._points) - 1
        if self._selected == 0:
            x = 0.0                     # uc noktalar yalnizca dikeyde
        elif self._selected == last:
            x = 1.0
        else:
            # Komsulari gecmesin; sira bozulursa egri tanimsiz olur
            left = self._points[self._selected - 1][0] + MIN_POINT_GAP * 0.5
            right = self._points[self._selected + 1][0] - MIN_POINT_GAP * 0.5
            x = float(np.clip(x, left, right))
        self._points[self._selected] = (x, y)
        self.update()
        self.curveChanged.emit(self.points())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            self._dragging = False
            self._points = curves.normalise_points(self._points)
            self.update()
            self.editingFinished.emit(self.points())

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.reset()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        step = 0.01 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier \
            else 0.04

        if key == Qt.Key.Key_Tab and self._points:
            self._selected = (self._selected + 1) % len(self._points)
            self.update()
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if 0 < self._selected < len(self._points) - 1:
                del self._points[self._selected]
                self._selected = -1
                self.update()
                self.curveChanged.emit(self.points())
                self.editingFinished.emit(self.points())
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.reset()
            event.accept()
            return

        if self._selected < 0:
            super().keyPressEvent(event)
            return

        x, y = self._points[self._selected]
        last = len(self._points) - 1
        if key == Qt.Key.Key_Up:
            y += step
        elif key == Qt.Key.Key_Down:
            y -= step
        elif key == Qt.Key.Key_Left and 0 < self._selected < last:
            x -= step
        elif key == Qt.Key.Key_Right and 0 < self._selected < last:
            x += step
        else:
            super().keyPressEvent(event)
            return

        if 0 < self._selected < last:
            left = self._points[self._selected - 1][0] + MIN_POINT_GAP * 0.5
            right = self._points[self._selected + 1][0] - MIN_POINT_GAP * 0.5
            x = float(np.clip(x, left, right))
        self._points[self._selected] = (x, float(np.clip(y, 0.0, 1.0)))
        self.update()
        self.curveChanged.emit(self.points())
        self.editingFinished.emit(self.points())
        event.accept()

    # ---------------------------------------------------------------- cizim
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self._plot_rect()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.bg_base))
        p.drawRoundedRect(r, RADIUS.sm, RADIUS.sm)

        # Histogram arka plani
        if self._histogram is not None and len(self._histogram) > 1:
            path = QPainterPath()
            path.moveTo(r.left(), r.bottom())
            n = len(self._histogram)
            for i, v in enumerate(self._histogram):
                x = r.left() + r.width() * i / (n - 1)
                y = r.bottom() - r.height() * float(min(1.0, v)) * 0.85
                path.lineTo(x, y)
            path.lineTo(r.right(), r.bottom())
            path.closeSubpath()
            fill = QColor(PALETTE.text_muted)
            fill.setAlphaF(0.20)
            p.setBrush(fill)
            p.drawPath(path)

        # Izgara
        p.setPen(QPen(QColor(PALETTE.border_subtle), 1.0))
        for i in (1, 2, 3):
            t = i / 4.0
            p.drawLine(QPointF(r.left() + r.width() * t, r.top()),
                       QPointF(r.left() + r.width() * t, r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + r.height() * t),
                       QPointF(r.right(), r.top() + r.height() * t))

        # Kimlik kosegeni
        diag = QPen(QColor(PALETTE.border), 1.0)
        diag.setStyle(Qt.PenStyle.DashLine)
        p.setPen(diag)
        p.drawLine(r.bottomLeft(), r.topRight())

        # Egri
        lut = curves.build_lut(self._points, 256)
        path = QPainterPath()
        for i, v in enumerate(lut):
            x = r.left() + r.width() * i / (len(lut) - 1)
            y = r.bottom() - r.height() * float(v)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        colour = self._curve_color if not self.isIdentity() \
            else QColor(PALETTE.text_muted)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(colour, 1.8))
        p.drawPath(path)

        # Kontrol noktalari
        for i, point in enumerate(self._points):
            w = self._to_widget(point)
            selected = i == self._selected
            hovered = i == self._hover
            radius = 5.5 if (selected or hovered) else 4.0
            if selected and self.hasFocus():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(PALETTE.accent))
                p.drawEllipse(w, radius + 3.0, radius + 3.0)
            p.setPen(QPen(QColor(PALETTE.bg_base), 1.5))
            p.setBrush(QColor(PALETTE.accent_hover if selected
                              else PALETTE.text_primary))
            p.drawEllipse(w, radius, radius)

        # Cerceve
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(PALETTE.border_subtle), 1.0))
        p.drawRoundedRect(r, RADIUS.sm, RADIUS.sm)

        # Secili nokta degeri
        if 0 <= self._selected < len(self._points):
            x, y = self._points[self._selected]
            f = QFont("Cascadia Mono")
            f.setPixelSize(TYPE.size_micro)
            p.setFont(f)
            p.setPen(QColor(PALETTE.text_secondary))
            p.drawText(QRectF(r.left() + 4, r.top() + 2, r.width() - 8, 14),
                       int(Qt.AlignmentFlag.AlignLeft),
                       f"giriş {x * 255:.0f}   çıkış {y * 255:.0f}")
        p.end()


class MultiCurveEditor(QWidget):
    """Kanal secicili tek egri editoru.

    Dort egriyi alt alta gostermek dikeyde ~800 px yer kapliyordu ve
    dar panelde kullanilamaz hale getiriyordu. Bunun yerine tek editor
    ve ustunde kanal dugmeleri - gercek fotograf editorlerinin
    yaklasimi. Degistirilmis kanallar dugmede nokta ile isaretlenir.

    Sinyaller:
        curvesChanged(dict): {kanal: noktalar}
        editingFinished(dict)
    """

    curvesChanged = Signal(dict)
    editingFinished = Signal(dict)

    def __init__(self, channels, parent: QWidget | None = None) -> None:  # noqa: ANN001
        """channels: ((anahtar, etiket, renk), ...)"""
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout

        from luma_atelier.ui.theme.tokens import SPACE

        self._channels = tuple(channels)
        self._values: dict[str, list[tuple[float, float]]] = {
            key: list(curves.IDENTITY_CURVE) for key, _l, _c in self._channels
        }
        self._active = self._channels[0][0]
        self._buttons: dict[str, object] = {}
        self._suppress = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE.xs)

        bar = QHBoxLayout()
        bar.setSpacing(SPACE.xxs)
        for key, label, _colour in self._channels:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(key == self._active)
            button.setToolTip(f"{label} eğrisini düzenle")
            button.setMinimumWidth(36)
            button.clicked.connect(
                lambda _checked=False, k=key: self.setActiveChannel(k)
            )
            bar.addWidget(button)
            self._buttons[key] = button
        bar.addStretch(1)
        root.addLayout(bar)

        self.editor = CurveEditor()
        self.editor.curveChanged.connect(self._on_changed)
        self.editor.editingFinished.connect(self._on_finished)
        root.addWidget(self.editor)
        self._apply_channel_colour()

    # --------------------------------------------------------------- kanal
    def setActiveChannel(self, key: str) -> None:  # noqa: N802
        if key not in self._values:
            return
        self._active = key
        for k, button in self._buttons.items():
            button.setChecked(k == key)  # type: ignore[attr-defined]
        self._suppress = True
        try:
            self.editor.setPoints(self._values[key])
        finally:
            self._suppress = False
        self._apply_channel_colour()
        self._refresh_button_marks()

    def activeChannel(self) -> str:  # noqa: N802
        return self._active

    def _apply_channel_colour(self) -> None:
        for key, _label, colour in self._channels:
            if key == self._active and colour:
                self.editor.setCurveColor(colour)
                return
        self.editor.setCurveColor(PALETTE.text_primary)

    def _refresh_button_marks(self) -> None:
        """Degistirilmis kanallari dugmede isaretle."""
        for key, label, _colour in self._channels:
            modified = not curves.is_identity(self._values[key])
            self._buttons[key].setText(  # type: ignore[attr-defined]
                f"{label} •" if modified else label
            )

    # ------------------------------------------------------------- degerler
    def values(self) -> dict[str, list[tuple[float, float]]]:
        out = {k: list(v) for k, v in self._values.items()}
        out[self._active] = self.editor.points()
        return out

    def setValues(self, values) -> None:  # noqa: ANN001, N802
        self._suppress = True
        try:
            for key in self._values:
                if key in values:
                    self._values[key] = curves.normalise_points(values[key])
            self.editor.setPoints(self._values[self._active])
        finally:
            self._suppress = False
        self._refresh_button_marks()

    def setHistogram(self, values) -> None:  # noqa: ANN001, N802
        self.editor.setHistogram(values)

    def isIdentity(self) -> bool:  # noqa: N802
        return all(curves.is_identity(v) for v in self.values().values())

    def resetAll(self) -> None:  # noqa: N802
        self._values = {k: list(curves.IDENTITY_CURVE) for k in self._values}
        self.setValues(self._values)
        self.curvesChanged.emit(self.values())
        self.editingFinished.emit(self.values())

    # -------------------------------------------------------------- olaylar
    def _on_changed(self, points: list) -> None:
        if self._suppress:
            return
        self._values[self._active] = list(points)
        self.curvesChanged.emit(self.values())

    def _on_finished(self, points: list) -> None:
        if self._suppress:
            return
        self._values[self._active] = list(points)
        self._refresh_button_marks()
        self.editingFinished.emit(self.values())

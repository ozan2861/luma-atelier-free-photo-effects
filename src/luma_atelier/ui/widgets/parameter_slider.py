"""Parametre kaydiricisi - etiket, yol, tutamak ve sayisal deger tek widget.

Neden ozel cizim
----------------
Qt'nin QSS kaydiricisinda `sub-page` groove yerine widget'in tum
yuksekligini kaplayarak kalin bir kutu gorunumu uretiyor. Bundan
bagimsiz olarak fotograf duzenleyicinin ihtiyaci olan davranislar
hazir kontrolde yok:

* Cift tiklama varsayilana doner.
* Cift yonlu parametrelerde (pozlama, kontrast) merkez isareti ve dolgu
  merkezden baslar.
* Shift ile ince ayar (1/5 hiz), Ctrl ile kaba ayar.
* Surukleme *tek* bir geri alma adimi uretir (yuzlerce degil).
* Sayiya tiklayip yazarak deger girme.
* Klavye: ok tuslari, Page Up/Down, Home/End.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QLineEdit, QSizePolicy, QWidget

from luma_atelier.ui.theme.tokens import METRICS, PALETTE, SPACE, TYPE

#: Shift basiliyken surukleme hizi carpani
FINE_FACTOR = 0.2
#: Ctrl basiliyken surukleme hizi carpani
COARSE_FACTOR = 3.0


@dataclass(frozen=True)
class SliderSpec:
    """Bir parametrenin kaydirici tanimi.

    Efekt semalari bu tanimi uretir; arayuz tarafinda elle sayi yazilmaz.
    """

    key: str
    label: str
    minimum: float
    maximum: float
    default: float = 0.0
    decimals: int = 2
    step: float = 0.01
    """Ok tuslarinin adim buyuklugu."""
    page_step: float = 0.1
    suffix: str = ""
    bipolar: bool | None = None
    """None ise minimum<0<maximum olmasindan otomatik cikarilir."""
    tooltip: str = ""

    @property
    def is_bipolar(self) -> bool:
        if self.bipolar is not None:
            return self.bipolar
        return self.minimum < 0.0 < self.maximum

    @property
    def span(self) -> float:
        return max(1e-9, self.maximum - self.minimum)

    def clamp(self, value: float) -> float:
        return min(self.maximum, max(self.minimum, value))

    def format(self, value: float) -> str:
        sign = "+" if self.is_bipolar and value > 0 else ""
        return f"{sign}{value:.{self.decimals}f}{self.suffix}"


class ParameterSlider(QWidget):
    """Tek satirlik parametre kontrolu.

    Sinyaller:
        valueChanged: her deger degisiminde (surukleme sirasinda dahil).
            Onizlemeyi tazelemek icin kullanilir.
        editingFinished: surukleme/duzenleme bittiginde bir kez.
            Geri alma adimi bu sinyalde kaydedilir; slider surukleyisi
            yuzlerce gecmis adimina donusmez.
    """

    valueChanged = Signal(float)
    editingFinished = Signal(float)

    def __init__(self, spec: SliderSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._value = spec.clamp(spec.default)
        self._hovered = False
        self._pressed = False
        self._drag_origin = 0.0
        self._drag_start_value = 0.0
        self._editor: QLineEdit | None = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(38)
        self.setMaximumHeight(38)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.setAccessibleName(spec.label)
        self._update_accessible_value()

    # ------------------------------------------------------------------ deger
    @property
    def spec(self) -> SliderSpec:
        return self._spec

    def value(self) -> float:
        return self._value

    def setValue(self, value: float, *, notify: bool = True) -> None:  # noqa: N802
        new = self._spec.clamp(float(value))
        if abs(new - self._value) < 1e-9:
            return
        self._value = new
        self._update_accessible_value()
        self.update()
        if notify:
            self.valueChanged.emit(new)

    def reset(self) -> None:
        """Varsayilana dondurur ve tek bir duzenleme adimi bildirir."""
        if abs(self._value - self._spec.default) < 1e-9:
            return
        self.setValue(self._spec.default)
        self.editingFinished.emit(self._value)

    def isModified(self) -> bool:  # noqa: N802
        return abs(self._value - self._spec.default) > 1e-9

    def _update_accessible_value(self) -> None:
        self.setAccessibleDescription(
            f"{self._spec.label}: {self._spec.format(self._value)}"
        )

    # --------------------------------------------------------------- yerlesim
    def _label_width(self) -> int:
        """Etiket sutunu genisligi.

        Dar panelde (sag panel ~312 px) sabit genislik yola cok az yer
        birakiyordu. Genislik hem metne hem de widget'in kendi
        genisliginin bir oranina gore sinirlanir; boylece yol her zaman
        kullanilabilir uzunlukta kalir.
        """
        fm = QFontMetrics(self._label_font())
        needed = fm.horizontalAdvance(self._spec.label) + SPACE.sm
        cap = max(52, int(self.width() * 0.30))
        return max(48, min(cap, needed))

    def _readout_width(self) -> int:
        fm = QFontMetrics(self._readout_font())
        widest = max(
            fm.horizontalAdvance(self._spec.format(self._spec.minimum)),
            fm.horizontalAdvance(self._spec.format(self._spec.maximum)),
        )
        return widest + SPACE.sm

    def _track_rect(self) -> QRectF:
        left = self._label_width() + SPACE.md
        right = self.width() - self._readout_width() - SPACE.md
        cy = self.height() / 2.0
        h = float(METRICS.slider_track)
        return QRectF(left, cy - h / 2.0, max(24.0, right - left), h)

    def _readout_rect(self) -> QRectF:
        w = self._readout_width()
        return QRectF(self.width() - w, 0, w, self.height())

    def _handle_x(self) -> float:
        track = self._track_rect()
        t = (self._value - self._spec.minimum) / self._spec.span
        return track.left() + t * track.width()

    @staticmethod
    def _label_font() -> QFont:
        f = QFont()
        f.setPixelSize(TYPE.size_label)
        return f

    @staticmethod
    def _readout_font() -> QFont:
        f = QFont("Cascadia Mono")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPixelSize(TYPE.size_label)
        return f

    # ----------------------------------------------------------------- cizim
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = self._track_rect()
        radius = track.height() / 2.0
        hx = self._handle_x()
        cy = track.center().y()

        # Etiket
        p.setFont(self._label_font())
        p.setPen(QColor(PALETTE.text_primary if self._hovered or self.hasFocus()
                        else PALETTE.text_secondary))
        label_rect = QRectF(0, 0, self._label_width(), self.height())
        elided = QFontMetrics(self._label_font()).elidedText(
            self._spec.label, Qt.TextElideMode.ElideRight,
            int(label_rect.width()),
        )
        p.drawText(
            label_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided,
        )

        # Bos yol - panel zemininden acikca ayrilmali
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.track_empty if self.isEnabled()
                          else PALETTE.track_empty_disabled))
        p.drawRoundedRect(track, radius, radius)

        # Dolu kisim: cift yonlu parametrede merkezden, tek yonlude soldan
        if self._spec.is_bipolar:
            zero_t = (0.0 - self._spec.minimum) / self._spec.span
            zx = track.left() + zero_t * track.width()
            fill = QRectF(min(zx, hx), track.top(), abs(hx - zx), track.height())
        else:
            fill = QRectF(track.left(), track.top(), hx - track.left(), track.height())
        if fill.width() > 0.5:
            p.setBrush(QColor(PALETTE.accent if self.isModified()
                              else PALETTE.text_muted))
            p.drawRoundedRect(fill, radius, radius)

        # Cift yonlu parametrede merkez isareti - "sifir nerede" belli olsun
        if self._spec.is_bipolar:
            zero_t = (0.0 - self._spec.minimum) / self._spec.span
            zx = track.left() + zero_t * track.width()
            p.setPen(QPen(QColor(PALETTE.text_disabled), 1.0))
            p.drawLine(QPointF(zx, cy - 6.0), QPointF(zx, cy + 6.0))

        # Tutamak
        r = METRICS.slider_handle / 2.0
        if self._pressed:
            handle_color = PALETTE.accent
        elif self._hovered:
            handle_color = PALETTE.accent_hover
        else:
            handle_color = PALETTE.text_primary
        if self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE.accent))
            p.drawEllipse(QPointF(hx, cy), r + 3.0, r + 3.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(handle_color))
        p.drawEllipse(QPointF(hx, cy), r, r)

        # Sayisal deger
        if self._editor is None:
            p.setFont(self._readout_font())
            p.setPen(QColor(PALETTE.accent_hover if self.isModified()
                            else PALETTE.text_muted))
            p.drawText(
                self._readout_rect(),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self._spec.format(self._value),
            )
        p.end()

    # ----------------------------------------------------------------- fare
    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self._readout_rect().contains(event.position()):
            self._open_editor()
            return
        self._pressed = True
        self._drag_origin = event.position().x()
        self._drag_start_value = self._value
        # Yola tiklandiginda tutamak oraya atlar
        if abs(event.position().x() - self._handle_x()) > METRICS.slider_handle:
            self.setValue(self._value_at(event.position().x()))
            self._drag_start_value = self._value
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._pressed:
            return
        mods = event.modifiers()
        factor = 1.0
        if mods & Qt.KeyboardModifier.ShiftModifier:
            factor = FINE_FACTOR
        elif mods & Qt.KeyboardModifier.ControlModifier:
            factor = COARSE_FACTOR
        track = self._track_rect()
        delta_px = event.position().x() - self._drag_origin
        delta = delta_px / max(1.0, track.width()) * self._spec.span * factor
        self.setValue(self._drag_start_value + delta)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._pressed:
            return
        self._pressed = False
        self.update()
        # Tek geri alma adimi: surukleme bittiginde bir kez bildirilir
        self.editingFinished.emit(self._value)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Cift tiklama varsayilana dondurur."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.reset()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not (self._hovered or self.hasFocus()):
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        factor = FINE_FACTOR if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        self.setValue(self._value + steps * self._spec.step * 10.0 * factor)
        self.editingFinished.emit(self._value)
        event.accept()

    def _value_at(self, x: float) -> float:
        track = self._track_rect()
        t = (x - track.left()) / max(1.0, track.width())
        return self._spec.minimum + t * self._spec.span

    # --------------------------------------------------------------- klavye
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        step = self._spec.step * (FINE_FACTOR if fine else 1.0)
        handled = True
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self.setValue(self._value - step)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self.setValue(self._value + step)
        elif key == Qt.Key.Key_PageDown:
            self.setValue(self._value - self._spec.page_step)
        elif key == Qt.Key.Key_PageUp:
            self.setValue(self._value + self._spec.page_step)
        elif key == Qt.Key.Key_Home:
            self.setValue(self._spec.minimum)
        elif key == Qt.Key.Key_End:
            self.setValue(self._spec.maximum)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.reset()
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2):
            self._open_editor()
            return
        else:
            handled = False

        if handled:
            self.editingFinished.emit(self._value)
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------- sayisal giris
    def _open_editor(self) -> None:
        """Sayinin uzerine tiklayinca deger yazmaya izin verir."""
        if self._editor is not None:
            return
        rect = self._readout_rect().toRect()
        rect.adjust(-SPACE.lg, 4, 0, -4)
        editor = QLineEdit(self)
        editor.setGeometry(rect)
        editor.setText(f"{self._value:.{self._spec.decimals}f}")
        editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        editor.selectAll()
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        editor.editingFinished.connect(self._commit_editor)
        editor.show()
        self._editor = editor
        self.update()

    def _commit_editor(self) -> None:
        editor, self._editor = self._editor, None
        if editor is None:
            return
        text = editor.text().strip().replace(",", ".")
        editor.deleteLater()
        try:
            self.setValue(float(text))
        except ValueError:
            pass  # gecersiz giris sessizce yok sayilir, deger korunur
        self.editingFinished.emit(self._value)
        self.update()

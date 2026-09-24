"""Ayar paneli: bir islemin parametrelerini kaydiriciya donusturur.

Panel, `ParamSpec` semasindan *otomatik* uretilir. Yeni bir islem
eklemek icin arayuz kodu yazmak gerekmez; sema yeterlidir. Bu, 35+
islem ve 120 preset hedefinde tutarliligi garanti eder.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.imaging.effects.base import Operation, ParamKind, ParamSpec
from luma_atelier.ui.theme.tokens import PALETTE, SPACE, TYPE
from luma_atelier.ui.widgets.color_wheel import ColorWheel
from luma_atelier.ui.widgets.curve_editor import (
    CurveEditor,
    MultiCurveEditor,
)
from luma_atelier.ui.widgets.parameter_slider import ParameterSlider, SliderSpec

log = logging.getLogger(__name__)


def slider_spec_from(spec: ParamSpec) -> SliderSpec:
    """ParamSpec -> SliderSpec. Tek donusum noktasi."""
    return SliderSpec(
        key=spec.key, label=spec.label,
        minimum=float(spec.minimum), maximum=float(spec.maximum),
        default=float(spec.default), decimals=spec.decimals,
        step=float(spec.step), page_step=float(spec.page_step),
        suffix=spec.suffix, bipolar=spec.bipolar, tooltip=spec.tooltip,
    )


class CollapsibleSection(QWidget):
    """Basligi tiklanabilir, daraltilabilir bolum.

    Paneller daraltilabilir olmali (1366x768'de hepsi ayni anda sigmaz).
    """

    toggled = Signal(bool)

    def __init__(self, title: str, *, expanded: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = expanded

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = QPushButton(title)
        self._header.setObjectName("SectionHeader")
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"QPushButton#SectionHeader {{"
            f" background: transparent; border: none; text-align: left;"
            f" padding: {SPACE.sm}px {SPACE.xs}px;"
            f" color: {PALETTE.text_muted}; font-size: {TYPE.size_caption}px;"
            f" font-weight: {TYPE.weight_semibold}; letter-spacing: 0.7px; }}"
            f"QPushButton#SectionHeader:hover {{ color: {PALETTE.text_primary}; }}"
            f"QPushButton#SectionHeader:checked {{ color: {PALETTE.text_secondary}; }}"
        )
        self._header.clicked.connect(self._on_header)
        root.addWidget(self._header)

        self.body = QWidget()
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, SPACE.sm)
        self._body_layout.setSpacing(SPACE.xxs)
        root.addWidget(self.body)
        self.body.setVisible(expanded)
        self._update_title(title)

    def _update_title(self, base: str) -> None:
        self._base_title = base
        arrow = "▾" if self._expanded else "▸"
        self._header.setText(f"{arrow}  {base.upper()}")

    def _on_header(self) -> None:
        self.setExpanded(not self._expanded)

    def setExpanded(self, value: bool) -> None:  # noqa: N802
        self._expanded = value
        self._header.setChecked(value)
        self.body.setVisible(value)
        self._update_title(self._base_title)
        self.toggled.emit(value)

    def isExpanded(self) -> bool:  # noqa: N802
        return self._expanded

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        self._body_layout.addWidget(widget)

    def addLayout(self, layout) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._body_layout.addLayout(layout)


class OperationControls(QWidget):
    """Tek bir islemin tum parametre kontrolleri.

    Sinyaller:
        valueChanged(op_id, params): her degisimde (onizleme icin)
        editingFinished(op_id, params): etkilesim bittiginde (gecmis icin)
        resetRequested(op_id)
    """

    valueChanged = Signal(str, dict)
    editingFinished = Signal(str, dict)
    resetRequested = Signal(str)

    def __init__(self, operation: Operation, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._op = operation
        self._sliders: dict[str, ParameterSlider] = {}
        self._checks: dict[str, QCheckBox] = {}
        self._combos: dict[str, QComboBox] = {}
        self._curves: dict[str, CurveEditor] = {}
        self._curve_group: MultiCurveEditor | None = None
        self._wheels: dict[str, ColorWheel] = {}
        self._suppress = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE.xxs)

        # Tek parametreli islemlerde ayri baslik gosterilmez: "Pozlama"
        # basligi + "Pozlama" kaydirici etiketi ayni adi iki kez yazip
        # dar panelde bosa yer harciyordu. Bu durumda kaydirici kendi
        # adini tasir; sifirlama cift tiklama ile yapilir (ipucunda yazar).
        self._compact = (len(operation.params) == 1
                         and operation.params[0].kind not in
                         (ParamKind.CURVE, ParamKind.COLOR))

        self._reset_button = QToolButton()
        self._reset_button.setText("Sıfırla")
        self._reset_button.setToolTip(
            f"{operation.name} ayarlarını varsayılana döndürür"
        )
        self._reset_button.setEnabled(False)
        self._reset_button.clicked.connect(
            lambda: self.resetRequested.emit(self._op.op_id)
        )

        if not self._compact:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            title = QLabel(operation.name)
            title.setObjectName("PanelHeading")
            title.setToolTip(operation.description)
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(self._reset_button)
            root.addLayout(header)
        else:
            self._reset_button.setVisible(False)

        curve_specs = [sp for sp in operation.params
                       if sp.kind is ParamKind.CURVE]
        if len(curve_specs) > 1:
            # Dort egriyi alt alta koymak dar panelde ~800 px yer
            # kapliyordu; kanal secicili tek editor kullanilir.
            channel_colours = {
                "red": PALETTE.hist_red, "green": PALETTE.hist_green,
                "blue": PALETTE.hist_blue,
            }
            self._curve_group = MultiCurveEditor(tuple(
                (sp.key, _short_channel_label(sp.label),
                 channel_colours.get(sp.key, PALETTE.text_primary))
                for sp in curve_specs
            ))
            self._curve_group.setValues(
                {sp.key: sp.default for sp in curve_specs}
            )
            self._curve_group.curvesChanged.connect(
                lambda _v: self._emit(self.valueChanged))
            self._curve_group.editingFinished.connect(
                lambda _v: self._emit(self.editingFinished))
            root.addWidget(self._curve_group)

        for spec in operation.params:
            if len(curve_specs) > 1 and spec.kind is ParamKind.CURVE:
                continue
            widget = self._build_control(spec)
            if widget is None:
                continue
            if self._compact and isinstance(widget, ParameterSlider):
                widget.setToolTip(
                    f"{operation.description}\n\n"
                    "Çift tıklama varsayılana döndürür."
                )
            root.addWidget(widget)

    # ------------------------------------------------------------ kontrol
    def _build_control(self, spec: ParamSpec) -> QWidget | None:
        if spec.kind in (ParamKind.SCALAR, ParamKind.PIXELS,
                         ParamKind.NORMALISED, ParamKind.ANGLE, ParamKind.SEED):
            sl_spec = slider_spec_from(spec)
            if self._compact and spec.label != self._op.name:
                # Tek parametreli islemde kaydirici islemin adini tasir
                sl_spec = replace(sl_spec, label=self._op.name)
            slider = ParameterSlider(sl_spec)
            slider.valueChanged.connect(
                lambda _v, k=spec.key: self._emit(self.valueChanged)
            )
            slider.editingFinished.connect(
                lambda _v, k=spec.key: self._emit(self.editingFinished)
            )
            self._sliders[spec.key] = slider
            return slider

        if spec.kind is ParamKind.BOOLEAN:
            check = QCheckBox(spec.label)
            check.setChecked(bool(spec.default))
            if spec.tooltip:
                check.setToolTip(spec.tooltip)
            check.toggled.connect(lambda _v: self._emit(self.editingFinished))
            self._checks[spec.key] = check
            return check

        if spec.kind is ParamKind.CHOICE and spec.choices:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(SPACE.sm)
            label = QLabel(spec.label)
            label.setMinimumWidth(80)
            combo = QComboBox()
            for text, value in spec.choices:
                combo.addItem(text, value)
            idx = combo.findData(spec.default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            if spec.tooltip:
                combo.setToolTip(spec.tooltip)
            combo.currentIndexChanged.connect(
                lambda _i: self._emit(self.editingFinished)
            )
            self._combos[spec.key] = combo
            lay.addWidget(label)
            lay.addWidget(combo, 1)
            return row

        if spec.kind is ParamKind.CURVE:
            editor = CurveEditor()
            editor.setPoints(spec.default)
            if spec.tooltip:
                editor.setToolTip(spec.tooltip + chr(10)*2 + editor.toolTip())
            # Kanal egrilerini kendi renginde goster
            channel_colour = {
                "red": PALETTE.hist_red, "green": PALETTE.hist_green,
                "blue": PALETTE.hist_blue,
            }.get(spec.key)
            if channel_colour:
                editor.setCurveColor(channel_colour)
            editor.curveChanged.connect(lambda _pts: self._emit(self.valueChanged))
            editor.editingFinished.connect(
                lambda _pts: self._emit(self.editingFinished)
            )
            self._curves[spec.key] = editor
            return self._labelled(spec.label, editor, stacked=True)

        if spec.kind is ParamKind.COLOR:
            wheel = ColorWheel(spec.label)
            wheel.setColor(spec.default)
            if spec.tooltip:
                wheel.setToolTip(spec.tooltip)
            wheel.colorChanged.connect(lambda _c: self._emit(self.valueChanged))
            wheel.editingFinished.connect(
                lambda _c: self._emit(self.editingFinished)
            )
            self._wheels[spec.key] = wheel
            return wheel

        log.debug("%s.%s: %s turu icin kontrol yok",
                  self._op.op_id, spec.key, spec.kind.value)
        return None

    @staticmethod
    def _labelled(label: str, widget: QWidget, *,
                  stacked: bool = False) -> QWidget:
        """Kontrolu etiketiyle sarar."""
        box = QWidget()
        lay = QVBoxLayout(box) if stacked else QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE.xxs)
        text = QLabel(label)
        text.setObjectName("Muted")
        lay.addWidget(text)
        lay.addWidget(widget)
        return box

    # -------------------------------------------------------------- deger
    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, slider in self._sliders.items():
            spec = self._op.param(key)
            value = slider.value()
            out[key] = int(round(value)) if spec and spec.kind is ParamKind.SEED \
                else value
        for key, check in self._checks.items():
            out[key] = check.isChecked()
        for key, combo in self._combos.items():
            out[key] = combo.currentData()
        for key, editor in self._curves.items():
            out[key] = editor.points()
        if self._curve_group is not None:
            out.update(self._curve_group.values())
        for key, wheel in self._wheels.items():
            out[key] = wheel.color()
        return out

    def setValues(self, params: dict[str, Any]) -> None:  # noqa: N802
        """Kontrolleri tarifteki degerlere esitler (sinyal yaymadan)."""
        self._suppress = True
        try:
            for key, slider in self._sliders.items():
                if key in params:
                    slider.setValue(float(params[key]), notify=False)
            for key, check in self._checks.items():
                if key in params:
                    check.setChecked(bool(params[key]))
            for key, combo in self._combos.items():
                if key in params:
                    idx = combo.findData(params[key])
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
            for key, editor in self._curves.items():
                if key in params:
                    editor.setPoints(params[key])
            if self._curve_group is not None:
                self._curve_group.setValues(params)
            for key, wheel in self._wheels.items():
                if key in params:
                    wheel.setColor(params[key])
        finally:
            self._suppress = False
        self._refresh_reset_state()

    def resetControls(self) -> None:  # noqa: N802
        self.setValues(self._op.defaults())

    def curve_editor(self, key: str) -> CurveEditor | None:
        return self._curves.get(key)

    def isModified(self) -> bool:  # noqa: N802
        return (any(s.isModified() for s in self._sliders.values())
                or any(not c.isIdentity() for c in self._curves.values())
                or (self._curve_group is not None
                    and not self._curve_group.isIdentity())
                or any(not w.isNeutral() for w in self._wheels.values()))

    def _refresh_reset_state(self) -> None:
        self._reset_button.setEnabled(self.isModified())

    def _emit(self, signal: Signal) -> None:
        if self._suppress:
            return
        self._refresh_reset_state()
        signal.emit(self._op.op_id, self.values())


def _short_channel_label(label: str) -> str:
    """'RGB egrisi' -> 'RGB', 'Kirmizi egrisi' -> 'Kirmizi'."""
    return label.replace(" eğrisi", "").strip() or label


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return line

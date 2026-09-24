"""Kadraj paneli: kirpma orani, dondurme, cevirme, ufuk duzeltme.

Panel yalnizca istenen `Geometry`'yi yayar. Maskelerin yeni kadraja
tasinmasi `Document.set_geometry` icinde yapilir; boylece kirpma ile
maske donusumu asla ayrisamaz.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.imaging.geometry import ASPECT_PRESETS, Geometry, fit_crop_to_aspect
from luma_atelier.ui.widgets.parameter_slider import ParameterSlider, SliderSpec

STRAIGHTEN = SliderSpec(
    key="straighten", label="Ufuk", minimum=-45.0, maximum=45.0, default=0.0,
    decimals=1, step=0.1, page_step=1.0, suffix="°",
    tooltip="Serbest açıda döndürür; boş köşeler otomatik kırpılır",
)


class CropPanel(QWidget):
    """Kirpma ve yonelim kontrolleri."""

    #: (geometri, etiket, birlestirme anahtari)
    geometryChanged = Signal(object, str, str)
    editingFinished = Signal()
    #: Kirpma araci acilsin/kapansin
    cropToolToggled = Signal(bool)
    #: Ucte bir rehberleri
    guidesToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CropPanel")
        self._geometry = Geometry()
        self._image_aspect = 1.0
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self._crop_toggle = QPushButton("Kırpma aracı")
        self._crop_toggle.setCheckable(True)
        self._crop_toggle.setToolTip(
            "Fotoğrafın üzerinde kırpma çerçevesini düzenler")
        self._crop_toggle.toggled.connect(self.cropToolToggled)
        root.addWidget(self._crop_toggle)

        root.addWidget(self._build_aspects())
        root.addWidget(self._build_orientation())

        self._straighten = ParameterSlider(STRAIGHTEN)
        self._straighten.valueChanged.connect(self._on_straighten)
        self._straighten.editingFinished.connect(
            lambda _v: self.editingFinished.emit())
        root.addWidget(self._straighten)

        self._guides = QCheckBox("Üçte bir rehberleri")
        self._guides.setChecked(True)
        self._guides.toggled.connect(self.guidesToggled)
        root.addWidget(self._guides)

        self._size_label = QLabel("")
        self._size_label.setObjectName("Muted")
        root.addWidget(self._size_label)

        reset = QPushButton("Kadrajı sıfırla")
        reset.clicked.connect(self._on_reset)
        root.addWidget(reset)
        root.addStretch(1)

    # ------------------------------------------------------------ yapilar
    def _build_aspects(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("EN-BOY ORANI")
        title.setObjectName("Overline")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(4)
        self._aspect_buttons: list[QPushButton] = []
        for i, (label, value) in enumerate(ASPECT_PRESETS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("aspectValue", value)
            button.clicked.connect(
                lambda _c=False, v=value: self._on_aspect(v))
            grid.addWidget(button, i // 3, i % 3)
            self._aspect_buttons.append(button)
        layout.addLayout(grid)
        return box

    def _build_orientation(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("YÖNELİM")
        title.setObjectName("Overline")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(4)
        actions = (
            ("↺ 90°", lambda: self._rotate(-90), "Sola 90° döndür"),
            ("↻ 90°", lambda: self._rotate(90), "Sağa 90° döndür"),
            ("⇆", lambda: self._flip(horizontal=True), "Yatay çevir"),
            ("⇅", lambda: self._flip(horizontal=False), "Dikey çevir"),
        )
        for text, handler, tip in actions:
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        return box

    # --------------------------------------------------------- doldurma
    def setGeometry(self, geometry: Geometry,  # type: ignore[override]  # noqa: N802
                    source_size: tuple[int, int]) -> None:
        """Paneli belgedeki kadrajla esitler.

        `QWidget.setGeometry` ile ayni ada sahip; bu panelde kasitli olarak
        golgelenir cunku panel bir kadraj editorudur ve konumu yerlesim
        yoneticisi belirler.
        """
        self._geometry = geometry
        width, height = source_size
        self._image_aspect = width / max(1, height)

        self._syncing = True
        self._straighten.setValue(geometry.straighten, notify=False)
        for button in self._aspect_buttons:
            value = button.property("aspectValue")
            button.setChecked(_same_aspect(value, geometry.aspect))
        self._syncing = False

        out_w, out_h = geometry.output_size(width, height)
        pixels = out_w * out_h / 1e6
        self._size_label.setText(f"Çıktı: {out_w} × {out_h} ({pixels:.1f} MP)")

    def setCropToolActive(self, active: bool) -> None:  # noqa: N802
        if self._crop_toggle.isChecked() != active:
            self._crop_toggle.setChecked(active)

    def geometryValue(self) -> Geometry:  # noqa: N802
        return self._geometry

    # ------------------------------------------------------------ olaylar
    def _on_aspect(self, value: float | None) -> None:
        if self._syncing:
            return
        from dataclasses import replace

        if value is None:
            geometry = replace(self._geometry, aspect=None)
        else:
            aspect = self._image_aspect if value == 0.0 else value
            crop = fit_crop_to_aspect(self._geometry.crop, aspect,
                                      self._image_aspect)
            geometry = replace(self._geometry, crop=crop, aspect=aspect)
        self._emit(geometry, "En-boy oranı")

    def _rotate(self, degrees: int) -> None:
        self._emit(self._geometry.rotated(degrees), "Döndürüldü")

    def _flip(self, *, horizontal: bool) -> None:
        from dataclasses import replace

        geometry = (replace(self._geometry, flip_h=not self._geometry.flip_h)
                    if horizontal
                    else replace(self._geometry, flip_v=not self._geometry.flip_v))
        self._emit(geometry, "Çevrildi")

    def _on_straighten(self, value: float) -> None:
        if self._syncing:
            return
        from dataclasses import replace

        self._emit(replace(self._geometry, straighten=value),
                   "Ufuk düzeltildi", merge_key="geometry:straighten")

    def _on_reset(self) -> None:
        self._emit(Geometry(), "Kadraj sıfırlandı")

    def _emit(self, geometry: Geometry, label: str,
              merge_key: str = "") -> None:
        self._geometry = geometry
        self.geometryChanged.emit(geometry, label, merge_key)


def _same_aspect(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if a == 0.0:
        return False        # "Orijinal" dugmesi cozunurlukten turetilir
    return abs(a - b) < 1e-4

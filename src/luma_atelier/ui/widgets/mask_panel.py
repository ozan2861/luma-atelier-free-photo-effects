"""Maske paneli: maske listesi, bilesenler ve parametreleri.

Model
-----
Bir *maske* (`MaskStack`) birden fazla *bilesenden* (`Mask`) olusur.
Bilesenler sirayla birlestirilir: "Ekle" birlesim, "Cikar" fark. Boylece
"gokyuzu radyal, ama agaclar haric" gibi maskeler kurulabilir.

Panel yalnizca sinyal yayar; belgeyi degistirmez. Belge islemleri
`EditorView` tarafindan yapilir; boylece geri alma tek noktadan yonetilir.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.imaging.masks import BlendOp, Mask, MaskKind, MaskStack
from luma_atelier.ui.widgets.canvas_tools import CanvasTool
from luma_atelier.ui.widgets.parameter_slider import ParameterSlider, SliderSpec

log = logging.getLogger(__name__)

#: Maske turu -> tuvalde kullanilacak arac
TOOL_FOR_KIND: dict[MaskKind, CanvasTool] = {
    MaskKind.BRUSH: CanvasTool.BRUSH,
    MaskKind.LINEAR: CanvasTool.LINEAR,
    MaskKind.RADIAL: CanvasTool.RADIAL,
    MaskKind.LUMINANCE: CanvasTool.NONE,
    MaskKind.COLOR_RANGE: CanvasTool.NONE,
}

#: Tum bilesenlerde ortak kaydiricilar
COMMON_SLIDERS: tuple[SliderSpec, ...] = (
    SliderSpec(key="feather", label="Yumuşatma", minimum=0.0, maximum=0.30,
               default=0.02, decimals=3, step=0.002, page_step=0.02,
               tooltip="Maske kenarının geçiş genişliği"),
    SliderSpec(key="opacity", label="Yoğunluk", minimum=0.0, maximum=1.0,
               default=1.0, decimals=2, step=0.01, page_step=0.1),
)

#: Tur bazli ek kaydiricilar
KIND_SLIDERS: dict[MaskKind, tuple[SliderSpec, ...]] = {
    MaskKind.LUMINANCE: (
        SliderSpec(key="luma_low", label="Alt sınır", minimum=0.0, maximum=1.0,
                   default=0.0, decimals=2, step=0.01, page_step=0.1),
        SliderSpec(key="luma_high", label="Üst sınır", minimum=0.0, maximum=1.0,
                   default=1.0, decimals=2, step=0.01, page_step=0.1),
        SliderSpec(key="luma_softness", label="Geçiş", minimum=0.0,
                   maximum=0.5, default=0.15, decimals=2, step=0.01,
                   page_step=0.05),
    ),
    MaskKind.COLOR_RANGE: (
        SliderSpec(key="hue_tolerance", label="Renk toleransı", minimum=1.0,
                   maximum=120.0, default=30.0, decimals=0, step=1.0,
                   page_step=10.0, suffix="°"),
        SliderSpec(key="sat_tolerance", label="Doygunluk tol.", minimum=0.02,
                   maximum=1.0, default=0.45, decimals=2, step=0.01,
                   page_step=0.1),
    ),
    MaskKind.RADIAL: (
        SliderSpec(key="angle", label="Açı", minimum=-90.0, maximum=90.0,
                   default=0.0, decimals=0, step=1.0, page_step=10.0,
                   suffix="°"),
    ),
}


class MaskPanel(QWidget):
    """Maskeleri olusturma ve duzenleme paneli."""

    #: (tur)
    maskCreateRequested = Signal(object)
    #: (mask_id)
    maskDeleteRequested = Signal(str)
    #: (mask_id)
    maskSelected = Signal(str)
    #: (mask_id, tur, karisim)
    componentAddRequested = Signal(str, object, object)
    #: (mask_id, sira)
    componentRemoveRequested = Signal(str, int)
    #: (mask_id, sira)
    componentSelected = Signal(str, int)
    #: (mask_id, sira, bilesen, etiket, birlestirme anahtari)
    componentChanged = Signal(str, int, object, str, str)
    #: Kaydirici birakildi - gecmis adimini muhurle
    editingFinished = Signal()
    #: (arac)
    toolRequested = Signal(object)
    #: (goster)
    showMaskToggled = Signal(bool)
    #: (mask_id veya "")
    layerAssignRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MaskPanel")
        self._masks: dict[str, MaskStack] = {}
        self._mask_id = ""
        self._index = 0
        self._syncing = False
        self._sliders: dict[str, ParameterSlider] = {}
        self._selected_layer = ""
        self._layer_mask = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self._build_mask_list())
        root.addWidget(self._build_components())
        self._params_host = QWidget()
        self._params_layout = QVBoxLayout(self._params_host)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self._params_layout.setSpacing(6)
        root.addWidget(self._params_host)
        root.addWidget(self._build_footer())
        root.addStretch(1)

        self._refresh_enabled()

    # ------------------------------------------------------------ yapilar
    def _build_mask_list(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("MASKELER")
        title.setObjectName("Overline")
        header.addWidget(title)
        header.addStretch(1)

        add = QToolButton()
        add.setText("+ Maske")
        add.setToolTip("Yeni maske ekle")
        add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(add)
        for kind in MaskKind:
            action = menu.addAction(kind.label)
            action.triggered.connect(
                lambda _checked=False, k=kind: self.maskCreateRequested.emit(k))
        add.setMenu(menu)
        header.addWidget(add)

        self._delete_btn = QToolButton()
        self._delete_btn.setText("Sil")
        self._delete_btn.setToolTip("Seçili maskeyi sil")
        self._delete_btn.clicked.connect(
            lambda: self._mask_id and self.maskDeleteRequested.emit(self._mask_id))
        header.addWidget(self._delete_btn)
        layout.addLayout(header)

        self._mask_list = QListWidget()
        self._mask_list.setObjectName("MaskList")
        self._mask_list.setMaximumHeight(96)
        self._mask_list.currentItemChanged.connect(self._on_mask_row)
        layout.addWidget(self._mask_list)

        self._empty = QLabel("Henüz maske yok. Efekti fotoğrafın yalnızca bir "
                             "bölümüne uygulamak için maske ekleyin.")
        self._empty.setObjectName("Muted")
        self._empty.setWordWrap(True)
        layout.addWidget(self._empty)
        return box

    def _build_components(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("BİLEŞENLER")
        title.setObjectName("Overline")
        header.addWidget(title)
        header.addStretch(1)

        for text, blend, tip in (
            ("+ Ekle", BlendOp.ADD, "Maskeye alan ekleyen bileşen"),
            ("− Çıkar", BlendOp.SUBTRACT, "Maskeden alan çıkaran bileşen"),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            for kind in MaskKind:
                action = menu.addAction(kind.label)
                action.triggered.connect(
                    lambda _c=False, k=kind, b=blend:
                    self._mask_id and self.componentAddRequested.emit(
                        self._mask_id, k, b))
            button.setMenu(menu)
            header.addWidget(button)
            setattr(self, f"_add_{blend.value}", button)

        self._component_remove = QToolButton()
        self._component_remove.setText("Sil")
        self._component_remove.clicked.connect(
            lambda: self._mask_id and self.componentRemoveRequested.emit(
                self._mask_id, self._index))
        header.addWidget(self._component_remove)
        layout.addLayout(header)

        self._component_list = QListWidget()
        self._component_list.setObjectName("MaskComponentList")
        self._component_list.setMaximumHeight(92)
        self._component_list.currentRowChanged.connect(self._on_component_row)
        layout.addWidget(self._component_list)
        return box

    def _build_footer(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._show_mask = QCheckBox("Maskeyi göster (M)")
        self._show_mask.setToolTip(
            "Maskeyi kırmızı örtü olarak gösterir. Çıktıyı etkilemez.")
        self._show_mask.toggled.connect(self.showMaskToggled)
        layout.addWidget(self._show_mask)

        row = QHBoxLayout()
        label = QLabel("Seçili katmanın maskesi")
        label.setObjectName("Muted")
        layout.addWidget(label)

        self._assign = QComboBox()
        self._assign.setToolTip(
            "Efekt yığınında seçili katmanı bu maskeye bağlar")
        self._assign.currentIndexChanged.connect(self._on_assign_changed)
        row.addWidget(self._assign, 1)
        layout.addLayout(row)

        self._assign_hint = QLabel("")
        self._assign_hint.setObjectName("Muted")
        self._assign_hint.setWordWrap(True)
        layout.addWidget(self._assign_hint)
        return box

    # --------------------------------------------------------- doldurma
    def setMasks(self, masks: dict[str, MaskStack], *,  # noqa: N802
                 selected: str = "", index: int = 0) -> None:
        """Maske listesini belgeyle esitler."""
        self._masks = dict(masks)
        if selected and selected in masks:
            self._mask_id = selected
        elif self._mask_id not in masks:
            self._mask_id = next(iter(masks), "")
        self._index = index

        self._syncing = True
        self._mask_list.clear()
        for mask_id, stack in masks.items():
            kinds = ", ".join(m.kind.label for m in stack.masks[:2])
            more = f" +{len(stack.masks) - 2}" if len(stack.masks) > 2 else ""
            item = QListWidgetItem(f"{mask_id}  ·  {kinds}{more}")
            item.setData(Qt.ItemDataRole.UserRole, mask_id)
            self._mask_list.addItem(item)
            if mask_id == self._mask_id:
                self._mask_list.setCurrentItem(item)
        self._syncing = False

        self._empty.setVisible(not masks)
        self._mask_list.setVisible(bool(masks))
        self._refresh_components()
        self._refresh_assign()
        self._refresh_enabled()

    def setSelectedLayer(self, instance_id: str, mask_id: str) -> None:  # noqa: N802
        """Efekt yiginindaki secili katmani ve onun maskesini bildirir."""
        self._selected_layer = instance_id
        self._layer_mask = mask_id
        self._refresh_assign()

    def selectedMask(self) -> str:  # noqa: N802
        return self._mask_id

    def componentIndex(self) -> int:  # noqa: N802
        return self._index

    def selectMask(self, mask_id: str) -> None:  # noqa: N802
        """Maskeyi programatik olarak secer (listeye tiklamayla ayni yol)."""
        for row in range(self._mask_list.count()):
            item = self._mask_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == mask_id:
                self._mask_list.setCurrentItem(item)
                if self._mask_id != mask_id:
                    self._mask_id = mask_id
                    self._index = 0
                    self._refresh_components()
                    self._refresh_enabled()
                    self.maskSelected.emit(mask_id)
                return

    def selectComponent(self, index: int) -> None:  # noqa: N802
        """Bileseni programatik olarak secer.

        Sinyali dogrudan yaymak panelin ic durumunu guncellemez; disaridan
        secim yapmanin dogru yolu budur.
        """
        stack = self._masks.get(self._mask_id)
        if stack is None or not 0 <= index < len(stack.masks):
            return
        self._component_list.setCurrentRow(index)
        if self._index != index:
            self._index = index
            self._rebuild_params()
            self.componentSelected.emit(self._mask_id, index)

    def selectedComponent(self) -> Mask | None:  # noqa: N802
        stack = self._masks.get(self._mask_id)
        if stack is None or not 0 <= self._index < len(stack.masks):
            return None
        return stack.masks[self._index]

    def setShowMask(self, value: bool) -> None:  # noqa: N802
        if self._show_mask.isChecked() != value:
            self._show_mask.setChecked(value)

    # -------------------------------------------------------- ic guncelleme
    def _refresh_components(self) -> None:
        stack = self._masks.get(self._mask_id)
        self._syncing = True
        self._component_list.clear()
        if stack is not None:
            for i, component in enumerate(stack.masks):
                prefix = "＋" if component.blend is BlendOp.ADD else "−"
                state = "" if component.enabled else "  (kapalı)"
                inverted = "  ters" if component.inverted else ""
                self._component_list.addItem(
                    f"{prefix} {component.display_name}{inverted}{state}")
            self._index = max(0, min(self._index, len(stack.masks) - 1))
            self._component_list.setCurrentRow(self._index)
        self._syncing = False
        self._rebuild_params()

    def _rebuild_params(self) -> None:
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._sliders.clear()

        component = self.selectedComponent()
        if component is None:
            self._params_host.setVisible(False)
            return
        self._params_host.setVisible(True)

        row = QHBoxLayout()
        enabled = QCheckBox("Etkin")
        enabled.setChecked(component.enabled)
        enabled.toggled.connect(
            lambda v: self._emit_component(enabled=v, label="Maske etkin"))
        row.addWidget(enabled)

        inverted = QCheckBox("Ters çevir")
        inverted.setChecked(component.inverted)
        inverted.toggled.connect(
            lambda v: self._emit_component(inverted=v, label="Maske ters"))
        row.addWidget(inverted)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        self._params_layout.addWidget(holder)

        tool = TOOL_FOR_KIND.get(component.kind, CanvasTool.NONE)
        if tool is not CanvasTool.NONE:
            tools = QHBoxLayout()
            group = QButtonGroup(self)
            group.setExclusive(True)
            entries = [(tool.label, tool)]
            if component.kind is MaskKind.BRUSH:
                entries.append((CanvasTool.ERASER.label, CanvasTool.ERASER))
            for text, value in entries:
                button = QPushButton(text)
                button.setCheckable(True)
                button.clicked.connect(
                    lambda _c=False, t=value: self.toolRequested.emit(t))
                group.addButton(button)
                tools.addWidget(button)
            tools.addStretch(1)
            tool_host = QWidget()
            tool_host.setLayout(tools)
            self._params_layout.addWidget(tool_host)
            if component.kind is MaskKind.BRUSH:
                hint = QLabel("Fotoğrafın üzerine sürükleyerek boyayın. "
                              "Fırça boyutu: fare tekerleği.")
                hint.setObjectName("Muted")
                hint.setWordWrap(True)
                self._params_layout.addWidget(hint)

        specs = list(COMMON_SLIDERS) + list(KIND_SLIDERS.get(component.kind, ()))
        if component.kind is MaskKind.BRUSH:
            specs = [s for s in specs if s.key != "feather"]
        for spec in specs:
            slider = ParameterSlider(spec)
            slider.setValue(float(getattr(component, spec.key, spec.default)),
                            notify=False)
            slider.valueChanged.connect(
                lambda value, key=spec.key, name=spec.label:
                self._emit_component(label=f"Maske {name.lower()}",
                                     merge_key=f"mask:{key}", **{key: value}))
            slider.editingFinished.connect(
                lambda _v: self.editingFinished.emit())
            slider.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Fixed)
            self._params_layout.addWidget(slider)
            self._sliders[spec.key] = slider

    def _refresh_assign(self) -> None:
        self._syncing = True
        self._assign.clear()
        self._assign.addItem("Maskesiz (tüm fotoğraf)", "")
        for mask_id in self._masks:
            self._assign.addItem(mask_id, mask_id)
        wanted = self._assign.findData(self._layer_mask or "")
        self._assign.setCurrentIndex(max(0, wanted))
        self._syncing = False

        has_layer = bool(self._selected_layer)
        self._assign.setEnabled(has_layer and bool(self._masks))
        self._assign_hint.setText(
            "" if has_layer
            else "Bağlamak için önce efekt yığınından bir katman seçin.")

    def _refresh_enabled(self) -> None:
        has_mask = bool(self._mask_id)
        self._delete_btn.setEnabled(has_mask)
        self._component_remove.setEnabled(has_mask)
        for blend in BlendOp:
            button = getattr(self, f"_add_{blend.value}", None)
            if button is not None:
                button.setEnabled(has_mask)
        self._show_mask.setEnabled(has_mask)

    # ------------------------------------------------------------ olaylar
    def _on_mask_row(self, current: QListWidgetItem | None, _prev=None) -> None:  # noqa: ANN001
        if self._syncing or current is None:
            return
        mask_id = current.data(Qt.ItemDataRole.UserRole) or ""
        if mask_id == self._mask_id:
            return
        self._mask_id = mask_id
        self._index = 0
        self._refresh_components()
        self._refresh_enabled()
        self.maskSelected.emit(mask_id)

    def _on_component_row(self, row: int) -> None:
        if self._syncing or row < 0 or row == self._index:
            return
        self._index = row
        self._rebuild_params()
        self.componentSelected.emit(self._mask_id, row)

    def _on_assign_changed(self, _index: int) -> None:
        if self._syncing or not self._selected_layer:
            return
        self.layerAssignRequested.emit(self._assign.currentData() or "")

    def _emit_component(self, *, label: str = "Maske",
                        merge_key: str = "", **fields: object) -> None:
        component = self.selectedComponent()
        if component is None:
            return
        updated = replace(component, **fields)
        if updated == component:
            return
        self.componentChanged.emit(self._mask_id, self._index, updated,
                                   label, merge_key)

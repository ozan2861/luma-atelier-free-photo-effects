"""Efekt yigini paneli: sirali katmanlar, ac/kapat, yogunluk, kaldirma.

Sira **gercekten** sonucu degistirir; bu yuzden surukleyip birakarak
yeniden siralanabilir. Preset katmanlari ayri isaretlenir ki kullanici
hangi katmanin gorunumden, hangisinin kendi ayarindan geldigini gorsun.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.document import PRESET_GROUP
from luma_atelier.imaging.recipe import Layer, Recipe
from luma_atelier.ui.theme.tokens import PALETTE, SPACE, TYPE

log = logging.getLogger(__name__)


class LayerRow(QWidget):
    """Yigindaki tek bir katman satiri."""

    toggled = Signal(str, bool)
    removeRequested = Signal(str)
    selected = Signal(str)

    def __init__(self, layer: Layer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._instance_id = layer.instance_id

        lay = QHBoxLayout(self)
        lay.setContentsMargins(SPACE.sm, SPACE.xs, SPACE.sm, SPACE.xs)
        lay.setSpacing(SPACE.sm)

        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setChecked(layer.enabled)
        self.toggle.setText("●" if layer.enabled else "○")
        self.toggle.setToolTip("Katmanı aç / kapat")
        self.toggle.setFixedWidth(24)
        self.toggle.toggled.connect(self._on_toggled)

        name = QLabel(layer.display_name())
        name.setStyleSheet(
            f"color: {PALETTE.text_primary if layer.enabled else PALETTE.text_disabled};"
            f" font-size: {TYPE.size_label}px;"
        )

        source = QLabel("görünüm" if layer.group == PRESET_GROUP else "elle")
        source.setObjectName("Muted")
        source.setToolTip(
            "Bu katman seçili görünümden geliyor; başka bir görünüm "
            "secilince degisir."
            if layer.group == PRESET_GROUP else
            "Bu katmanı siz eklediniz; görünüm değişince korunur."
        )

        remove = QToolButton()
        remove.setText("✕")
        remove.setToolTip("Katmanı kaldır")
        remove.setFixedWidth(24)
        remove.clicked.connect(lambda: self.removeRequested.emit(self._instance_id))

        lay.addWidget(self.toggle)
        lay.addWidget(name, 1)
        lay.addWidget(source)
        lay.addWidget(remove)

    def _on_toggled(self, value: bool) -> None:
        self.toggle.setText("●" if value else "○")
        self.toggled.emit(self._instance_id, value)

    @property
    def instance_id(self) -> str:
        return self._instance_id


class EffectStackPanel(QWidget):
    """Tarifin katmanlarini gosteren ve duzenleyen panel.

    Sinyaller:
        layerToggled(instance_id, enabled)
        layerRemoved(instance_id)
        layerMoved(instance_id, new_index)
        layerSelected(instance_id)
    """

    layerToggled = Signal(str, bool)
    layerRemoved = Signal(str)
    layerMoved = Signal(str, int)
    layerSelected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EffectStackPanel")
        self._order: list[str] = []
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE.xs)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("EFEKT YIĞINI")
        title.setObjectName("Overline")
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        root.addLayout(header)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setToolTip(
            "Katmanları sürükleyerek sırayı değiştirin.\n"
            "Sıra sonucu gerçekten değiştirir."
        )
        self.list.setMaximumHeight(210)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.currentRowChanged.connect(self._on_row_selected)
        root.addWidget(self.list)

        self.empty_label = QLabel("Henüz efekt yok. Bir görünüm seçin veya "
                                  "ayar yapın.")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

    # ------------------------------------------------------------- tazeleme
    def setRecipe(self, recipe: Recipe | None) -> None:  # noqa: N802
        self._syncing = True
        try:
            self.list.clear()
            self._order = []
            layers = list(recipe.layers) if recipe else []
            for layer in layers:
                row = LayerRow(layer)
                row.toggled.connect(self.layerToggled)
                row.removeRequested.connect(self.layerRemoved)
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 30))
                item.setData(Qt.ItemDataRole.UserRole, layer.instance_id)
                self.list.addItem(item)
                self.list.setItemWidget(item, row)
                self._order.append(layer.instance_id)
        finally:
            self._syncing = False

        count = len(self._order)
        self.count_label.setText(f"{count} katman" if count else "")
        self.list.setVisible(count > 0)
        self.empty_label.setVisible(count == 0)

    def _on_rows_moved(self, *_args) -> None:  # noqa: ANN002
        if self._syncing:
            return
        new_order = [
            self.list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list.count())
        ]
        for index, instance_id in enumerate(new_order):
            if index < len(self._order) and self._order[index] != instance_id:
                self.layerMoved.emit(instance_id, index)
                return

    def _on_row_selected(self, row: int) -> None:
        if self._syncing or row < 0 or row >= len(self._order):
            return
        self.layerSelected.emit(self._order[row])

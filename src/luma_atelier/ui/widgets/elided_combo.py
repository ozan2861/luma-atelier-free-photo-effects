"""Metnini kutusuna sigdiran acilir liste.

Qt'nin `QComboBox`'i secili metni **kirpmaz**: kutu dar oldugunda yazi
kenardan tasar ve okunamaz hale gelir. `setMinimumContentsLength`
yalnizca `sizeHint`'i etkiler, cizimi degil.

Bu sinif secili metni kutuya gore kisaltir ("Analog ve vinta…"); acilan
listede ve arac ipucunda tam ad gorunmeye devam eder.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QComboBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QWidget,
)


class ElidedComboBox(QComboBox):
    """Secili metni kutusuna sigdiran acilir liste."""

    def __init__(self, parent: QWidget | None = None,
                 *, minimum_width: int = 84) -> None:
        super().__init__(parent)
        self._minimum_width = minimum_width
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Panel daralinca kuculebilmesi icin kucuk bir alt sinir.

        Varsayilan deger en uzun ogeye gore hesaplanir; o zaman kutu
        hicbir zaman kuculemez ve paneli tasirdi.
        """
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self._minimum_width), hint.height())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QStylePainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))

        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxEditField, self)
        text = self.fontMetrics().elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight,
            max(0, text_rect.width() - 2))

        painter.save()
        painter.setPen(self.palette().color(
            self.palette().ColorRole.ButtonText if self.isEnabled()
            else self.palette().ColorRole.PlaceholderText))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text)
        painter.restore()
        painter.end()
        _ = QPainter  # tur ipucu icin tutuldu

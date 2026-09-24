"""Film seridi: duzenleyicinin altinda fotograflar arasi hizli gecis.

Kucuk resimler `ThumbnailService` uzerinden **eszamansiz** gelir; serit
hicbir zaman goruntu yuklemek icin beklemez. Gorunmeyen karelerin resmi
istenmez, boylece 500 fotografli bir kitaplikta bile acilis anidir.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from luma_atelier.ui.theme.tokens import PALETTE, RADIUS, TYPE

log = logging.getLogger(__name__)

#: Bir karenin genisligi ve yuksekligi (piksel)
CELL_WIDTH = 108
CELL_HEIGHT = 74
#: Kareler arasi bosluk
CELL_GAP = 6
#: Seridin toplam yuksekligi
STRIP_HEIGHT = CELL_HEIGHT + 22


class Filmstrip(QScrollArea):
    """Yatay kaydirilan fotograf seridi."""

    photoActivated = Signal(object)     # Path
    favouriteToggled = Signal(object)   # Path

    def __init__(self, session, thumbnails,  # noqa: ANN001
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Filmstrip")
        self._inner = _StripCanvas(session, thumbnails, self)
        self._inner.photoActivated.connect(self.photoActivated)
        self._inner.favouriteToggled.connect(self.favouriteToggled)

        self.setWidget(self._inner)
        self.setWidgetResizable(False)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setFixedHeight(STRIP_HEIGHT)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.horizontalScrollBar().valueChanged.connect(
            lambda _v: self._inner.requestVisible())

    def refresh(self) -> None:
        """Oturum degisince seridi yeniden kurar."""
        self._inner.rebuild()
        self._scroll_to_current()

    def _scroll_to_current(self) -> None:
        """Etkin fotografi gorunur alana getirir."""
        index = self._inner.currentIndex()
        if index < 0:
            return
        x = index * (CELL_WIDTH + CELL_GAP)
        bar = self.horizontalScrollBar()
        left, right = bar.value(), bar.value() + self.viewport().width()
        if x < left:
            bar.setValue(max(0, x - CELL_GAP))
        elif x + CELL_WIDTH > right:
            bar.setValue(x + CELL_WIDTH - self.viewport().width() + CELL_GAP)
        self._inner.requestVisible()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Dikey tekerlek yatay kaydirir - serit yatay oldugu icin."""
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
            event.accept()
            return
        super().wheelEvent(event)


class _StripCanvas(QWidget):
    """Kareleri cizen ic yuzey."""

    photoActivated = Signal(object)
    favouriteToggled = Signal(object)

    def __init__(self, session, thumbnails,  # noqa: ANN001
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._thumbnails = thumbnails
        self._entries: list = []
        self._pixmaps: dict[str, QPixmap] = {}
        self._requested: set[str] = set()
        self._hover = -1
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(STRIP_HEIGHT)

        if hasattr(thumbnails, "thumbnailReady"):
            thumbnails.thumbnailReady.connect(self._on_thumbnail)

    # ------------------------------------------------------------- veri
    def rebuild(self) -> None:
        self._entries = list(self._session.entries)
        width = max(1, len(self._entries) * (CELL_WIDTH + CELL_GAP) + CELL_GAP)
        self.setFixedWidth(width)
        self.update()
        self.requestVisible()

    def currentIndex(self) -> int:  # noqa: N802
        current = self._session.current
        if current is None:
            return -1
        for i, entry in enumerate(self._entries):
            if entry.path == current.path:
                return i
        return -1

    def requestVisible(self) -> None:  # noqa: N802
        """Yalnizca gorunen karelerin kucuk resmini ister.

        Istek `paint` icinden degil buradan yapilir; cizim sirasinda is
        baslatmak yeniden cizimle yaris olusturur ve bazi kareler hic
        istenmezdi.
        """
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area is None:
            visible = QRect(0, 0, self.width(), self.height())
        else:
            left = area.horizontalScrollBar().value()
            visible = QRect(left, 0, area.viewport().width(), self.height())

        margin = CELL_WIDTH * 2      # komsu kareler onden hazirlanir
        for i, entry in enumerate(self._entries):
            x = CELL_GAP + i * (CELL_WIDTH + CELL_GAP)
            if x + CELL_WIDTH < visible.left() - margin:
                continue
            if x > visible.right() + margin:
                break
            key = str(entry.path)
            if key in self._pixmaps or key in self._requested:
                continue
            self._requested.add(key)
            try:
                # Onbellekte varsa aninda doner; yoksa is parcaciginda
                # uretilir ve `thumbnailReady` ile gelir.
                ready = self._thumbnails.request(entry.path)
            except Exception:  # noqa: BLE001 - serit render'i cokmesin
                log.debug("Kucuk resim istenemedi: %s", entry.path)
                continue
            if ready is not None and not ready.isNull():
                self._pixmaps[key] = ready

    def _on_thumbnail(self, path: str, pixmap: object) -> None:
        if not isinstance(pixmap, QPixmap):
            return
        self._pixmaps[str(path)] = pixmap
        self.update()

    # ------------------------------------------------------------ cizim
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(PALETTE.bg_panel))

        current = self.currentIndex()
        font = QFont(TYPE.family_text)
        font.setPixelSize(TYPE.size_micro)
        p.setFont(font)

        for i, entry in enumerate(self._entries):
            x = CELL_GAP + i * (CELL_WIDTH + CELL_GAP)
            if x > event.rect().right() + CELL_WIDTH:
                break
            if x + CELL_WIDTH < event.rect().left() - CELL_WIDTH:
                continue
            self._paint_cell(p, entry, x, i == current, i == self._hover)
        p.end()

    def _paint_cell(self, p: QPainter, entry, x: int,  # noqa: ANN001
                    is_current: bool, is_hover: bool) -> None:
        rect = QRect(x, 6, CELL_WIDTH, CELL_HEIGHT)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.bg_raised))
        p.drawRoundedRect(rect, RADIUS.sm, RADIUS.sm)

        pixmap = self._pixmaps.get(str(entry.path))
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                QSize(CELL_WIDTH - 4, CELL_HEIGHT - 4),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            target = QRect(
                rect.center().x() - scaled.width() // 2,
                rect.center().y() - scaled.height() // 2,
                scaled.width(), scaled.height())
            p.drawPixmap(target, scaled)
        else:
            p.setPen(QColor(PALETTE.text_disabled))
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "…")

        # Cerceve: etkin kare vurgulu
        if is_current:
            p.setPen(QPen(QColor(PALETTE.accent), 2))
        elif is_hover:
            p.setPen(QPen(QColor(PALETTE.text_muted), 1))
        else:
            p.setPen(Qt.PenStyle.NoPen)
        if is_current or is_hover:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1),
                              RADIUS.sm, RADIUS.sm)

        # Favori isareti
        if getattr(entry, "favourite", False):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE.accent))
            p.drawEllipse(rect.right() - 12, rect.top() + 5, 7, 7)

        # Dosya adi
        p.setPen(QColor(PALETTE.text_primary if is_current
                        else PALETTE.text_muted))
        name_rect = QRect(x, rect.bottom() + 2, CELL_WIDTH, 14)
        metrics = p.fontMetrics()
        text = metrics.elidedText(entry.name, Qt.TextElideMode.ElideMiddle,
                                  CELL_WIDTH - 4)
        p.drawText(name_rect, int(Qt.AlignmentFlag.AlignCenter), text)

    # ---------------------------------------------------------- olaylar
    def _index_at(self, x: float) -> int:
        index = int((x - CELL_GAP) // (CELL_WIDTH + CELL_GAP))
        return index if 0 <= index < len(self._entries) else -1

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        index = self._index_at(event.position().x())
        if index != self._hover:
            self._hover = index
            if 0 <= index < len(self._entries):
                self.setToolTip(self._entries[index].name)
            self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = -1
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        index = self._index_at(event.position().x())
        if index < 0:
            return
        entry = self._entries[index]
        if event.button() == Qt.MouseButton.LeftButton:
            self.photoActivated.emit(entry.path)
        elif event.button() == Qt.MouseButton.RightButton:
            self.favouriteToggled.emit(entry.path)

"""Kitaplik: kucuk resim izgarasi, arama, siralama, favoriler.

Sanallastirma
-------------
Izgara `QListView` + `QAbstractListModel` uzerine kurulu. Kucuk resim
yalnizca *gorunur* satirlar icin istenir; ekran disina cikan istekler
iptal edilir. Boylece 2000 fotografli bir klasor acildiginda uygulama
2000 dosyayi birden okumaz.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.session import PhotoEntry, Session, SortKey
from luma_atelier.services.thumbnails import ThumbnailService
from luma_atelier.ui.theme.tokens import METRICS, PALETTE, RADIUS, SPACE, TYPE

log = logging.getLogger(__name__)

#: Model rolleri
ROLE_ENTRY = int(Qt.ItemDataRole.UserRole) + 1
ROLE_PATH = int(Qt.ItemDataRole.UserRole) + 2

CARD_PADDING = 8
CAPTION_HEIGHT = 34


class LibraryModel(QAbstractListModel):
    """Oturumdaki gorunur fotograflari izgaraya baglar."""

    def __init__(self, session: Session, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._rows: list[PhotoEntry] = []
        self.refresh()

    def refresh(self) -> None:
        """Oturum degistiginde listeyi yeniden kurar."""
        self.beginResetModel()
        self._rows = self._session.visible
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def entry_at(self, row: int) -> PhotoEntry | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def row_of_path(self, path: str | Path) -> int:
        key = str(Path(path)).casefold()
        for i, e in enumerate(self._rows):
            if e.key == key:
                return i
        return -1

    def data(self, index: QModelIndex | QPersistentModelIndex,
             role: int = int(Qt.ItemDataRole.DisplayRole)):  # noqa: ANN201
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        entry = self._rows[index.row()]
        if role == ROLE_ENTRY:
            return entry
        if role == ROLE_PATH:
            return str(entry.path)
        if role == int(Qt.ItemDataRole.DisplayRole):
            return entry.name
        if role == int(Qt.ItemDataRole.ToolTipRole):
            lines = [
                entry.name,
                str(entry.path.parent),
                f"{entry.dimensions_label}   ·   {entry.size_label}",
            ]
            if entry.missing:
                lines.append("Dosya bulunamiyor")
            if entry.error:
                lines.append(entry.error)
            return "\n".join(lines)
        if role == int(Qt.ItemDataRole.AccessibleTextRole):
            fav = "favori, " if entry.favourite else ""
            return f"{fav}{entry.name}, {entry.dimensions_label}"
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return base


class ThumbnailDelegate(QStyledItemDelegate):
    """Kucuk resim karti cizer: gorsel, ad, favori yildizi, durum."""

    def __init__(self, thumbs: ThumbnailService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thumbs = thumbs
        self._cell = METRICS.thumb_size

    def set_cell_size(self, size: int) -> None:
        self._cell = max(88, min(280, size))

    def sizeHint(self, option: QStyleOptionViewItem,  # noqa: N802
                 index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(self._cell + CARD_PADDING * 2,
                     self._cell + CARD_PADDING * 2 + CAPTION_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex | QPersistentModelIndex) -> None:
        entry: PhotoEntry | None = index.data(ROLE_ENTRY)
        if entry is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Kart zemini
        if selected:
            bg, border = PALETTE.accent_soft, PALETTE.accent
        elif hovered:
            bg, border = PALETTE.bg_hover, PALETTE.border_strong
        else:
            bg, border = PALETTE.bg_raised, PALETTE.border_subtle
        painter.setBrush(QColor(bg))
        painter.setPen(QPen(QColor(border), 1.0))
        painter.drawRoundedRect(rect, RADIUS.md, RADIUS.md)

        image_rect = QRect(
            rect.left() + CARD_PADDING, rect.top() + CARD_PADDING,
            rect.width() - CARD_PADDING * 2,
            rect.height() - CARD_PADDING * 2 - CAPTION_HEIGHT,
        )

        pm = self._thumbs.cached(entry.path)
        if pm is None and not entry.missing and not entry.error:
            self._thumbs.request(entry.path)

        if entry.missing or entry.error:
            self._paint_problem(painter, image_rect,
                                "Bulunamadı" if entry.missing else "Okunamadı")
        elif pm is None:
            self._paint_loading(painter, image_rect)
        else:
            scaled = pm.scaled(image_rect.size(), Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            x = image_rect.left() + (image_rect.width() - scaled.width()) // 2
            y = image_rect.top() + (image_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        # Dosya adi - sigmazsa ortadan kisalt
        caption_rect = QRect(rect.left() + CARD_PADDING,
                             image_rect.bottom() + 4,
                             rect.width() - CARD_PADDING * 2, 16)
        f = QFont()
        f.setPixelSize(TYPE.size_caption)
        painter.setFont(f)
        painter.setPen(QColor(PALETTE.text_primary if selected
                              else PALETTE.text_secondary))
        elided = QFontMetrics(f).elidedText(
            entry.name, Qt.TextElideMode.ElideMiddle, caption_rect.width()
        )
        painter.drawText(caption_rect,
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         elided)

        # Boyut bilgisi
        meta_rect = QRect(caption_rect.left(), caption_rect.bottom(),
                          caption_rect.width(), 14)
        f2 = QFont()
        f2.setPixelSize(TYPE.size_micro)
        painter.setFont(f2)
        painter.setPen(QColor(PALETTE.text_muted))
        painter.drawText(meta_rect,
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         entry.dimensions_label)

        if entry.favourite:
            self._paint_star(painter, QPoint(rect.right() - 17, rect.top() + 17))
        painter.restore()

    @staticmethod
    def _paint_loading(painter: QPainter, rect: QRect) -> None:
        painter.setBrush(QColor(PALETTE.bg_base))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, RADIUS.sm, RADIUS.sm)
        f = QFont()
        f.setPixelSize(TYPE.size_micro)
        painter.setFont(f)
        painter.setPen(QColor(PALETTE.text_disabled))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "yükleniyor")

    @staticmethod
    def _paint_problem(painter: QPainter, rect: QRect, text: str) -> None:
        painter.setBrush(QColor(PALETTE.bg_base))
        painter.setPen(QPen(QColor(PALETTE.danger), 1.0, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(rect, RADIUS.sm, RADIUS.sm)
        f = QFont()
        f.setPixelSize(TYPE.size_micro)
        painter.setFont(f)
        painter.setPen(QColor(PALETTE.danger))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    @staticmethod
    def _paint_star(painter: QPainter, center: QPoint) -> None:
        import math
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 140))
        painter.drawEllipse(center, 11, 11)
        painter.setBrush(QColor(PALETTE.accent_hover))
        pts = []
        for i in range(10):
            angle = math.radians(-90 + i * 36)
            r = 7.0 if i % 2 == 0 else 3.0
            pts.append(QPoint(int(center.x() + r * math.cos(angle)),
                              int(center.y() + r * math.sin(angle))))
        painter.drawPolygon(pts)


class LibraryView(QWidget):
    """Kitaplik ekrani."""

    photoActivated = Signal(Path)      # cift tiklama -> duzenleyiciye gec
    selectionChanged = Signal(list)    # secili PhotoEntry listesi
    addFilesRequested = Signal()
    relocateRequested = Signal(Path)

    def __init__(self, session: Session, thumbs: ThumbnailService,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LibraryView")
        self._session = session
        self._thumbs = thumbs
        # Yeniden giris koruyucusu. Secim degisimi oturumu bilgilendirir,
        # oturum kitapligi tazeler, tazeleme secimi yeniden kurar ve olay
        # bastan baslar. Bu bayrak olmadan zincir sonsuz donguye giriyordu.
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.lg, SPACE.md, SPACE.lg, SPACE.md)
        root.setSpacing(SPACE.md)

        root.addLayout(self._build_toolbar())

        self.model = LibraryModel(session, self)
        self.delegate = ThumbnailDelegate(thumbs, self)

        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setSpacing(SPACE.xs)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.view.setMouseTracking(True)
        self.view.doubleClicked.connect(self._on_activated)
        self.view.selectionModel().selectionChanged.connect(self._on_selection)
        root.addWidget(self.view, 1)

        self.empty_label = QLabel(
            "Kitaplık boş. Fotoğraf eklemek için sürükleyip bırakın "
            "veya 'Fotoğraf ekle' deyin."
        )
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label)

        thumbs.thumbnailReady.connect(self._on_thumb_ready)
        thumbs.thumbnailFailed.connect(self._on_thumb_failed)
        session.add_listener(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ arac cubugu
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(SPACE.sm)

        self.count_label = QLabel("")
        self.count_label.setObjectName("Overline")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Dosya veya klasör adı ara")
        self.search.setProperty("searchField", True)
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(280)
        self.search.setToolTip("Dosya adına veya klasör adına göre filtrele")
        self.search.textChanged.connect(self._session.set_search)

        self.fav_button = QToolButton()
        self.fav_button.setText("Favoriler")
        self.fav_button.setCheckable(True)
        self.fav_button.setToolTip("Yalnızca favorileri göster")
        self.fav_button.toggled.connect(self._session.set_favourites_only)

        self.sort_combo = QComboBox()
        for key in SortKey:
            self.sort_combo.addItem(key.label, key)
        self.sort_combo.setToolTip("Sıralama ölçütü")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        self.sort_dir = QToolButton()
        self.sort_dir.setText("Artan")
        self.sort_dir.setCheckable(True)
        self.sort_dir.setToolTip("Sıralama yönü")
        self.sort_dir.toggled.connect(self._on_sort_changed)

        self.size_combo = QComboBox()
        for label, value in [("Küçük", 96), ("Orta", 132), ("Büyük", 180),
                             ("Çok büyük", 240)]:
            self.size_combo.addItem(label, value)
        self.size_combo.setCurrentIndex(1)
        self.size_combo.setToolTip("Küçük resim boyutu")
        self.size_combo.currentIndexChanged.connect(self._on_size_changed)

        bar.addWidget(self.count_label)
        bar.addStretch(1)
        bar.addWidget(self.search)
        bar.addWidget(self.fav_button)
        bar.addWidget(QLabel("Sırala"))
        bar.addWidget(self.sort_combo)
        bar.addWidget(self.sort_dir)
        bar.addWidget(self.size_combo)
        return bar

    # -------------------------------------------------------------- olaylar
    def _on_sort_changed(self) -> None:
        key = self.sort_combo.currentData()
        descending = self.sort_dir.isChecked()
        self.sort_dir.setText("Azalan" if descending else "Artan")
        if isinstance(key, SortKey):
            self._session.set_sort(key, descending)

    def _on_size_changed(self) -> None:
        self.delegate.set_cell_size(int(self.size_combo.currentData()))
        self.model.refresh()
        self.view.doItemsLayout()

    def _on_activated(self, index: QModelIndex) -> None:
        entry = self.model.entry_at(index.row())
        if entry is None:
            return
        if entry.missing:
            self.relocateRequested.emit(entry.path)
            return
        self.photoActivated.emit(entry.path)

    def _on_selection(self) -> None:
        if self._syncing:
            return
        rows = [i.row() for i in self.view.selectionModel().selectedIndexes()]
        entries = [e for e in (self.model.entry_at(r) for r in rows) if e is not None]
        indices = [self._session.index_of(e.path) for e in entries]
        self._syncing = True
        try:
            self._session.set_selection([i for i in indices if i >= 0])
        finally:
            self._syncing = False
        self.selectionChanged.emit(entries)

    def _on_thumb_ready(self, path: str, _pixmap: QPixmap) -> None:
        row = self.model.row_of_path(path)
        if row >= 0:
            idx = self.model.index(row, 0)
            self.view.update(idx)

    def _on_thumb_failed(self, path: str, message: str) -> None:
        log.debug("Kucuk resim basarisiz: %s (%s)", path, message)
        row = self.model.row_of_path(path)
        if row >= 0:
            self.view.update(self.model.index(row, 0))

    # ------------------------------------------------------------- tazeleme
    def refresh(self) -> None:
        if self._syncing:
            return
        self.model.refresh()
        total = len(self._session)
        shown = self.model.rowCount()
        if total == 0:
            self.count_label.setText("KITAPLIK BOŞ")
        elif shown == total:
            self.count_label.setText(f"{total} FOTOĞRAF")
        else:
            self.count_label.setText(f"{shown} / {total} FOTOĞRAF")
        self.empty_label.setVisible(shown == 0)
        self.view.setVisible(shown > 0)
        self._sync_selection()

    def _sync_selection(self) -> None:
        current = self._session.current
        if current is None:
            return
        row = self.model.row_of_path(current.path)
        if row < 0:
            return
        idx = self.model.index(row, 0)
        sel = self.view.selectionModel()
        if sel.isSelected(idx):
            return
        # setCurrentIndex selectionChanged tetikler; koruyucu olmadan
        # oturum -> kitaplik -> oturum dongusu olusur.
        self._syncing = True
        try:
            self.view.setCurrentIndex(idx)
            self.view.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        finally:
            self._syncing = False

    def toggle_favourite_on_selection(self) -> None:
        for entry in self._session.selection:
            self._session.toggle_favourite(self._session.index_of(entry.path))

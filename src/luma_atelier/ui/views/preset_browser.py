"""Preset tarayicisi: kategoriler, arama, favoriler, kullanici gorunumleri.

Davranis sozlesmesi (gereksinim belgesi Bolum 8)
-----------------------------------------------
* Kucuk resimler kullanicinin **kendi fotografi** uzerinde uretilir.
* Yalnizca gorunur kartlar oncelikli uretilir; sonuclar onbeklenir.
* Hover onizlemesi **gecici**: projeyi degistirmez, fare cikinca geri
  alinir.
* Tiklama mevcut preset grubunu **degistirir**, ustune eklemez;
  tekrar tiklama yigini cogaltmaz.
* Ayrica "Yigina ekle" secenegi vardir ve bu acikca birikimlidir.
* Genel yogunluk, favori, arama, kategori ve son kullanilanlar bulunur.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    QSize,
    Qt,
    QTimer,
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
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.services.preset_previews import PresetPreviewService
from luma_atelier.storage.presets import Preset, PresetLibrary
from luma_atelier.ui.theme.tokens import METRICS, PALETTE, RADIUS, SPACE, TYPE
from luma_atelier.ui.widgets.elided_combo import ElidedComboBox
from luma_atelier.ui.widgets.parameter_slider import ParameterSlider, SliderSpec

log = logging.getLogger(__name__)

ROLE_PRESET = int(Qt.ItemDataRole.UserRole) + 1

CARD_PADDING = 6
CAPTION_HEIGHT = 30
#: Son kullanilanlar listesinde tutulacak preset sayisi
RECENT_LIMIT = 12


class PresetModel(QAbstractListModel):
    """Filtrelenmis preset listesi."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[Preset] = []

    def setPresets(self, presets: list[Preset]) -> None:  # noqa: N802
        self.beginResetModel()
        self._rows = list(presets)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def preset_at(self, row: int) -> Preset | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def row_of(self, preset_id: str) -> int:
        for i, p in enumerate(self._rows):
            if p.preset_id == preset_id:
                return i
        return -1

    def data(self, index: QModelIndex | QPersistentModelIndex,
             role: int = int(Qt.ItemDataRole.DisplayRole)):  # noqa: ANN201
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        preset = self._rows[index.row()]
        if role == ROLE_PRESET:
            return preset
        if role == int(Qt.ItemDataRole.DisplayRole):
            return preset.name
        if role == int(Qt.ItemDataRole.ToolTipRole):
            lines = [preset.name, preset.description]
            if preset.intent:
                lines.append(f"Uygun: {preset.intent}")
            ops = preset.operations()
            if ops:
                lines.append("Kullanılan işlemler: " + ", ".join(ops))
            if not preset.builtin:
                lines.append("Kendi kaydettiğiniz görünüm")
            return "\n\n".join(lines)
        if role == int(Qt.ItemDataRole.AccessibleTextRole):
            return f"{preset.name}, {preset.category_label}"
        return None


class PresetDelegate(QStyledItemDelegate):
    """Preset kartini cizer."""

    def __init__(self, previews: PresetPreviewService,
                 is_favourite: Callable[[str], bool],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._previews = previews
        self._is_favourite = is_favourite
        self._cell = METRICS.preset_card_width
        self._active_id = ""

    def set_cell_size(self, size: int) -> None:
        self._cell = max(96, min(260, size))

    def set_active(self, preset_id: str) -> None:
        self._active_id = preset_id

    def sizeHint(self, option: QStyleOptionViewItem,  # noqa: N802
                 index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(self._cell + CARD_PADDING * 2,
                     int(self._cell * 0.72) + CARD_PADDING * 2 + CAPTION_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex | QPersistentModelIndex) -> None:
        preset: Preset | None = index.data(ROLE_PRESET)
        if preset is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        active = preset.preset_id == self._active_id

        if active:
            bg, border = PALETTE.accent_soft, PALETTE.accent
        elif selected or hovered:
            bg, border = PALETTE.bg_hover, PALETTE.border_strong
        else:
            bg, border = PALETTE.bg_raised, PALETTE.border_subtle
        painter.setBrush(QColor(bg))
        painter.setPen(QPen(QColor(border), 1.6 if active else 1.0))
        painter.drawRoundedRect(rect, RADIUS.md, RADIUS.md)

        image_rect = QRect(
            rect.left() + CARD_PADDING, rect.top() + CARD_PADDING,
            rect.width() - CARD_PADDING * 2,
            rect.height() - CARD_PADDING * 2 - CAPTION_HEIGHT,
        )

        pixmap = self._previews.cached(preset.preset_id)
        if pixmap is None:
            self._previews.request(preset.preset_id, preset.recipe)
            self._paint_loading(painter, image_rect)
        else:
            scaled = pixmap.scaled(image_rect.size(),
                                   Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            painter.save()
            from PySide6.QtGui import QPainterPath
            clip = QPainterPath()
            clip.addRoundedRect(image_rect, RADIUS.sm, RADIUS.sm)
            painter.setClipPath(clip)
            x = image_rect.left() + (image_rect.width() - scaled.width()) // 2
            y = image_rect.top() + (image_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.restore()

        # Ad
        caption = QRect(rect.left() + CARD_PADDING, image_rect.bottom() + 3,
                        rect.width() - CARD_PADDING * 2, 15)
        f = QFont()
        f.setPixelSize(TYPE.size_caption)
        f.setWeight(QFont.Weight.DemiBold if active else QFont.Weight.Normal)
        painter.setFont(f)
        painter.setPen(QColor(PALETTE.accent_hover if active
                              else PALETTE.text_primary))
        painter.drawText(
            caption,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(f).elidedText(preset.name, Qt.TextElideMode.ElideRight,
                                       caption.width()),
        )

        # Kategori
        meta = QRect(caption.left(), caption.bottom(), caption.width(), 13)
        f2 = QFont()
        f2.setPixelSize(TYPE.size_micro)
        painter.setFont(f2)
        painter.setPen(QColor(PALETTE.text_muted))
        label = preset.category_label if preset.builtin else "Kendi görünümüm"
        painter.drawText(
            meta, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(f2).elidedText(label, Qt.TextElideMode.ElideRight,
                                        meta.width()),
        )

        if self._is_favourite(preset.preset_id):
            self._paint_star(painter, image_rect.right() - 12,
                             image_rect.top() + 12)
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
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "hazirlaniyor")

    @staticmethod
    def _paint_star(painter: QPainter, cx: int, cy: int) -> None:
        import math
        from PySide6.QtCore import QPoint
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawEllipse(QPoint(cx, cy), 10, 10)
        painter.setBrush(QColor(PALETTE.accent_hover))
        pts = []
        for i in range(10):
            angle = math.radians(-90 + i * 36)
            r = 6.5 if i % 2 == 0 else 2.8
            pts.append(QPoint(int(cx + r * math.cos(angle)),
                              int(cy + r * math.sin(angle))))
        painter.drawPolygon(pts)


class PresetBrowser(QWidget):
    """Preset secme paneli.

    Sinyaller:
        presetApplied(Preset, intensity): kalici uygulama (grubu degistirir)
        presetAdded(Preset, intensity): yigina ekleme (birikimli)
        presetPreviewed(Preset, intensity): gecici hover onizlemesi
        previewCleared(): hover bitti, gecici onizleme geri alinsin
        savePresetRequested(): kullanici mevcut ayarlari kaydetmek istiyor
        deletePresetRequested(str)
        importPresetRequested()
        exportPresetRequested(str)
    """

    presetApplied = Signal(object, float)
    presetAdded = Signal(object, float)
    presetPreviewed = Signal(object, float)
    previewCleared = Signal()
    savePresetRequested = Signal()
    deletePresetRequested = Signal(str)
    importPresetRequested = Signal()
    exportPresetRequested = Signal(str)

    def __init__(self, library: PresetLibrary, previews: PresetPreviewService,
                 *, cinema_only: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PresetBrowser")
        self._library = library
        self._previews = previews
        self._cinema_only = cinema_only
        self._favourites: set[str] = set()
        self._recent: list[str] = []
        self._active_id = ""
        self._hover_id = ""
        self._filter_favourites = False
        self._filter_recent = False

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(260)
        self._hover_timer.timeout.connect(self._emit_hover_preview)

        # Gorunur kartlarin onizlemesi *acikca* istenir. Yalnizca
        # `paint()` icinden istemek kirilgandi: cizim olayi gelmeden
        # hicbir onizleme baslamiyordu. Cizim yan etkisiz kalmali.
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(60)
        self._prefetch_timer.timeout.connect(self._prefetch_visible)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.md, SPACE.md, SPACE.md, SPACE.md)
        root.setSpacing(SPACE.sm)

        root.addLayout(self._build_toolbar())

        self.model = PresetModel(self)
        self.delegate = PresetDelegate(previews, self._is_favourite, self)

        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setSpacing(SPACE.xs)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setMouseTracking(True)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.clicked.connect(self._on_clicked)
        self.view.entered.connect(self._on_entered)
        self.view.viewport().installEventFilter(self)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        root.addWidget(self.view, 1)

        root.addWidget(self._build_footer())
        previews.previewReady.connect(self._on_preview_ready)
        self.view.verticalScrollBar().valueChanged.connect(
            lambda _v: self._prefetch_timer.start())
        self.refresh()

    # ------------------------------------------------------------ arac cubugu
    def _build_toolbar(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(SPACE.xs)

        top = QHBoxLayout()
        top.setSpacing(SPACE.xs)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Görünüm ara")
        self.search.setProperty("searchField", True)
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Ad, açıklama veya etikete göre ara")
        self.search.textChanged.connect(lambda _t: self.refresh())
        # Yer tutucu metne gore hesaplanan alt sinir paneli tasiriyordu;
        # arama kutusu daralabilmeli.
        self.search.setMinimumWidth(80)
        top.addWidget(self.search, 1)

        self.fav_button = QToolButton()
        self.fav_button.setText("★")
        self.fav_button.setCheckable(True)
        self.fav_button.setToolTip("Yalnızca favorileri göster")
        self.fav_button.toggled.connect(self._on_fav_filter)
        top.addWidget(self.fav_button)

        self.recent_button = QToolButton()
        self.recent_button.setText("Son")
        self.recent_button.setCheckable(True)
        self.recent_button.setToolTip("Son kullanılan görünümler")
        self.recent_button.toggled.connect(self._on_recent_filter)
        top.addWidget(self.recent_button)
        box.addLayout(top)

        second = QHBoxLayout()
        second.setSpacing(SPACE.xs)
        # Panel dar oldugunda metni kisaltan liste; kutusundan tasmaz.
        self.category_combo = ElidedComboBox(minimum_width=92)
        self.category_combo.setToolTip("Kategori")
        self.category_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        second.addWidget(self.category_combo, 1)

        self.size_combo = ElidedComboBox(minimum_width=72)
        for label, value in [("Küçük", 110), ("Orta", 148), ("Büyük", 196)]:
            self.size_combo.addItem(label, value)
        self.size_combo.setCurrentIndex(1)
        self.size_combo.setToolTip("Kart boyutu")
        self.size_combo.currentIndexChanged.connect(self._on_size_changed)
        second.addWidget(self.size_combo)
        box.addLayout(second)

        self.intensity = ParameterSlider(SliderSpec(
            key="intensity", label="Yoğunluk", minimum=0.0, maximum=100.0,
            default=100.0, decimals=0, step=1.0, page_step=10.0, suffix=" %",
            bipolar=False,
            tooltip=(
                "Seçili görünümün genel şiddeti. Yoğunluk parametresi "
                "olmayan işlemler (pozlama, beyaz dengesi) oransal "
                "zayıflatılamaz; onlar olduğu gibi uygulanır."
            ),
        ))
        self.intensity.editingFinished.connect(self._on_intensity_changed)
        box.addWidget(self.intensity)
        return box

    def _build_footer(self) -> QWidget:
        """Alt satir: sayac ustte, iki eylem altta.

        Uceyi yan yana koymak paneli tasiriyordu: iki dugmenin metni ve
        sayac birlikte 374 px istiyor, panel ise 268 px. Sayac bilgi
        amacli oldugu icin kendi satirina alindi.
        """
        footer = QWidget()
        outer = QVBoxLayout(footer)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE.xxs)

        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        outer.addWidget(self.count_label)

        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE.xs)
        outer.addLayout(lay)

        self.add_button = QPushButton("Yığına ekle")
        self.add_button.setToolTip(
            "Seçili görünümü mevcut ayarların üstüne ekler.\n"
            "Karta tıklamak ise görünümü değiştirir, üstüne eklemez."
        )
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._on_add_to_stack)

        self.save_button = QPushButton("Kaydet")
        self.save_button.setToolTip("Mevcut ayarları kendi görünümün olarak kaydet")
        self.save_button.clicked.connect(self.savePresetRequested)

        lay.addWidget(self.add_button, 1)
        lay.addWidget(self.save_button)
        return footer

    # ---------------------------------------------------------------- filtre
    def prefetchVisible(self) -> None:  # noqa: N802
        """Gorunur kartlarin onizlemesini hemen ister."""
        self._prefetch_visible()

    def _prefetch_visible(self) -> None:
        """Gorunen (ve hemen altindaki) kartlarin onizlemesini ister.

        Gorunur alandan uzak kartlarin bekleyen istekleri iptal edilir;
        boylece kullanici hizlica kaydirinca ekranin disindaki isler
        kuyrugu tikamaz.
        """
        if not self._previews.has_source:
            return
        count = self.model.rowCount()
        if not count:
            return

        viewport = self.view.viewport().rect()
        # Gorunur araligi bul, altina bir ekran daha ekle (on yukleme)
        first, last = 0, count - 1
        for row in range(count):
            rect = self.view.visualRect(self.model.index(row, 0))
            if rect.bottom() >= 0:
                first = row
                break
        for row in range(first, count):
            rect = self.view.visualRect(self.model.index(row, 0))
            if rect.top() > viewport.height() * 2:
                last = row
                break
        else:
            last = count - 1

        wanted: set[str] = set()
        for row in range(first, min(count, last + 1)):
            preset = self.model.preset_at(row)
            if preset is None:
                continue
            wanted.add(preset.preset_id)
            self._previews.request(preset.preset_id, preset.recipe)

        # Gorunur alandan cikan bekleyen istekleri iptal et
        for row in range(count):
            if first <= row <= last:
                continue
            preset = self.model.preset_at(row)
            if preset is not None and preset.preset_id not in wanted:
                self._previews.cancel(preset.preset_id)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().showEvent(event)
        self._prefetch_timer.start()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().resizeEvent(event)
        self._prefetch_timer.start()

    def refresh(self) -> None:
        self._rebuild_categories()
        presets = self._filtered()
        self.model.setPresets(presets)
        total = len(self._library.cinema() if self._cinema_only
                    else self._library.general())
        shown = len(presets)
        self.count_label.setText(
            f"{shown} görünüm" if shown == total else f"{shown} / {total} görünüm"
        )
        self._sync_selection()
        self._prefetch_timer.start()

    def _rebuild_categories(self) -> None:
        if self.category_combo.count():
            return
        self.category_combo.blockSignals(True)
        if self._cinema_only:
            self.category_combo.addItem("Tüm sinematik görünümler", "")
        else:
            self.category_combo.addItem("Tüm kategoriler", "")
            for key, label, count in self._library.categories():
                if key == "cinema":
                    continue
                self.category_combo.addItem(f"{label}  ({count})", key)
            self.category_combo.addItem("Kendi görünümlerim", "__user__")
        self.category_combo.blockSignals(False)

    def _filtered(self) -> list[Preset]:
        pool = (self._library.cinema() if self._cinema_only
                else self._library.general())
        category = self.category_combo.currentData() or ""

        if category == "__user__":
            pool = [p for p in pool if not p.builtin]
        elif category:
            pool = [p for p in pool if p.category == category]

        needle = self.search.text().casefold().strip()
        if needle:
            pool = [p for p in pool if needle in p.search_text()]

        if self._filter_favourites:
            pool = [p for p in pool if p.preset_id in self._favourites]
        if self._filter_recent:
            order = {pid: i for i, pid in enumerate(self._recent)}
            pool = [p for p in pool if p.preset_id in order]
            pool.sort(key=lambda p: order[p.preset_id])
        return pool

    def _on_fav_filter(self, value: bool) -> None:
        self._filter_favourites = value
        if value:
            self.recent_button.setChecked(False)
        self.refresh()

    def _on_recent_filter(self, value: bool) -> None:
        self._filter_recent = value
        if value:
            self.fav_button.setChecked(False)
        self.refresh()

    def _on_size_changed(self) -> None:
        self.delegate.set_cell_size(int(self.size_combo.currentData()))
        self.view.doItemsLayout()

    # ------------------------------------------------------------- etkilesim
    def _on_clicked(self, index: QModelIndex) -> None:
        preset = self.model.preset_at(index.row())
        if preset is None:
            return
        # Tekrar tiklama yigini cogaltmaz: ayni preset zaten etkinse
        # yalnizca yogunluk yeniden uygulanir.
        self._set_active(preset.preset_id)
        self._remember(preset.preset_id)
        self.add_button.setEnabled(True)
        self.presetApplied.emit(preset, self.intensity.value())

    def _on_add_to_stack(self) -> None:
        preset = self._library.get(self._active_id)
        if preset is not None:
            self.presetAdded.emit(preset, self.intensity.value())

    def _on_intensity_changed(self, _value: float) -> None:
        preset = self._library.get(self._active_id)
        if preset is not None:
            self.presetApplied.emit(preset, self.intensity.value())

    def _on_entered(self, index: QModelIndex) -> None:
        preset = self.model.preset_at(index.row())
        if preset is None or preset.preset_id == self._active_id:
            self._hover_timer.stop()
            return
        self._hover_id = preset.preset_id
        self._hover_timer.start()

    def _emit_hover_preview(self) -> None:
        preset = self._library.get(self._hover_id)
        if preset is not None:
            self.presetPreviewed.emit(preset, self.intensity.value())

    def eventFilter(self, obj, event) -> bool:  # type: ignore[no-untyped-def]  # noqa: N802
        from PySide6.QtCore import QEvent
        if obj is self.view.viewport() and event.type() == QEvent.Type.Leave:
            self._hover_timer.stop()
            if self._hover_id:
                self._hover_id = ""
                # Gecici onizleme geri alinir; proje degismemistir
                self.previewCleared.emit()
        return super().eventFilter(obj, event)

    def _on_context_menu(self, pos) -> None:  # noqa: ANN001
        index = self.view.indexAt(pos)
        preset = self.model.preset_at(index.row()) if index.isValid() else None
        menu = QMenu(self)

        if preset is not None:
            fav = preset.preset_id in self._favourites
            action = menu.addAction(
                "Favorilerden çıkar" if fav else "Favorilere ekle"
            )
            action.triggered.connect(
                lambda: self._toggle_favourite(preset.preset_id)
            )
            menu.addSeparator()
            export = menu.addAction("JSON olarak dışa aktar...")
            export.triggered.connect(
                lambda: self.exportPresetRequested.emit(preset.preset_id)
            )
            if not preset.builtin:
                delete = menu.addAction("Bu görünümü sil")
                delete.triggered.connect(
                    lambda: self.deletePresetRequested.emit(preset.preset_id)
                )
            menu.addSeparator()

        imp = menu.addAction("JSON'dan içe aktar...")
        imp.triggered.connect(self.importPresetRequested)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------- favoriler
    def _is_favourite(self, preset_id: str) -> bool:
        return preset_id in self._favourites

    def _toggle_favourite(self, preset_id: str) -> None:
        if preset_id in self._favourites:
            self._favourites.discard(preset_id)
        else:
            self._favourites.add(preset_id)
        self.refresh()

    def favourites(self) -> list[str]:
        return sorted(self._favourites)

    def setFavourites(self, ids) -> None:  # noqa: ANN001, N802
        self._favourites = {str(i) for i in ids}
        self.refresh()

    def recent(self) -> list[str]:
        return list(self._recent)

    def setRecent(self, ids) -> None:  # noqa: ANN001, N802
        self._recent = [str(i) for i in ids][:RECENT_LIMIT]

    def _remember(self, preset_id: str) -> None:
        if preset_id in self._recent:
            self._recent.remove(preset_id)
        self._recent.insert(0, preset_id)
        del self._recent[RECENT_LIMIT:]

    # --------------------------------------------------------------- secim
    def activePresetId(self) -> str:  # noqa: N802
        return self._active_id

    def _set_active(self, preset_id: str) -> None:
        self._active_id = preset_id
        self.delegate.set_active(preset_id)
        self.view.viewport().update()

    def clearActive(self) -> None:  # noqa: N802
        """Kullanici elle ayar yapinca preset secimi kalkar."""
        if self._active_id:
            self._set_active("")
            self.add_button.setEnabled(False)

    def _sync_selection(self) -> None:
        row = self.model.row_of(self._active_id)
        if row >= 0:
            self.view.setCurrentIndex(self.model.index(row, 0))

    def _on_preview_ready(self, preset_id: str, _pixmap: QPixmap) -> None:
        row = self.model.row_of(preset_id)
        if row >= 0:
            self.view.update(self.model.index(row, 0))

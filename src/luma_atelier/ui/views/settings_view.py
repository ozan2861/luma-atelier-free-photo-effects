"""Ayarlar calisma alani.

Panel ayarlari *toplar* ve degisiklikleri sinyalle bildirir; diske
yazma ve uygulama `core/settings.py` ile kabuk tarafindadir.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.branding import APP_NAME, APP_VERSION
from luma_atelier.core.settings import (
    AUTOSAVE_INTERVALS,
    CACHE_LIMITS,
    PREVIEW_SIZES,
    Settings,
)
from luma_atelier.ui.theme.tokens import SPACE
from luma_atelier.ui.widgets.adjustment_panel import divider

log = logging.getLogger(__name__)

#: Kisayol listesi - kullanicinin gorebilecegi tek yer burasi
SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Ctrl+O", "Fotoğraf aç"),
    ("Ctrl+Shift+O", "Klasör ekle"),
    ("Ctrl+Shift+P", "Proje aç"),
    ("Ctrl+Shift+S", "Projeyi kaydet"),
    ("Ctrl+S", "Kopya olarak kaydet"),
    ("Ctrl+Z / Ctrl+Y", "Geri al / yinele"),
    ("Ctrl+C / Ctrl+Shift+V", "Ayarları kopyala / yapıştır"),
    ("← / →", "Önceki / sonraki fotoğraf"),
    ("F", "Favoriye ekle veya çıkar"),
    ("0", "Ekrana sığdır"),
    ("1", "Gerçek piksel (%100)"),
    ("+ / −", "Yakınlaştır / uzaklaştır"),
    ("Boşluk (basılı)", "Orijinali göster"),
    ("Ctrl+Q", "Çıkış"),
)


class SettingsView(QWidget):
    """Tercihler, klasörler, önbellek ve kısayollar."""

    settingsChanged = Signal(object)        # Settings
    clearCacheRequested = Signal()
    openFolderRequested = Signal(object)    # Path
    statusMessage = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsView")
        self._settings = Settings()
        self._syncing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.lg)
        lay.setSpacing(SPACE.md)

        title = QLabel("Ayarlar")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)

        lay.addWidget(self._build_performance())
        lay.addWidget(divider())
        lay.addWidget(self._build_folders())
        lay.addWidget(divider())
        lay.addWidget(self._build_behaviour())
        lay.addWidget(divider())
        lay.addWidget(self._build_shortcuts())
        lay.addWidget(divider())
        lay.addWidget(self._build_about())
        lay.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------ bolumler
    def _build_performance(self) -> QWidget:
        box, grid = _section("PERFORMANS")

        self.preview_box = QComboBox()
        for label, value in PREVIEW_SIZES:
            self.preview_box.addItem(label, value)
        self.preview_box.setToolTip(
            "Düzenlerken gösterilen önizlemenin uzun kenarı. Büyük değer "
            "daha keskin görünür ama her ayar değişikliği daha uzun sürer.")
        self.preview_box.currentIndexChanged.connect(
            lambda: self._update(preview_long_edge=self.preview_box.currentData()))
        grid.addWidget(QLabel("Önizleme kalitesi"), 0, 0)
        grid.addWidget(self.preview_box, 0, 1)

        self.cache_box = QComboBox()
        for label, value in CACHE_LIMITS:
            self.cache_box.addItem(label, value)
        self.cache_box.setToolTip(
            "Küçük resim ve görünüm önizlemeleri için ayrılan disk alanı.")
        self.cache_box.currentIndexChanged.connect(
            lambda: self._update(cache_limit_mb=self.cache_box.currentData()))
        grid.addWidget(QLabel("Önbellek sınırı"), 1, 0)
        grid.addWidget(self.cache_box, 1, 1)

        cache_row = QHBoxLayout()
        self.cache_label = QLabel("")
        self.cache_label.setObjectName("Muted")
        clear = QPushButton("Önbelleği temizle")
        clear.setToolTip("Fotoğraflarınıza ve projelerinize dokunmaz; "
                         "yalnızca yeniden üretilebilir dosyaları siler.")
        clear.clicked.connect(self.clearCacheRequested)
        cache_row.addWidget(self.cache_label, 1)
        cache_row.addWidget(clear)
        grid.addLayout(cache_row, 2, 0, 1, 2)
        return box

    def _build_folders(self) -> QWidget:
        box, grid = _section("KLASÖRLER")

        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        browse = QPushButton("Seç...")
        browse.clicked.connect(self._choose_output)
        reset = QPushButton("Varsayılan")
        reset.clicked.connect(lambda: self._update(output_folder=""))
        row = QHBoxLayout()
        row.addWidget(self.output_edit, 1)
        row.addWidget(browse)
        row.addWidget(reset)
        grid.addWidget(QLabel("Varsayılan kayıt yeri"), 0, 0)
        grid.addLayout(row, 0, 1)

        links = QHBoxLayout()
        for text, kind in (("Veri klasörünü aç", "data"),
                           ("Günlük klasörünü aç", "log"),
                           ("Önbellek klasörünü aç", "cache")):
            button = QPushButton(text)
            button.setObjectName("GhostButton")
            button.clicked.connect(
                lambda _c=False, k=kind: self._open_known(k))
            links.addWidget(button)
        links.addStretch(1)
        grid.addLayout(links, 1, 0, 1, 2)
        return box

    def _build_behaviour(self) -> QWidget:
        box, grid = _section("DAVRANIŞ")

        self.autosave_box = QComboBox()
        for label, value in AUTOSAVE_INTERVALS:
            self.autosave_box.addItem(label, value)
        self.autosave_box.setToolTip(
            "Kaydedilmemiş düzenlemeler ayrı bir kurtarma dosyasına yazılır. "
            "Normal kaydınızın yerine geçmez.")
        self.autosave_box.currentIndexChanged.connect(
            lambda: self._update(
                autosave_seconds=self.autosave_box.currentData()))
        grid.addWidget(QLabel("Otomatik kurtarma"), 0, 0)
        grid.addWidget(self.autosave_box, 0, 1)

        self.confirm_check = QCheckBox(
            "Çok sayıda fotoğraf dışa aktarılırken onay iste")
        self.confirm_check.toggled.connect(
            lambda v: self._update(confirm_large_export=v))
        grid.addWidget(self.confirm_check, 1, 0, 1, 2)

        self.tooltip_check = QCheckBox("Araç ipuçlarını göster")
        self.tooltip_check.toggled.connect(
            lambda v: self._update(show_tooltips=v))
        grid.addWidget(self.tooltip_check, 2, 0, 1, 2)

        self.window_check = QCheckBox("Pencere boyutunu ve konumunu hatırla")
        self.window_check.toggled.connect(
            lambda v: self._update(remember_window=v))
        grid.addWidget(self.window_check, 3, 0, 1, 2)

        self.contrast_check = QCheckBox(
            "Yüksek kontrast (metin ve kenarlıkları belirginleştirir)")
        self.contrast_check.toggled.connect(
            lambda v: self._update(high_contrast=v))
        grid.addWidget(self.contrast_check, 4, 0, 1, 2)

        self.hints_check = QCheckBox("Klavye kısayollarını ipuçlarında göster")
        self.hints_check.toggled.connect(
            lambda v: self._update(keyboard_hints=v))
        grid.addWidget(self.hints_check, 5, 0, 1, 2)
        return box

    def _build_shortcuts(self) -> QWidget:
        box, grid = _section("KLAVYE KISAYOLLARI")
        for row, (keys, what) in enumerate(SHORTCUTS):
            key_label = QLabel(keys)
            key_label.setObjectName("ValueReadout")
            key_label.setMinimumWidth(150)
            grid.addWidget(key_label, row, 0)
            grid.addWidget(QLabel(what), row, 1)
        grid.setColumnStretch(1, 1)
        return box

    def _build_about(self) -> QWidget:
        box, grid = _section("HAKKINDA")
        text = QLabel(
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Tamamen çevrimdışı çalışır; fotoğraflarınız bilgisayarınızdan "
            "çıkmaz. Orijinal dosyalarınız hiçbir işlemde değiştirilmez.")
        text.setObjectName("Muted")
        text.setWordWrap(True)
        grid.addWidget(text, 0, 0, 1, 2)
        return box

    # ------------------------------------------------------------ doldurma
    def setSettings(self, settings: Settings) -> None:  # noqa: N802
        """Paneli kayitli ayarlarla esitler."""
        self._settings = settings
        self._syncing = True
        try:
            _select(self.preview_box, settings.preview_long_edge)
            _select(self.cache_box, settings.cache_limit_mb)
            _select(self.autosave_box, settings.autosave_seconds)
            self.output_edit.setText(str(settings.output_path))
            self.confirm_check.setChecked(settings.confirm_large_export)
            self.tooltip_check.setChecked(settings.show_tooltips)
            self.window_check.setChecked(settings.remember_window)
            self.contrast_check.setChecked(settings.high_contrast)
            self.hints_check.setChecked(settings.keyboard_hints)
        finally:
            self._syncing = False

    def settings(self) -> Settings:
        return self._settings

    def setCacheSize(self, size_bytes: int) -> None:  # noqa: N802
        from luma_atelier.services.export import format_bytes

        self.cache_label.setText(f"Önbellekte {format_bytes(size_bytes)} var")

    # ------------------------------------------------------------- olaylar
    def _update(self, **changes: object) -> None:
        if self._syncing:
            return
        updated = replace(self._settings, **changes)
        if updated == self._settings:
            return
        self._settings = updated
        if "output_folder" in changes:
            self.output_edit.setText(str(updated.output_path))
        self.settingsChanged.emit(updated)

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Varsayılan kayıt klasörü", self.output_edit.text())
        if folder:
            self._update(output_folder=folder)

    def _open_known(self, kind: str) -> None:
        from luma_atelier.core.paths import cache_dir, log_dir, user_data_dir

        folder = {"data": user_data_dir, "log": log_dir,
                  "cache": cache_dir}[kind]()
        self.openFolderRequested.emit(folder)


def _section(title: str) -> tuple[QWidget, QGridLayout]:
    """Baslikli bir bolum ve iceriginin izgara yerlesimi."""
    box = QWidget()
    outer = QVBoxLayout(box)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(SPACE.sm)
    label = QLabel(title)
    label.setObjectName("Overline")
    outer.addWidget(label)
    grid = QGridLayout()
    grid.setSpacing(SPACE.sm)
    grid.setColumnMinimumWidth(0, 210)
    outer.addLayout(grid)
    return box, grid


def _select(box: QComboBox, value: object) -> None:
    index = box.findData(value)
    if index >= 0:
        box.setCurrentIndex(index)

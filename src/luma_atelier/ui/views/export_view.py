"""Disa Aktar calisma alani: secenekler, kuyruk ve sonuclar.

Panel yalnizca *ayarlari* toplar ve kuyrugu izler; render ve yazma isi
`services/export.py` icindedir. Boylece disa aktarma arayuzsuz de test
edilebilir.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.imaging.saver import OutputFormat
from luma_atelier.services.export import (
    NAME_TOKENS,
    ConflictPolicy,
    ExportResult,
    ExportSettings,
    ExportSummary,
    MetadataPolicy,
    ResizeMode,
    estimate_bytes,
    format_bytes,
    preview_names,
)
from luma_atelier.ui.theme.tokens import SPACE
from luma_atelier.ui.widgets.adjustment_panel import divider

log = logging.getLogger(__name__)

#: Kalite kaydiricisinin adimlari
QUALITY_PRESETS: tuple[tuple[str, int], ...] = (
    ("Ekran (80)", 80),
    ("Yüksek (92)", 92),
    ("En yüksek (98)", 98),
)


class ExportView(QWidget):
    """Toplu ve tekli disa aktarma ekrani."""

    #: (isler icin kaynak secimi, ayarlar)
    exportRequested = Signal(str, object)
    cancelRequested = Signal()
    retryRequested = Signal(object)
    openFolderRequested = Signal(object)
    statusMessage = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ExportView")
        self._sources: list[Path] = []
        self._current_size = (0, 0)
        self._syncing = False
        self._last_summary: ExportSummary | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(SPACE.lg, SPACE.lg, SPACE.lg, SPACE.lg)
        root.setSpacing(SPACE.lg)
        root.addWidget(self._build_options(), 0)
        root.addWidget(self._build_queue(), 1)
        self._refresh_estimate()

    # ------------------------------------------------------------ secenekler
    def _build_options(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("SidePanel")
        panel.setMinimumWidth(380)
        panel.setMaximumWidth(460)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACE.md, SPACE.md, SPACE.md, SPACE.md)
        lay.setSpacing(SPACE.sm)

        title = QLabel("DIŞA AKTARMA AYARLARI")
        title.setObjectName("Overline")
        lay.addWidget(title)

        # --- kapsam ---
        lay.addWidget(_overline("Hangi fotoğraflar"))
        self.scope_current = QRadioButton("Yalnızca açık fotoğraf")
        self.scope_current.setChecked(True)
        self.scope_selected = QRadioButton("Kitaplıkta seçili olanlar")
        self.scope_all = QRadioButton("Kitaplıktaki tüm fotoğraflar")
        for button in (self.scope_current, self.scope_selected, self.scope_all):
            button.toggled.connect(self._refresh_estimate)
            lay.addWidget(button)
        self.scope_note = QLabel("")
        self.scope_note.setObjectName("Muted")
        self.scope_note.setWordWrap(True)
        lay.addWidget(self.scope_note)
        lay.addWidget(divider())

        # --- hedef klasor ---
        lay.addWidget(_overline("Hedef klasör"))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setToolTip("Çıktıların yazılacağı klasör")
        browse = QPushButton("Seç...")
        browse.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        lay.addLayout(folder_row)
        lay.addWidget(divider())

        # --- bicim ---
        lay.addWidget(_overline("Biçim"))
        grid = QGridLayout()
        grid.setSpacing(SPACE.xs)
        self.format_box = QComboBox()
        for fmt in OutputFormat:
            self.format_box.addItem(fmt.label, fmt)
        self.format_box.currentIndexChanged.connect(self._on_format_changed)
        grid.addWidget(QLabel("Dosya biçimi"), 0, 0)
        grid.addWidget(self.format_box, 0, 1)

        self.quality_box = QComboBox()
        for label, value in QUALITY_PRESETS:
            self.quality_box.addItem(label, value)
        self.quality_box.setCurrentIndex(1)
        self.quality_box.currentIndexChanged.connect(self._refresh_estimate)
        self.quality_label = QLabel("Kalite")
        grid.addWidget(self.quality_label, 1, 0)
        grid.addWidget(self.quality_box, 1, 1)

        self.depth_box = QComboBox()
        self.depth_box.addItem("8 bit", 8)
        self.depth_box.addItem("16 bit", 16)
        self.depth_box.currentIndexChanged.connect(self._refresh_estimate)
        self.depth_label = QLabel("Bit derinliği")
        grid.addWidget(self.depth_label, 2, 0)
        grid.addWidget(self.depth_box, 2, 1)
        lay.addLayout(grid)

        self.lossless_check = QCheckBox("WebP kayıpsız")
        self.lossless_check.toggled.connect(self._refresh_estimate)
        lay.addWidget(self.lossless_check)
        lay.addWidget(divider())

        # --- boyut ---
        lay.addWidget(_overline("Boyut"))
        size_row = QHBoxLayout()
        self.resize_box = QComboBox()
        for mode in ResizeMode:
            self.resize_box.addItem(mode.label, mode)
        self.resize_box.currentIndexChanged.connect(self._on_resize_changed)
        self.resize_value = QSpinBox()
        self.resize_value.setRange(1, 60000)
        self.resize_value.setValue(2048)
        self.resize_value.valueChanged.connect(self._refresh_estimate)
        size_row.addWidget(self.resize_box, 1)
        size_row.addWidget(self.resize_value)
        lay.addLayout(size_row)
        self.size_note = QLabel("")
        self.size_note.setObjectName("Muted")
        lay.addWidget(self.size_note)
        lay.addWidget(divider())

        # --- adlandirma ---
        lay.addWidget(_overline("Dosya adı"))
        self.name_edit = QLineEdit("{ad}-luma")
        self.name_edit.setToolTip(
            "Kullanılabilir alanlar:\n"
            + "\n".join(f"{token}  —  {desc}" for token, desc in NAME_TOKENS))
        self.name_edit.textChanged.connect(self._refresh_estimate)
        lay.addWidget(self.name_edit)
        self.name_preview = QLabel("")
        self.name_preview.setObjectName("Muted")
        self.name_preview.setWordWrap(True)
        lay.addWidget(self.name_preview)

        conflict_row = QHBoxLayout()
        conflict_row.addWidget(QLabel("Aynı ad varsa"))
        self.conflict_box = QComboBox()
        for policy in ConflictPolicy:
            self.conflict_box.addItem(policy.label, policy)
        conflict_row.addWidget(self.conflict_box, 1)
        lay.addLayout(conflict_row)
        lay.addWidget(divider())

        # --- ust veri ---
        lay.addWidget(_overline("Üst veri"))
        self.metadata_box = QComboBox()
        for policy in MetadataPolicy:
            self.metadata_box.addItem(policy.label, policy)
        self.metadata_box.setCurrentIndex(1)     # varsayilan: GPS kaldir
        self.metadata_box.currentIndexChanged.connect(self._on_metadata_changed)
        lay.addWidget(self.metadata_box)
        self.metadata_note = QLabel("")
        self.metadata_note.setObjectName("Muted")
        self.metadata_note.setWordWrap(True)
        lay.addWidget(self.metadata_note)
        self.icc_check = QCheckBox("Renk profilini (ICC) göm")
        self.icc_check.setChecked(True)
        lay.addWidget(self.icc_check)

        lay.addStretch(1)

        self.estimate_label = QLabel("")
        self.estimate_label.setObjectName("Muted")
        self.estimate_label.setWordWrap(True)
        lay.addWidget(self.estimate_label)

        self.export_button = QPushButton("Dışa aktar")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.setMinimumHeight(38)
        self.export_button.clicked.connect(self._on_export)
        lay.addWidget(self.export_button)
        self._on_format_changed()
        self._on_metadata_changed()
        self._on_resize_changed()
        return panel

    # --------------------------------------------------------------- kuyruk
    def _build_queue(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE.sm)

        head = QHBoxLayout()
        title = QLabel("KUYRUK")
        title.setObjectName("Overline")
        head.addWidget(title)
        head.addStretch(1)
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancelRequested)
        head.addWidget(self.cancel_button)
        self.retry_button = QPushButton("Başarısızları yeniden dene")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self._on_retry)
        head.addWidget(self.retry_button)
        self.open_button = QPushButton("Klasörü aç")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(
            lambda: self.openFolderRequested.emit(self._folder()))
        head.addWidget(self.open_button)
        lay.addLayout(head)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m")
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("ExportQueue")
        self.queue_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.queue_list.setAlternatingRowColors(False)
        self.queue_list.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Expanding)
        lay.addWidget(self.queue_list, 1)

        self.summary_label = QLabel(
            "Henüz dışa aktarma yapılmadı. Soldan ayarları seçip "
            "“Dışa aktar” düğmesine basın.")
        self.summary_label.setObjectName("Muted")
        self.summary_label.setWordWrap(True)
        self.summary_label.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self.summary_label)
        return panel

    # ------------------------------------------------------------ doldurma
    def setContext(self, *, current: Path | None, selected: int,  # noqa: N802
                   total: int, output_size: tuple[int, int],
                   default_folder: Path) -> None:
        """Kabuk, geçerli durumu buraya bildirir."""
        self._current_size = output_size
        self.scope_current.setEnabled(current is not None)
        self.scope_selected.setEnabled(selected > 0)
        self.scope_all.setEnabled(total > 0)
        if current is None and total > 0:
            self.scope_all.setChecked(True)
        self.scope_note.setText(
            f"Açık: {current.name if current else '—'}  ·  "
            f"seçili {selected}  ·  kitaplıkta {total}")
        if not self.folder_edit.text():
            self.folder_edit.setText(str(default_folder))
        self._refresh_estimate()

    def setSources(self, sources: list[Path]) -> None:  # noqa: N802
        """Ad onizlemesi icin kaynak listesi."""
        self._sources = list(sources)
        self._refresh_estimate()

    def settings(self) -> ExportSettings:
        """Panelden geçerli ayarları toplar."""
        return ExportSettings(
            folder=self._folder(),
            fmt=self._enum(self.format_box, OutputFormat),
            quality=int(self.quality_box.currentData() or 92),
            bit_depth=int(self.depth_box.currentData() or 8),
            resize=self._enum(self.resize_box, ResizeMode),
            resize_value=self.resize_value.value(),
            name_template=self.name_edit.text().strip() or "{ad}-luma",
            metadata=self._enum(self.metadata_box, MetadataPolicy),
            conflict=self._enum(self.conflict_box, ConflictPolicy),
            embed_icc=self.icc_check.isChecked(),
            webp_lossless=self.lossless_check.isChecked(),
        )

    def scope(self) -> str:
        if self.scope_current.isChecked():
            return "current"
        if self.scope_selected.isChecked():
            return "selected"
        return "all"

    def _enum(self, box: QComboBox, enum_type):  # noqa: ANN001, ANN202
        """QComboBox verisini enum'a geri cevirir.

        Qt, `str` tabanli enum'lari QVariant icinde duz metne cevirir;
        `currentData()` bu yuzden enum degil string dondurur. Donusumu
        tek yerde yapmak, her cagrida `.value` unutma riskini kaldirir.
        """
        raw = box.currentData()
        if isinstance(raw, enum_type):
            return raw
        try:
            return enum_type(raw)
        except ValueError:
            return next(iter(enum_type))

    def _folder(self) -> Path:
        return Path(self.folder_edit.text() or ".")

    # ---------------------------------------------------------- kuyruk akisi
    def onQueueStarted(self, total: int) -> None:  # noqa: N802
        self.queue_list.clear()
        self.progress.setVisible(True)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.export_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.retry_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.summary_label.setText(f"{total} fotoğraf işleniyor...")

    def onItemStarted(self, index: int, name: str) -> None:  # noqa: N802
        item = QListWidgetItem(f"⏳  {index:>3}.  {name}")
        item.setData(Qt.ItemDataRole.UserRole, index)
        self.queue_list.addItem(item)
        self.queue_list.scrollToBottom()

    def onItemFinished(self, result: ExportResult) -> None:  # noqa: N802
        rows = self.queue_list.count()
        item = self.queue_list.item(rows - 1) if rows else None
        text, tooltip = _result_text(result)
        if item is not None:
            item.setText(text)
            item.setToolTip(tooltip)
        else:
            self.queue_list.addItem(text)

    def onProgress(self, done: int, total: int) -> None:  # noqa: N802
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def onQueueFinished(self, summary: ExportSummary) -> None:  # noqa: N802
        self._last_summary = summary
        self.export_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.retry_button.setEnabled(bool(summary.failed))
        self.open_button.setEnabled(bool(summary.succeeded))
        self.progress.setVisible(False)
        self.summary_label.setText(summary.message())
        if summary.failed:
            self.summary_label.setText(
                summary.message()
                + "  —  başarısızlar listede ⚠ ile işaretli, "
                  "yeniden denenebilir.")

    # ------------------------------------------------------------ olaylar
    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Hedef klasör", self.folder_edit.text() or str(Path.home()))
        if folder:
            self.folder_edit.setText(folder)
            self._refresh_estimate()

    def _on_format_changed(self) -> None:
        fmt = self._enum(self.format_box, OutputFormat)
        supports_quality = fmt.supports_quality
        self.quality_box.setVisible(supports_quality)
        self.quality_label.setVisible(supports_quality)
        self.depth_box.setVisible(fmt.supports_16bit)
        self.depth_label.setVisible(fmt.supports_16bit)
        self.lossless_check.setVisible(fmt is OutputFormat.WEBP)
        if not fmt.supports_16bit:
            self.depth_box.setCurrentIndex(0)
        self._refresh_estimate()

    def _on_resize_changed(self) -> None:
        mode = self._enum(self.resize_box, ResizeMode)
        self.resize_value.setVisible(mode.needs_value)
        if mode is ResizeMode.PERCENT:
            self.resize_value.setRange(1, 400)
            self.resize_value.setSuffix(" %")
            if self.resize_value.value() > 400:
                self.resize_value.setValue(100)
        elif mode.needs_value:
            self.resize_value.setSuffix(" px")
            self.resize_value.setRange(16, 60000)
        self._refresh_estimate()

    def _on_metadata_changed(self) -> None:
        policy = self._enum(self.metadata_box, MetadataPolicy)
        self.metadata_note.setText(policy.description)
        self._refresh_estimate()

    def _on_export(self) -> None:
        self.exportRequested.emit(self.scope(), self.settings())

    def _on_retry(self) -> None:
        if self._last_summary is not None:
            self.retryRequested.emit(self._last_summary)

    def _refresh_estimate(self) -> None:
        if self._syncing:
            return
        settings = self.settings()
        width, height = self._current_size
        if width and height:
            out_w, out_h = settings.output_size(width, height)
            size = estimate_bytes(out_w, out_h, settings)
            mp = out_w * out_h / 1e6
            self.size_note.setText(
                f"Çıktı: {out_w} × {out_h} ({mp:.1f} MP)")
            self.estimate_label.setText(
                f"Yaklaşık dosya boyutu: {format_bytes(size)} "
                f"(içeriğe göre değişir)")
        else:
            self.size_note.setText("")
            self.estimate_label.setText("")

        names = preview_names(settings.name_template, self._sources, settings)
        if names:
            more = "  ..." if len(self._sources) > len(names) else ""
            self.name_preview.setText("Örnek: " + ",  ".join(names) + more)
        else:
            self.name_preview.setText("")


def _overline(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Overline")
    return label


def _result_text(result: ExportResult) -> tuple[str, str]:
    """Kuyruk satiri metni ve ipucu."""
    name = result.job.source.name
    if result.error:
        return (f"⚠  {name}  —  {result.error}", result.error)
    if result.skipped:
        return (f"⤼  {name}  —  atlandı (dosya zaten var)",
                str(result.path or ""))
    size = format_bytes(result.bytes_written)
    detail = (f"{result.width} × {result.height}  ·  {size}  ·  "
              f"{result.bit_depth} bit  ·  {result.elapsed_ms:.0f} ms")
    mark = "✓" if not result.renamed else "✓*"
    suffix = "  (yeni ad verildi)" if result.renamed else ""
    return (f"{mark}  {result.path.name if result.path else name}  —  {detail}"
            f"{suffix}", str(result.path or ""))

"""Baslangic ekrani: fotograf ekle, klasor ekle, son projeler.

Tasarim notu: reklam karti, buyuk gradyan blob veya kalabalik karsilama
yok. Ekranin merkezinde tek is var - fotografi iceri almak.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.branding import APP_NAME, TAGLINE
from luma_atelier.ui.theme.tokens import METRICS, PALETTE, RADIUS, SPACE, TYPE


class DropZone(QWidget):
    """Buyuk surukle-birak alani.

    Kendi cizimi var: kesikli kenarlik ve durum geri bildirimi QSS ile
    guvenilir yapilamaz.
    """

    filesDropped = Signal(list)
    browseRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Fotoğraf bırakma alanı")
        self.setToolTip("Fotoğrafları buraya sürükleyin veya tıklayarak seçin")
        self._hover = False
        self._active = False

    # ------------------------------------------------------------- olaylar
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self._active = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._active = False
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._active = False
        self.update()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.browseRequested.emit()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.browseRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    # --------------------------------------------------------------- cizim
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)

        if self._active:
            border, fill, tint = PALETTE.accent, PALETTE.accent_soft, PALETTE.accent_hover
        elif self._hover or self.hasFocus():
            border, fill, tint = PALETTE.border_strong, PALETTE.bg_raised, PALETTE.text_primary
        else:
            border, fill, tint = PALETTE.border, PALETTE.bg_panel, PALETTE.text_secondary

        p.setBrush(QColor(fill))
        pen = QPen(QColor(border), 1.6)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([7, 5])
        p.setPen(pen)
        p.drawRoundedRect(rect, RADIUS.lg, RADIUS.lg)

        # Diyafram benzeri sade simge: halka + ice bakan arti
        cx, cy = rect.center().x(), rect.center().y() - 26
        r = 26.0
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(tint), 1.8))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.setPen(QPen(QColor(tint), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx - 10, cy), QPointF(cx + 10, cy))
        p.drawLine(QPointF(cx, cy - 10), QPointF(cx, cy + 10))

        f = QFont()
        f.setPixelSize(TYPE.size_heading)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(PALETTE.text_primary if self._active else PALETTE.text_secondary))
        p.drawText(
            QRectF(rect.left(), cy + r + 14, rect.width(), 26),
            int(Qt.AlignmentFlag.AlignCenter),
            "Fotoğrafları buraya bırakın" if self._active
            else "Fotoğrafları sürükleyip bırakın",
        )

        f2 = QFont()
        f2.setPixelSize(TYPE.size_caption)
        p.setFont(f2)
        p.setPen(QColor(PALETTE.text_muted))
        p.drawText(
            QRectF(rect.left(), cy + r + 40, rect.width(), 22),
            int(Qt.AlignmentFlag.AlignCenter),
            "veya tıklayarak dosya seçin  ·  JPEG, PNG, WebP, TIFF",
        )
        p.end()


class StartView(QWidget):
    """Uygulamanin acilis ekrani."""

    filesDropped = Signal(list)
    openFilesRequested = Signal()
    openFolderRequested = Signal(bool)   # recursive
    openProjectRequested = Signal()
    recentRequested = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StartView")
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.xxxl, SPACE.xxl, SPACE.xxxl, SPACE.xxl)
        root.setSpacing(SPACE.lg)

        # --- Baslik ---
        header = QVBoxLayout()
        header.setSpacing(SPACE.xxs)
        title = QLabel(APP_NAME)
        title.setObjectName("DisplayTitle")
        subtitle = QLabel(TAGLINE)
        subtitle.setObjectName("Caption")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)
        root.addSpacing(SPACE.sm)

        # --- Birakma alani ---
        self.drop_zone = DropZone()
        self.drop_zone.filesDropped.connect(self.filesDropped)
        self.drop_zone.browseRequested.connect(self.openFilesRequested)
        root.addWidget(self.drop_zone, 1)

        # --- Eylemler ---
        actions = QHBoxLayout()
        actions.setSpacing(SPACE.sm)

        add_files = QPushButton("Fotoğraf ekle")
        add_files.setObjectName("PrimaryButton")
        add_files.setMinimumWidth(148)
        add_files.clicked.connect(self.openFilesRequested)
        add_files.setToolTip("Bir veya birden fazla fotoğraf seçin (Ctrl+O)")

        add_folder = QPushButton("Klasör ekle")
        add_folder.setMinimumWidth(128)
        add_folder.clicked.connect(
            lambda: self.openFolderRequested.emit(self.recursive_check.isChecked())
        )
        add_folder.setToolTip("Bir klasördeki fotoğrafları ekleyin")

        open_project = QPushButton("Proje aç")
        open_project.setMinimumWidth(110)
        open_project.clicked.connect(self.openProjectRequested)
        open_project.setToolTip("Kaydedilmiş .luma projesini açın")

        self.recursive_check = QCheckBox("Alt klasörleri de tara")
        self.recursive_check.setToolTip(
            "İşaretliyse seçilen klasörün tüm alt klasörleri taranır"
        )

        actions.addWidget(add_files)
        actions.addWidget(add_folder)
        actions.addWidget(open_project)
        actions.addSpacing(SPACE.md)
        actions.addWidget(self.recursive_check)
        actions.addStretch(1)
        root.addLayout(actions)

        # --- Son projeler ---
        self._recent_box = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_box)
        self._recent_layout.setContentsMargins(0, SPACE.sm, 0, 0)
        self._recent_layout.setSpacing(SPACE.xs)
        recent_title = QLabel("SON KULLANILANLAR")
        recent_title.setObjectName("Overline")
        self._recent_layout.addWidget(recent_title)
        self._recent_empty = QLabel("Henüz bir proje açmadınız.")
        self._recent_empty.setObjectName("Muted")
        self._recent_layout.addWidget(self._recent_empty)
        root.addWidget(self._recent_box)

        # --- Ilk kullanim ipucu ---
        root.addWidget(_build_first_run_hint())

    # ------------------------------------------------------------ surukle
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    # -------------------------------------------------------- son projeler
    def set_recent(self, entries: list[tuple[str, Path]]) -> None:
        """Son kullanilan projeleri listeler."""
        # Basliktan sonraki her seyi temizle. `deleteLater` gecikmeli
        # calistigi icin once ebeveynlikten cikarilir; aksi halde eski
        # satirlar bir kare daha ekranda kaliyordu.
        while self._recent_layout.count() > 1:
            item = self._recent_layout.takeAt(1)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if not entries:
            empty = QLabel("Henüz bir proje açmadınız.")
            empty.setObjectName("Muted")
            self._recent_layout.addWidget(empty, 0, Qt.AlignmentFlag.AlignLeft)
            return

        for label, path in entries[:5]:
            btn = QPushButton(f"{label}      {path.parent}")
            btn.setObjectName("GhostButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(str(path))
            btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet("text-align: left;")
            btn.clicked.connect(lambda _=False, p=path: self.recentRequested.emit(p))
            self._recent_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)


def _build_first_run_hint() -> QWidget:
    """Ilk kullanimda uc kisa adim."""
    box = QWidget()
    box.setObjectName("PanelCard")
    lay = QHBoxLayout(box)
    lay.setContentsMargins(SPACE.lg, SPACE.md, SPACE.lg, SPACE.md)
    lay.setSpacing(SPACE.xl)

    steps = [
        ("1", "Fotografini ekle", "Surukle birak veya dosya seç"),
        ("2", "Görünümü seç", "Preset dene, ayarları ince ayarla"),
        ("3", "Çıktı al", "Orijinal korunur, kopyasi kaydedilir"),
    ]
    for number, title, detail in steps:
        col = QVBoxLayout()
        col.setSpacing(1)
        head = QLabel(f"{number}.  {title}")
        head.setObjectName("PanelHeading")
        sub = QLabel(detail)
        sub.setObjectName("Muted")
        col.addWidget(head)
        col.addWidget(sub)
        lay.addLayout(col)
    lay.addStretch(1)
    box.setMaximumHeight(METRICS.nav_height + 32)
    return box

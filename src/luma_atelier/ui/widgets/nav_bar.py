"""Ust gezinti serisi: calisma alanlari arasinda gecis.

Sekme gorunumu yerine ozel cizim: aktif alanin altinda ince bakir cizgi,
devre disi alanlar sonuk. Ayni serit sagda baglama duyarli eylemleri
tasir.
"""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from luma_atelier.core.branding import APP_NAME
from luma_atelier.ui.theme.tokens import METRICS, PALETTE, SPACE, TYPE


class Workspace(str, Enum):
    """Uygulamanin ana calisma alanlari."""

    START = "start"
    LIBRARY = "library"
    EDITOR = "editor"
    CINEMA = "cinema"
    EXPORT = "export"
    SETTINGS = "settings"

    @property
    def label(self) -> str:
        return {
            Workspace.START: "Başlangıç",
            Workspace.LIBRARY: "Kitaplık",
            Workspace.EDITOR: "Düzenleyici",
            Workspace.CINEMA: "Sinema Laboratuvarı",
            Workspace.EXPORT: "Dışa Aktar",
            Workspace.SETTINGS: "Ayarlar",
        }[self]

    @property
    def short_label(self) -> str:
        """Dar ekranlarda kullanilan kisa ad.

        Gezinti seridi sigmadiginda tam adlar yerine bunlar gosterilir;
        boylece hicbir sekme gizlenmek zorunda kalmaz.
        """
        return {
            Workspace.START: "Başlangıç",
            Workspace.LIBRARY: "Kitaplık",
            Workspace.EDITOR: "Düzenle",
            Workspace.CINEMA: "Sinema",
            Workspace.EXPORT: "Aktar",
            Workspace.SETTINGS: "Ayarlar",
        }[self]

    @property
    def shortcut(self) -> str:
        return {
            Workspace.START: "Ctrl+1",
            Workspace.LIBRARY: "Ctrl+2",
            Workspace.EDITOR: "Ctrl+3",
            Workspace.CINEMA: "Ctrl+4",
            Workspace.EXPORT: "Ctrl+5",
            Workspace.SETTINGS: "Ctrl+,",
        }[self]


class NavButton(QWidget):
    """Tek bir calisma alani dugmesi."""

    clicked = Signal(Workspace)

    def __init__(self, workspace: Workspace, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self._active = False
        self._hover = False
        self._enabled_state = True
        self._compact = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(METRICS.nav_height)
        self.setToolTip(f"{workspace.label}  ({workspace.shortcut})")
        self.setAccessibleName(workspace.label)
        self._apply_width()

    def _font(self) -> QFont:
        f = QFont()
        f.setPixelSize(TYPE.size_label)
        f.setWeight(QFont.Weight.DemiBold if self._active else QFont.Weight.Medium)
        return f

    def displayText(self) -> str:  # noqa: N802
        """Ekranda gosterilecek metin; kompakt kipte kisa ad."""
        return (self.workspace.short_label if self._compact
                else self.workspace.label)

    def setCompact(self, value: bool) -> None:  # noqa: N802
        """Dar seritte kisa etikete gecer."""
        if value != self._compact:
            self._compact = value
            self._apply_width()
            self.update()

    def naturalWidth(self, compact: bool) -> int:  # noqa: N802
        """Bu dugmenin verilen kipte isteyecegi genislik.

        Kompakt kipte yanlardaki dolgu da daralir; dar seritte her
        piksel menu cubugundan arta kalandir.
        """
        from PySide6.QtGui import QFontMetrics

        text = (self.workspace.short_label if compact
                else self.workspace.label)
        padding = SPACE.md if compact else SPACE.xl
        return QFontMetrics(self._font()).horizontalAdvance(text) + padding

    def _apply_width(self) -> None:
        self.setFixedWidth(self.naturalWidth(self._compact))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def setActive(self, value: bool) -> None:  # noqa: N802
        if value != self._active:
            self._active = value
            self._apply_width()
            self.update()

    def setAvailable(self, value: bool) -> None:  # noqa: N802
        """Fotograf yokken duzenleyici gibi alanlar erisilemez olur."""
        if value != self._enabled_state:
            self._enabled_state = value
            self.setCursor(Qt.CursorShape.PointingHandCursor if value
                           else Qt.CursorShape.ForbiddenCursor)
            self.update()

    def isAvailable(self) -> bool:  # noqa: N802
        return self._enabled_state

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled_state:
            self.clicked.emit(self.workspace)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._enabled_state:
                self.clicked.emit(self.workspace)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())

        if not self._enabled_state:
            color = PALETTE.text_disabled
        elif self._active:
            color = PALETTE.text_primary
        elif self._hover:
            color = PALETTE.text_primary
        else:
            color = PALETTE.text_muted

        if self._hover and self._enabled_state and not self._active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE.bg_hover))
            p.drawRoundedRect(rect.adjusted(2, 6, -2, -8), 5, 5)

        if self.hasFocus():
            p.setPen(QColor(PALETTE.accent))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1.5, 5.5, -1.5, -7.5), 5, 5)

        p.setFont(self._font())
        p.setPen(QColor(color))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self.displayText())

        if self._active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE.accent))
            p.drawRoundedRect(
                QRectF(rect.left() + 6, rect.bottom() - 3,
                       rect.width() - 12, 2.0), 1, 1
            )
        p.end()


class NavBar(QWidget):
    """Ust serit: marka, calisma alanlari, baglama eylemleri."""

    workspaceRequested = Signal(Workspace)
    undoRequested = Signal()
    redoRequested = Signal()

    ORDER = (Workspace.START, Workspace.LIBRARY, Workspace.EDITOR,
             Workspace.CINEMA, Workspace.EXPORT, Workspace.SETTINGS)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavBar")
        self.setFixedHeight(METRICS.nav_height)
        self.setAutoFillBackground(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(SPACE.md, 0, SPACE.lg, 0)
        lay.setSpacing(SPACE.xxs)
        self._layout = lay

        self.brand = QLabel(APP_NAME)
        self.brand.setObjectName("PanelHeading")
        lay.addWidget(self.brand)
        lay.addSpacing(SPACE.lg)

        # Menu cubugu icin yer tutucu. Ayri bir satir yerine ayni seride
        # durur: iki gezinti sirasi hem yer harcar hem kalabalik gorunur.
        self._menu_slot = 2
        lay.addSpacing(SPACE.md)

        self._buttons: dict[Workspace, NavButton] = {}
        for ws in self.ORDER:
            btn = NavButton(ws)
            btn.clicked.connect(self.workspaceRequested)
            lay.addWidget(btn)
            self._buttons[ws] = btn

        lay.addStretch(1)

        self.undo_button = QPushButton("Geri al")
        self.undo_button.setObjectName("GhostButton")
        self.undo_button.setToolTip("Son işlemi geri al  (Ctrl+Z)")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undoRequested)

        self.redo_button = QPushButton("Yinele")
        self.redo_button.setObjectName("GhostButton")
        self.redo_button.setToolTip("Geri alınanı yinele  (Ctrl+Y)")
        self.redo_button.setEnabled(False)
        self.redo_button.clicked.connect(self.redoRequested)

        lay.addWidget(self.undo_button)
        lay.addWidget(self.redo_button)

        self._menubar: QWidget | None = None
        self.setActive(Workspace.START)

    # ------------------------------------------------- uyarlanir yerlesim
    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        """Serit sigmadiginda kademeli olarak sadelesir.

        Sira: tam etiket -> kisa etiket -> markayi gizle -> geri al/yinele
        dugmelerini simgeye indir. Hicbir asamada sekme gizlenmez; bir
        calisma alanina ulasilamamak islev kaybi olurdu.
        """
        available = self.width()
        if available <= 0:
            return

        gaps = SPACE.md * 2 + SPACE.lg + SPACE.xxs * (len(self._buttons) + 4)
        if self._menubar is not None:
            gaps += self._menubar.sizeHint().width()

        def tabs(compact: bool) -> int:
            return sum(b.naturalWidth(compact) for b in self._buttons.values())

        brand = self.brand.sizeHint().width() + SPACE.lg
        actions = (self.undo_button.sizeHint().width()
                   + self.redo_button.sizeHint().width())

        if gaps + brand + tabs(False) + actions <= available:
            self._apply_tier(compact=False, show_brand=True, icons=False)
        elif gaps + brand + tabs(True) + actions <= available:
            self._apply_tier(compact=True, show_brand=True, icons=False)
        elif gaps + tabs(True) + actions <= available:
            self._apply_tier(compact=True, show_brand=False, icons=False)
        else:
            self._apply_tier(compact=True, show_brand=False, icons=True)

    def _apply_tier(self, *, compact: bool, show_brand: bool,
                    icons: bool) -> None:
        for button in self._buttons.values():
            button.setCompact(compact)
        self.brand.setVisible(show_brand)
        self.undo_button.setText("↶" if icons else "Geri al")
        self.redo_button.setText("↷" if icons else "Yinele")

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """En dar kipte gereken genislik.

        Varsayilan `minimumSizeHint` cocuklarin *o anki* sabit
        genisliklerini toplar; serit o yuzden hicbir zaman kuculemez
        gorunurdu ve pencere onu tasirdi.
        """
        width = sum(b.naturalWidth(True) for b in self._buttons.values())
        width += SPACE.md * 2 + SPACE.xxs * (len(self._buttons) + 4)
        width += 2 * (METRICS.control_height_sm + SPACE.lg)
        if self._menubar is not None:
            width += self._menubar.sizeHint().width()
        return QSize(width, METRICS.nav_height)

    def embedMenuBar(self, menubar: QWidget) -> None:  # noqa: N802
        """Menu cubugunu gezinti seridinin icine yerlestirir.

        Ayri bir QMenuBar satiri yerine ayni serit kullanilir; Alt tusu
        erisimi korunur ama dikeyde bir satir kazanilir.
        """
        menubar.setParent(self)
        menubar.setFixedHeight(METRICS.nav_height)
        self._layout.insertWidget(self._menu_slot, menubar)
        self._menubar = menubar
        self._relayout()

    def setActive(self, workspace: Workspace) -> None:  # noqa: N802
        for ws, btn in self._buttons.items():
            btn.setActive(ws is workspace)

    def setAvailable(self, workspace: Workspace, value: bool) -> None:  # noqa: N802
        self._buttons[workspace].setAvailable(value)

    def isAvailable(self, workspace: Workspace) -> bool:  # noqa: N802
        return self._buttons[workspace].isAvailable()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(PALETTE.bg_panel))
        p.setPen(QColor(PALETTE.border_subtle))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

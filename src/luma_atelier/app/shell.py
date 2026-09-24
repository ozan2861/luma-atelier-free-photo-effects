"""Ana pencere kabugu.

Calisma alanlarini (baslangic, kitaplik, duzenleyici, sinema, disa
aktarma, ayarlar) tek pencerede toplar; sürükle-bırak, kısayollar,
durum cubugu ve hata bildirimlerini yonetir.

Faz 1'de duzenleyici yalnizca tuval + gezinme icerir; ton/renk araclari
Faz 2'de eklenir. Henuz calismayan alanlar **dugme olarak gosterilmez**;
erisilemez isaretlenir ve nedeni durum cubuginda yazar.
"""
from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import (
    QByteArray,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.branding import APP_NAME, APP_VERSION
from luma_atelier.core.paths import cache_dir, pictures_dir, resources_dir
from luma_atelier.core.settings import (
    cache_folder_size,
    clear_cache,
    load_settings,
    save_settings,
)
from luma_atelier.core.session import ImportReport, Session
from luma_atelier.imaging.loader import ImageLoadError, load_image
from luma_atelier.services.thumbnails import ThumbnailService
from luma_atelier.ui.theme.stylesheet import build_stylesheet
from luma_atelier.ui.theme.tokens import METRICS, SPACE
from luma_atelier.core.document import Document
from luma_atelier.services.preset_previews import PresetPreviewService
from luma_atelier.services.render import RenderService
from luma_atelier.storage.presets import Preset, PresetLibrary, slugify
from luma_atelier.ui.views.editor_view import EditorView
from luma_atelier.ui.views.library_view import LibraryView
from luma_atelier.ui.views.start_view import StartView
from luma_atelier.services.export import (
    ExportJob,
    ExportQueue,
    ExportSummary,
)
from luma_atelier.ui.views.export_view import ExportView
from luma_atelier.ui.views.settings_view import SettingsView
from luma_atelier.ui.widgets.nav_bar import NavBar, Workspace

log = logging.getLogger(__name__)

#: Proje acilirken kaynagin nasil bulunduguna gore durum metni
PROJECT_STATUS = {
    "ok": "Proje açıldı: {name}",
    "embedded": "Proje açıldı: {name}  ·  fotoğraf projeden çıkarıldı",
    "relocated": "Proje açıldı: {name}  ·  fotoğraf yeni konumunda bulundu",
    "changed": "Proje açıldı: {name}  ·  kaynak fotoğraf değişmiş",
}

#: Otomatik kurtarma yazma araligi
AUTOSAVE_INTERVAL_MS = 45_000

IMAGE_FILTER = (
    "Fotoğraflar (*.jpg *.jpeg *.jpe *.png *.webp *.tif *.tiff *.bmp);;"
    "JPEG (*.jpg *.jpeg);;PNG (*.png);;WebP (*.webp);;TIFF (*.tif *.tiff);;"
    "Tüm dosyalar (*)"
)


class _LoadSignals(QObject):
    #: jeton, yol, pikseller, metadata
    done = Signal(int, str, object, object)
    #: jeton, yol, mesaj
    failed = Signal(int, str, str)


class _LoadTask(QRunnable):
    """Tam boy fotografi arka planda okur - UI donmasin.

    Sonuc **jetonla** birlikte gelir. Jeton olmadan, terk edilmis bir
    yuklemenin sonucu (ozellikle hata sonucu) kullanicinin o an actigi
    fotografin uzerine yazabiliyordu.
    """

    def __init__(self, path: Path, signals: _LoadSignals, token: int) -> None:
        super().__init__()
        self._path = path
        self._signals = signals
        self._token = token
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        try:
            loaded = load_image(self._path)
            self._signals.done.emit(self._token, str(self._path),
                                    loaded.pixels, loaded.metadata)
        except ImageLoadError as exc:
            self._signals.failed.emit(self._token, str(self._path), str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Fotograf yuklenemedi: %s", self._path)
            self._signals.failed.emit(self._token, str(self._path),
                                      f"Beklenmeyen hata: {exc}")


class PlaceholderView(QWidget):
    """Henuz gelistirilmemis calisma alani icin durum ekrani.

    Calismayan dugme gostermez; yalnizca hangi fazda gelecegini soyler.
    """

    def __init__(self, title: str, message: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(SPACE.sm)
        head = QLabel(title)
        head.setObjectName("SectionTitle")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(message)
        body.setObjectName("Muted")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        body.setMaximumWidth(460)
        lay.addWidget(head)
        lay.addWidget(body)


#: Bu sayidan itibaren disa aktarma "cok sayida" sayilir ve
#: (ayar aciksa) onay istenir.
LARGE_EXPORT_COUNT = 20


class MainWindow(QMainWindow):
    """Luma Atelier ana penceresi."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(METRICS.window_min_width, METRICS.window_min_height)
        self.resize(METRICS.window_default_width, METRICS.window_default_height)
        self.setAcceptDrops(True)

        icon_path = resources_dir() / "icons" / "app.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Ayarlar arayuzden **once** yuklenir; onizleme kalitesi ve
        # kurtarma araligi gibi degerler kurulum sirasinda kullanilir.
        self.settings = load_settings()
        self._restore_geometry()

        self.session = Session()
        self.thumbnails = ThumbnailService(self)
        self.renderer = RenderService(self)
        self.preset_previews = PresetPreviewService(self)
        self.presets = PresetLibrary()
        self._preset_report = self.presets.load_all()
        self.document: Document | None = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._load_signals = _LoadSignals()
        self._load_signals.done.connect(self._on_photo_loaded,
                                        Qt.ConnectionType.QueuedConnection)
        self._load_signals.failed.connect(self._on_photo_failed,
                                          Qt.ConnectionType.QueuedConnection)
        self._load_token = 0
        self._current_pixels: np.ndarray | None = None
        self._current_path: Path | None = None
        #: Yuklenmesi *istenen* yol. `_current_path` yalnizca yukleme
        #: bittiginde yazilir; ikisini ayirmak cift yuklemeyi ve
        #: ileri-geri sikismasini onler.
        self._requested_path: Path | None = None
        self._busy_since = 0.0

        self._build_ui()
        self._build_actions()
        self.session.add_listener(self._on_session_changed)
        self._on_session_changed()

    # ------------------------------------------------------------- yerlesim
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavBar()
        self.nav.workspaceRequested.connect(self.show_workspace)
        self.nav.undoRequested.connect(self._undo)
        self.nav.redoRequested.connect(self._redo)
        root.addWidget(self.nav)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.start_view = StartView()
        self.start_view.filesDropped.connect(self._import_paths)
        self.start_view.openFilesRequested.connect(self._choose_files)
        self.start_view.openFolderRequested.connect(self._choose_folder)
        self.start_view.openProjectRequested.connect(self._open_project)

        self.library_view = LibraryView(self.session, self.thumbnails)
        self.library_view.photoActivated.connect(self._open_in_editor)
        self.library_view.relocateRequested.connect(self._relocate)

        self.editor_view = EditorView(self.renderer, self.presets,
                                      self.preset_previews)
        self.editor_view.requestPrevious.connect(self._go_previous)
        self.editor_view.requestNext.connect(self._go_next)
        self.editor_view.statusMessage.connect(self._set_status)
        self.editor_view.savePresetRequested.connect(self._save_user_preset)
        self.editor_view.presets.importPresetRequested.connect(
            self._import_preset)
        self.editor_view.presets.exportPresetRequested.connect(
            self._export_preset)
        self.editor_view.presets.deletePresetRequested.connect(
            self._delete_preset)

        # Sinema Laboratuvari: ayni belge, farkli arac seti.
        # Ekran degisince duzenlemeler kaybolmaz.
        self.cinema_view = EditorView(self.renderer, self.presets,
                                      self.preset_previews, cinema=True)
        self.cinema_view.requestPrevious.connect(self._go_previous)
        self.cinema_view.requestNext.connect(self._go_next)
        self.cinema_view.statusMessage.connect(self._set_status)
        self.cinema_view.savePresetRequested.connect(self._save_user_preset)
        self.cinema_view.presets.importPresetRequested.connect(
            self._import_preset)
        self.cinema_view.presets.exportPresetRequested.connect(
            self._export_preset)
        self.cinema_view.presets.deletePresetRequested.connect(
            self._delete_preset)

        for view in (self.editor_view, self.cinema_view):
            view.attachFilmstrip(self.session, self.thumbnails)
            view.photoRequested.connect(self._open_in_editor)
            view.favouriteToggled.connect(self._toggle_favourite_path)

        self.export_view = ExportView()
        self.export_view.exportRequested.connect(self._start_export)
        self.export_view.cancelRequested.connect(self._cancel_export)
        self.export_view.retryRequested.connect(self._retry_export)
        self.export_view.openFolderRequested.connect(self._open_folder)
        self.export_view.statusMessage.connect(self._set_status)

        self.export_queue = ExportQueue(self)
        self.export_queue.started.connect(self.export_view.onQueueStarted)
        self.export_queue.itemStarted.connect(self.export_view.onItemStarted)
        self.export_queue.itemFinished.connect(self.export_view.onItemFinished)
        self.export_queue.progress.connect(self.export_view.onProgress)
        self.export_queue.finished.connect(self._on_export_finished)
        self.settings_view = SettingsView()
        self.settings_view.settingsChanged.connect(self._apply_settings)
        self.settings_view.clearCacheRequested.connect(self._clear_cache)
        self.settings_view.openFolderRequested.connect(self._open_folder)
        self.settings_view.statusMessage.connect(self._set_status)

        self._pages: dict[Workspace, QWidget] = {
            Workspace.START: self.start_view,
            Workspace.LIBRARY: self.library_view,
            Workspace.EDITOR: self.editor_view,
            Workspace.CINEMA: self.cinema_view,
            Workspace.EXPORT: self.export_view,
            Workspace.SETTINGS: self.settings_view,
        }
        for page in self._pages.values():
            self.stack.addWidget(page)

        self.setCentralWidget(central)
        self._build_statusbar()
        self._pending_project = None
        self._project_path: Path | None = None
        #: Bu oturumda kurtarma kaydi yazilan kaynaklar. Uygulamanin
        #: kendi yazdigi kayit icin 'geri yuklensin mi?' diye sormak
        #: anlamsizdir; cokme olmamistir.
        self._session_autosaves: set[Path] = set()

        # Otomatik kurtarma: normal kaydin yerine gecmez, ayri dosyaya yazar
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave_tick)

        self._apply_settings(self.settings, persist=False)
        self.settings_view.setSettings(self.settings)

        self.show_workspace(Workspace.START)

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        bar.setSizeGripEnabled(True)
        self.status_message = QLabel("Hazir")
        self.status_detail = QLabel("")
        self.status_detail.setObjectName("Muted")
        bar.addWidget(self.status_message, 1)
        bar.addPermanentWidget(self.status_detail)
        self.setStatusBar(bar)

    def _build_actions(self) -> None:
        def add(text: str, shortcut: str, slot, tip: str = "") -> QAction:  # noqa: ANN001
            act = QAction(text, self)
            act.setShortcut(QKeySequence(shortcut))
            act.setStatusTip(tip or text)
            act.triggered.connect(slot)
            self.addAction(act)
            return act

        from PySide6.QtWidgets import QMenuBar

        # Menu cubugu QMainWindow'un kendi satirinda degil, gezinti
        # seridinin icinde durur (bkz. NavBar.embedMenuBar).
        menu = QMenuBar(self)
        menu.setNativeMenuBar(False)
        self._menu_bar = menu
        self.nav.embedMenuBar(menu)

        file_menu = menu.addMenu("&Dosya")
        file_menu.setToolTipsVisible(True)
        file_menu.addAction(add("Fotoğraf aç...", "Ctrl+O", self._choose_files,
                                "Bir veya birden fazla fotoğraf ekle"))
        file_menu.addAction(add("Klasör ekle...", "Ctrl+Shift+O",
                                lambda: self._choose_folder(False),
                                "Bir klasördeki fotoğrafları ekle"))
        file_menu.addSeparator()
        file_menu.addAction(add("Proje aç...", "Ctrl+Shift+P", self._open_project,
                                "Kaydedilmiş .luma projesini aç"))
        self.save_project_action = add(
            "Projeyi kaydet", "Ctrl+Shift+S", self._save_project,
            "Duzenlemeleri .luma projesi olarak kaydet")
        self.save_project_action.setEnabled(False)
        file_menu.addAction(self.save_project_action)
        self.save_project_as_action = add(
            "Projeyi farklı kaydet...", "Ctrl+Alt+S",
            lambda: self._save_project(ask=True),
            "Projeyi yeni bir dosyaya kaydet")
        self.save_project_as_action.setEnabled(False)
        file_menu.addAction(self.save_project_as_action)
        file_menu.addSeparator()
        self.save_action = add("Kopya olarak kaydet...", "Ctrl+S", self._save_copy,
                               "Düzenlenmiş fotoğrafı yeni dosyaya yaz")
        self.save_action.setEnabled(False)
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        file_menu.addAction(add("Çıkış", "Ctrl+Q", self.close, "Uygulamayı kapat"))

        view_menu = menu.addMenu("&Görünüm")
        view_menu.setToolTipsVisible(True)
        for ws in NavBar.ORDER:
            view_menu.addAction(
                add(ws.label, ws.shortcut,
                    lambda _=False, w=ws: self.show_workspace(w))
            )
        view_menu.addSeparator()
        self.filmstrip_action = add(
            "Film şeridi", "T", self._toggle_filmstrip,
            "Fotoğraflar arasında hızlı geçiş şeridini gösterir veya gizler")
        self.filmstrip_action.setCheckable(True)
        self.filmstrip_action.setChecked(True)
        view_menu.addAction(self.filmstrip_action)
        view_menu.addSeparator()
        view_menu.addAction(add("Ekrana sığdır", "0",
                                self.editor_view.canvas.zoomToFit))
        view_menu.addAction(add("Gerçek piksel (%100)", "1",
                                self.editor_view.canvas.zoomToActualPixels))
        view_menu.addAction(add("Yakınlaştır", "+",
                                lambda: self.editor_view.canvas.zoomIn()))
        view_menu.addAction(add("Uzaklaştır", "-",
                                lambda: self.editor_view.canvas.zoomOut()))

        edit_menu = menu.addMenu("&Düzenle")
        edit_menu.setToolTipsVisible(True)
        self.undo_action = add("Geri al", "Ctrl+Z", self._undo,
                               "Son duzenlemeyi geri al")
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)
        self.redo_action = add("Yinele", "Ctrl+Y", self._redo,
                               "Geri alinan duzenlemeyi yinele")
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        self.reset_action = add("Tüm ayarları sıfırla", "Ctrl+Shift+R",
                                self._reset_all, "Tarifi temizler")
        self.reset_action.setEnabled(False)
        edit_menu.addAction(self.reset_action)
        edit_menu.addSeparator()
        self.copy_recipe_action = add("Ayarları kopyala", "Ctrl+Shift+C",
                                      self._copy_recipe,
                                      "Bu fotografin tarifini panoya alir")
        self.copy_recipe_action.setEnabled(False)
        edit_menu.addAction(self.copy_recipe_action)
        self.paste_recipe_action = add("Ayarları yapıştır", "Ctrl+Shift+V",
                                       self._paste_recipe,
                                       "Kopyalanan tarifi bu fotoğrafa uygular")
        self.paste_recipe_action.setEnabled(False)
        edit_menu.addAction(self.paste_recipe_action)

        photo_menu = menu.addMenu("&Fotoğraf")
        photo_menu.setToolTipsVisible(True)
        photo_menu.addAction(add("Önceki fotoğraf", "Left", self._go_previous))
        photo_menu.addAction(add("Sonraki fotoğraf", "Right", self._go_next))
        photo_menu.addAction(add("Favoriye ekle / çıkar", "F",
                                 self._toggle_favourite))

        help_menu = menu.addMenu("&Yardım")
        help_menu.setToolTipsVisible(True)
        help_menu.addAction(add("Günlük klasörünü aç", "",
                                self._open_log_folder,
                                "Hata günlüklerinin bulunduğu klasörü açar"))
        help_menu.addAction(add(f"{APP_NAME} hakkında", "", self._about))

    # ------------------------------------------------------------ gezinme
    def show_workspace(self, workspace: Workspace) -> None:
        """Calisma alanina gecer. Erisilemez alanlar sessizce yutulmaz."""
        if not self.nav.isAvailable(workspace):
            self._set_status(
                "Bu bolum için önce bir fotoğraf ekleyin.", detail=""
            )
            return
        self.stack.setCurrentWidget(self._pages[workspace])
        self.nav.setActive(workspace)
        if workspace is Workspace.EXPORT:
            self._refresh_export_context()
        if workspace is Workspace.SETTINGS:
            self.settings_view.setSettings(self.settings)
            self.settings_view.setCacheSize(cache_folder_size())
        if workspace in (Workspace.EDITOR, Workspace.CINEMA):
            # Kitaplikta tek tiklama etkin fotografi degistirir ama
            # yuklemez. Buraya gecerken esitlemezsek ekranda eski
            # fotograf kalir, konum etiketi ve ok tuslari yenisini
            # gosterir; kullanici gordugunden baska fotografi duzenler.
            self._load_current()
            view = (self.editor_view if workspace is Workspace.EDITOR
                    else self.cinema_view)
            view.canvas.setFocus()
            if self.document is not None:
                view.refreshPreview()

    # ------------------------------------------------------- ice aktarma
    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Fotoğraf seç", str(pictures_dir()), IMAGE_FILTER
        )
        if paths:
            self._import_paths([Path(p) for p in paths])

    def _choose_folder(self, recursive: bool) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Klasör seç", str(pictures_dir())
        )
        if not folder:
            return
        self._set_status("Klasör taraniyor...")
        QApplication.processEvents()
        report = self.session.add_paths([Path(folder)], recursive=recursive)
        self._report_import(report)

    def _import_paths(self, paths: list[Path]) -> None:
        if not paths:
            return
        # Proje dosyalari fotograf degildir: kitaplia eklenmeye
        # calisilirsa "desteklenmeyen bicim" diye reddedilirler.
        # Kurulum `.luma` iliskilendirmesini kaydettigi icin bu yol
        # gercek bir kullanici yolu (dosyaya cift tiklama).
        from luma_atelier.core.branding import PROJECT_EXTENSION

        projects = [p for p in paths
                    if p.suffix.lower() == PROJECT_EXTENSION.lower()]
        photos = [p for p in paths if p not in projects]
        for project in projects:
            self._open_project_path(project)
        if not photos:
            return
        self._set_status("Fotoğraflar ekleniyor...")
        QApplication.processEvents()
        recursive = self.start_view.recursive_check.isChecked()
        report = self.session.add_paths(paths, recursive=recursive)
        self._report_import(report)

    def _report_import(self, report: ImportReport) -> None:
        self._set_status(report.summary())
        if report.added:
            first = report.added[0]
            if self._current_path is None:
                self._open_in_editor(first.path)
            else:
                self.show_workspace(Workspace.LIBRARY)
        if report.has_problems:
            self._show_import_problems(report)

    def _show_import_problems(self, report: ImportReport) -> None:
        lines: list[str] = []
        if report.unsupported:
            lines.append(
                f"Desteklenmeyen biçim ({len(report.unsupported)}):\n  "
                + "\n  ".join(p.name for p in report.unsupported[:8])
            )
        if report.failed:
            lines.append(
                f"Okunamayan dosya ({len(report.failed)}):\n  "
                + "\n  ".join(f"{p.name} — {msg}" for p, msg in report.failed[:8])
            )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Bazı dosyalar eklenemedi")
        box.setText(report.summary())
        box.setInformativeText("\n\n".join(lines))
        box.exec()

    # -------------------------------------------------------- fotograf ac
    def _open_in_editor(self, path: Path) -> None:
        """Fotografi duzenleyicide acar.

        `_load_current` **bir kez** cagrilir. `set_current` oturum
        bildirimi uzerinden zaten `_load_current`'a varabiliyor;
        ayrica burada cagirmak ayni fotografi iki kez yukletiyordu.
        Artik `_load_current` kendi basina yinelemeye karsi korumali
        (`_requested_path`), bu yuzden iki yol da guvenli.
        """
        index = self.session.index_of(path)
        if index >= 0:
            self.session.set_current(index)
        self._load_current()
        self.show_workspace(Workspace.EDITOR)

    def _load_current(self) -> None:
        """Etkin fotografi yukler.

        **Istenen** yol (`_requested_path`) ile **yuklenmis** yol
        (`_current_path`) ayri tutulur. Tek bir alan kullanmak iki
        hataya yol aciyordu: ayni fotograf iki kez yukleniyordu (cunku
        yukleme bitene kadar alan guncellenmiyordu) ve A->B->A hizli
        gecisinde yukleme hic baslamayip duzenleyici bos kaliyordu.
        """
        entry = self.session.current
        if entry is None:
            self.editor_view.canvas.clear()
            self._current_pixels = None
            self._current_path = None
            self._requested_path = None
            return
        if entry.path == self._requested_path:
            return      # bu fotograf zaten yuklendi veya yukleniyor

        self._requested_path = entry.path
        self.document = None
        self.save_action.setEnabled(False)
        self.editor_view.setDocument(None)
        self.cinema_view.setDocument(None)
        self._load_token += 1
        self._busy_since = time.perf_counter()
        self._set_status(f"{entry.name} yükleniyor...")
        self.editor_view.canvas.setPlaceholder("Yükleniyor...")
        self._pool.start(_LoadTask(entry.path, self._load_signals, self._load_token))

    def _on_photo_loaded(self, token: int, path: str, pixels: object,
                         metadata: object) -> None:
        if token != self._load_token:
            return  # terk edilmis yukleme; kullanici baska fotografa gecti
        entry = self.session.current
        if entry is None or str(entry.path) != path:
            return
        if not isinstance(pixels, np.ndarray):
            raise TypeError("pixels must be a NumPy array")
        self._current_pixels = pixels
        self._current_path = Path(path)
        self._requested_path = Path(path)

        from luma_atelier.imaging.loader import LoadedImage
        self.document = Document(LoadedImage(pixels=pixels, metadata=metadata))
        self.document.add_listener(self._on_document_changed)
        self.editor_view.setDocument(self.document)
        self.cinema_view.setDocument(self.document)
        self.save_action.setEnabled(True)
        if self._pending_project is None:
            self._project_path = None
        self._refresh_project_actions()
        self._apply_pending_project()
        self._offer_recovery()

        ms = (time.perf_counter() - self._busy_since) * 1000
        m = metadata
        detail = (
            f"{getattr(m, 'width', 0)} × {getattr(m, 'height', 0)}  ·  "
            f"{getattr(m, 'source_format', '')} {getattr(m, 'source_bit_depth', 8)}-bit"
        )
        if getattr(m, "has_alpha", False):
            detail += "  ·  saydam"
        if getattr(m, "orientation_applied", False):
            detail += f"  ·  EXIF yön {getattr(m, 'exif_orientation', 1)} uygulandı"
        if getattr(m, "assumed_srgb", True):
            detail += "  ·  sRGB varsayıldı"
        else:
            detail += f"  ·  {getattr(m, 'icc_description', 'ICC')}"
        self.status_detail.setText(detail)
        self._set_status(f"{Path(path).name} açıldı  ({ms:.0f} ms)", keep_detail=True)
        self.setWindowTitle(f"{Path(path).name} — {APP_NAME} {APP_VERSION}")
        self._update_position()

    def _on_photo_failed(self, token: int, path: str, message: str) -> None:
        if token != self._load_token:
            # Terk edilmis bir yuklemenin hatasi. Jeton kontrolu olmadan
            # bu, kullanicinin o an actigi saglam fotografin tuvalini
            # temizliyor ve yanlis fotograf icin uyari gosteriyordu.
            log.debug("Eski yukleme hatasi yok sayildi: %s", path)
            return
        self._requested_path = None
        self.editor_view.canvas.clear()
        self.editor_view.canvas.setPlaceholder(message)
        self._set_status(message)
        self.save_action.setEnabled(False)
        QMessageBox.warning(self, "Fotoğraf açılamadı", message)

    # --------------------------------------------------------- gezinme
    def _go_previous(self) -> None:
        if self.session.previous_photo():
            self._load_current()

    def _go_next(self) -> None:
        if self.session.next_photo():
            self._load_current()

    def _update_position(self) -> None:
        self.editor_view.set_position(
            self.session.current_index, len(self.session),
            self.session.can_go_previous(), self.session.can_go_next(),
        )

    def _toggle_favourite(self) -> None:
        idx = self.session.current_index
        if idx < 0:
            return
        now = self.session.toggle_favourite(idx)
        name = self.session.current.name if self.session.current else ""
        self._set_status(
            f"{name} favorilere eklendi" if now else f"{name} favorilerden cikarildi"
        )

    # ---------------------------------------------------------- duzenleme
    def _undo(self) -> None:
        if self.document is not None and self.document.undo():
            self._set_status(f"Geri alindi: {self.document.history.redo_label()}")

    def _redo(self) -> None:
        if self.document is not None and self.document.redo():
            self._set_status(f"Yinelendi: {self.document.history.current_label}")

    def _reset_all(self) -> None:
        if self.document is not None:
            self.document.reset_all()
            self.document.commit()
            self._set_status("Tüm ayarlar sıfırlandı")

    def _copy_recipe(self) -> None:
        if self.document is None:
            return
        self._clipboard_recipe = self.document.copy_recipe()
        self.paste_recipe_action.setEnabled(True)
        self._set_status(
            f"{len(self._clipboard_recipe)} ayar kopyalandi. "
            "Başka bir fotografta Ctrl+Shift+V ile uygulayin."
        )

    def _paste_recipe(self) -> None:
        recipe = getattr(self, "_clipboard_recipe", None)
        if self.document is None or recipe is None:
            return
        self.document.paste_recipe(recipe)
        self.document.commit()
        self._set_status(f"{len(recipe)} ayar uygulandı")

    def _on_document_changed(self) -> None:
        doc = self.document
        has_doc = doc is not None
        self.undo_action.setEnabled(has_doc and doc.can_undo())
        self.redo_action.setEnabled(has_doc and doc.can_redo())
        self.nav.undo_button.setEnabled(has_doc and doc.can_undo())
        self.nav.redo_button.setEnabled(has_doc and doc.can_redo())
        self.reset_action.setEnabled(has_doc and doc.has_edits)
        self.copy_recipe_action.setEnabled(has_doc and doc.has_edits)
        if has_doc:
            self.nav.undo_button.setToolTip(
                f"Geri al: {doc.history.undo_label()}  (Ctrl+Z)"
                if doc.can_undo() else "Geri alınacak işlem yok"
            )
            self.nav.redo_button.setToolTip(
                f"Yinele: {doc.history.redo_label()}  (Ctrl+Y)"
                if doc.can_redo() else "Yinelenecek işlem yok"
            )
            self._update_title_modified()

    def _update_title_modified(self) -> None:
        doc = self.document
        if doc is None:
            return
        mark = " •" if doc.is_modified else ""
        self.setWindowTitle(f"{doc.path.name}{mark} — {APP_NAME} {APP_VERSION}")

    # ---------------------------------------------------------- presetler
    def _active_editor(self) -> EditorView:
        """Su an gorunur olan duzenleyici (normal veya sinema)."""
        current = self.stack.currentWidget()
        return self.cinema_view if current is self.cinema_view else self.editor_view

    def _save_user_preset(self) -> None:
        """Mevcut ayarlari kullanicinin kendi gorunumu olarak kaydeder."""
        from PySide6.QtWidgets import QInputDialog

        if self.document is None or self.document.recipe.is_empty:
            QMessageBox.information(
                self, "Kaydedilecek ayar yok",
                "Önce bir görünüm seçin veya ayar yapın.",
            )
            return

        name, ok = QInputDialog.getText(
            self, "Görünümü kaydet", "Görünüm adı:",
            text="Kendi görünümüm",
        )
        if not ok or not name.strip():
            return

        editor = self._active_editor()
        category = "cinema" if editor is self.cinema_view else "creative"
        preset_id = slugify(name)
        if self.presets.get(preset_id) is not None:
            preset_id = f"{preset_id}-{len(self.presets)}"

        preset = Preset(
            preset_id=preset_id, name=name.strip(), category=category,
            description="Kendi kaydettiğiniz görünüm.",
            recipe=self.document.recipe, builtin=False,
            intent="", tags=("kullanici",),
        )
        try:
            path = self.presets.save_user_preset(preset)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Kaydedilemedi", str(exc))
            return

        self.editor_view.presets.refresh()
        self.cinema_view.presets.refresh()
        self._set_status(f"Görünüm kaydedildi: {preset.name}  ({path.name})")

    def _import_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Görünüm içe aktar", str(pictures_dir()),
            "Luma görünüm dosyaları (*.json);;Tüm dosyalar (*)",
        )
        if not path:
            return
        try:
            preset = self.presets.import_preset(Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "İçe aktarılamadı", str(exc))
            return
        self.editor_view.presets.refresh()
        self.cinema_view.presets.refresh()
        self._set_status(f"Görünüm içe aktarildi: {preset.name}")

    def _export_preset(self, preset_id: str) -> None:
        preset = self.presets.get(preset_id)
        if preset is None:
            return
        suggested = pictures_dir() / f"{preset.preset_id}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Görünümü dışa aktar", str(suggested),
            "Luma görünüm dosyaları (*.json)",
        )
        if not path:
            return
        try:
            self.presets.export_preset(preset_id, Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Dışa aktarılamadı", str(exc))
            return
        self._set_status(f"Görünüm dışa aktarildi: {Path(path).name}")

    def _delete_preset(self, preset_id: str) -> None:
        preset = self.presets.get(preset_id)
        if preset is None or preset.builtin:
            return
        answer = QMessageBox.question(
            self, "Görünümü sil",
            f"'{preset.name}' görünümü silinsin mi?\n"
            "Bu işlem geri alınamaz.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.presets.delete_user_preset(preset_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Silinemedi", str(exc))
            return
        self.editor_view.presets.refresh()
        self.cinema_view.presets.refresh()
        self._set_status(f"Görünüm silindi: {preset.name}")

    # ------------------------------------------------------------- kaydet
    def _save_copy(self) -> None:
        """Faz 1'de tek fotograf kaydetme. Tam export kuyruğu Faz 7'de."""
        if self._current_pixels is None or self._current_path is None:
            return
        from luma_atelier.core.paths import default_output_dir
        from luma_atelier.imaging.saver import (
            ImageSaveError,
            OutputFormat,
            SaveOptions,
            save_image,
        )

        suggested = default_output_dir() / f"{self._current_path.stem}-luma.jpg"
        path, selected = QFileDialog.getSaveFileName(
            self, "Kopya olarak kaydet", str(suggested),
            "JPEG (*.jpg);;PNG (*.png);;WebP (*.webp);;TIFF 16-bit (*.tif)",
        )
        if not path:
            return
        fmt = {
            "JPEG (*.jpg)": OutputFormat.JPEG,
            "PNG (*.png)": OutputFormat.PNG,
            "WebP (*.webp)": OutputFormat.WEBP,
            "TIFF 16-bit (*.tif)": OutputFormat.TIFF,
        }.get(selected, OutputFormat.JPEG)
        opts = SaveOptions(
            fmt=fmt, quality=94,
            bit_depth=16 if fmt is OutputFormat.TIFF else 8,
            overwrite=True,  # kullanici dosya secicide zaten onayladi
        )
        try:
            rendered = (self.renderer.render_now(self.document.source,
                                                 self.document.recipe)
                        if self.document is not None else self._current_pixels)
            result = save_image(rendered, Path(path), opts)
        except ImageSaveError as exc:
            QMessageBox.critical(self, "Kaydedilemedi", str(exc))
            return
        if self.document is not None:
            self.document.mark_saved()
            self._update_title_modified()
        self._set_status(
            f"Kaydedildi: {result.path.name}  "
            f"({result.bytes_written / 1024:.0f} KB, {result.bit_depth}-bit)"
        )

    # ---------------------------------------------------------- yardimci
    def _relocate(self, missing: Path) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"{missing.name} dosyasının yeni konumu",
            str(missing.parent), IMAGE_FILTER,
        )
        if path and self.session.relocate(missing, Path(path)):
            self._set_status(f"{missing.name} yeniden konumlandirildi")

    # ============================================================= PROJELER
    def _open_project(self) -> None:
        """Dosya secicisiyle bir `.luma` projesi acar."""
        from luma_atelier.storage.project import PROJECT_FILTER

        path, _ = QFileDialog.getOpenFileName(
            self, "Proje aç", str(pictures_dir()), PROJECT_FILTER)
        if path:
            self._open_project_path(Path(path))

    def _open_project_path(self, project_path: Path) -> None:
        """Verilen `.luma` projesini acar ve kaynagini cozer.

        Dosya seciciden de, komut satirindan da (`.luma` dosyasina cift
        tiklama) buraya gelinir. Once yalnizca secici vardi: kurulum
        dosya iliskilendirmesini kaydediyor ama cift tiklanan proje
        "desteklenmeyen bicim" diye reddediliyordu.
        """
        from luma_atelier.storage.project import (
            ProjectError,
            load_project,
            resolve_source,
        )

        path = str(project_path)
        start = str(pictures_dir())
        try:
            project = load_project(path, extract_dir=cache_dir() / "projects")
        except ProjectError as exc:
            QMessageBox.warning(self, "Proje açılamadı", str(exc))
            self._set_status(f"Proje açılamadı: {exc}")
            return

        search = [Path(path).parent, pictures_dir()]
        source, status = resolve_source(project, search_dirs=search)

        if source is None:
            answer = QMessageBox.question(
                self, "Kaynak fotoğraf bulunamadı",
                f"Proje '{project.source.path.name}' dosyasına baglı ama dosya "
                f"bulunamadı.\n\nFotoğrafın yeni konumunu göstermek ister "
                f"misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            chosen, _ = QFileDialog.getOpenFileName(
                self, f"{project.source.path.name} dosyasının yeni konumu",
                start, IMAGE_FILTER)
            if not chosen:
                return
            source = Path(chosen)
            status = "relocated"

        if status == "changed":
            QMessageBox.warning(
                self, "Kaynak fotoğraf değişmiş",
                f"'{source.name}' dosyasının içeriği proje kaydedildiğinden beri "
                f"değişmiş. Düzenlemeler uygulanacak ama sonuç farklı "
                f"görünebilir.",
            )

        self._pending_project = project
        self.session.add_paths([source])
        if self.session.index_of(source) < 0:
            QMessageBox.warning(
                self, "Kaynak fotoğraf açılamadı",
                f"'{source.name}' kitaplığa eklenemedi; dosya türü "
                f"desteklenmiyor olabilir.")
            self._pending_project = None
            return

        already_open = self._current_path == source and self.document is not None
        self._open_in_editor(source)
        if already_open:
            # Ayni fotograf zaten acik: yukleme tetiklenmez, dolayisiyla
            # _on_photo_loaded da cagrilmaz. Tarifi burada uygulariz.
            self._apply_pending_project()
        self._set_status(PROJECT_STATUS.get(status, "Proje açıldı: {name}")
                         .format(name=Path(path).name))

    def _apply_pending_project(self) -> None:
        """Fotograf yuklendikten sonra projedeki tarifi uygular.

        Tarif yalnizca *dogru* fotograf acildiginda uygulanir; kullanici
        bu arada baska bir fotografa gecmisse proje beklemede kalmaz,
        sessizce dusurulur.
        """
        project = self._pending_project
        if project is None or self.document is None:
            return
        self._pending_project = None
        self.document.paste_recipe(project.recipe)
        self.document.mark_saved()
        self._project_path = project.path
        self._refresh_project_actions()
        self.editor_view.refreshPreview()
        self.cinema_view.refreshPreview()

    def _save_project(self, *, ask: bool = False) -> None:
        from luma_atelier.storage.project import (
            PROJECT_EXTENSION,
            PROJECT_FILTER,
            ProjectError,
            save_project,
        )

        if self.document is None:
            return
        target = self._project_path
        portable = False
        if ask or target is None:
            default = self.document.path.with_suffix(PROJECT_EXTENSION)
            path, _ = QFileDialog.getSaveFileName(
                self, "Projeyi kaydet", str(default), PROJECT_FILTER)
            if not path:
                return
            target = Path(path)
            portable = self._ask_portable()

        preview = self.editor_view.current_preview()
        try:
            project = save_project(target, self.document.path,
                                   self.document.recipe, preview,
                                   portable=portable)
        except ProjectError as exc:
            QMessageBox.warning(self, "Proje kaydedilemedi", str(exc))
            self._set_status(f"Proje kaydedilemedi: {exc}")
            return

        self._project_path = project.path
        self.document.mark_saved()
        self._refresh_project_actions()
        size_kb = (project.path.stat().st_size / 1024) if project.path else 0
        self._set_status(
            f"Proje kaydedildi: {project.path.name}  ({size_kb:.0f} KB)")

    def _ask_portable(self) -> bool:
        """Kaynagin pakete gomulup gomulmeyecegini sorar."""
        from luma_atelier.storage.project import estimate_portable_size

        if self.document is None:
            return False
        extra_mb = estimate_portable_size(self.document.path) / (1024 * 1024)
        box = QMessageBox(self)
        box.setWindowTitle("Proje türü")
        box.setText("Fotoğrafın kopyası projeye gömülsün mü?")
        box.setInformativeText(
            f"Gömülü proje fotoğraf taşınsa veya silinse bile açılır, "
            f"ancak yaklaşık {extra_mb:.1f} MB daha büyük olur.\n\n"
            f"Gömülmezse proje yalnızca fotoğrafın yolunu saklar."
        )
        embed = box.addButton("Göm (taşınabilir)",
                              QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Yalnızca bağlantı", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is embed

    def _refresh_project_actions(self) -> None:
        has_doc = self.document is not None
        self.save_project_action.setEnabled(has_doc)
        self.save_project_as_action.setEnabled(has_doc)
        if self._project_path is not None:
            self.save_project_action.setText(
                f"Projeyi kaydet ({self._project_path.name})")
        else:
            self.save_project_action.setText("Projeyi kaydet")

    # ------------------------------------------------------ otomatik kurtarma
    def _autosave_tick(self) -> None:
        """Duzenleme varsa kurtarma kaydi yazar.

        Kurtarma kaydi normal kaydin **yerine gecmez**: ayri bir dosyaya
        yazilir ve yalnizca kullanici onay verirse uygulanir.
        """
        from luma_atelier.storage.project import write_autosave

        doc = self.document
        if doc is None or not doc.is_modified or not doc.has_edits:
            return
        if write_autosave(doc.path, doc.recipe,
                          self.editor_view.current_preview()) is not None:
            self._session_autosaves.add(doc.path)
            self.status_detail.setText("kurtarma kaydı güncellendi")

    def _offer_recovery(self) -> None:
        """Acilan fotograf icin kurtarma kaydi varsa kullaniciya sorar."""
        from luma_atelier.storage.project import (
            ProjectError,
            clear_autosave,
            find_autosave,
            load_project,
        )

        doc = self.document
        if doc is None or doc.has_edits:
            return
        if doc.path in self._session_autosaves:
            # Bu oturumda biz yazdik; cokme olmadi, sorulacak bir sey yok.
            return
        found = find_autosave(doc.path)
        if found is None:
            return
        answer = QMessageBox.question(
            self, "Kurtarma kaydı bulundu",
            f"'{doc.path.name}' için kaydedilmemiş düzenlemeler bulundu.\n\n"
            f"Geri yüklensin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            clear_autosave(doc.path)
            self._set_status("Kurtarma kaydı atıldı")
            return
        try:
            project = load_project(found)
        except ProjectError as exc:
            QMessageBox.warning(self, "Kurtarma okunamadı", str(exc))
            return
        doc.paste_recipe(project.recipe)
        self.editor_view.refreshPreview()
        self.cinema_view.refreshPreview()
        self._set_status("Kurtarma kaydı geri yüklendi")

    # ============================================================ DISA AKTAR
    def _refresh_export_context(self) -> None:
        """Disa aktarma ekranina guncel durumu bildirir."""
        from luma_atelier.core.paths import default_output_dir

        size = (0, 0)
        if self.document is not None:
            size = self.document.output_size()
        elif self.session.current is not None:
            meta = self.session.current.metadata
            size = (getattr(meta, "width", 0), getattr(meta, "height", 0))

        self.export_view.setContext(
            current=self._current_path,
            selected=len(self.session.selection),
            total=len(self.session),
            output_size=size,
            default_folder=default_output_dir(),
        )
        self.export_view.setSources(self._export_sources(
            self.export_view.scope()))

    def _export_sources(self, scope: str) -> list[Path]:
        """Kapsama gore kaynak fotograf yollari."""
        if scope == "current":
            return [self._current_path] if self._current_path else []
        if scope == "selected":
            return [e.path for e in self.session.selection]
        return [e.path for e in self.session.entries]

    def _build_jobs(self, scope: str) -> list[ExportJob]:
        """Kaynaklari isa cevirir.

        Acik fotografin *duzenlenmis* tarifi kullanilir ve pikselleri
        yeniden okunmaz. Kitapliktaki digerleri icin tarif yoktur;
        kullanicinin beklentisi budur - toplu is "ayni ayarlari herkese
        uygula" degil, "her fotografi kendi durumuyla yaz" demektir.
        """
        jobs: list[ExportJob] = []
        preset_name = ""
        if self.document is not None:
            preset_name = self.document.active_preset_id or ""
        for path in self._export_sources(scope):
            if (self.document is not None and self._current_path == path):
                jobs.append(ExportJob(
                    source=path, recipe=self.document.recipe,
                    preset_name=preset_name,
                    pixels=self.document.source,
                    metadata=self.document.metadata))
            else:
                jobs.append(ExportJob(source=path))
        return jobs

    def _start_export(self, scope: str, settings: object) -> None:
        if self.export_queue.is_running:
            self._set_status("Dışa aktarma zaten çalışıyor")
            return
        jobs = self._build_jobs(scope)
        if not jobs:
            QMessageBox.information(
                self, "Dışa aktarılacak fotoğraf yok",
                "Önce bir fotoğraf açın veya kitaplıktan seçim yapın.")
            return
        if not self._confirm_export(jobs, settings):
            return
        self.export_queue.start(jobs, settings)
        self._set_status(f"{len(jobs)} fotoğraf dışa aktarılıyor...")

    def _confirm_export(self, jobs: list[ExportJob], settings: object) -> bool:
        """Buyuk veya riskli isler icin onay alir."""
        folder = Path(getattr(settings, "folder", "."))
        if not folder.parent.exists() and not folder.exists():
            QMessageBox.warning(
                self, "Hedef klasör yok",
                f"'{folder}' klasörüne ulaşılamıyor. Başka bir klasör seçin.")
            return False

        sources = {j.source.parent.resolve() for j in jobs}
        try:
            target = folder.resolve()
        except OSError:
            target = folder
        warnings: list[str] = []
        if target in sources:
            warnings.append(
                "Hedef klasör kaynak fotoğrafların klasörüyle aynı. "
                "Orijinaller değiştirilmez; çıktılar ayrı dosya olarak yazılır.")
        # "Çok sayıda fotoğraf dışa aktarılırken onay iste" ayari burada
        # uygulanir; onceden toplaniyor ama hicbir yerde okunmuyordu.
        # Hedef klasor uyarisi ayara bagli **degildir**: o bir kolaylik
        # degil, veri guvenligi uyarisi.
        if self.settings.confirm_large_export and len(jobs) >= LARGE_EXPORT_COUNT:
            warnings.append(f"{len(jobs)} fotoğraf işlenecek; bu biraz sürebilir.")
        if not warnings:
            return True
        answer = QMessageBox.question(
            self, "Dışa aktarma", "\n\n".join(warnings) + "\n\nDevam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        return answer == QMessageBox.StandardButton.Yes

    def _cancel_export(self) -> None:
        self.export_queue.cancel()
        self._set_status("Dışa aktarma iptal ediliyor "
                         "(işlenen dosya tamamlanıyor)...")

    def _retry_export(self, summary: object) -> None:
        jobs = summary.retry_jobs() if isinstance(summary, ExportSummary) else []
        if not jobs:
            return
        self.export_queue.start(jobs, self.export_view.settings())
        self._set_status(f"{len(jobs)} başarısız iş yeniden deneniyor...")

    def _on_export_finished(self, summary: object) -> None:
        if not isinstance(summary, ExportSummary):
            raise TypeError("summary must be an ExportSummary")
        self.export_view.onQueueFinished(summary)
        self._set_status(summary.message())
        if summary.failed and not summary.cancelled:
            names = "\n".join(
                f"· {r.job.source.name}: {r.error}" for r in summary.failed[:10])
            more = (f"\n\n...ve {len(summary.failed) - 10} tane daha"
                    if len(summary.failed) > 10 else "")
            QMessageBox.warning(
                self, "Bazı fotoğraflar dışa aktarılamadı",
                f"{len(summary.succeeded)} fotoğraf başarıyla yazıldı, "
                f"{len(summary.failed)} tanesi yazılamadı:\n\n{names}{more}"
                f"\n\nBaşarısızları kuyruk ekranından yeniden deneyebilirsiniz.")

    def _open_folder(self, folder: object) -> None:
        import os

        path = Path(str(folder))
        if not path.exists():
            self._set_status(f"Klasör bulunamadı: {path}")
            return
        try:
            os.startfile(path)  # noqa: S606 - kullanicinin kendi klasoru
        except OSError as exc:
            self._set_status(f"Klasör açılamadı: {exc}")

    # ============================================================== AYARLAR
    def _apply_settings(self, settings: object, *, persist: bool = True) -> None:
        """Ayarlari **gercekten** uygular; yalnizca saklamaz.

        Her secenegin gozle gorulur bir karsiligi olmali; yoksa ayar
        ekrani sus olurdu.
        """
        from luma_atelier.core.settings import Settings

        if not isinstance(settings, Settings):
            raise TypeError("settings must be a Settings instance")
        self.settings = settings

        # Onizleme kalitesi -> render servisi
        self.renderer.set_preview_long_edge(settings.preview_long_edge)

        # Onbellek siniri -> kucuk resim servisi. Sinir yalnizca
        # ayarlaniyordu; hicbir yerde uygulanmadigi icin disk onbellegi
        # sinirsiz buyuyordu. Budama arka planda calisir.
        self.thumbnails.set_cache_limit(settings.cache_bytes)
        self.thumbnails.prune_cache_async()

        # Otomatik kurtarma araligi (0 = kapali)
        if settings.autosave_seconds > 0:
            self._autosave_timer.setInterval(settings.autosave_seconds * 1000)
            if not self._autosave_timer.isActive():
                self._autosave_timer.start()
        else:
            self._autosave_timer.stop()

        # Arac ipuclari
        self._set_tooltips_enabled(settings.show_tooltips)

        # Klavye kisayollarini ipuclarinda goster
        self._apply_keyboard_hints(settings.keyboard_hints)

        # Yuksek kontrast
        self._apply_contrast(settings.high_contrast)

        if persist and not save_settings(settings):
            self._set_status("Ayarlar kaydedilemedi; bu oturumda geçerli")

    def _set_tooltips_enabled(self, enabled: bool) -> None:
        """Arac ipuclarini acar/kapatir.

        Kapatirken metinler **saklanir** (`_stashed_tooltip` ozelliginde),
        boylece yeniden acildiginda geri gelir.
        """
        for widget in self.findChildren(QWidget):
            if enabled:
                stashed = widget.property("_stashed_tooltip")
                if stashed:
                    widget.setToolTip(str(stashed))
                    widget.setProperty("_stashed_tooltip", None)
            elif widget.toolTip():
                widget.setProperty("_stashed_tooltip", widget.toolTip())
                widget.setToolTip("")


    def _apply_keyboard_hints(self, enabled: bool) -> None:
        """Eylemlerin ipucuna klavye kisayolunu ekler/cikarir.

        Ayar toplaniyordu ama hicbir yerde okunmuyordu: "Klavye
        kısayollarını ipuçlarında göster" kutusu etkisizdi. Duz metin
        ayri bir ozellikte saklanir; acip kapatmak metni bozmaz.
        """
        for act in self.findChildren(QAction):
            plain = act.property("_plain_tooltip")
            if plain is None:
                plain = act.toolTip() or act.text().replace("&", "")
                act.setProperty("_plain_tooltip", plain)
            sequence = act.shortcut().toString(
                QKeySequence.SequenceFormat.NativeText)
            act.setToolTip(f"{plain}  ({sequence})"
                           if enabled and sequence else str(plain))

    def _apply_contrast(self, high: bool) -> None:
        """Yuksek kontrast stil katmanini acar/kapatir."""
        from luma_atelier.ui.theme.stylesheet import build_stylesheet

        app = QApplication.instance()
        if app is None:
            return
        try:
            app.setStyleSheet(build_stylesheet(high_contrast=high))
        except TypeError:
            # Stil uretici bu secenegi desteklemiyorsa temel stile don
            app.setStyleSheet(build_stylesheet())

    def _clear_cache(self) -> None:
        from luma_atelier.services.export import format_bytes

        answer = QMessageBox.question(
            self, "Önbelleği temizle",
            "Küçük resimler ve görünüm önizlemeleri silinecek. "
            "Fotoğraflarınıza ve projelerinize dokunulmaz.\n\n"
            "Devam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed, freed = clear_cache()
        self.thumbnails.clear_memory_cache()
        self.settings_view.setCacheSize(cache_folder_size())
        self._set_status(
            f"Önbellek temizlendi: {removed} dosya, {format_bytes(freed)}")

    def _toggle_filmstrip(self) -> None:
        visible = self.filmstrip_action.isChecked()
        self.editor_view.setFilmstripVisible(visible)
        self.cinema_view.setFilmstripVisible(visible)
        self._set_status("Film şeridi açık" if visible
                         else "Film şeridi gizlendi")

    def _clear_session_autosaves(self) -> None:
        """Bu oturumda yazilan kurtarma kayitlarini siler."""
        from luma_atelier.storage.project import clear_autosave

        for path in list(self._session_autosaves):
            clear_autosave(path)
        self._session_autosaves.clear()

    def _open_log_folder(self) -> None:
        import os
        import subprocess

        from luma_atelier.core.paths import log_dir
        folder = log_dir()
        try:
            os.startfile(folder)  # noqa: S606 - kullanicinin kendi klasoru
        except (AttributeError, OSError):
            subprocess.Popen(["explorer", str(folder)])  # noqa: S603,S607

    def _about(self) -> None:
        from luma_atelier.core.build_info import build_info
        from luma_atelier.core.paths import log_dir, user_data_dir

        # Derleme kimligi: "kısayolun açtığı sürüm hangi kaynaktan
        # derlendi?" sorusunun cevabi. Surum numarasi degismeden kaynak
        # defalarca degisebilir; kimlik kaynak ozetini tasir.
        info = build_info()
        QMessageBox.about(
            self, f"{APP_NAME} hakkında",
            f"<b>{APP_NAME}</b> {APP_VERSION}<br>"
            f"<small>{info.summary()}</small><br><br>"
            "Cevrimdisi calisan fotoğraf efekt studyosu.<br>"
            "Fotograflariniz ve dosya yollariniz hicbir yere gonderilmez.<br><br>"
            f"Veri klasörü: {user_data_dir()}<br>"
            f"Gunlukler: {log_dir()}",
        )

    def _set_status(self, message: str, detail: str | None = None,
                    keep_detail: bool = False) -> None:
        self.status_message.setText(message)
        if detail is not None:
            self.status_detail.setText(detail)
        elif not keep_detail:
            pass

    def _toggle_favourite_path(self, path: object) -> None:
        index = self.session.index_of(Path(str(path)))
        if index >= 0:
            self.session.toggle_favourite(index)

    def _on_session_changed(self) -> None:
        self.editor_view.refreshFilmstrip()
        self.cinema_view.refreshFilmstrip()
        has_photos = len(self.session) > 0
        self.nav.setAvailable(Workspace.EDITOR, has_photos)
        self.nav.setAvailable(Workspace.CINEMA, has_photos)
        self.nav.setAvailable(Workspace.EXPORT, has_photos)
        self.nav.setAvailable(Workspace.LIBRARY, has_photos)
        self._update_position()
        if has_photos and self.session.current is not None:
            if self.stack.currentWidget() is self.editor_view:
                self._load_current()

    # ------------------------------------------------------- surukle-birak
    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if paths:
            self._import_paths(paths)
            event.acceptProposedAction()

    # -------------------------------------------------------------- kapanis

    # ----------------------------------------------------- pencere konumu
    def _restore_geometry(self) -> None:
        """Onceki oturumun pencere boyutunu ve konumunu geri yukler.

        Ayar toplaniyordu ama hicbir yerde kullanilmiyordu: "Pencere
        boyutunu ve konumunu hatirla" kutusu etkisizdi.

        Kayitli geometri okunamazsa veya ekran yerlesimi degistigi icin
        pencere gorunur alanin disina duserse varsayilan boyut kullanilir;
        aksi halde pencere ekranda bulunamazdi.
        """
        if not self.settings.remember_window or not self.settings.window_geometry:
            return
        try:
            blob = QByteArray.fromBase64(
                self.settings.window_geometry.encode("ascii"))
        except (UnicodeEncodeError, ValueError):
            log.debug("Kayitli pencere geometrisi okunamadi")
            return
        if blob.isEmpty() or not self.restoreGeometry(blob):
            return
        if not self._is_on_a_screen():
            log.info("Kayitli pencere konumu ekran disinda; varsayilana donuldu")
            self.resize(METRICS.window_default_width,
                        METRICS.window_default_height)
            self.move(80, 60)

    def _is_on_a_screen(self) -> bool:
        """Pencerenin en az bir ekranla kesisip kesismedigi."""
        app = QApplication.instance()
        if app is None:
            return True
        frame = self.frameGeometry()
        return any(screen.availableGeometry().intersects(frame)
                   for screen in app.screens())

    def _remember_geometry(self) -> None:
        """Pencere boyut/konumunu ayarlara yazar."""
        if not self.settings.remember_window:
            return
        blob = bytes(self.saveGeometry().toBase64().data()).decode("ascii")
        if blob == self.settings.window_geometry:
            return
        self.settings = replace(self.settings, window_geometry=blob)
        if not save_settings(self.settings):
            log.debug("Pencere geometrisi kaydedilemedi")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Kapanis: once kullaniciya sor, sonra isleri durdur.

        Iki hata buradaydi:
        * Kaydedilmemis duzenlemeler **sorulmadan** gidiyordu ve
          `_clear_session_autosaves` kurtarma kaydini da siliyordu;
          yani geri alma yolu kalmiyordu.
        * Suren disa aktarma kuyrugu durdurulmuyordu; pencere kapandigi
          halde surec dosya yazmaya devam ediyor, kapanis kuyruk bitene
          kadar bloke oluyordu.
        """
        if not self._confirm_close():
            event.ignore()
            return

        self._remember_geometry()

        if self.export_queue.is_running:
            self.export_queue.cancel()
            self.export_queue.wait(10_000)

        self.thumbnails.shutdown()
        self.renderer.shutdown()
        self.preset_previews.shutdown()
        self._pool.clear()
        self._pool.waitForDone(2000)
        super().closeEvent(event)

    def _confirm_close(self) -> bool:
        """Kaydedilmemis is ve suren export icin onay alir.

        Returns:
            Kapanmaya devam edilecekse True.
        """
        doc = self.document
        if doc is not None and doc.is_modified and doc.has_edits:
            answer = QMessageBox.question(
                self, "Kaydedilmemiş düzenlemeler",
                f"'{doc.path.name}' üzerindeki düzenlemeler kaydedilmedi.\n\n"
                f"Projeyi kaydetmek ister misiniz?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save)
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Save:
                self._save_project()
                if doc.is_modified:
                    return False        # kullanici kayit diyalogunu iptal etti
                self._clear_session_autosaves()
            # Discard: kurtarma kaydi **birakilir**, geri donus yolu kalsin
        else:
            # Kaydedilmemis is yok; kurtarma kaydi gereksiz
            self._clear_session_autosaves()

        if self.export_queue.is_running:
            answer = QMessageBox.question(
                self, "Dışa aktarma sürüyor",
                "Dışa aktarma hâlâ çalışıyor. Şimdi kapatırsanız kalan "
                "fotoğraflar yazılmaz.\n\nYine de kapatılsın mı?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        return True


def create_application(argv: list[str] | None = None) -> QApplication:
    """QApplication'i olusturur ve temayi uygular."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    icon_path = resources_dir() / "icons" / "app.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(build_stylesheet())
    return app


def run_app(files: list[str] | None = None) -> int:
    """Uygulamayi baslatir."""
    app = create_application()
    window = MainWindow()
    window.show()
    if files:
        QTimer.singleShot(
            0, lambda: window._import_paths([Path(f) for f in files])
        )
    return app.exec()

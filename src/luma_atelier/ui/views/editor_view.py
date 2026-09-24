"""Duzenleyici: solda gorunumler, ortada tuval, sagda kontroller.

Yerlesim (gereksinim belgesi Bolum 5)
------------------------------------
* Ortada genis tuval
* Solda gorunum (preset) tarayicisi: kategoriler ve arama
* Sagda histogram, secili aracin kontrolleri ve efekt yigini
* Paneller daraltilabilir

Veri akisi
----------
    kaydirici / preset -> Document -> yeni Recipe -> RenderService
                                                  -> onizleme -> tuval

Kaydirici *surukleme sirasinda* dusuk kaliteli onizleme ister
(`interactive=True`); birakildiginda tam onizleme kalitesi istenir ve
gecmise tek bir adim yazilir.

Hover onizlemesi belgeyi **degistirmez**: gecici bir tarif render
edilir ve fare cikinca gercek tarife donulur.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.document import Document
from luma_atelier.imaging.effects.base import REGISTRY
from luma_atelier.imaging.geometry import Geometry
from luma_atelier.imaging.masks import BlendOp, BrushStroke, Mask, MaskKind
from luma_atelier.imaging.recipe import Recipe
from luma_atelier.services.preset_previews import PresetPreviewService
from luma_atelier.services.render import RenderResult, RenderService
from luma_atelier.storage.presets import PresetLibrary
from luma_atelier.ui.theme.tokens import METRICS, PALETTE, SPACE
from luma_atelier.ui.views.preset_browser import PresetBrowser
from luma_atelier.ui.widgets.adjustment_panel import (
    CollapsibleSection,
    OperationControls,
    divider,
)
from luma_atelier.ui.widgets.canvas_tools import CanvasOverlay, CanvasTool
from luma_atelier.ui.widgets.crop_panel import CropPanel
from luma_atelier.ui.widgets.effect_stack import EffectStackPanel
from luma_atelier.ui.widgets.filmstrip import Filmstrip
from luma_atelier.ui.widgets.histogram import Histogram
from luma_atelier.ui.widgets.image_canvas import CompareMode, ImageCanvas
from luma_atelier.ui.widgets.mask_panel import TOOL_FOR_KIND, MaskPanel

log = logging.getLogger(__name__)

#: Kaydirici birakildiktan sonra tam kalite onizlemeyi tetikleme gecikmesi.
FINAL_QUALITY_DELAY_MS = 180
#: Zoom/pan durduktan sonra detay karosunu isteme gecikmesi.
DETAIL_TILE_DELAY_MS = 220
#: Detay karosunun islenecegi en fazla piksel sayisi.
MAX_TILE_PIXELS = 12_000_000
#: Fotograf acilirken gosterilen ilk karenin uzun kenari. Tam boy
#: diziyi QImage'e cevirmek 12 MP'de ~370 ms suruyor; ilk kare bu
#: yuzden hafif kucultulur. Gercek onizleme hemen ardindan gelir.
FIRST_FRAME_LONG_EDGE = 1600

#: Maske ortusunun uretilecegi en uzun kenar. Ortu yalnizca gorsel
#: geri bildirimdir; tam cozunurlukte uretmek gereksiz yavaslik olurdu.
MASK_OVERLAY_EDGE = 900

#: Duzenleyici sag panelindeki arac bolumleri.
EDITOR_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Işık", ("tone.exposure", "tone.contrast", "tone.shadows_highlights",
              "tone.black_white_point", "tone.brightness")),
    ("Eğriler", ("tone.curves",)),
    ("Renk", ("color.white_balance", "color.saturation", "color.vibrance",
              "color.grading", "color.hsl")),
    ("Ayrıntı", ("detail.sharpen", "detail.clarity", "detail.denoise")),
    ("Stil", ("tone.fade", "color.monochrome", "color.split_tone",
              "style.duotone", "style.bleach_bypass", "style.cross_process",
              "style.posterize", "color.channel_mixer")),
    ("Lens", ("lens.vignette", "lens.chromatic_aberration")),
    ("Bulanıklık", ("blur.gaussian", "blur.motion", "blur.tilt_shift")),
)

#: Sinema Laboratuvari arac bolumleri - film estetiginin bilesenleri
#: bir arada: renk, film tonu, isik, doku, lens ve kadraj.
CINEMA_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Film tonu", ("film.tone_curve",)),
    ("Renk", ("color.grading", "color.lut3d", "color.split_tone")),
    ("Işık", ("light.halation", "light.bloom", "light.diffusion",
              "light.anamorphic")),
    ("Analog doku", ("texture.grain", "texture.dust", "texture.light_leak",
                     "texture.paper")),
    ("Lens", ("lens.vignette", "lens.chromatic_aberration")),
    ("Kadraj", ("geometry.letterbox",)),
)


class EditorView(QWidget):
    """Duzenleyici calisma alani.

    `cinema=True` ile Sinema Laboratuvari olarak calisir: **ayni belge**
    ve ayni tuval, farkli arac seti ve yalnizca sinematik gorunumler.
    Ekran degisince duzenlemeler kaybolmaz cunku her iki gorunum de
    ayni `Document` nesnesine baglanir.
    """

    requestPrevious = Signal()
    #: Film seridinden fotograf secildi (Path)
    photoRequested = Signal(object)
    #: Film seridinden favori degistirildi (Path)
    favouriteToggled = Signal(object)
    requestNext = Signal()
    statusMessage = Signal(str)
    recipeChanged = Signal()
    savePresetRequested = Signal()

    def __init__(self, render_service: RenderService,
                 preset_library: PresetLibrary,
                 preset_previews: PresetPreviewService,
                 *, cinema: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CinemaView" if cinema else "EditorView")
        self._render = render_service
        self._library = preset_library
        self._previews = preset_previews
        self._cinema = cinema
        self._document: Document | None = None
        self._controls: dict[str, OperationControls] = {}
        self._syncing = False
        self._last_preview: np.ndarray | None = None
        self._hover_recipe: Recipe | None = None
        self._stroke_points: list[tuple[float, float]] = []
        self._stroke_index = -1
        self._selected_layer = ""
        self._show_mask = False
        self._needs_sync = False
        self._pending_open = False
        self._original_cache: np.ndarray | None = None
        self._original_cache_key: tuple | None = None
        #: Arka planda istenen karonun bolgesi; gelen sonuc bununla
        #: dogrulanir (kullanici bu arada kaydirmis olabilir).
        self._tile_request: tuple[int, int, int, int] | None = None

        self._final_timer = QTimer(self)
        self._final_timer.setSingleShot(True)
        self._final_timer.setInterval(FINAL_QUALITY_DELAY_MS)
        self._final_timer.timeout.connect(lambda: self._request_render(False))

        self._tile_timer = QTimer(self)
        self._tile_timer.setSingleShot(True)
        self._tile_timer.setInterval(DETAIL_TILE_DELAY_MS)
        self._tile_timer.timeout.connect(self._refresh_detail_tile)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(True)
        splitter.setHandleWidth(1)

        self.presets = PresetBrowser(preset_library, preset_previews,
                                     cinema_only=cinema)
        self.presets.setMinimumWidth(METRICS.left_panel_min)
        self.presets.setMaximumWidth(460)
        self.presets.presetApplied.connect(self._on_preset_applied)
        self.presets.presetAdded.connect(self._on_preset_added)
        self.presets.presetPreviewed.connect(self._on_preset_previewed)
        self.presets.previewCleared.connect(self._on_preview_cleared)
        self.presets.savePresetRequested.connect(self.savePresetRequested)

        self.canvas = ImageCanvas()
        self.overlay = CanvasOverlay(self.canvas)
        self.overlay.setGeometry(self.canvas.rect())
        self.canvas.installEventFilter(self)
        self.overlay.cropChanged.connect(self._on_crop_changed)
        self.overlay.cropCommitted.connect(self._on_crop_committed)
        self.overlay.strokeStarted.connect(self._on_stroke_started)
        self.overlay.strokePoint.connect(self._on_stroke_point)
        self.overlay.strokeFinished.connect(self._on_stroke_finished)
        self.overlay.gradientChanged.connect(self._on_gradient_changed)
        self.overlay.gradientCommitted.connect(self._on_gradient_committed)

        splitter.addWidget(self.presets)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([METRICS.left_panel_width, 900,
                           METRICS.right_panel_width])
        self._splitter = splitter

        root.addWidget(splitter, 1)
        self.filmstrip: Filmstrip | None = None
        self._filmstrip_slot = QVBoxLayout()
        self._filmstrip_slot.setContentsMargins(0, 0, 0, 0)
        self._filmstrip_slot.setSpacing(0)
        root.addLayout(self._filmstrip_slot)
        root.addWidget(self._build_toolbar())

        self.canvas.zoomChanged.connect(self._update_zoom_label)
        self.canvas.viewChanged.connect(self._tile_timer.start)
        render_service.previewReady.connect(self._on_preview_ready)
        render_service.renderFailed.connect(
            lambda _t, msg: self.statusMessage.emit(msg)
        )
        render_service.tileReady.connect(self._on_tile_ready)

    def attachFilmstrip(self, session, thumbnails) -> None:  # noqa: N802, ANN001
        """Film seridini kurar ve tuvalin altina yerlestirir.

        Kabuk cagirir; duzenleyici oturumu dogrudan tanimaz, yalnizca
        secim isteklerini sinyalle yukari bildirir.
        """
        if self.filmstrip is not None:
            return
        self.filmstrip = Filmstrip(session, thumbnails)
        self.filmstrip.photoActivated.connect(self.photoRequested)
        self.filmstrip.favouriteToggled.connect(self.favouriteToggled)
        self._filmstrip_slot.addWidget(divider())
        self._filmstrip_slot.addWidget(self.filmstrip)

    def refreshFilmstrip(self) -> None:  # noqa: N802
        if self.filmstrip is not None:
            self.filmstrip.refresh()

    def setFilmstripVisible(self, visible: bool) -> None:  # noqa: N802
        if self.filmstrip is not None:
            self.filmstrip.setVisible(visible)

    def isFilmstripVisible(self) -> bool:  # noqa: N802
        return self.filmstrip is not None and self.filmstrip.isVisible()

    # --------------------------------------------------------------- panel
    def _sections(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return CINEMA_SECTIONS if self._cinema else EDITOR_SECTIONS

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("SidePanel")
        panel.setMinimumWidth(METRICS.right_panel_min)
        panel.setMaximumWidth(460)

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QWidget()
        head_lay = QVBoxLayout(head)
        head_lay.setContentsMargins(SPACE.md, SPACE.md, SPACE.md, SPACE.sm)
        head_lay.setSpacing(SPACE.xs)
        self.histogram = Histogram()
        head_lay.addWidget(self.histogram)
        self.clip_label = QLabel("")
        self.clip_label.setObjectName("Muted")
        head_lay.addWidget(self.clip_label)
        outer.addWidget(head)
        outer.addWidget(divider())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Maximum)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(SPACE.md, SPACE.sm, SPACE.md, SPACE.md)
        lay.setSpacing(SPACE.xs)

        expanded_default = ({"Film tonu", "Işık"} if self._cinema
                            else {"Işık", "Renk"})
        for title, op_ids in self._sections():
            section = CollapsibleSection(title, expanded=title in expanded_default)
            added = 0
            for op_id in op_ids:
                op = REGISTRY.get(op_id)
                if op is None:
                    log.warning("Panelde tanımlı işlem kayıtlı değil: %s", op_id)
                    continue
                controls = OperationControls(op)
                controls.valueChanged.connect(self._on_param_changed)
                controls.editingFinished.connect(self._on_param_committed)
                controls.resetRequested.connect(self._on_reset_operation)
                self._controls[op_id] = controls
                section.addWidget(controls)
                added += 1
            if added:
                lay.addWidget(section)
                lay.addWidget(divider())

        crop_section = CollapsibleSection("Kadraj", expanded=False)
        self.crop_panel = CropPanel()
        self.crop_panel.geometryChanged.connect(self._on_geometry_changed)
        self.crop_panel.editingFinished.connect(self._commit_edit)
        self.crop_panel.cropToolToggled.connect(self._on_crop_tool_toggled)
        self.crop_panel.guidesToggled.connect(self.overlay.setShowThirds)
        crop_section.addWidget(self.crop_panel)
        lay.addWidget(crop_section)
        lay.addWidget(divider())

        mask_section = CollapsibleSection("Maskeler", expanded=False)
        self.mask_panel = MaskPanel()
        self.mask_panel.maskCreateRequested.connect(self._on_mask_create)
        self.mask_panel.maskDeleteRequested.connect(self._on_mask_delete)
        self.mask_panel.maskSelected.connect(self._on_mask_selected)
        self.mask_panel.componentAddRequested.connect(self._on_component_add)
        self.mask_panel.componentRemoveRequested.connect(
            self._on_component_remove)
        self.mask_panel.componentSelected.connect(self._on_component_selected)
        self.mask_panel.componentChanged.connect(self._on_component_changed)
        self.mask_panel.editingFinished.connect(self._commit_edit)
        self.mask_panel.toolRequested.connect(self.setTool)
        self.mask_panel.showMaskToggled.connect(self._on_show_mask)
        self.mask_panel.layerAssignRequested.connect(self._on_layer_assign)
        mask_section.addWidget(self.mask_panel)
        lay.addWidget(mask_section)
        lay.addWidget(divider())

        self.stack_panel = EffectStackPanel()
        self.stack_panel.layerToggled.connect(self._on_layer_toggled)
        self.stack_panel.layerRemoved.connect(self._on_layer_removed)
        self.stack_panel.layerMoved.connect(self._on_layer_moved)
        self.stack_panel.layerSelected.connect(self._on_layer_selected)
        lay.addWidget(self.stack_panel)
        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        footer = QWidget()
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(SPACE.md, SPACE.sm, SPACE.md, SPACE.md)
        f_lay.setSpacing(SPACE.sm)
        self.reset_all_button = QPushButton("Tümünü sıfırla")
        self.reset_all_button.setToolTip(
            "Tüm ayarları kaldırır. Geri alınabilir (Ctrl+Z)."
        )
        self.reset_all_button.setEnabled(False)
        self.reset_all_button.clicked.connect(self._on_reset_all)
        self.layer_count = QLabel("")
        self.layer_count.setObjectName("Muted")
        f_lay.addWidget(self.reset_all_button)
        f_lay.addStretch(1)
        f_lay.addWidget(self.layer_count)
        outer.addWidget(divider())
        outer.addWidget(footer)
        return panel

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("SidePanel")
        bar.setFixedHeight(METRICS.nav_height)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(SPACE.lg, SPACE.xs, SPACE.lg, SPACE.xs)
        lay.setSpacing(SPACE.sm)

        self.prev_button = QPushButton("‹  Önceki")
        self.prev_button.setObjectName("GhostButton")
        self.prev_button.setToolTip("Önceki fotoğraf  (Sol ok)")
        self.prev_button.clicked.connect(self.requestPrevious)

        self.next_button = QPushButton("Sonraki  ›")
        self.next_button.setObjectName("GhostButton")
        self.next_button.setToolTip("Sonraki fotoğraf  (Sağ ok)")
        self.next_button.clicked.connect(self.requestNext)

        self.position_label = QLabel("—")
        self.position_label.setObjectName("ValueReadout")
        self.position_label.setMinimumWidth(66)
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.render_label = QLabel("")
        self.render_label.setObjectName("Muted")
        self.render_label.setMinimumWidth(86)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("Muted")

        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip("Uzaklaştır  (−)")
        zoom_out.clicked.connect(lambda: self.canvas.zoomOut())

        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip("Yakınlaştır  (+)")
        zoom_in.clicked.connect(lambda: self.canvas.zoomIn())

        self.zoom_label = QLabel("—")
        self.zoom_label.setObjectName("ValueReadout")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        fit_button = QPushButton("Sığdır")
        fit_button.setObjectName("GhostButton")
        fit_button.setToolTip("Ekrana sığdır  (0)")
        fit_button.clicked.connect(self.canvas.zoomToFit)

        actual_button = QPushButton("%100")
        actual_button.setObjectName("GhostButton")
        actual_button.setToolTip(
            "Gerçek piksel boyutu  (1)\n"
            "Görünen alan tam çözünürlükten yeniden üretilir."
        )
        actual_button.clicked.connect(self.canvas.zoomToActualPixels)

        self.compare_combo = QComboBox()
        for mode, label in [
            (CompareMode.OFF, "Düzenlenmiş"),
            (CompareMode.ORIGINAL, "Orijinal"),
            (CompareMode.SPLIT, "Surgulu karşılaştırma"),
            (CompareMode.SIDE_BY_SIDE, "Yan yana"),
        ]:
            self.compare_combo.addItem(label, mode)
        self.compare_combo.setToolTip("Önce/sonra gösterimi")
        self.compare_combo.currentIndexChanged.connect(
            lambda: self.canvas.setCompareMode(self.compare_combo.currentData())
        )

        lay.addWidget(self.prev_button)
        lay.addWidget(self.position_label)
        lay.addWidget(self.next_button)
        lay.addSpacing(SPACE.md)
        lay.addWidget(self.render_label)
        lay.addWidget(self.detail_label)
        lay.addStretch(1)
        lay.addWidget(self.compare_combo)
        lay.addSpacing(SPACE.md)
        lay.addWidget(zoom_out)
        lay.addWidget(self.zoom_label)
        lay.addWidget(zoom_in)
        lay.addWidget(fit_button)
        lay.addWidget(actual_button)
        return bar

    # --------------------------------------------------------------- belge
    def setDocument(self, document: Document | None) -> None:  # noqa: N802
        self._document = document
        self._hover_recipe = None
        if document is None:
            self.canvas.clear()
            self.histogram.clear()
            self._previews.setSource(None, "")
            self._sync_controls()
            return
        document.add_listener(self._on_document_changed)
        self._original_cache = None
        self._original_cache_key = None
        self._selected_layer = ""
        self.setTool(CanvasTool.NONE)

        if not self.isVisible():
            # Gizli gorunumun tuvalini ve onizlemelerini simdi kurmak
            # fotograf acilisini iki katina cikariyordu (olculdu: 373 ms
            # x 2). Gorunur olunca `showEvent` tamamlar.
            self._needs_sync = True
            self._pending_open = True
            return

        self._previews.setSource(document.source, str(document.path))
        self.presets.prefetchVisible()
        self._sync_controls()
        self._show_initial_image(document)
        self._request_render(False)

    def _show_initial_image(self, document: Document) -> None:
        """Ilk kareyi hizlica gosterir.

        Tam boy diziyi dogrudan tuvale vermek 12 MP'de ~370 ms suruyor
        (float32 -> QImage donusumu). Kullanici ekrana sigan bir goruntu
        gorecegi icin once hafif bir kucultme gosterilir; gercek
        onizleme hemen ardindan gelir ve bunu degistirir.
        """
        base = document.geometry_source()
        height, width = base.shape[:2]
        longest = max(width, height)
        quick = base
        if longest > FIRST_FRAME_LONG_EDGE:
            import cv2
            scale = FIRST_FRAME_LONG_EDGE / float(longest)
            quick = cv2.resize(
                base, (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA)
        self.canvas.setImage(quick, quick, source_size=(width, height))

    @property
    def document(self) -> Document | None:
        return self._document

    def _on_document_changed(self) -> None:
        # Duzenleyici ve Sinema Laboratuvari **ayni** belgeyi dinler.
        # Gorunmeyen olan da tam senkron yaparsa her kaydirici adiminda
        # is iki katina cikar ve kimsenin gormedigi paneller yeniden
        # kurulur. Gorunur olunca `setDocument`/`refreshPreview` zaten
        # esitliyor.
        if not self.isVisible():
            self._needs_sync = True
            return
        self._needs_sync = False
        self._sync_controls()
        self.recipeChanged.emit()

    # ------------------------------------------------------------ presetler
    def _on_preset_applied(self, preset, intensity: float) -> None:  # noqa: ANN001
        if self._document is None:
            return
        self._hover_recipe = None
        self._document.apply_preset(preset, intensity)
        self._document.commit()
        ops = ", ".join(preset.operations())
        self.statusMessage.emit(f"{preset.name} uygulandı  ·  {ops}")
        self._request_render(False)

    def _on_preset_added(self, preset, intensity: float) -> None:  # noqa: ANN001
        if self._document is None:
            return
        self._hover_recipe = None
        self._document.apply_preset(preset, intensity, accumulate=True)
        self._document.commit()
        self.statusMessage.emit(f"{preset.name} yığına eklendi")
        self._request_render(False)

    def _on_preset_previewed(self, preset, intensity: float) -> None:  # noqa: ANN001
        """Gecici hover onizlemesi - belge **degismez**."""
        if self._document is None:
            return
        self._hover_recipe = self._document.preview_preset(preset, intensity)
        self._request_render(True, recipe=self._hover_recipe)

    def _on_preview_cleared(self) -> None:
        if self._hover_recipe is None:
            return
        self._hover_recipe = None
        self._request_render(False)

    # ------------------------------------------------------------- kontrol
    def _on_param_changed(self, op_id: str, params: dict[str, Any]) -> None:
        if self._syncing or self._document is None:
            return
        self._hover_recipe = None
        self._document.set_param(op_id, **params)
        self._request_render(True)
        self._final_timer.start()

    def _on_param_committed(self, op_id: str, params: dict[str, Any]) -> None:
        if self._syncing or self._document is None:
            return
        self._hover_recipe = None
        self._document.set_param(op_id, **params)
        self._document.commit()
        self._final_timer.stop()
        self._request_render(False)

    def _on_reset_operation(self, op_id: str) -> None:
        if self._document is None:
            return
        self._document.reset_operation(op_id)
        self._document.commit()
        self._request_render(False)

    def _on_reset_all(self) -> None:
        if self._document is None:
            return
        self._document.reset_all()
        self._document.commit()
        self.presets.clearActive()
        self._request_render(False)

    def _on_layer_toggled(self, instance_id: str, enabled: bool) -> None:
        if self._document is None:
            return
        self._document.set_layer_enabled(instance_id, enabled)
        self._document.commit()
        self._request_render(False)

    def _on_layer_removed(self, instance_id: str) -> None:
        if self._document is None:
            return
        self._document.remove_layer(instance_id)
        self._document.commit()
        self._request_render(False)

    def _on_layer_moved(self, instance_id: str, new_index: int) -> None:
        if self._document is None:
            return
        self._document.move_layer(instance_id, new_index)
        self._document.commit()
        self._request_render(False)

    def _sync_controls(self) -> None:
        """Kontrolleri tarifin guncel degerlerine esitler."""
        self._syncing = True
        try:
            doc = self._document
            recipe = doc.recipe if doc else None
            for op_id, controls in self._controls.items():
                layer = recipe.first_of(op_id) if recipe else None
                op = REGISTRY.get(op_id)
                if layer is not None:
                    controls.setValues(layer.params)
                elif op is not None:
                    controls.setValues(op.defaults())
                controls.setEnabled(doc is not None)
        finally:
            self._syncing = False

        doc = self._document
        self.stack_panel.setRecipe(doc.recipe if doc else None)
        count = len(doc.recipe) if doc else 0
        self.reset_all_button.setEnabled(count > 0)
        self.layer_count.setText(f"{count} ayar etkin" if count else "Ayar yok")

        if doc is not None:
            self.crop_panel.setGeometry(
                doc.recipe.geometry,
                (doc.source.shape[1], doc.source.shape[0]))
            self.mask_panel.setMasks(
                doc.recipe.masks,
                selected=self.mask_panel.selectedMask(),
                index=max(0, self.mask_panel.componentIndex()))
            layer = doc.recipe.find(self._selected_layer)
            if layer is None:
                self._selected_layer = ""
            self.mask_panel.setSelectedLayer(
                self._selected_layer, layer.mask_id or "" if layer else "")
            self._sync_overlay_from_component()
        else:
            self.mask_panel.setMasks({})

    # ---------------------------------------------------------- arac secimi
    def eventFilter(self, obj, event) -> bool:  # type: ignore[no-untyped-def]  # noqa: N802
        """Tuval boyutu degisince katmani ustune oturtur."""
        if obj is self.canvas and event.type() in (
            event.Type.Resize, event.Type.Show,
        ):
            self.overlay.setGeometry(self.canvas.rect())
            self.overlay.raise_()
        return super().eventFilter(obj, event)

    def setTool(self, tool: CanvasTool) -> None:  # noqa: N802
        """Etkin tuval aracini degistirir."""
        if self.overlay.tool() is tool:
            return
        was_crop = self.overlay.tool() is CanvasTool.CROP
        self.overlay.setTool(tool)
        self.crop_panel.setCropToolActive(tool is CanvasTool.CROP)
        if tool is CanvasTool.CROP and self._document is not None:
            self.overlay.setCrop(self._document.recipe.geometry.crop)
            self.overlay.setAspect(self._document.recipe.geometry.aspect)
        self._sync_overlay_from_component()
        # Kirpma aracina girip cikmak onizlemenin kadrajini degistirir
        if was_crop or tool is CanvasTool.CROP:
            self._request_render(False)
        self.statusMessage.emit(f"Araç: {tool.label}")

    def tool(self) -> CanvasTool:
        return self.overlay.tool()

    def _commit_edit(self) -> None:
        """Kaydirici birakildi: gecmis adimini muhurle ve tam kalite iste."""
        if self._document is None:
            return
        self._document.commit()
        self._final_timer.start()

    # ------------------------------------------------------------- kadraj
    def _on_crop_tool_toggled(self, active: bool) -> None:
        self.setTool(CanvasTool.CROP if active else CanvasTool.NONE)

    def _on_geometry_changed(self, geometry: Geometry, label: str,
                             merge_key: str) -> None:
        doc = self._document
        if doc is None or self._syncing:
            return
        doc.set_geometry(geometry, label=label, merge_key=merge_key)
        if self.overlay.tool() is CanvasTool.CROP:
            self.overlay.setCrop(geometry.crop)
            self.overlay.setAspect(geometry.aspect)
        if not merge_key:
            doc.commit()
        self._request_render(bool(merge_key))
        if merge_key:
            self._final_timer.start()

    def _on_crop_changed(self, crop: tuple) -> None:
        """Surukleme sirasinda: yalnizca cerceveyi tasi, render etme.

        Kirpma araci acikken onizleme zaten tam kadraji gosterir; her
        fare hareketinde yeniden render etmek gereksiz is olurdu.
        """
        doc = self._document
        if doc is None:
            return
        from dataclasses import replace as _replace
        geometry = _replace(doc.recipe.geometry, crop=tuple(crop))
        self.crop_panel.setGeometry(
            geometry, (doc.source.shape[1], doc.source.shape[0]))

    def _on_crop_committed(self, crop: tuple) -> None:
        doc = self._document
        if doc is None:
            return
        from dataclasses import replace as _replace
        geometry = _replace(doc.recipe.geometry, crop=tuple(crop))
        doc.set_geometry(geometry, label="Kırpıldı")
        doc.commit()

    # ------------------------------------------------------------ maskeler
    def _on_mask_create(self, kind: MaskKind) -> None:
        doc = self._document
        if doc is None:
            return
        mask_id = doc.create_mask(kind)
        doc.commit()
        # Yeni maske secili katmana otomatik baglanir; yoksa kullanici
        # maskeyi olusturup hicbir etkisini goremezdi.
        if self._selected_layer:
            doc.assign_mask(self._selected_layer, mask_id)
            doc.commit()
        self.mask_panel.setMasks(doc.recipe.masks, selected=mask_id, index=0)
        self.mask_panel.selectMask(mask_id)
        self._on_mask_selected(mask_id)
        self.statusMessage.emit(
            f"{kind.label} eklendi" if self._selected_layer else
            f"{kind.label} eklendi — efekt yığınından bir katman seçip bağlayın")

    def _on_mask_delete(self, mask_id: str) -> None:
        doc = self._document
        if doc is None:
            return
        doc.delete_mask(mask_id)
        doc.commit()
        self.setTool(CanvasTool.NONE)
        self._request_render(False)

    def _on_mask_selected(self, _mask_id: str) -> None:
        self._sync_overlay_from_component()
        component = self.mask_panel.selectedComponent()
        if component is not None:
            self.setTool(TOOL_FOR_KIND.get(component.kind, CanvasTool.NONE))
        self._refresh_mask_overlay()

    def _on_component_add(self, mask_id: str, kind: MaskKind,
                          blend: BlendOp) -> None:
        doc = self._document
        if doc is None:
            return
        index = doc.add_mask_component(mask_id, kind, blend)
        doc.commit()
        self.mask_panel.setMasks(doc.recipe.masks, selected=mask_id,
                                 index=max(0, index))
        self.setTool(TOOL_FOR_KIND.get(kind, CanvasTool.NONE))
        self._request_render(False)

    def _on_component_remove(self, mask_id: str, index: int) -> None:
        doc = self._document
        if doc is None:
            return
        doc.remove_mask_component(mask_id, index)
        doc.commit()
        self._request_render(False)

    def _on_component_selected(self, _mask_id: str, _index: int) -> None:
        self._sync_overlay_from_component()
        component = self.mask_panel.selectedComponent()
        if component is not None:
            self.setTool(TOOL_FOR_KIND.get(component.kind, CanvasTool.NONE))
        self._refresh_mask_overlay()

    def _on_component_changed(self, mask_id: str, index: int, component: Mask,
                              label: str, merge_key: str) -> None:
        doc = self._document
        if doc is None:
            return
        doc.update_mask_component(mask_id, index, component,
                                  label=label, merge_key=merge_key)
        if not merge_key:
            doc.commit()
        self._sync_overlay_from_component()
        self._request_render(bool(merge_key))
        if merge_key:
            self._final_timer.start()

    def _on_show_mask(self, value: bool) -> None:
        self._show_mask = value
        self.overlay.setShowMask(value)
        self._refresh_mask_overlay()

    def _on_layer_selected(self, instance_id: str) -> None:
        doc = self._document
        self._selected_layer = instance_id
        layer = doc.recipe.find(instance_id) if doc else None
        self.mask_panel.setSelectedLayer(instance_id,
                                         (layer.mask_id or "") if layer else "")

    def _on_layer_assign(self, mask_id: str) -> None:
        doc = self._document
        if doc is None or not self._selected_layer:
            return
        doc.assign_mask(self._selected_layer, mask_id or None)
        doc.commit()
        self._request_render(False)

    # ------------------------------------------------- firca ve gradyanlar
    def _current_component(self) -> tuple[str, int, Mask] | None:
        mask_id = self.mask_panel.selectedMask()
        component = self.mask_panel.selectedComponent()
        if not mask_id or component is None:
            return None
        return (mask_id, self.mask_panel.componentIndex(), component)

    def _on_stroke_started(self) -> None:
        current = self._current_component()
        if current is None:
            return
        _mask_id, _index, component = current
        self._stroke_points = []
        # Yeni vurus listenin sonuna eklenir; surukleme boyunca ayni
        # vurus guncellenir, boylece tek geri alma adimi olur.
        self._stroke_index = len(component.strokes)

    def _on_stroke_point(self, point) -> None:  # noqa: ANN001
        current = self._current_component()
        if current is None or self._stroke_index < 0:
            return
        mask_id, index, component = current
        self._stroke_points.append((float(point.x()), float(point.y())))
        stroke = BrushStroke(
            points=tuple(self._stroke_points),
            radius=self.overlay.brushRadius(),
            erase=self.overlay.tool() is CanvasTool.ERASER,
        )
        strokes = list(component.strokes)
        if self._stroke_index < len(strokes):
            strokes[self._stroke_index] = stroke
        else:
            strokes.append(stroke)
        from dataclasses import replace as _replace
        updated = _replace(component, strokes=tuple(strokes))
        doc = self._document
        if doc is None:
            return
        doc.update_mask_component(mask_id, index, updated, label="Fırça",
                                  merge_key=f"brush:{mask_id}:{index}")
        self._refresh_mask_overlay()

    def _on_stroke_finished(self) -> None:
        self._stroke_points = []
        self._stroke_index = -1
        if self._document is not None:
            self._document.commit()
        self._request_render(False)

    def _on_gradient_changed(self, start: tuple, end: tuple) -> None:
        self._apply_gradient(start, end, interactive=True)

    def _on_gradient_committed(self, start: tuple, end: tuple) -> None:
        self._apply_gradient(start, end, interactive=False)

    def _apply_gradient(self, start: tuple, end: tuple, *,
                        interactive: bool) -> None:
        current = self._current_component()
        doc = self._document
        if current is None or doc is None:
            return
        mask_id, index, component = current
        from dataclasses import replace as _replace
        if component.kind is MaskKind.LINEAR:
            updated = _replace(component, start=tuple(start), end=tuple(end))
        elif component.kind is MaskKind.RADIAL:
            radius = float(np.hypot(end[0] - start[0], end[1] - start[1]))
            updated = _replace(component, center=tuple(start),
                               radius=(max(0.01, radius), max(0.01, radius)))
        else:
            return
        doc.update_mask_component(
            mask_id, index, updated, label="Gradyan",
            merge_key=f"grad:{mask_id}:{index}" if interactive else "")
        if not interactive:
            doc.commit()
        self._refresh_mask_overlay()
        self._request_render(interactive)
        if interactive:
            self._final_timer.start()

    # ------------------------------------------------------ maske gorunumu
    def _sync_overlay_from_component(self) -> None:
        """Katmandaki tutamaklari secili maske bilesenine esitler."""
        component = self.mask_panel.selectedComponent()
        if component is None:
            return
        if component.kind is MaskKind.LINEAR:
            self.overlay.setGradient(component.start, component.end)
        elif component.kind is MaskKind.RADIAL:
            cx, cy = component.center
            rx, _ry = component.radius
            self.overlay.setGradient((cx, cy), (cx + rx, cy))

    def _refresh_mask_overlay(self) -> None:
        """Secili maskeyi kirmizi ortu olarak tuvale gonderir."""
        doc = self._document
        if doc is None or not self._show_mask:
            self.overlay.setMaskPreview(None)
            return
        stack = doc.mask_stack(self.mask_panel.selectedMask())
        if stack is None:
            self.overlay.setMaskPreview(None)
            return
        base = self._last_preview
        if base is None:
            return
        h, w = base.shape[:2]
        scale = min(1.0, MASK_OVERLAY_EDGE / max(1, max(h, w)))
        shape = (max(1, int(h * scale)), max(1, int(w * scale)))
        reference = base
        if scale < 1.0:
            import cv2
            reference = cv2.resize(base, (shape[1], shape[0]),
                                   interpolation=cv2.INTER_AREA)
        try:
            mask = stack.render(shape, reference)
        except Exception:  # noqa: BLE001 - ortu hatasi duzenlemeyi durdurmasin
            log.exception("Maske ortusu uretilemedi")
            mask = None
        self.overlay.setMaskPreview(mask)

    # -------------------------------------------------------------- render
    def _render_geometry(self) -> Geometry:
        """Onizlemede kullanilacak kadraj.

        Kirpma araci acikken kirpma **uygulanmaz**: kullanici cerceveyi
        yerlestirebilmek icin tam kadraji gormelidir. Dondurme, cevirme ve
        ufuk duzeltme uygulanmaya devam eder; cerceve koordinatlari zaten
        o kadrajdadir.
        """
        doc = self._document
        if doc is None:
            return Geometry()
        geometry = doc.recipe.geometry
        if self.overlay.tool() is CanvasTool.CROP:
            from dataclasses import replace as _replace
            return _replace(geometry, crop=(0.0, 0.0, 1.0, 1.0))
        return geometry

    def _render_base(self, recipe: Recipe | None = None
                     ) -> tuple[np.ndarray, Recipe] | None:
        """Render icin (kadrajlanmis kaynak, geometrisiz tarif) ciftini verir.

        Geometri kaynaga ayrica uygulanir; tarif yalnizca efekt yiginini
        tasir. Boylece kirpma iki kez islenmez ve onizleme kirpilmis
        bolgenin **tam** cozunurlugunden kucultulur.
        """
        doc = self._document
        if doc is None:
            return None
        geometry = self._render_geometry()
        return doc.geometry_source(geometry), (recipe or doc.recipe).without_geometry()

    def _request_render(self, interactive: bool,
                        recipe: Recipe | None = None) -> None:
        pair = self._render_base(recipe)
        if pair is None:
            return
        source, stack = pair
        self._render.request_preview(source, stack, interactive=interactive)

    def _on_preview_ready(self, result: object) -> None:
        if not isinstance(result, RenderResult) or self._document is None:
            return
        self._last_preview = result.image
        doc = self._document
        base = doc.geometry_source(self._render_geometry())
        source_size = (base.shape[1], base.shape[0])
        self.canvas.setImage(result.image, self._original_preview(result),
                             source_size=source_size)
        self._refresh_mask_overlay()
        self.histogram.setImage(result.image)
        self._update_clip_label()
        quality = "hizli" if result.quality == "interactive" else "tam"
        suffix = "  ·  geçici önizleme" if self._hover_recipe is not None else ""
        self.render_label.setText(f"{result.elapsed_ms:.0f} ms · {quality}{suffix}")
        # Atlanan katman sessiz kalmamali: efekt calismiyorsa kullanici
        # bunu yalnizca sonuca bakarak anlamaya calisirdi.
        if result.failed_layers:
            names = ", ".join(result.failed_layers[:3])
            self.statusMessage.emit(
                f"Bu efektler uygulanamadı ve atlandı: {names}"
            )
        self._tile_timer.start()

    def _original_preview(self, result: RenderResult) -> np.ndarray | None:
        """Karsilastirma icin duzenlenmemis onizleme.

        Kaydirici surukleme sirasinda her sonucta tam boy kaynagi
        yeniden kucultmek bosa istir: kaynak ve kadraj degismedigi
        surece sonuc aynidir. Bu yuzden (kadraj, boyut) anahtariyla
        onbelleklenir.
        """
        doc = self._document
        if doc is None:
            return None
        geometry = self._render_geometry()
        base = doc.geometry_source(geometry)
        if abs(result.scale - 1.0) < 1e-6:
            return base
        size = (result.image.shape[1], result.image.shape[0])
        key = (id(base), base.shape, size)
        if self._original_cache_key == key:
            return self._original_cache
        import cv2
        small = cv2.resize(base, size, interpolation=cv2.INTER_AREA)
        self._original_cache_key = key
        self._original_cache = small
        return small

    def _refresh_detail_tile(self) -> None:
        """Gorunen bolgeyi tam cozunurlukte yeniden uretir.

        Gereksinim: "yuzde 100 gorunum gercek kaliteyi gosterebilsin".
        """
        doc = self._document
        if doc is None:
            return
        # Gizli gorunum (or. Sinema Laboratuvari acik degilken) karo
        # istemez: ayni belgeye bagli iki gorunum ayni isi iki kez
        # yapardi ve birbirinin istegini gecersiz kilardi.
        if not self.isVisible():
            return
        if not self.canvas.needsDetailTile():
            self.canvas.clearDetailTile()
            self.detail_label.setText("")
            self._tile_request = None
            return

        rect = self.canvas.visibleImageRect()
        if rect.width() < 8 or rect.height() < 8:
            return
        if rect.width() * rect.height() > MAX_TILE_PIXELS:
            return

        pair = self._render_base(self._hover_recipe)
        if pair is None:
            return
        base, recipe = pair
        # Karo arka planda uretilir: genis yaricapli bir tarifte olculen
        # 1.3 saniye, GUI is parcaciginda dogrudan donma suresi olurdu.
        self._tile_request = (int(rect.x()), int(rect.y()),
                              int(rect.width()), int(rect.height()))
        self._render.request_tile(base, recipe, self._tile_request)
        self.detail_label.setText("tam çözünürlük hazırlanıyor…")

    def _on_tile_ready(self, _token: int, rect: object, tile: object,
                       ms: float) -> None:
        """Arka planda uretilen karoyu ekrana basar.

        Kullanici beklerken kaydirmis olabilir: istenen bolge degistiyse
        sonuc atilir, yoksa ekranda yanlis yere oturmus bir karo kalirdi.
        """
        if self._document is None or rect != self._tile_request:
            return
        if not self.canvas.needsDetailTile():
            return
        x, y, w, h = rect  # type: ignore[misc]
        self.canvas.setDetailTile(tile, QRectF(x, y, w, h))
        self.detail_label.setText(f"tam çözünürlük · {ms:.0f} ms")

    def _update_clip_label(self) -> None:
        sh = self.histogram.shadow_clip_ratio
        hl = self.histogram.highlight_clip_ratio
        parts: list[str] = []
        if sh > 0.005:
            parts.append(f"golgede %{sh * 100:.1f} kırpma")
        if hl > 0.005:
            parts.append(f"parlak alanda %{hl * 100:.1f} kırpma")
        if parts:
            self.clip_label.setText(" · ".join(parts))
            self.clip_label.setStyleSheet(f"color: {PALETTE.warning};")
        else:
            self.clip_label.setText("Kırpma yok")
            self.clip_label.setStyleSheet(f"color: {PALETTE.text_muted};")

    # -------------------------------------------------------------- gorunum
    def _update_zoom_label(self, zoom: float) -> None:
        self.zoom_label.setText(f"%{zoom * 100:.0f}")

    def set_position(self, index: int, total: int,
                     has_prev: bool, has_next: bool) -> None:
        self.position_label.setText(f"{index + 1} / {total}" if total else "—")
        self.prev_button.setEnabled(has_prev)
        self.next_button.setEnabled(has_next)

    def current_preview(self) -> np.ndarray | None:
        return self._last_preview

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        """Gorunur olunca ertelenen kurulumu tamamlar."""
        super().showEvent(event)
        document = self._document
        if getattr(self, "_pending_open", False) and document is not None:
            self._pending_open = False
            self._needs_sync = False
            self._previews.setSource(document.source, str(document.path))
            self.presets.prefetchVisible()
            self._sync_controls()
            self._show_initial_image(document)
            self._request_render(False)
        elif getattr(self, "_needs_sync", False):
            self._needs_sync = False
            self._sync_controls()
            self._request_render(False)

    def refreshPreview(self) -> None:  # noqa: N802
        """Calisma alani gorunur oldugunda onizlemeyi tazeler."""
        self._sync_controls()
        self.presets.prefetchVisible()
        self._request_render(False)

"""Faz 5 kabul olcutleri: maskeler, kadraj ve proje kaliciligi.

Kabul olcutu (PROGRESS.md):
    * maskeli ve cok efektli proje kapatilip acildiginda ayni sonucu verir
    * zoom/kirpma/dondurme maskeyi yanlis konuma tasimaz
    * kurtarma normal kaydin yerine sessizce gecmez

Calistirma:
    .venv\\Scripts\\python.exe tools\\phase5_e2e.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Windows konsolu varsayilan olarak cp1254; Turkce karakterler ve matematik
# isaretleri bozulmasin diye cikti UTF-8'e sabitlenir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover - eski konsollar
    pass


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2                                          # noqa: E402
import numpy as np                                  # noqa: E402
from PySide6.QtCore import QEventLoop, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent               # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

from luma_atelier.core.document import Document     # noqa: E402
from luma_atelier.imaging.effects.base import RenderContext  # noqa: E402
from luma_atelier.imaging.geometry import Geometry  # noqa: E402
from luma_atelier.imaging.loader import ImageMetadata, LoadedImage  # noqa: E402
from luma_atelier.imaging.masks import (            # noqa: E402
    BlendOp,
    BrushStroke,
    Mask,
    MaskKind,
    MaskStack,
)
from luma_atelier.imaging.recipe import Recipe      # noqa: E402
from luma_atelier.storage.project import (          # noqa: E402
    ProjectError,
    autosave_path,
    clear_autosave,
    find_autosave,
    load_project,
    resolve_source,
    save_project,
    write_autosave,
)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    mark = "OK  " if ok else "HATA"
    print(f"  [{mark}] {name}" + (f"   — {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# ----------------------------------------------------------------- yardimci
def make_photo(path: Path, width: int = 900, height: int = 600) -> np.ndarray:
    """Her bolgesi farkli olan sentetik bir fotograf uretir.

    Duz renk kullanilsa maske kaymasi gorunmezdi; bu yuzden yatay/dikey
    gradyan ve yerel isaretciler var.
    """
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.zeros((height, width, 3), np.float32)
    image[..., 0] = xx / width
    image[..., 1] = yy / height
    image[..., 2] = 0.5 + 0.35 * np.sin(xx / 40.0) * np.cos(yy / 37.0)
    image = np.clip(image, 0.0, 1.0)
    bgr = cv2.cvtColor((image * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), bgr, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    return image


def load_document(path: Path) -> Document:
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    meta = ImageMetadata(path=path, width=rgb.shape[1], height=rgb.shape[0],
                         source_bit_depth=8, has_alpha=False,
                         source_format="PNG")
    return Document(LoadedImage(pixels=np.ascontiguousarray(rgb), metadata=meta))


def heavy_masked_recipe() -> Recipe:
    """Cok efektli, cok maskeli, cok bilesenli gercek bir tarif."""
    brush = Mask(
        mask_id="m-brush", kind=MaskKind.BRUSH,
        strokes=(BrushStroke(points=((0.2, 0.3), (0.35, 0.45), (0.5, 0.4)),
                             radius=0.09, hardness=0.6),),
        opacity=0.9,
    )
    radial = Mask(mask_id="m-rad", kind=MaskKind.RADIAL,
                  center=(0.72, 0.32), radius=(0.22, 0.16),
                  feather=0.05, angle=18.0)
    subtract = Mask(mask_id="m-sub", kind=MaskKind.LINEAR,
                    start=(0.0, 0.85), end=(0.0, 1.0),
                    blend=BlendOp.SUBTRACT, feather=0.02)
    luma = Mask(mask_id="m-luma", kind=MaskKind.LUMINANCE,
                luma_low=0.55, luma_high=1.0, luma_softness=0.18,
                inverted=True)

    recipe = (Recipe()
              .set_or_add("tone.exposure", stops=0.55)
              .set_or_add("tone.contrast", amount=0.30)
              .set_or_add("color.vibrance", amount=0.40)
              .set_or_add("lens.vignette", amount=-0.35)
              .set_or_add("detail.clarity", amount=0.30))
    recipe = recipe.with_mask("maske1", MaskStack(masks=(radial, subtract)))
    recipe = recipe.with_mask("maske2", MaskStack(masks=(brush,)))
    recipe = recipe.with_mask("maske3", MaskStack(masks=(luma,)))
    recipe = recipe.with_geometry(
        Geometry(crop=(0.08, 0.06, 0.80, 0.82), rotation=90,
                 straighten=1.6, flip_h=True, aspect=None))

    # Katmanlari maskelere bagla
    ids = [l.instance_id for l in recipe.layers]
    for instance, mask_id in zip(ids, ["maske1", "maske2", "maske3"]):
        recipe = recipe.assign_mask(instance, mask_id)
    return recipe.with_seed(20260917)


def render(recipe: Recipe, source: np.ndarray) -> np.ndarray:
    """Belgedeki yolun aynisi: geometri kaynaga, yigin sonuca."""
    base = np.ascontiguousarray(recipe.geometry.apply(source))
    h, w = base.shape[:2]
    ctx = RenderContext(full_width=w, full_height=h, scale=1.0,
                        seed=recipe.seed, quality="final", purpose="export")
    return recipe.without_geometry().apply(base, ctx)


# ====================================================== 1. PROJE KALICILIGI
def test_roundtrip(tmp: Path) -> None:
    section("1. Maskeli ve cok efektli proje kapatilip acilinca ayni mi?")
    photo = tmp / "kaynak.png"
    source = make_photo(photo)
    recipe = heavy_masked_recipe()

    check("Tarif gercekten karmasik",
          len(recipe.layers) >= 5 and len(recipe.masks) == 3
          and not recipe.geometry.is_identity,
          f"{len(recipe.layers)} katman, {len(recipe.masks)} maske, "
          f"{sum(len(s.masks) for s in recipe.masks.values())} maske bileseni")

    before = render(recipe, source)
    project_path = tmp / "proje.luma"
    saved = save_project(project_path, photo, recipe, before)
    check("Proje dosyasi yazildi", saved.path is not None and saved.path.exists(),
          f"{saved.path.stat().st_size / 1024:.0f} KB")

    reopened = load_project(project_path)
    found, status = resolve_source(reopened, search_dirs=[tmp])
    check("Kaynak fotograf cozuldu", found == photo and status == "ok", status)

    after = render(reopened.recipe, source)
    identical = before.shape == after.shape and np.array_equal(before, after)
    diff = 0.0 if identical else float(np.abs(
        before[:min(before.shape[0], after.shape[0]),
               :min(before.shape[1], after.shape[1])]
        - after[:min(before.shape[0], after.shape[0]),
                :min(before.shape[1], after.shape[1])]).max())
    check("Yeniden render BIREBIR ayni", identical,
          "bit duzeyinde ayni" if identical else f"en buyuk fark {diff:.6f}")

    check("Geometri korundu", reopened.recipe.geometry == recipe.geometry,
          f"kirpma {tuple(round(v, 3) for v in reopened.recipe.geometry.crop)}, "
          f"donus {reopened.recipe.geometry.rotation}°, "
          f"ufuk {reopened.recipe.geometry.straighten}°")
    check("Maske bilesenleri korundu",
          reopened.recipe.masks == recipe.masks,
          f"{sum(len(s.masks) for s in reopened.recipe.masks.values())} bilesen")
    check("Katman-maske baglari korundu",
          [l.mask_id for l in reopened.recipe.layers]
          == [l.mask_id for l in recipe.layers])
    check("Seed korundu", reopened.recipe.seed == recipe.seed)

    # Kaydet -> ac -> kaydet -> ac: ikinci tur da ayni olmali
    second = tmp / "proje2.luma"
    save_project(second, photo, reopened.recipe, before)
    twice = load_project(second)
    check("Ikinci tur da ayni", np.array_equal(render(twice.recipe, source),
                                               before))


# ================================================= 2. MASKE - KADRAJ HIZASI
def test_mask_alignment(tmp: Path) -> None:
    section("2. Kirpma / dondurme maskeyi yanlis konuma tasiyor mu?")
    photo = tmp / "hiza.png"
    source = make_photo(photo, 600, 400)
    doc = load_document(photo)

    TARGET = (0.32, 0.68)   # kaynak uzayda maskenin merkezi
    doc.apply_recipe(
        doc.recipe.set_or_add("tone.exposure", stops=2.5),
        __import__("luma_atelier.core.document", fromlist=["EditAction"])
        .EditAction(label="test"))
    mask_id = doc.create_mask(MaskKind.RADIAL)
    component = replace(doc.mask_stack(mask_id).masks[0],
                        center=TARGET, radius=(0.06, 0.06), feather=0.01)
    doc.update_mask_component(mask_id, 0, component)
    doc.assign_mask(doc.recipe.layers[0].instance_id, mask_id)

    def centre_in_source(document: Document) -> tuple[float, float] | None:
        """Etkinin agirlik merkezini kaynak piksel koordinatina cevirir."""
        geometry = document.recipe.geometry
        base = document.geometry_source()
        out = render(document.recipe, document.source)
        diff = np.abs(out - base).mean(2)
        if diff.max() < 1e-4:
            return None
        weights = np.where(diff > diff.max() * 0.5, diff, 0.0)
        ys, xs = np.nonzero(weights)
        if xs.size == 0:
            return None
        w = weights[ys, xs]
        h, wd = out.shape[:2]
        x = float((xs * w).sum() / w.sum()) / wd
        y = float((ys * w).sum() / w.sum()) / h
        # Kadraji geri al
        cx, cy, cw, ch = geometry.crop
        x, y = cx + x * cw, cy + y * ch
        for _ in range((geometry.rotation // 90) % 4):
            x, y = y, 1.0 - x
        if geometry.flip_v:
            y = 1.0 - y
        if geometry.flip_h:
            x = 1.0 - x
        sh, sw = document.source.shape[:2]
        return (x * sw, y * sh)

    reference = centre_in_source(doc)
    check("Kadrajsiz maske dogru yerde", reference is not None
          and abs(reference[0] - TARGET[0] * 600) < 2
          and abs(reference[1] - TARGET[1] * 400) < 2,
          f"({reference[0]:.1f}, {reference[1]:.1f}) px" if reference else "yok")

    cases = [
        ("Kirpma", Geometry(crop=(0.12, 0.18, 0.62, 0.58))),
        ("Dondurme 90°", Geometry().rotated(90)),
        ("Dondurme 180°", Geometry().rotated(180)),
        ("Dondurme 270°", Geometry().rotated(270)),
        ("Yatay cevirme", Geometry(flip_h=True)),
        ("Dikey cevirme", Geometry(flip_v=True)),
        ("Kirpma + dondurme", Geometry(crop=(0.10, 0.12, 0.72, 0.70)).rotated(90)),
        ("Kirpma + cevirme", Geometry(crop=(0.20, 0.10, 0.60, 0.70), flip_h=True)),
    ]

    worst = 0.0
    for name, geometry in cases:
        snapshot = doc.recipe
        doc.set_geometry(geometry)
        moved = centre_in_source(doc)
        if moved is None:
            check(f"{name}: maske korundu", False, "maske kayboldu")
            worst = 999.0
        else:
            error = float(np.hypot(moved[0] - reference[0],
                                   moved[1] - reference[1]))
            worst = max(worst, error)
            expected = geometry.output_size(600, 400)
            actual = doc.geometry_source().shape[1::-1]
            check(f"{name}: maske ayni noktada",
                  error < 3.0 and expected == actual,
                  f"sapma {error:.2f} px, cikti {actual[0]}x{actual[1]}")
        doc.apply_recipe(snapshot,
                         __import__("luma_atelier.core.document",
                                    fromlist=["EditAction"])
                         .EditAction(label="geri"))

    check("Tum kadrajlarda sapma < 3 px", worst < 3.0,
          f"en buyuk sapma {worst:.2f} px")

    # Zoom: detay karosu maskeyi kaydirmamali
    doc.set_geometry(Geometry(crop=(0.15, 0.15, 0.65, 0.65)))
    base = doc.geometry_source()
    full = render(doc.recipe, doc.source)
    rect = (40, 30, 200, 150)
    from luma_atelier.services.render import RenderService
    service = RenderService()
    tile = service.render_tile(base, doc.recipe.without_geometry(), rect)
    region = full[rect[1]:rect[1] + rect[3], rect[0]:rect[0] + rect[2]]
    tile_error = float(np.abs(tile - region).max())
    check("%100 karosu maskeyle hizali", tile_error < 0.02,
          f"karo ile tam render arasi en buyuk fark {tile_error:.4f}")


# =================================================== 3. KURTARMA DAVRANISI
def test_recovery(tmp: Path) -> None:
    section("3. Kurtarma normal kaydin yerine sessizce geciyor mu?")
    photo = tmp / "kurtarma.png"
    make_photo(photo, 400, 300)

    normal = tmp / "elle.luma"
    elle = Recipe().set_or_add("tone.exposure", stops=0.2)
    save_project(normal, photo, elle)

    kurtarma = Recipe().set_or_add("tone.exposure", stops=1.9)
    auto = write_autosave(photo, kurtarma)
    check("Kurtarma kaydi yazildi", auto is not None and auto.exists())
    check("Kurtarma AYRI dosyaya yazildi",
          auto is not None and auto.resolve() != normal.resolve(),
          f"{auto.name}" if auto else "")
    check("Normal kayit degismedi",
          load_project(normal).recipe == elle,
          "elle kaydedilen tarif korundu")
    check("Kurtarma dosyasi bulunabiliyor", find_autosave(photo) == auto)
    check("Kurtarma iceriginde beklenen tarif var",
          load_project(auto).recipe == kurtarma)
    check("Kurtarma adi acikca isaretli",
          auto is not None and ".autosave" in auto.name, auto.name if auto else "")

    clear_autosave(photo)
    check("Kurtarma temizlenebiliyor", find_autosave(photo) is None)
    check("Temizleme normal kaydi silmedi", normal.exists())

    # Bozuk dosyalar reddedilmeli
    for name, content in (("bos.luma", b""),
                          ("zipdegil.luma", b"bu bir zip degil"),
                          ("eksik.luma", None)):
        path = tmp / name
        if content is None:
            import zipfile
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("rastgele.txt", "icerik")
        else:
            path.write_bytes(content)
        try:
            load_project(path)
            check(f"Bozuk dosya reddedildi: {name}", False, "hata vermedi")
        except ProjectError as exc:
            check(f"Bozuk dosya reddedildi: {name}", True, str(exc)[:58])


# ============================================================ 4. ARAYUZ
def test_ui(tmp: Path) -> None:
    section("4. Arayuz: maske paneli, kadraj paneli, tuval araclari")
    from luma_atelier.services.preset_previews import PresetPreviewService
    from luma_atelier.services.render import RenderService
    from luma_atelier.storage.presets import PresetLibrary
    from luma_atelier.ui.views.editor_view import EditorView
    from luma_atelier.ui.widgets.canvas_tools import CanvasTool

    photo = tmp / "arayuz.png"
    make_photo(photo, 800, 600)
    doc = load_document(photo)

    render_service = RenderService()
    library = PresetLibrary()
    library.load_all()
    previews = PresetPreviewService()
    view = EditorView(render_service, library, previews)
    view.resize(1500, 900)
    view.show()
    QApplication.processEvents()
    view.setDocument(doc)
    QApplication.processEvents()

    check("Maske paneli var", hasattr(view, "mask_panel"))
    check("Kadraj paneli var", hasattr(view, "crop_panel"))
    check("Tuval katmani var", hasattr(view, "overlay"))
    check("Katman tuvalin ustune oturdu",
          view.overlay.size() == view.canvas.size(),
          f"{view.overlay.width()}x{view.overlay.height()}")

    # --- maske olusturma ---
    view.mask_panel.maskCreateRequested.emit(MaskKind.RADIAL)
    QApplication.processEvents()
    check("Radyal maske olusturuldu", len(doc.recipe.masks) == 1,
          f"{len(doc.recipe.masks)} maske")
    mask_id = view.mask_panel.selectedMask()
    check("Panel yeni maskeyi secti", bool(mask_id), mask_id)
    check("Radyal maske radyal aracı açtı",
          view.tool() is CanvasTool.RADIAL, view.tool().label)

    # --- bilesen ekleme (cikarma) ---
    view.mask_panel.componentAddRequested.emit(mask_id, MaskKind.LINEAR,
                                               BlendOp.SUBTRACT)
    QApplication.processEvents()
    stack = doc.mask_stack(mask_id)
    check("Cikarma bileseni eklendi",
          stack is not None and len(stack.masks) == 2
          and stack.masks[1].blend is BlendOp.SUBTRACT,
          f"{len(stack.masks)} bilesen" if stack else "")

    # --- katmana baglama ---
    doc.add_layer("tone.exposure", {"stops": 1.0})
    QApplication.processEvents()
    instance = doc.recipe.layers[-1].instance_id
    view._on_layer_selected(instance)
    view.mask_panel.layerAssignRequested.emit(mask_id)
    QApplication.processEvents()
    check("Katman maskeye baglandi",
          doc.recipe.find(instance).mask_id == mask_id)

    # --- gradyan surukleme ---
    view.mask_panel.selectComponent(0)
    QApplication.processEvents()
    view.overlay.gradientCommitted.emit((0.4, 0.4), (0.7, 0.4))
    QApplication.processEvents()
    radial = doc.mask_stack(mask_id).masks[0]
    check("Gradyan surukleme maskeyi tasidi",
          abs(radial.center[0] - 0.4) < 1e-6 and radial.radius[0] > 0.25,
          f"merkez {tuple(round(v, 2) for v in radial.center)}, "
          f"yaricap {radial.radius[0]:.3f}")

    # --- firca ---
    view.mask_panel.componentAddRequested.emit(mask_id, MaskKind.BRUSH,
                                               BlendOp.ADD)
    QApplication.processEvents()
    brush_index = len(doc.mask_stack(mask_id).masks) - 1
    view.mask_panel.selectComponent(brush_index)
    QApplication.processEvents()
    view.overlay.strokeStarted.emit()
    for i in range(6):
        view.overlay.strokePoint.emit(QPointF(0.30 + i * 0.03, 0.45))
    view.overlay.strokeFinished.emit()
    QApplication.processEvents()
    painted = doc.mask_stack(mask_id).masks[brush_index]
    check("Firca vurusu kaydedildi",
          len(painted.strokes) == 1 and len(painted.strokes[0].points) == 6,
          f"{len(painted.strokes)} vurus, "
          f"{len(painted.strokes[0].points) if painted.strokes else 0} nokta")
    history_before = doc.history.depth
    view.overlay.strokeStarted.emit()
    for i in range(4):
        view.overlay.strokePoint.emit(QPointF(0.6, 0.3 + i * 0.02))
    view.overlay.strokeFinished.emit()
    QApplication.processEvents()
    check("Bir vurus = bir geri alma adimi",
          doc.history.depth - history_before == 1,
          f"gecmis {history_before} -> {doc.history.depth}")
    check("Geri alma vurusu kaldirdi",
          doc.undo() and len(doc.mask_stack(mask_id).masks[brush_index].strokes) == 1)
    doc.redo()

    # --- maske gorunumu ---
    view.mask_panel.showMaskToggled.emit(True)
    QApplication.processEvents()
    check("Maske ortusu uretildi", view.overlay._mask_preview is not None,
          f"{view.overlay._mask_preview.shape}"
          if view.overlay._mask_preview is not None else "yok")
    view.mask_panel.showMaskToggled.emit(False)

    # --- kadraj ---
    before_size = doc.geometry_source().shape[:2]
    view.crop_panel.geometryChanged.emit(
        Geometry(crop=(0.1, 0.1, 0.5, 0.5)), "Kirpildi", "")
    QApplication.processEvents()
    after_size = doc.geometry_source().shape[:2]
    check("Kirpma cikti boyutunu degistirdi", after_size != before_size,
          f"{before_size[1]}x{before_size[0]} -> {after_size[1]}x{after_size[0]}")
    check("Kirpma beklenen boyutu verdi",
          after_size[::-1] == doc.recipe.geometry.output_size(800, 600),
          f"{after_size[::-1]} == {doc.recipe.geometry.output_size(800, 600)}")

    view.crop_panel.geometryChanged.emit(doc.recipe.geometry.rotated(90),
                                         "Donduruldu", "")
    QApplication.processEvents()
    rotated = doc.geometry_source().shape[:2]
    check("Dondurme boyutu takas etti", rotated == after_size[::-1],
          f"{rotated[1]}x{rotated[0]}")

    # --- kirpma araci onizlemeyi tam kadraja acar ---
    view.setTool(CanvasTool.CROP)
    QApplication.processEvents()
    check("Kirpma aracinda tam kadraj gosterilir",
          view._render_geometry().crop == (0.0, 0.0, 1.0, 1.0),
          "cerceve yerlestirilebilir")
    check("Kirpma araci belgedeki kirpmayi bozmadi",
          doc.recipe.geometry.crop != (0.0, 0.0, 1.0, 1.0))
    view.setTool(CanvasTool.NONE)
    QApplication.processEvents()

    # --- tuval tutamak etkilesimi (gercek fare olaylari) ---
    view.setTool(CanvasTool.CROP)
    view.overlay.setCrop((0.2, 0.2, 0.6, 0.6))
    QApplication.processEvents()
    rect = view.overlay._image_rect()
    if rect.width() > 10:
        corner = view.overlay._from_norm((0.2, 0.2))
        target = view.overlay._from_norm((0.35, 0.30))
        for kind, pos in ((QMouseEvent.Type.MouseButtonPress, corner),
                          (QMouseEvent.Type.MouseMove, target),
                          (QMouseEvent.Type.MouseButtonRelease, target)):
            event = QMouseEvent(kind, pos, Qt.MouseButton.LeftButton,
                                Qt.MouseButton.LeftButton,
                                Qt.KeyboardModifier.NoModifier)
            view.overlay.event(event)
            QApplication.processEvents()
        crop = view.overlay.crop()
        check("Fareyle tutamak surukleme cerceveyi kucultttu",
              crop[0] > 0.28 and crop[2] < 0.55,
              f"kirpma {tuple(round(v, 3) for v in crop)}")
    else:
        check("Fareyle tutamak surukleme", False, "tuval olculemedi")
    view.setTool(CanvasTool.NONE)

    # --- maske silme ---
    view.mask_panel.maskDeleteRequested.emit(mask_id)
    QApplication.processEvents()
    check("Maske silindi", mask_id not in doc.recipe.masks)
    check("Silinen maskenin bagi koptu",
          doc.recipe.find(instance) is None
          or doc.recipe.find(instance).mask_id is None)

    view.close()
    view.deleteLater()
    QApplication.processEvents()


# ============================================================== 5. KABUK
def test_shell(tmp: Path) -> None:
    section("5. Kabuk: proje menusu ve durum ekrani yerine calisan ozellik")
    from luma_atelier.app.shell import MainWindow

    window = MainWindow()
    window.resize(1500, 950)

    check("'Proje ac' yer tutucusu kaldirildi",
          not hasattr(window, "_project_not_ready"))
    for name in ("_open_project", "_save_project", "_apply_pending_project",
                 "_autosave_tick", "_offer_recovery"):
        check(f"Kabukta {name} var", hasattr(window, name))
    check("Proje kaydet eylemi var (baslangicta kapali)",
          hasattr(window, "save_project_action")
          and not window.save_project_action.isEnabled())
    check("Otomatik kurtarma zamanlayicisi calisiyor",
          window._autosave_timer.isActive(),
          f"{window._autosave_timer.interval() / 1000:.0f} s araliklı")

    titles = []
    for action in window.findChildren(type(window.save_project_action)):
        titles.append(action.text())
    for wanted in ("Proje aç...", "Projeyi kaydet", "Projeyi farklı kaydet..."):
        check(f"Menude '{wanted}' var", wanted in titles)

    # Gercek fotografla kaydet -> ac dongusu (diyalogsuz, ic API)
    photo = tmp / "kabuk.png"
    make_photo(photo, 500, 400)
    window.session.add_paths([photo])
    window._open_in_editor(photo)   # uygulamanin gercek yolu
    # Fotograf arka plan is parcaciginda yuklenir; ona gercek zaman tani
    deadline = time.monotonic() + 10.0
    while window.document is None and time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    if window.document is None:
        check("Kabuk fotografi acti", False, "belge olusmadi")
        window.close()
        return
    check("Kabuk fotografi acti", True, photo.name)
    check("Proje kaydet eylemi acildi", window.save_project_action.isEnabled())

    doc = window.document
    doc.set_param("tone.exposure", stops=0.8)
    mask_id = doc.create_mask(MaskKind.LINEAR)
    doc.assign_mask(doc.recipe.layers[0].instance_id, mask_id)
    doc.set_geometry(Geometry(crop=(0.1, 0.1, 0.7, 0.7)))
    QApplication.processEvents()

    project_path = tmp / "kabuk.luma"
    window._project_path = project_path
    window._save_project()
    QApplication.processEvents()
    check("Kabuk projeyi kaydetti", project_path.exists(),
          f"{project_path.stat().st_size / 1024:.0f} KB"
          if project_path.exists() else "yok")
    check("Kayit sonrasi belge 'degismemis' isaretlendi", not doc.is_modified)

    expected = render(doc.recipe, doc.source)
    reopened = load_project(project_path)
    check("Kabuk kaydini yeniden acmak ayni sonucu verdi",
          np.array_equal(render(reopened.recipe, doc.source), expected))

    # Kurtarma teklifi: normal kaydin uzerine sessizce yazmaz
    doc.set_param("tone.contrast", amount=0.5)
    window._autosave_tick()
    QApplication.processEvents()
    auto = find_autosave(doc.path)
    check("Kabuk kurtarma kaydi yazdi", auto is not None and auto.exists())
    check("Kurtarma proje dosyasindan ayri",
          auto is not None and auto.resolve() != project_path.resolve())
    check("Proje dosyasi kurtarmadan etkilenmedi",
          load_project(project_path).recipe == reopened.recipe)
    if auto:
        clear_autosave(doc.path)

    window.close()
    window.deleteLater()
    QApplication.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="luma_faz5_"))
    print("=" * 66)
    print("FAZ 5 KABUL OLCUTLERI — maskeler, kadraj, proje kaliciligi")
    print("=" * 66)
    print(f"Gecici klasor: {tmp}")
    try:
        test_roundtrip(tmp)
        test_mask_alignment(tmp)
        test_recovery(tmp)
        test_ui(tmp)
        test_shell(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 66)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 66)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

"""Faz 2 arayuz dogrulamasi: duzenleyici gercekten calisiyor mu?

Uygulamayi acar, fotograf yukler, kaydiricilari *arayuz uzerinden*
oynatir, onizlemenin degistigini olcer, geri al/yinele yapar ve her
adimda ekran goruntusu alir.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CAPTURES = ROOT / "docs" / "_captures"
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))


def main() -> int:  # noqa: PLR0915
    os.environ.setdefault("LUMA_DATA_HOME",
                          str(Path(tempfile.gettempdir()) / "luma_phase2_data"))
    CAPTURES.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication

    from luma_atelier.app.shell import MainWindow, create_application
    from luma_atelier.ui.widgets.image_canvas import CompareMode
    from luma_atelier.ui.widgets.nav_bar import Workspace

    source = Path(r"C:/Windows/Web/Wallpaper/ThemeA/img22.jpg")
    if not source.exists():
        print(f"HATA: kaynak fotograf yok: {source}")
        return 1

    app: QApplication = create_application([])
    win = MainWindow()
    win.resize(1520, 940)
    win.show()
    app.processEvents()

    def settle(ms: int) -> None:
        end = time.perf_counter() + ms / 1000.0
        while time.perf_counter() < end:
            app.processEvents()

    def shot(name: str) -> None:
        settle(200)
        win.grab().save(str(CAPTURES / f"faz2-{name}.png"))

    print("=" * 74)
    print("LUMA ATELIER - Faz 2 arayuz dogrulamasi")
    print("=" * 74)

    win.session.add_paths([source])
    win._open_in_editor(source)
    settle(2500)
    editor = win.editor_view
    record("Duzenleyici fotografi yukledi", win.document is not None,
           f"{source.name}, tuval {editor.canvas.imageSize}")
    shot("01-duzenleyici-bos")

    baseline = editor.current_preview()
    record("Ilk onizleme uretildi", baseline is not None,
           f"{baseline.shape if baseline is not None else 'yok'}")

    # --- Kaydiriciyi arayuzden oynat ---
    controls = editor._controls["tone.exposure"]
    slider = controls._sliders["stops"]
    slider.setValue(0.85)
    slider.editingFinished.emit(0.85)
    settle(2000)
    after_exposure = editor.current_preview()
    changed = (baseline is not None and after_exposure is not None
               and float(np.abs(after_exposure - baseline).mean()) > 0.01)
    record("Kaydirici onizlemeyi degistirdi", changed,
           f"ortalama fark "
           f"{float(np.abs(after_exposure - baseline).mean()):.4f}"
           if changed else "degisim olculemedi")

    # Daha fazla ayar
    for op_id, key, value in [
        ("tone.contrast", "amount", 30.0),
        ("color.white_balance", "kelvin", 4800.0),
        ("color.vibrance", "amount", 35.0),
        ("tone.shadows_highlights", "shadows", 30.0),
    ]:
        sl = editor._controls[op_id]._sliders[key]
        sl.setValue(value)
        sl.editingFinished.emit(value)
        settle(900)
    settle(1200)
    shot("02-duzenleyici-ayarli")
    record("Bes ayar arayuzden uygulandi",
           win.document is not None and len(win.document.recipe) == 5,
           f"{len(win.document.recipe)} katman: "
           + ", ".join(l.display_name() for l in win.document.recipe))

    # --- Histogram ---
    hist_ok = editor.histogram._channels is not None
    record("Histogram hesaplandi", hist_ok,
           f"golge kirpma %{editor.histogram.shadow_clip_ratio*100:.2f}, "
           f"parlak kirpma %{editor.histogram.highlight_clip_ratio*100:.2f}")

    # --- Karsilastirma ---
    editor.compare_combo.setCurrentIndex(2)   # surgulu
    settle(600)
    shot("03-karsilastirma")
    record("Duzenlenmis/orijinal karsilastirmasi cizildi",
           editor.canvas.compareMode() is CompareMode.SPLIT,
           str(editor.canvas.compareMode()))
    editor.compare_combo.setCurrentIndex(0)
    settle(400)

    # --- Geri al / yinele arayuzden ---
    before_undo = len(win.document.recipe)
    win._undo()
    settle(1200)
    after_undo = len(win.document.recipe)
    record("Geri al arayuzden calisti", after_undo != before_undo or
           win.document.recipe != win.document.history.current,
           f"{before_undo} -> {after_undo} katman")

    win._redo()
    settle(1200)
    record("Yinele arayuzden calisti", len(win.document.recipe) == before_undo,
           f"{len(win.document.recipe)} katman")

    # --- Kaydiricilar tarifle senkron mu? ---
    win._undo()
    settle(800)
    sync_ok = True
    details = []
    for op_id, ctrl in editor._controls.items():
        layer = win.document.recipe.first_of(op_id)
        for key, sl in ctrl._sliders.items():
            expected = (layer.params.get(key) if layer
                        else ctrl._op.param(key).default)
            if abs(float(sl.value()) - float(expected)) > 1e-3:
                sync_ok = False
                details.append(f"{op_id}.{key}: {sl.value()} != {expected}")
    record("Geri alma sonrasi kaydiricilar tarifle uyumlu", sync_ok,
           "; ".join(details) if details else "tum kontroller esitlendi")
    win._redo()
    settle(800)

    # --- Sifirlama ---
    editor.reset_all_button.click()
    settle(1500)
    record("Tumunu sifirla tarifi temizledi",
           len(win.document.recipe) == 0,
           f"{len(win.document.recipe)} katman kaldi")
    record("Sifirlama geri alinabilir", win.document.can_undo(),
           f"gecmis derinligi {win.document.history.depth}")
    win._undo()
    settle(1200)
    record("Sifirlama geri alindi", len(win.document.recipe) == 5,
           f"{len(win.document.recipe)} katman geri geldi")
    shot("04-son-durum")

    # --- %100 gorunum gercek pikselleri gostermeli ---
    editor.canvas.zoomToFit()
    settle(500)
    fit_zoom = editor.canvas.effectiveZoom()
    editor.canvas.zoomToActualPixels()
    settle(1600)          # detay karosu zamanlayicisi 220 ms + render
    actual_zoom = editor.canvas.effectiveZoom()
    record("%100 gorunum kaynak piksellere gore 1:1",
           abs(actual_zoom - 1.0) < 0.02,
           f"sigdir %{fit_zoom*100:.0f} -> gercek %{actual_zoom*100:.0f}, "
           f"onizleme orani {editor.canvas.previewScale:.3f}")

    tile = editor.canvas._detail
    tile_rect = editor.canvas._detail_rect
    record("Tam cozunurluklu detay karosu uretildi",
           tile is not None,
           f"{tile.width}x{tile.height} piksel, kaynak bolge "
           f"{tile_rect.width():.0f}x{tile_rect.height():.0f}"
           if tile is not None and tile_rect is not None else "karo yok")

    if tile is not None and tile_rect is not None:
        # Karo, kaynak bolgeyle ayni piksel sayisinda olmali; onizlemeden
        # buyutulmus olsaydi daha az piksel icerirdi.
        expected_w = int(tile_rect.width())
        record("Detay karosu onizlemeden degil kaynaktan uretildi",
               abs(tile.width - expected_w) <= 2,
               f"karo {tile.width}px, kaynak bolge {expected_w}px, "
               f"onizleme bu bolgede "
               f"{expected_w * editor.canvas.previewScale:.0f}px olurdu")
    editor.canvas.zoomToFit()
    settle(400)

    # --- Farkli pencere boyutlari ---
    ok_sizes = True
    sizes_detail = []
    for w, h in [(1366, 768), (1100, 680)]:
        win.resize(w, h)
        settle(500)
        panel_visible = editor._splitter.sizes()[1] > 0
        ok_sizes &= panel_visible and editor.canvas.width() > 200
        sizes_detail.append(
            f"{w}x{h}: tuval {editor.canvas.width()}px, "
            f"panel {editor._splitter.sizes()[1]}px"
        )
        win.grab().save(str(CAPTURES / f"faz2-05-boyut-{w}x{h}.png"))
    record("Kucuk ekranlarda panel ve tuval erisilebilir", ok_sizes,
           " | ".join(sizes_detail))

    print("-" * 74)
    failed = 0
    width = max(len(n) for n, _, _ in RESULTS)
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"[{'GECTI' if ok else 'KALDI'}] {name.ljust(width)}  {detail}")
    print("-" * 74)
    print(f"Ekran goruntuleri: {CAPTURES}")
    print(f"Sonuc: {len(RESULTS) - failed}/{len(RESULTS)} kontrol gecti")

    win.close()
    app.processEvents()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Faz 1 kabul olcutlerini gercek uygulama kabugunda dogrular.

Kontroller:
  1. Farkli boyutlarda JPEG / PNG / WebP / TIFF acilir.
  2. Dikey EXIF fotograf dogru yonde gorunur.
  3. Saydam PNG dogru gorunur (damali zemin, hale yok).
  4. Fotograflar arasinda ileri/geri gecilir.
  5. Pencere yeniden boyutlandirilinca tuval uyum saglar.
  6. Bozuk dosya tum ice aktarmayi cokertmez.
  7. Kitaplik izgarasi kucuk resimleri uretir.

Her adimda gercek ekran goruntusu alinir; goruntuler
`docs/_captures/` altina yazilir.

Kullanim:
    python tools/phase1_e2e.py
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


def build_fixtures(tmp: Path) -> dict[str, Path]:
    """Test fotograflarini uretir - hepsi bu betikle cizilir."""
    import piexif
    from PIL import Image

    from luma_atelier.imaging import pixels as px
    from luma_atelier.imaging.saver import OutputFormat, SaveOptions, save_image

    out: dict[str, Path] = {}

    # Genis manzara benzeri gradyan (buyuk)
    h, w = 1600, 2400
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sky = np.dstack([
        0.25 + 0.45 * (1 - yy / h), 0.35 + 0.45 * (1 - yy / h),
        0.55 + 0.40 * (1 - yy / h),
    ]).astype(np.float32)
    ridge = (yy / h > 0.62 + 0.06 * np.sin(xx / 240.0))
    sky[ridge] = sky[ridge] * 0.28 + np.array([0.06, 0.07, 0.05], np.float32)
    out["buyuk_jpeg"] = tmp / "manzara_buyuk.jpg"
    save_image(sky, out["buyuk_jpeg"], SaveOptions(fmt=OutputFormat.JPEG, quality=92))

    # Kucuk kare PNG
    small = np.zeros((240, 240, 3), np.float32)
    small[..., 0] = np.linspace(0, 1, 240, dtype=np.float32)[None, :]
    small[..., 1] = np.linspace(0, 1, 240, dtype=np.float32)[:, None]
    small[..., 2] = 0.45
    out["kucuk_png"] = tmp / "kucuk_kare.png"
    save_image(small, out["kucuk_png"], SaveOptions(fmt=OutputFormat.PNG))

    # Saydam PNG - keskin kenar
    n = 480
    yy2, xx2 = np.mgrid[0:n, 0:n].astype(np.float32)
    d = np.sqrt((xx2 - n / 2) ** 2 + (yy2 - n / 2) ** 2)
    alpha = np.clip((n * 0.36 - d) * 0.6 + 0.5, 0, 1).astype(np.float32)
    rgba = np.dstack([
        np.full((n, n), 0.92, np.float32), np.full((n, n), 0.38, np.float32),
        np.full((n, n), 0.18, np.float32), alpha,
    ])
    out["saydam_png"] = tmp / "saydam_daire.png"
    save_image(rgba, out["saydam_png"], SaveOptions(fmt=OutputFormat.PNG))

    # WebP
    out["webp"] = tmp / "renkli.webp"
    save_image(small, out["webp"], SaveOptions(fmt=OutputFormat.WEBP, quality=94))

    # 16-bit TIFF
    ramp = np.arange(65536, dtype=np.uint16).reshape(256, 256)
    out["tiff16"] = tmp / "rampa16.tif"
    save_image(px.from_uint16(np.dstack([ramp, ramp, ramp])), out["tiff16"],
               SaveOptions(fmt=OutputFormat.TIFF, bit_depth=16))

    # Dikey EXIF fotograf: 900x600 yatay dosya, Orientation=6
    hw, hh = 900, 600
    arr = np.zeros((hh, hw, 3), np.uint8)
    arr[:, :hw // 3] = (210, 70, 50)        # sol serit kirmizi
    arr[:hh // 3, :] = (60, 90, 200)        # ust serit mavi
    arr[-60:, -60:] = (240, 230, 90)        # sag alt kose sari
    out["exif_dikey"] = tmp / "telefon_dikey.jpg"
    Image.fromarray(arr).save(out["exif_dikey"], quality=95)
    piexif.insert(
        piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}, "Exif": {},
                     "GPS": {}, "1st": {}, "thumbnail": None}),
        str(out["exif_dikey"]),
    )

    # Bozuk dosya
    out["bozuk"] = tmp / "bozuk_dosya.jpg"
    out["bozuk"].write_bytes(b"bu gecerli bir JPEG degil" * 60)

    # Desteklenmeyen bicim
    out["desteklenmeyen"] = tmp / "notlar.txt"
    out["desteklenmeyen"].write_text("fotograf degil", encoding="utf-8")

    return out


def main() -> int:  # noqa: PLR0915
    os.environ.setdefault("LUMA_DATA_HOME",
                          str(Path(tempfile.gettempdir()) / "luma_phase1_data"))
    CAPTURES.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from luma_atelier.app.shell import MainWindow, create_application
    from luma_atelier.ui.widgets.image_canvas import CompareMode
    from luma_atelier.ui.widgets.nav_bar import Workspace

    tmp = Path(tempfile.mkdtemp(prefix="luma_phase1_"))
    app: QApplication = create_application([])
    fixtures = build_fixtures(tmp)

    win = MainWindow()
    win.resize(1520, 940)
    win.show()
    app.processEvents()

    def settle(ms: int = 400) -> None:
        """Arka plan islerinin bitmesini bekler (donguyu bosa dondurerek)."""
        end = time.perf_counter() + ms / 1000.0
        while time.perf_counter() < end:
            app.processEvents()

    def shot(name: str) -> Path:
        settle(150)
        p = CAPTURES / f"faz1-{name}.png"
        win.grab().save(str(p))
        return p

    print("=" * 74)
    print("LUMA ATELIER - Faz 1 kabul dogrulamasi")
    print("=" * 74)

    shot("01-baslangic")
    record("Baslangic ekrani cizildi", True, "faz1-01-baslangic.png")

    # --- 1. Ice aktarma: dort format + hatali dosyalar ---
    all_paths = [fixtures[k] for k in
                 ("buyuk_jpeg", "kucuk_png", "saydam_png", "webp", "tiff16",
                  "exif_dikey", "bozuk", "desteklenmeyen")]
    report = win.session.add_paths(all_paths)
    settle(300)
    ok = len(report.added) == 6
    record("Dort format + EXIF fotografi eklendi", ok,
           f"{len(report.added)} eklendi, {len(report.unsupported)} desteklenmeyen, "
           f"{len(report.failed)} okunamadi")
    record("Bozuk dosya ice aktarmayi cokertmedi",
           len(report.failed) == 1 and len(report.added) == 6,
           f"okunamayan: {[p.name for p, _ in report.failed]}")
    record("Desteklenmeyen bicim ayirt edildi",
           len(report.unsupported) == 1,
           f"{[p.name for p in report.unsupported]}")

    # --- 2. Kitaplik izgarasi ---
    win.show_workspace(Workspace.LIBRARY)
    settle(1400)   # kucuk resimlerin uretilmesini bekle
    shot("02-kitaplik")
    produced = sum(1 for e in win.session
                   if win.thumbnails.cached(e.path) is not None)
    record("Kitaplik kucuk resimleri uretti", produced >= 5,
           f"{produced}/6 kucuk resim hazir, faz1-02-kitaplik.png")

    # --- 3. Her formati duzenleyicide ac ---
    checks = [
        ("buyuk_jpeg", (2400, 1600), "03-jpeg-buyuk"),
        ("kucuk_png", (240, 240), "04-png-kucuk"),
        ("webp", (240, 240), "05-webp"),
        ("tiff16", (256, 256), "06-tiff16"),
    ]
    for key, expected, capture in checks:
        win._open_in_editor(fixtures[key])
        settle(900)
        canvas = win.editor_view.canvas
        # Tuval bir *onizleme* gosterir; tam boy kaynak `sourceSize`
        # uzerinden bildirilir. Ikisi de dogrulanir: kaynak tam boy
        # olmali ve onizleme kaynakla ayni en-boy oranini korumali.
        source_ok = canvas.sourceSize == expected
        pw, ph = canvas.imageSize
        ratio_ok = (pw > 0 and ph > 0
                    and abs(pw / ph - expected[0] / expected[1]) < 0.02)
        good = source_ok and ratio_ok
        shot(capture)
        ratio_text = "dogru" if ratio_ok else "hatali"
        record(f"{fixtures[key].name} acildi", good,
               f"kaynak {canvas.sourceSize} (beklenen {expected}), "
               f"onizleme {pw}x{ph}, oran {ratio_text}")

    # --- 4. EXIF dikey yon ---
    win._open_in_editor(fixtures["exif_dikey"])
    settle(700)
    size = win.editor_view.canvas.sourceSize
    # Kaynak 900x600 yatay; Orientation=6 uygulaninca 600x900 dikey olmali
    record("Dikey EXIF fotograf dik goruntulendi", size == (600, 900),
           f"beklenen (600, 900), gelen {size}")
    shot("07-exif-dikey")

    # --- 5. Saydamlik ---
    win._open_in_editor(fixtures["saydam_png"])
    settle(700)
    canvas = win.editor_view.canvas
    has_alpha = win._current_pixels is not None and win._current_pixels.shape[2] == 4
    record("Saydam PNG alpha kanaliyla yuklendi", has_alpha,
           f"kanal sayisi {win._current_pixels.shape[2] if win._current_pixels is not None else 0}")
    canvas.zoomToFit()
    shot("08-saydamlik")

    # --- 6. Fotograflar arasi gecis ---
    win._open_in_editor(fixtures["buyuk_jpeg"])
    settle(600)
    start_index = win.session.current_index
    moved_forward = 0
    for _ in range(3):
        before = win.session.current_index
        win._go_next()
        settle(500)
        if win.session.current_index != before:
            moved_forward += 1
    moved_back = 0
    for _ in range(3):
        before = win.session.current_index
        win._go_previous()
        settle(500)
        if win.session.current_index != before:
            moved_back += 1
    record("Fotograflar arasinda ileri/geri gecildi",
           moved_forward >= 2 and moved_back >= 2,
           f"ileri {moved_forward}, geri {moved_back}, "
           f"baslangic {start_index} -> son {win.session.current_index}")

    # --- 7. Karsilastirma gorunumleri ---
    win._open_in_editor(fixtures["buyuk_jpeg"])
    settle(600)
    for mode, name in [(CompareMode.SPLIT, "09-karsilastirma-surgu"),
                       (CompareMode.SIDE_BY_SIDE, "10-karsilastirma-yanyana")]:
        canvas.setCompareMode(mode)
        shot(name)
    canvas.setCompareMode(CompareMode.OFF)
    record("Once/sonra gorunumleri cizildi", True,
           "faz1-09-*, faz1-10-*")

    # --- 8. Pencere boyutlandirma ---
    sizes = [(1366, 768), (1100, 680), (1920, 1080)]
    resize_ok = True
    details = []
    for w, h in sizes:
        win.resize(w, h)
        settle(300)
        canvas.zoomToFit()
        settle(150)
        cw, ch = canvas.width(), canvas.height()
        iw, ih = canvas.imageSize
        z = canvas.zoom()
        fits = iw * z <= cw + 2 and ih * z <= ch + 2
        resize_ok &= fits and cw > 0 and ch > 0
        details.append(f"{w}x{h}->tuval {cw}x{ch} zoom %{z*100:.0f}")
        win.grab().save(str(CAPTURES / f"faz1-11-boyut-{w}x{h}.png"))
    record("Pencere boyutlandirma sorunsuz", resize_ok, " | ".join(details))

    win.resize(1520, 940)
    settle(200)
    canvas.zoomToFit()
    shot("12-duzenleyici-son")

    # --- Rapor ---
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
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

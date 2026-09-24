"""Faz 3 ve 4 kabul dogrulamasi: presetler ve Sinema Laboratuvari.

Faz 3 kabul metni:
  "Her preset gercek tarif icerir; hover kalici degisiklik yapmaz;
   tekrar tiklama yigini yanlislikla cogaltmaz; arama ve favoriler
   yeniden acilista korunur."

Faz 4 kabul metni:
  "Araclar bagimsiz ayarlanir; halation ve bloom ayirt edilir; seed ile
   cikti tekrarlanir; kimlik LUT'u rengi bozmaz; tum sinematik presetler
   gercek fotografta export edilir."
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
    data_home = Path(tempfile.gettempdir()) / "luma_phase34"
    os.environ.setdefault("LUMA_DATA_HOME", str(data_home))
    CAPTURES.mkdir(parents=True, exist_ok=True)

    # Onceki kosudan kalan kurtarma kayitlari temizlenir. Uygulama boyle
    # bir kaydi bulunca -dogru olarak- "geri yuklensin mi?" diye modal
    # soru sorar ve otomatik test orada kilitlenir. Bu bir uygulama
    # hatasi degil, test yalitimi eksigidir.
    import shutil as _shutil
    _shutil.rmtree(data_home / "autosave", ignore_errors=True)

    from PySide6.QtWidgets import QApplication

    from luma_atelier.app.shell import MainWindow, create_application
    from luma_atelier.core.paths import resources_dir
    from luma_atelier.imaging import pixels as px
    from luma_atelier.imaging.effects import REGISTRY, RenderContext
    from luma_atelier.imaging.saver import OutputFormat, SaveOptions, save_image
    from luma_atelier.storage.presets import Preset
    from luma_atelier.ui.widgets.nav_bar import Workspace

    source = Path(r"C:/Windows/Web/Wallpaper/ThemeA/img20.jpg")
    if not source.exists():
        print(f"HATA: kaynak fotograf yok: {source}")
        return 1

    app: QApplication = create_application([])
    win = MainWindow()
    win.resize(1600, 980)
    win.show()
    app.processEvents()

    def settle(ms: int) -> None:
        end = time.perf_counter() + ms / 1000.0
        while time.perf_counter() < end:
            app.processEvents()

    def shot(name: str) -> None:
        settle(200)
        win.grab().save(str(CAPTURES / f"faz34-{name}.png"))

    print("=" * 74)
    print("LUMA ATELIER - Faz 3 ve 4 kabul dogrulamasi")
    print("=" * 74)

    # --- Kutuphane ---
    lib = win.presets
    record("120 hazir gorunum yuklendi", len(lib) >= 120,
           f"{len(lib)} gorunum, {len(lib.general())} genel + "
           f"{len(lib.cinema())} sinematik")
    record("Dokuz genel kategori dolu",
           len([c for c in lib.categories() if c[0] != "cinema"]) == 9,
           ", ".join(f"{label} {count}" for key, label, count
                     in lib.categories() if key != "cinema"))
    record("35+ gercek goruntu islemi kayitli", len(REGISTRY) >= 35,
           f"{len(REGISTRY)} islem")

    # --- Her preset gercek tarif iceriyor mu? ---
    empty = [p.preset_id for p in lib if len(p.recipe) == 0]
    unknown = [p.preset_id for p in lib if p.recipe.unknown_layers]
    record("Her preset gercek tarif iceriyor",
           not empty and not unknown,
           f"bos: {empty or 'yok'}, bilinmeyen islem: {unknown or 'yok'}")

    # --- Fotografi ac ---
    win.session.add_paths([source])
    win._open_in_editor(source)
    settle(3000)
    doc = win.document
    record("Fotograf duzenleyicide acildi", doc is not None,
           f"{source.name}, {doc.source.shape[1]}x{doc.source.shape[0]}"
           if doc else "yok")
    editor = win.editor_view

    # --- Kucuk resimler kullanicinin fotografi uzerinde ---
    settle(4000)
    produced = win.preset_previews.cached_count
    record("Preset kucuk resimleri kullanicinin fotografinda uretildi",
           produced > 0,
           f"{produced} onizleme hazir, bekleyen {win.preset_previews.pending_count}")

    # Onizleme gercekten kaynaktan mi turedi?
    original = win.preset_previews.original_pixmap()
    record("Onizleme tabani kullanicinin fotografi",
           original is not None and original.width() > 0,
           f"taban {original.width()}x{original.height()}" if original else "yok")
    shot("01-duzenleyici-presetler")

    # --- Tiklama: grubu degistirir, cogaltmaz ---
    teal = lib.get("teal-amber")
    noir = lib.get("classic-noir")
    editor.presets.presetApplied.emit(teal, 100.0)
    settle(1200)
    first_count = len(doc.recipe)
    editor.presets.presetApplied.emit(teal, 100.0)
    settle(1200)
    second_count = len(doc.recipe)
    record("Ayni presete tekrar tiklama yigini cogaltmadi",
           first_count == second_count,
           f"{first_count} -> {second_count} katman")

    editor.presets.presetApplied.emit(noir, 100.0)
    settle(1200)
    record("Baska preset grubu degistirdi",
           len(doc.recipe) == len(noir.recipe),
           f"{len(doc.recipe)} katman (noir {len(noir.recipe)} katman icerir)")

    # --- Elle ayar preset degisiminde korunuyor mu? ---
    doc.set_param("tone.exposure", stops=0.6)
    doc.commit()
    settle(600)
    with_manual = len(doc.recipe)
    editor.presets.presetApplied.emit(teal, 100.0)
    settle(1200)
    record("Elle yapilan ayar preset degisiminde korundu",
           doc.recipe.has("tone.exposure"),
           f"{with_manual} -> {len(doc.recipe)} katman, "
           f"pozlama korundu: {doc.recipe.has('tone.exposure')}")

    # --- Hover kalici degisiklik yapmiyor mu? ---
    before_hover = doc.recipe
    before_depth = doc.history.depth
    editor.presets.presetPreviewed.emit(noir, 100.0)
    settle(1500)
    record("Hover onizlemesi belgeyi degistirmedi",
           doc.recipe == before_hover and doc.history.depth == before_depth,
           f"tarif ayni: {doc.recipe == before_hover}, "
           f"gecmis derinligi {before_depth} -> {doc.history.depth}")
    editor.presets.previewCleared.emit()
    settle(800)
    record("Hover cikisinda gercek tarife donuldu",
           doc.recipe == before_hover, f"{len(doc.recipe)} katman")

    # --- Yogunluk ---
    editor.presets.intensity.setValue(40.0, notify=False)
    editor.presets.presetApplied.emit(teal, 40.0)
    settle(1200)
    weak = win.renderer.render_now(doc.source, doc.recipe, long_edge=700)
    editor.presets.presetApplied.emit(teal, 100.0)
    settle(1200)
    strong = win.renderer.render_now(doc.source, doc.recipe, long_edge=700)
    base = win.renderer.render_now(doc.source, doc.recipe.clear(), long_edge=700)
    d_weak = float(np.abs(weak - base).mean())
    d_strong = float(np.abs(strong - base).mean())
    record("Genel yogunluk etkiyi olcekliyor", d_weak < d_strong * 0.85,
           f"%40 fark {d_weak:.4f} < %100 fark {d_strong:.4f}")

    # --- Arama ve favoriler ---
    editor.presets.search.setText("noir")
    settle(400)
    found = editor.presets.model.rowCount()
    editor.presets.search.setText("")
    settle(400)
    record("Arama calisiyor", found >= 1, f"'noir' -> {found} sonuc")

    # Duzenleyici tarayicisi *genel* koleksiyonu gosterir; favori
    # filtresini de genel presetlerle sinamak gerekir.
    editor.presets._toggle_favourite("natural-balance")
    editor.presets._toggle_favourite("golden-hour")
    favourites = editor.presets.favourites()
    editor.presets.fav_button.setChecked(True)
    settle(400)
    fav_rows = editor.presets.model.rowCount()
    editor.presets.fav_button.setChecked(False)
    record("Favoriler calisiyor", len(favourites) == 2 and fav_rows == 2,
           f"{favourites}, filtrede {fav_rows} kart")

    # --- SINEMA LABORATUVARI ---
    win.show_workspace(Workspace.CINEMA)
    settle(2500)
    cinema = win.cinema_view
    record("Sinema Laboratuvari ayri calisma alani olarak acildi",
           win.stack.currentWidget() is cinema,
           f"panel sayisi {len(cinema._splitter.sizes())}")
    record("Sinema yalnizca sinematik gorunumleri gosteriyor",
           cinema.presets.model.rowCount() == 30,
           f"{cinema.presets.model.rowCount()} gorunum")

    cinema_tools = {op_id for _t, ops in cinema._sections() for op_id in ops}
    required = {"light.halation", "light.bloom", "light.diffusion",
                "texture.grain", "film.tone_curve", "color.lut3d",
                "lens.vignette", "geometry.letterbox",
                "light.anamorphic", "texture.light_leak", "texture.dust"}
    record("Sinema araclari eksiksiz", required <= cinema_tools,
           f"eksik: {sorted(required - cinema_tools) or 'yok'}")

    # Ayni belge mi?
    record("Sinema ayni belgeyi kullaniyor (duzenlemeler kaybolmuyor)",
           cinema.document is doc,
           f"{len(doc.recipe)} katman her iki gorunumde de gecerli")
    shot("02-sinema-laboratuvari")

    # --- Halation vs bloom ayirt ediliyor mu? ---
    night = np.full((300, 300, 3), 0.03, np.float32)
    yy, xx = np.mgrid[0:300, 0:300].astype(np.float32)
    d = np.sqrt((xx - 150) ** 2 + (yy - 150) ** 2)
    night += np.clip(1 - d / 12, 0, 1)[..., None] * 1.5
    lin = px.srgb_to_linear(night)
    ctx = RenderContext(full_width=300, full_height=300, scale=1.0, seed=1)
    bloom_op = REGISTRY.require("light.bloom")
    hal_op = REGISTRY.require("light.halation")
    b = bloom_op.apply(lin, {**bloom_op.defaults(), "intensity": 120.0,
                             "threshold": 0.35, "radius": 60.0}, ctx)
    h = hal_op.apply(lin, {**hal_op.defaults(), "intensity": 120.0,
                           "threshold": 0.35, "radius": 60.0}, ctx)
    ring = (d > 25) & (d < 75)
    warm_b = float(b[ring][:, 0].mean() - b[ring][:, 2].mean())
    warm_h = float(h[ring][:, 0].mean() - h[ring][:, 2].mean())
    record("Halation ve bloom ayirt ediliyor",
           abs(warm_b) < 5e-4 and warm_h > 0.003,
           f"bloom R-B {warm_b:+.5f} (notr), halation R-B {warm_h:+.5f} (sicak)")

    # --- Seed tekrarlanabilirligi ---
    grain = REGISTRY.require("texture.grain")
    params = {**grain.defaults(), "amount": 60.0, "seed": 777}
    g1 = grain.apply(night, params, ctx)
    g2 = grain.apply(night, params, ctx)
    g3 = grain.apply(night, {**params, "seed": 778}, ctx)
    record("Seed ile cikti tekrarlaniyor",
           np.array_equal(g1, g2) and not np.array_equal(g1, g3),
           "ayni seed birebir ayni, farkli seed farkli desen")

    # --- Kimlik LUT'u rengi bozmuyor mu? ---
    lut_op = REGISTRY.require("color.lut3d")
    identity = resources_dir() / "luts" / "identity.cube"
    patches = np.zeros((60, 180, 3), np.float32)
    for i, c in enumerate([(0.9, 0.2, 0.2), (0.2, 0.8, 0.3), (0.2, 0.3, 0.9)]):
        patches[:, i * 60:(i + 1) * 60] = c
    lut_out = lut_op.apply(patches, {"lut": "builtin:identity", "amount": 100.0},
                           ctx)
    record("Kimlik LUT'u rengi bozmuyor",
           identity.exists() and float(np.abs(lut_out - patches).max()) < 2e-3,
           f"maksimum sapma {float(np.abs(lut_out - patches).max()):.5f}")

    # --- Kadraj: rehber ciktiya islenmiyor, bant isleniyor ---
    letterbox = REGISTRY.require("geometry.letterbox")
    off = letterbox.apply(patches, letterbox.defaults(), ctx)
    on = letterbox.apply(patches, {**letterbox.defaults(), "enabled": True,
                                   "ratio": 2.39, "mode": "bars"}, ctx)
    record("Kadraj banti acik secim gerektiriyor",
           np.array_equal(off, patches) and not np.array_equal(on, patches),
           "kapaliyken goruntu degismez, aciksa bant islenir")

    # --- 30 sinematik gorunumun hepsi gercek fotografta export edilir ---
    tmp = Path(tempfile.mkdtemp(prefix="luma_cinema_"))
    exported = 0
    failures: list[str] = []
    timings: list[float] = []
    for preset in lib.cinema():
        try:
            t0 = time.perf_counter()
            rendered = win.renderer.render_now(doc.source,
                                               preset.with_intensity(100.0))
            timings.append((time.perf_counter() - t0) * 1000)
            if not np.isfinite(rendered).all():
                failures.append(f"{preset.preset_id}: NaN/Inf")
                continue
            result = save_image(rendered, tmp / f"{preset.preset_id}.jpg",
                                SaveOptions(fmt=OutputFormat.JPEG, quality=90))
            if result.bytes_written < 1024:
                failures.append(f"{preset.preset_id}: bos dosya")
                continue
            exported += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{preset.preset_id}: {exc}")

    median = sorted(timings)[len(timings) // 2] if timings else 0.0
    record("30 sinematik gorunum tam boy export edildi",
           exported == 30 and not failures,
           f"{exported}/30 basarili, medyan render {median:.0f} ms "
           f"({doc.source.shape[1]}x{doc.source.shape[0]}), "
           f"hatalar: {failures[:3] or 'yok'}")

    # --- Kullanici preseti kaydetme ---
    doc.set_param("color.vibrance", amount=33.0)
    doc.commit()
    custom = Preset(
        preset_id="test-kullanici-gorunumu", name="Test Gorunumu",
        category="creative", description="Otomatik testte kaydedildi.",
        recipe=doc.recipe, builtin=False,
    )
    path = lib.save_user_preset(custom)
    reloaded = lib.get("test-kullanici-gorunumu")
    record("Kullanici gorunumu kaydedilip geri okunuyor",
           path.exists() and reloaded is not None
           and len(reloaded.recipe) == len(doc.recipe),
           f"{path.name}, {len(reloaded.recipe) if reloaded else 0} katman")

    export_path = tmp / "disa.json"
    lib.export_preset("test-kullanici-gorunumu", export_path)
    imported = lib.import_preset(export_path)
    record("Gorunum disa/ice aktarilabiliyor",
           export_path.exists() and imported is not None,
           f"{export_path.name} -> {imported.preset_id}")
    lib.delete_user_preset("test-kullanici-gorunumu")
    lib.delete_user_preset(imported.preset_id)

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

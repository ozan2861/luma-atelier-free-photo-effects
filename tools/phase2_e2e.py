"""Faz 2 kabul olcutu: ac -> ayarla -> geri al -> yinele -> tam boy kaydet.

Gereksinim belgesi Faz 2 kabul metni:
  "Bir fotograf acilir, ayarlanir, geri alinir, yeniden uygulanir ve tam
   boy kaydedilir. Kaynak dosya hash'i degismez. Ayarlar gorunumde ve
   ciktida calisir."

Ek olarak olculur:
  * Onizleme ve tam boy render ayni karakteri uretiyor mu?
  * Kaydirici suruklemesi tek geri alma adimi mi uretiyor?
  * Hizli ardisik istekte son istek mi ekranda kaliyor?
  * Onizleme gecikmesi hedef araligina giriyor mu?
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:  # noqa: PLR0915
    import cv2
    from PySide6.QtCore import QCoreApplication

    from luma_atelier.core.document import Document
    from luma_atelier.imaging import pixels as px
    from luma_atelier.imaging.effects import REGISTRY
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.imaging.recipe import Recipe
    from luma_atelier.imaging.saver import OutputFormat, SaveOptions, save_image
    from luma_atelier.services.render import RenderService

    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:/Windows/Web/Wallpaper/ThemeA/img21.jpg")
    if not source_path.exists():
        print(f"HATA: kaynak fotograf yok: {source_path}")
        return 1

    app = QCoreApplication.instance() or QCoreApplication([])
    tmp = Path(tempfile.mkdtemp(prefix="luma_phase2_"))

    print("=" * 74)
    print("LUMA ATELIER - Faz 2 kabul dogrulamasi")
    print("=" * 74)

    # --- 1. Ac ---
    before_hash = sha256(source_path)
    loaded = load_image(source_path)
    doc = Document(loaded)
    m = loaded.metadata
    print(f"Kaynak : {source_path.name}  {m.width}x{m.height} "
          f"({m.megapixels:.1f} MP)")
    print(f"Kayitli islem sayisi: {len(REGISTRY)}")
    record("Fotograf acildi", doc.source.shape[2] in (3, 4),
           f"{m.width}x{m.height}, {m.source_bit_depth}-bit")

    # --- 2. Ayarla (birden fazla islem) ---
    doc.set_param("tone.exposure", stops=0.45)
    doc.commit()
    doc.set_param("tone.contrast", amount=28.0)
    doc.commit()
    doc.set_param("color.white_balance", kelvin=5200.0, tint=6.0)
    doc.commit()
    doc.set_param("color.vibrance", amount=32.0)
    doc.commit()
    doc.set_param("tone.shadows_highlights", shadows=22.0, highlights=-30.0)
    doc.commit()

    record("Bes ayar tarife eklendi", len(doc.recipe) == 5,
           f"{len(doc.recipe)} katman: "
           + ", ".join(l.display_name() for l in doc.recipe))

    # --- 3. Ayarlar goruntude calisiyor mu? ---
    service = RenderService()
    ctx_full = service.render_now(doc.source, doc.recipe)
    delta = float(np.abs(ctx_full[..., :3] - doc.source[..., :3]).mean())
    record("Ayarlar goruntuye islendi", delta > 0.01,
           f"kaynaktan ortalama fark {delta:.4f}")

    # --- 4. Kaydirici suruklemesi tek adim mi? ---
    depth_before = doc.history.depth
    for value in range(0, 60, 3):          # 20 ardisik hareket
        doc.set_param("tone.exposure", stops=value / 100.0)
    doc.commit()
    added = doc.history.depth - depth_before
    record("Kaydirici suruklemesi tek gecmis adimi uretti", added == 1,
           f"20 hareket -> {added} adim")

    # --- 5. Geri al / yinele ---
    doc.set_param("color.saturation", amount=40.0)
    doc.commit()
    with_sat = doc.recipe
    assert doc.can_undo()
    doc.undo()
    after_undo = doc.recipe
    record("Geri alma tarifi onceki duruma dondurdu",
           after_undo != with_sat and not after_undo.has("color.saturation"),
           f"katman sayisi {len(with_sat)} -> {len(after_undo)}")

    doc.redo()
    record("Yineleme ayni tarifi geri getirdi", doc.recipe == with_sat,
           f"{len(doc.recipe)} katman")

    # 50 adim gereksinimi
    for i in range(60):
        doc.set_param("tone.brightness", amount=float(i % 40))
        doc.commit()
    undo_count = 0
    while doc.can_undo() and undo_count < 200:
        doc.undo()
        undo_count += 1
    record("En az 50 geri alma adimi destekleniyor", undo_count >= 50,
           f"{undo_count} adim geri alindi, yigin derinligi {doc.history.depth}")
    for _ in range(undo_count):
        doc.redo()

    # --- 6. Onizleme ve tam boy ayni karakterde mi? ---
    recipe = doc.recipe
    full = service.render_now(doc.source, recipe)
    preview = service.render_now(doc.source, recipe, long_edge=1800,
                                 purpose="preview")
    full_down = cv2.resize(full, (preview.shape[1], preview.shape[0]),
                           interpolation=cv2.INTER_AREA)
    char_diff = float(np.abs(full_down[..., :3] - preview[..., :3]).mean())
    record("Onizleme ve tam boy ayni karakteri uretiyor", char_diff < 0.01,
           f"ortalama fark {char_diff:.5f} (esik 0.01)")

    # --- 7. Hizli ardisik istekte son istek kaliyor mu? ---
    received: list[object] = []
    service.previewReady.connect(lambda r: received.append(r))
    tokens = []
    for stops in (0.1, 0.3, 0.5, 0.7, 0.9):
        r = recipe.set_or_add("tone.exposure", stops=stops)
        tokens.append(service.request_preview(doc.source, r, interactive=True))
    deadline = time.perf_counter() + 12.0
    while time.perf_counter() < deadline and not received:
        app.processEvents()
    for _ in range(50):
        app.processEvents()
        time.sleep(0.02)
    last_token = tokens[-1]
    got_tokens = [r.token for r in received]  # type: ignore[attr-defined]
    record("Hizli istekte yalnizca son sonuc kabul edildi",
           bool(received) and all(t == last_token for t in got_tokens),
           f"{len(tokens)} istek gonderildi, alinan jetonlar {got_tokens}, "
           f"son jeton {last_token}")

    # --- 8. Onizleme gecikmesi ---
    def measure(r, long_edge: int, rounds: int = 3) -> float:
        service.render_now(doc.source, r, long_edge=long_edge, purpose="preview")
        times = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            service.render_now(doc.source, r, long_edge=long_edge,
                               purpose="preview")
            times.append((time.perf_counter() - t0) * 1000)
        return sorted(times)[len(times) // 2]

    simple = Recipe().set_or_add("tone.exposure", stops=0.4)                      .set_or_add("tone.contrast", amount=20.0)
    simple_ms = measure(simple, 1800)
    record("Basit onizleme hedef araliginda", simple_ms <= 320.0,
           f"{simple_ms:.0f} ms, 2 katman, 1800 px (hedef 150-300 ms)")

    heavy_ms = measure(recipe, 1800)
    record("Agir birlesim onizlemesi 1 sn altinda", heavy_ms < 1000.0,
           f"{heavy_ms:.0f} ms, {len(recipe)} katman, 1800 px "
           f"(hedef ~1 sn civari)")

    interactive_ms = measure(recipe, 1100)
    record("Surukleme sirasi (dusuk kalite) akici", interactive_ms < 250.0,
           f"{interactive_ms:.0f} ms, {len(recipe)} katman, 1100 px")

    t0 = time.perf_counter()
    service.render_now(doc.source, recipe)
    full_ms = (time.perf_counter() - t0) * 1000
    record("Tam boy render suresi olculdu", True,
           f"{full_ms:.0f} ms ({m.megapixels:.1f} MP, {len(recipe)} katman)")

    # --- 9. Tam boy kaydet ---
    out_path = tmp / f"{source_path.stem}-duzenlenmis.jpg"
    result = save_image(full, out_path, SaveOptions(fmt=OutputFormat.JPEG,
                                                    quality=94,
                                                    icc_profile=m.icc_profile))
    back = load_image(result.path)
    size_ok = (back.width, back.height) == (m.width, m.height)
    # Ciktinin kaynaktan farkli, duzenlenmis goruntuye yakin olmasi beklenir
    to_source = float(np.abs(back.pixels[..., :3] - doc.source[..., :3]).mean())
    to_edited = float(np.abs(back.pixels[..., :3]
                             - np.clip(full[..., :3], 0, 1)).mean())
    record("Tam boy cikti yazildi ve dogrulandi",
           size_ok and to_edited < 0.01 and to_source > 0.01,
           f"{result.bytes_written/1024:.0f} KB, {back.width}x{back.height}, "
           f"duzenlenmise fark {to_edited:.4f}, kaynaga fark {to_source:.4f}")

    # --- 10. Kaynak korundu mu? ---
    record("Kaynak dosya hash'i degismedi", sha256(source_path) == before_hash,
           f"SHA-256 {before_hash[:16]}...")

    # --- 11. Tarif JSON gidis-donusu ---
    data = doc.recipe.to_dict()
    import json
    restored = Recipe.from_dict(json.loads(json.dumps(data)))
    same_render = service.render_now(doc.source, restored, long_edge=900)
    ref_render = service.render_now(doc.source, doc.recipe, long_edge=900)
    record("Tarif JSON'a yazilip geri okunabiliyor",
           np.array_equal(same_render, ref_render),
           f"{len(restored)} katman, JSON {len(json.dumps(data))} bayt")

    # --- 12. Bilinmeyen islem silinmiyor ---
    data_with_unknown = dict(data)
    data_with_unknown["layers"] = list(data["layers"]) + [
        {"op": "gelecek.surumden.efekt", "params": {"x": 1}}
    ]
    kept = Recipe.from_dict(data_with_unknown)
    round_trip = kept.to_dict()
    still_there = any(l.get("op") == "gelecek.surumden.efekt"
                      for l in round_trip["layers"])
    record("Bilinmeyen islem sessizce silinmiyor", still_there,
           f"{len(kept.unknown_layers)} bilinmeyen katman saklandi")

    # --- Rapor ---
    print("-" * 74)
    failed = 0
    width = max(len(n) for n, _, _ in RESULTS)
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"[{'GECTI' if ok else 'KALDI'}] {name.ljust(width)}  {detail}")
    print("-" * 74)
    print(f"Sonuc: {len(RESULTS) - failed}/{len(RESULTS)} kontrol gecti")

    service.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

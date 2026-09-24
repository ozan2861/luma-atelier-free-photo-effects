"""Yerlesik preset koleksiyonunu uretir ve dogrular.

Uretmekle kalmaz, her preseti **gercek bir fotograf uzerinde calistirip**
denetler:

* Tarif gecerli mi, bilinmeyen islem var mi?
* Preset gercekten bir sey yapiyor mu (etkisiz preset kabul edilmez)?
* Iki preset ayni sonucu mu uretiyor (renk varyasyonuyla sisirme)?
* NaN/Inf uretiyor mu?
* Asiri kirpma yapiyor mu (siyahlar ezilmis, parlaklar patlamis)?

Kullanim:
    python tools/make_presets.py            # uret + dogrula
    python tools/make_presets.py --check    # yalnizca dogrula
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from presets_cinema import CINEMA  # noqa: E402
from presets_general import CATEGORY_PRESETS  # noqa: E402

from luma_atelier.core.branding import APP_VERSION, PRESET_FORMAT_VERSION  # noqa: E402
from luma_atelier.imaging import pixels as px  # noqa: E402
from luma_atelier.imaging.effects import REGISTRY, RenderContext  # noqa: E402
from luma_atelier.imaging.recipe import Recipe  # noqa: E402
from luma_atelier.storage.presets import (  # noqa: E402
    CATEGORY_LABELS,
    Preset,
    PresetLibrary,
)

OUT_DIR = ROOT / "resources" / "presets"

#: Tekrar esikleri iki kademelidir.
#:
#: *Ayni kategorideki* iki gorunum kullanicinin onunde yan yana durur ve
#: dogrudan yarisir; aralarinda gozle secilebilir bir fark olmali.
#: 0.012 ~ 3/255 fark, bu esigin altinda ayirt edilemez.
SAME_CATEGORY_THRESHOLD = 0.012
#:
#: *Farkli kategorilerdeki* iki gorunum ayri listelerde ve ayri fotograf
#: turleri icin durur; benzer olmalari makuldur (orn. "Warm Clean" ile
#: "Golden Hour" ikisi de sicaktir). Yine de birebir ayni olamazlar.
CROSS_CATEGORY_THRESHOLD = 0.005

#: Bir preset gercek bir fotografta en az bu kadar degisiklik yapmali.
#: Altinda kalan preset kullaniciya "calismiyor" gibi gorunur.
MIN_EFFECT = 0.012


def build_test_images() -> dict[str, np.ndarray]:
    """Denetim icin temsili sahneler. Hepsi kodla uretilir."""
    out: dict[str, np.ndarray] = {}
    rng = np.random.default_rng(4242)

    # Portre benzeri: ten bolgesi + yumusak arka plan
    h, w = 400, 300
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = 0.24 + 0.16 * (yy / h)
    img = np.dstack([bg * 0.88, bg * 0.94, bg * 1.04]).astype(np.float32)
    e = ((yy - h * 0.42) / (h * 0.24)) ** 2 + ((xx - w * 0.5) / (w * 0.22)) ** 2
    mask = np.clip(1.6 - e, 0, 1)[..., None]
    skin = np.array([0.78, 0.60, 0.50], np.float32)
    img = img * (1 - mask) + skin * mask
    out["portre"] = np.clip(img, 0, 1).astype(np.float32)

    # Manzara: gokyuzu + yesil + kaya
    h, w = 340, 520
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sky = np.dstack([0.42 + 0.30 * (1 - yy / h), 0.55 + 0.30 * (1 - yy / h),
                     0.78 + 0.20 * (1 - yy / h)]).astype(np.float32)
    ground = yy / h > 0.58
    sky[ground] = np.array([0.22, 0.34, 0.16], np.float32)
    rock = (yy / h > 0.72) & (xx / w > 0.6)
    sky[rock] = np.array([0.46, 0.40, 0.33], np.float32)
    out["manzara"] = np.clip(sky, 0, 1).astype(np.float32)

    # Gece: koyu zemin + parlak isik kaynaklari
    h, w = 320, 480
    img = np.full((h, w, 3), 0.035, np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for cx, cy, r, colour in [(110, 110, 8, (1.0, 0.86, 0.6)),
                              (300, 90, 6, (0.8, 0.9, 1.0)),
                              (400, 210, 11, (1.0, 0.45, 0.3))]:
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        img += (np.clip(1 - d / r, 0, 1) ** 0.5)[..., None] * np.array(colour,
                                                                      np.float32) * 1.7
    img[int(h * 0.76):] += 0.05
    out["gece"] = img.astype(np.float32)

    # Renk yamalari + gri rampa: renk kaymasi ve bantlasma icin
    patch = np.zeros((240, 360, 3), np.float32)
    colours = [(0.95, 0.95, 0.95), (0.5, 0.5, 0.5), (0.05, 0.05, 0.05),
               (0.85, 0.15, 0.12), (0.12, 0.65, 0.22), (0.10, 0.25, 0.80),
               (0.92, 0.80, 0.12), (0.82, 0.62, 0.48), (0.30, 0.42, 0.28)]
    for i, c in enumerate(colours):
        r, q = divmod(i, 3)
        patch[r * 80:(r + 1) * 80, q * 120:(q + 1) * 120] = c
    out["renk"] = patch

    # Duz gradyan: bantlasma testi
    grad = np.linspace(0.02, 0.98, 400, dtype=np.float32)[None, :]
    out["gradyan"] = np.dstack([grad.repeat(120, 0)] * 3).astype(np.float32)

    # Doygun sahne: presetlerin birbirinden ayrilmasi en zor oldugu
    # kosul. Gun batimi ve neon gibi gercek sahnelerde siklikla olusur.
    h, w = 260, 380
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h
    vivid = np.dstack([
        0.15 + 0.80 * np.clip(1.4 - 2.2 * np.abs(u - 0.75), 0, 1),
        0.10 + 0.55 * np.clip(1.2 - 2.0 * np.abs(v - 0.30), 0, 1),
        0.20 + 0.75 * np.clip(1.3 - 2.0 * np.abs(u - 0.25), 0, 1),
    ]).astype(np.float32)
    vivid[int(h * 0.80):] *= 0.35
    out["doygun"] = np.clip(vivid, 0, 1)

    return out


def build_presets() -> list[Preset]:
    """Tanimlardan Preset nesneleri uretir."""
    presets: list[Preset] = []
    seen: set[str] = set()

    def make(category: str, definition) -> Preset:  # noqa: ANN001
        pid, name, intent, description, layers = definition
        if pid in seen:
            raise SystemExit(f"Kimlik tekrari: {pid}")
        seen.add(pid)
        recipe = Recipe()
        for op_id, params in layers:
            if REGISTRY.get(op_id) is None:
                raise SystemExit(f"{pid}: bilinmeyen islem {op_id}")
            recipe = recipe.add(op_id, params)
        return Preset(
            preset_id=pid, name=name, category=category,
            description=description, intent=intent, recipe=recipe,
            builtin=True, version=PRESET_FORMAT_VERSION,
            app_version=APP_VERSION,
        )

    for category, definitions in CATEGORY_PRESETS.items():
        for definition in definitions:
            presets.append(make(category, definition))
    for definition in CINEMA:
        presets.append(make("cinema", definition))
    return presets


def write_presets(presets: list[Preset]) -> Path:
    """Kategorilere gore ayri JSON dosyalari yazar."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()

    by_category: dict[str, list[Preset]] = {}
    for p in presets:
        by_category.setdefault(p.category, []).append(p)

    for category, items in by_category.items():
        payload = {
            "version": PRESET_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "category": category,
            "label": CATEGORY_LABELS.get(category, category),
            "presets": [p.to_dict() for p in items],
        }
        path = OUT_DIR / f"{category}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return OUT_DIR


def audit(presets: list[Preset], images: dict[str, np.ndarray]) -> int:
    """Her preseti temsili sahnelerde calistirip denetler.

    Olcum kurallari:

    * **Etki:** preset en az *bir* sahnede gorunur bir degisiklik
      yapmali. Yesil odakli bir gorunumu yesil icermeyen sahnede
      olcmek haksiz olurdu.
    * **Tekrar:** iki preset *tum* sahnelerde ayirt edilemiyorsa
      aynidir. Tek sahnede benzesmeleri normaldir.
    """
    failures: list[str] = []
    warnings: list[str] = []
    #: preset_id -> {sahne: sonuc}
    renders: dict[str, dict[str, np.ndarray]] = {}
    category_of = {p.preset_id: p.category for p in presets}

    scene_names = list(images)

    for preset in presets:
        if preset.recipe.unknown_layers:
            failures.append(f"{preset.preset_id}: bilinmeyen islem iceriyor")
            continue
        if len(preset.recipe) == 0:
            failures.append(f"{preset.preset_id}: bos tarif")
            continue

        outputs: dict[str, np.ndarray] = {}
        effects: dict[str, float] = {}
        broken = False

        for scene, image in images.items():
            sh, sw = image.shape[:2]
            scene_ctx = RenderContext(full_width=sw, full_height=sh,
                                      scale=1.0, seed=1)
            try:
                out = preset.recipe.apply(image, scene_ctx)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{preset.preset_id} [{scene}]: hata {exc}")
                broken = True
                break

            if not np.isfinite(out).all():
                failures.append(f"{preset.preset_id} [{scene}]: NaN/Inf")
                broken = True
                break

            clipped = np.clip(out, 0.0, 1.0)
            outputs[scene] = clipped
            effects[scene] = float(np.abs(clipped[..., :3] - image[..., :3]).mean())

            # Asiri kirpma - gerceke yakin sahnelerde
            if scene in ("portre", "manzara", "doygun"):
                dark = float((out[..., :3] <= 0.0).mean())
                bright = float((out[..., :3] >= 1.0).mean())
                if dark > 0.16:
                    warnings.append(
                        f"{preset.preset_id} [{scene}]: siyahlarin "
                        f"%{dark * 100:.0f} kadari eziliyor"
                    )
                if bright > 0.18:
                    warnings.append(
                        f"{preset.preset_id} [{scene}]: parlak alanlarin "
                        f"%{bright * 100:.0f} kadari kliplenmis"
                    )

        if broken:
            continue

        best_scene = max(effects, key=effects.get)
        if effects[best_scene] < MIN_EFFECT:
            failures.append(
                f"{preset.preset_id}: hicbir sahnede gorunur etki yok "
                f"(en iyi {best_scene} sahnesinde {effects[best_scene]:.5f} "
                f"< {MIN_EFFECT})"
            )
            continue
        renders[preset.preset_id] = outputs

    # --- Ayirt edilemeyen presetler ---
    ids = list(renders)
    duplicates: list[tuple[str, str, float, bool]] = []
    near: list[tuple[str, str, float]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            # Tum sahnelerdeki en BUYUK fark: bir sahnede bile
            # ayrilabiliyorlarsa ayri gorunumlerdir.
            diff = max(
                float(np.abs(renders[a][scene] - renders[b][scene]).mean())
                for scene in scene_names
            )
            same_category = category_of[a] == category_of[b]
            limit = (SAME_CATEGORY_THRESHOLD if same_category
                     else CROSS_CATEGORY_THRESHOLD)
            if diff < limit:
                duplicates.append((a, b, diff, same_category))
            elif same_category and diff < SAME_CATEGORY_THRESHOLD * 1.5:
                near.append((a, b, diff))

    print("=" * 74)
    print("PRESET DENETIMI")
    print("=" * 74)
    print(f"Toplam preset        : {len(presets)}")
    by_cat: dict[str, int] = {}
    for p in presets:
        by_cat[p.category] = by_cat.get(p.category, 0) + 1
    for key, label in CATEGORY_LABELS.items():
        if key in by_cat:
            print(f"  {label:22s} {by_cat[key]:3d}")
    print(f"Denetlenen sahne     : {', '.join(scene_names)}")
    print(f"Kullanilan islem     : "
          f"{len({l.op_id for p in presets for l in p.recipe})} / {len(REGISTRY)}")

    if near:
        print(f"\nAYNI KATEGORIDE YAKIN (sinirda, hata degil) ({len(near)}):")
        for a, b, diff in sorted(near, key=lambda x: x[2])[:10]:
            print(f"  {a} ~ {b}  (en buyuk fark {diff:.5f})")

    if duplicates:
        print(f"\nAYIRT EDILEMEYEN PRESETLER ({len(duplicates)}):")
        for a, b, diff, same in sorted(duplicates, key=lambda x: x[2]):
            scope = "AYNI KATEGORI" if same else "farkli kategori"
            print(f"  {a} ~ {b}  (en buyuk fark {diff:.5f}, {scope})")
        failures.extend(
            f"ayirt edilemez: {a} ~ {b} ({diff:.5f})"
            for a, b, diff, _ in duplicates
        )

    if warnings:
        print(f"\nUYARILAR ({len(warnings)}):")
        for wmsg in warnings[:20]:
            print(f"  {wmsg}")

    if failures:
        print(f"\nHATALAR ({len(failures)}):")
        for f in failures[:30]:
            print(f"  {f}")
        print("\nSONUC: DENETIM BASARISIZ")
        return 1

    print("\nSONUC: tum presetler gecti"
          + (f" ({len(warnings)} uyari)" if warnings else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="Yalnizca dogrula, dosya yazma")
    args = ap.parse_args()

    presets = build_presets()
    images = build_test_images()
    status = audit(presets, images)

    if status == 0 and not args.check:
        folder = write_presets(presets)
        print(f"\nYazildi: {folder}")
        # Geri okuyup dogrula
        library = PresetLibrary()
        report = library.load_folder(folder, builtin=True)
        print(f"Geri okuma: {report.summary()}")
        if len(library) != len(presets):
            print(f"HATA: {len(presets)} yazildi ama {len(library)} okundu")
            return 1
        if report.failed:
            for path, msg in report.failed:
                print(f"  {path.name}: {msg}")
            return 1

    return status


if __name__ == "__main__":
    raise SystemExit(main())

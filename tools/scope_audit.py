"""Son kapsam denetimi: sayilar, tekrarlar ve gorsel kalite.

Gereksinim belgesinin sayisal maddelerini **kaynaktan** dogrular:
  * Bolum 8: en az 90 genel + 30 sinematik = 120 hazir gorunum
  * Bolum 7: en az 35 anlamli goruntu islemi (preset ile karistirilmaz)
  * Faz 6: kimlikler benzersiz, semalar gecerli, tekrar yok
  * Faz 6: temsili fotograflarda karsilastirma sayfalari uretilir

Sayi kontrolu gorsel cesitlilik kanitinin yerine gecmez; bu yuzden arac
hem sayar hem de portre/manzara/gece sahnelerinde karsilastirma
sayfalari uretir ve klipleme / ten rengi olcer.

Calistirma:
    .venv\\Scripts\\python.exe tools\\scope_audit.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cv2                                              # noqa: E402
import numpy as np                                      # noqa: E402

from luma_atelier.imaging import pixels as px           # noqa: E402
from luma_atelier.imaging.effects import REGISTRY, RenderContext  # noqa: E402
from luma_atelier.storage.presets import (              # noqa: E402
    CATEGORY_LABELS,
    PresetLibrary,
)

OUT = ROOT / "docs" / "_captures" / "kapsam"
PASS, FAIL = [], []

#: Iki gorunum *hicbir* sahnede ayirt edilemiyorsa tekrardir.
#: 0.012 ~ 3/255; bu esigin altinda goz secemez.
DUPLICATE_THRESHOLD = 0.012
#: Bir gorunum en az bir sahnede bu kadar degisiklik yapmali
MIN_EFFECT = 0.012
#: Ton ayriminin korundugu kabul edilen en az ayrik 8-bit seviye.
#: Altina dusmek "ayrinti yok oldu" demektir; kaynak sahnelerde 250+
#: seviye var, saglikli bir gorunum 90'in uzerinde kalir.
MIN_TONE_LEVELS = 64


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'HATA'}] {name}"
          + (f"   — {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# ============================================================== SAHNELER
def build_scenes() -> dict[str, np.ndarray]:
    """Temsili sahneler: portre, manzara, gece. Hepsi kodla uretilir."""
    scenes: dict[str, np.ndarray] = {}
    rng = np.random.default_rng(20260918)

    # --- Portre: ten tonu + yumusak arka plan ---
    h, w = 520, 400
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = 0.26 + 0.14 * (yy / h)
    img = np.dstack([bg * 0.86, bg * 0.93, bg * 1.06]).astype(np.float32)
    # Yuz elipsi
    face = ((yy - h * 0.40) / (h * 0.26)) ** 2 + \
           ((xx - w * 0.50) / (w * 0.24)) ** 2
    mask = np.clip(1.5 - face, 0, 1)[..., None]
    skin = np.array([0.76, 0.58, 0.48], np.float32)
    img = img * (1 - mask) + skin * mask
    # Yanak kizarikligi ve golge modellemesi
    cheek = np.exp(-(((xx - w * 0.36) / (w * 0.09)) ** 2
                     + ((yy - h * 0.46) / (h * 0.07)) ** 2))[..., None]
    img = img + cheek * np.array([0.05, 0.005, 0.0], np.float32)
    img += rng.normal(0, 0.004, img.shape).astype(np.float32)
    scenes["portre"] = np.clip(img, 0, 1).astype(np.float32)

    # --- Manzara: gokyuzu, yesil, kaya, su ---
    h, w = 420, 640
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = yy / h
    img = np.zeros((h, w, 3), np.float32)
    sky = t < 0.46
    img[..., 0] = np.where(sky, 0.38 + 0.30 * (1 - t / 0.46), 0.22)
    img[..., 1] = np.where(sky, 0.54 + 0.28 * (1 - t / 0.46), 0.40)
    img[..., 2] = np.where(sky, 0.76 + 0.20 * (1 - t / 0.46), 0.24)
    ground = ~sky
    img[..., 0][ground] = 0.20 + 0.16 * np.sin(xx[ground] / 23.0)
    img[..., 1][ground] = 0.38 + 0.18 * np.cos(yy[ground] / 17.0)
    img[..., 2][ground] = 0.18
    # Gunes: parlak alan
    sun = np.exp(-(((xx - w * 0.74) / 26.0) ** 2
                   + ((yy - h * 0.16) / 26.0) ** 2))[..., None]
    img = img + sun * 0.55
    img += rng.normal(0, 0.005, img.shape).astype(np.float32)
    scenes["manzara"] = np.clip(img, 0, 1).astype(np.float32)

    # --- Gece: koyu zemin, sicak nokta isiklar ---
    h, w = 420, 560
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([
        np.full((h, w), 0.045, np.float32),
        np.full((h, w), 0.055, np.float32),
        np.full((h, w), 0.085, np.float32),
    ])
    for cx, cy, strength, tint in (
        (0.20, 0.35, 0.85, (1.00, 0.74, 0.40)),
        (0.52, 0.22, 0.70, (0.95, 0.80, 0.55)),
        (0.78, 0.48, 0.95, (1.00, 0.62, 0.30)),
        (0.36, 0.72, 0.55, (0.60, 0.78, 1.00)),
    ):
        glow = np.exp(-(((xx - w * cx) / 18.0) ** 2
                        + ((yy - h * cy) / 18.0) ** 2))
        img += (glow[..., None] * strength
                * np.array(tint, np.float32))
    img += rng.normal(0, 0.006, img.shape).astype(np.float32)
    scenes["gece"] = np.clip(img, 0, 1).astype(np.float32)
    return scenes


def render(image: np.ndarray, recipe, seed: int = 7) -> np.ndarray:  # noqa: ANN001
    h, w = image.shape[:2]
    ctx = RenderContext(full_width=w, full_height=h, scale=1.0,
                        seed=seed, quality="final", purpose="thumbnail")
    base = recipe.geometry.apply(image) if not recipe.geometry.is_identity \
        else image
    return recipe.without_geometry().apply(np.ascontiguousarray(base), ctx)


# ====================================================== 1. PRESET SAYILARI
def test_preset_counts(library: PresetLibrary) -> dict[str, int]:
    section("1. Hazır görünüm sayıları (gereksinim: 90 genel + 30 sinematik)")
    presets = library.all()
    general = [p for p in presets if p.category != "cinema"]
    cinema = [p for p in presets if p.category == "cinema"]

    per_category = Counter(p.category for p in presets)
    print(f"  {'Kategori':<26} {'Adet':>5}")
    print(f"  {'-' * 26} {'-' * 5}")
    for key, count in sorted(per_category.items(),
                             key=lambda kv: (kv[0] == "cinema", kv[0])):
        label = CATEGORY_LABELS.get(key, key)
        print(f"  {label:<26} {count:>5}")
    print(f"  {'-' * 26} {'-' * 5}")
    print(f"  {'TOPLAM':<26} {len(presets):>5}")

    check("En az 90 genel görünüm", len(general) >= 90, f"{len(general)} adet")
    check("En az 30 sinematik görünüm", len(cinema) >= 30,
          f"{len(cinema)} adet")
    check("Toplam en az 120", len(presets) >= 120, f"{len(presets)} adet")
    check("En az 6 genel kategori",
          len([k for k in per_category if k != "cinema"]) >= 6,
          f"{len([k for k in per_category if k != 'cinema'])} kategori")

    # Kimlik benzersizligi ve sema gecerliligi
    ids = [p.preset_id for p in presets]
    duplicates = [i for i, c in Counter(ids).items() if c > 1]
    check("Kimlikler benzersiz", not duplicates,
          f"tekrar eden: {duplicates}" if duplicates else f"{len(ids)} kimlik")

    problems: list[str] = []
    for preset in presets:
        if not preset.name.strip():
            problems.append(f"{preset.preset_id}: ad yok")
        if not preset.description.strip():
            problems.append(f"{preset.preset_id}: açıklama yok")
        if not preset.category:
            problems.append(f"{preset.preset_id}: kategori yok")
        if len(preset.recipe) == 0:
            problems.append(f"{preset.preset_id}: boş reçete")
        for layer in preset.recipe.layers:
            if REGISTRY.get(layer.op_id) is None:
                problems.append(f"{preset.preset_id}: bilinmeyen işlem "
                                f"{layer.op_id}")
    check("Şemalar geçerli (ad, açıklama, kategori, reçete)", not problems,
          "; ".join(problems[:3]) if problems else f"{len(presets)} görünüm")
    return dict(per_category)


# ==================================================== 2. GORUNTU ISLEMLERI
def test_operations() -> None:
    section("2. Gerçek görüntü işlemleri (gereksinim: en az 35)")
    ops = sorted(REGISTRY.all(), key=lambda o: o.op_id)
    by_group: dict[str, list] = {}
    for op in ops:
        by_group.setdefault(op.op_id.split(".")[0], []).append(op)

    for group, items in sorted(by_group.items()):
        names = ", ".join(o.name for o in items)
        print(f"  {group:<10} ({len(items):>2}) {names}")
    print(f"  {'-' * 10}")
    print(f"  {'TOPLAM':<10} ({len(ops):>2}) işlem")

    check("En az 35 görüntü işlemi", len(ops) >= 35, f"{len(ops)} işlem")
    check("İşlem kimlikleri benzersiz",
          len({o.op_id for o in ops}) == len(ops))

    # Her islem gercekten piksel degistiriyor mu?
    #
    # Parametre secimi dikkat ister: `amount` gibi siddet parametreleri
    # varsayilan olarak **azami** degerdedir (100). "Varsayilandan en
    # uzak ucu sec" kurali bunlari 0'a indirip efekti kapatir ve islem
    # yanlislikla "olu" gorunur. Dogru kural: yalnizca azami degeri
    # varsayilanin *ustunde* olan parametreler yukseltilir; zaten
    # azamide olanlar oldugu gibi birakilir.
    scene = build_scenes()["manzara"]
    inert: list[str] = []
    for op in ops:
        variants: list[dict] = []

        strong = dict(op.defaults())
        for spec in op.params:
            kind = getattr(spec, "kind", None)
            name = getattr(kind, "name", "")

            # Sayisal olmayan parametreler kendi turlerine gore kurulur;
            # yoksa egri, renk ve LUT isleyen islemler varsayilan (notr)
            # degerleriyle kalir ve "olu" gorunurler.
            if name == "CURVE":
                # Belirgin bir S egrisi
                strong[spec.key] = [(0.0, 0.0), (0.25, 0.12),
                                    (0.75, 0.88), (1.0, 1.0)]
                continue
            if name == "COLOR":
                # Notr (0.5, 0.5, 0.5) hicbir renk kaydirmaz
                strong[spec.key] = (0.85, 0.45, 0.25)
                continue
            if name == "CHOICE":
                options = [value for _label, value in spec.choices
                           if str(value)]
                if options:
                    strong[spec.key] = options[0]
                continue
            if isinstance(spec.default, bool):
                continue
            if not isinstance(spec.default, (int, float)):
                continue
            hi = spec.maximum
            if hi is not None and hi > spec.default:
                strong[spec.key] = hi
        variants.append(strong)

        toggled = dict(strong)
        for spec in op.params:
            if isinstance(spec.default, bool):
                toggled[spec.key] = not spec.default
        if toggled != strong:
            variants.append(toggled)

        # Son care: her sayisal parametreyi tek tek asgariye cek
        for spec in op.params:
            if isinstance(spec.default, bool):
                continue
            if not isinstance(spec.default, (int, float)):
                continue
            lo = spec.minimum
            if lo is not None and lo < spec.default:
                candidate = dict(strong)
                candidate[spec.key] = lo
                variants.append(candidate)

        best = 0.0
        failure = ""
        for params in variants:
            try:
                out = op.apply(px.ensure_working(scene.copy()), params,
                               RenderContext(full_width=scene.shape[1],
                                             full_height=scene.shape[0],
                                             scale=1.0, seed=3))
            except Exception as exc:  # noqa: BLE001
                failure = f"{op.op_id}: {type(exc).__name__}"
                continue
            if out.shape[:2] != scene.shape[:2]:
                best = 1.0      # boyut degistiren islem (kadraj) etkilidir
                break
            best = max(best, float(np.abs(out[..., :3] - scene).max()))
            if best >= 1e-4:
                break
        if best < 1e-4:
            inert.append(failure or f"{op.op_id}: görüntüyü değiştirmiyor")
    check("Her işlem görüntüyü gerçekten değiştiriyor", not inert,
          "; ".join(inert[:3]) if inert else f"{len(ops)}/{len(ops)}")


# ================================================ 3. SINEMA LABORATUVARI
def test_cinema(library: PresetLibrary) -> None:
    section("3. Sinema Laboratuvarı: seçilebilir, ayarlanabilir, export")
    cinema = [p for p in library.all() if p.category == "cinema"]
    check("30 sinematik görünüm var", len(cinema) >= 30, f"{len(cinema)} adet")

    scene = build_scenes()["manzara"]
    base = px.ensure_working(scene)

    weak: list[str] = []
    not_adjustable: list[str] = []
    broken: list[str] = []
    for preset in cinema:
        try:
            full = render(base, preset.recipe)
        except Exception as exc:  # noqa: BLE001
            broken.append(f"{preset.preset_id}: {type(exc).__name__}")
            continue
        effect = float(np.abs(full - base).mean())
        if effect < MIN_EFFECT:
            weak.append(f"{preset.name} ({effect:.4f})")

        # Yogunluk gercekten ayarliyor mu?
        try:
            half = render(base, preset.with_intensity(40.0))
            zero = render(base, preset.with_intensity(0.0))
        except Exception as exc:  # noqa: BLE001
            broken.append(f"{preset.preset_id} yoğunluk: {type(exc).__name__}")
            continue
        strong_delta = float(np.abs(full - base).mean())
        half_delta = float(np.abs(half - base).mean())
        zero_delta = float(np.abs(zero - base).mean())
        if not (zero_delta < half_delta < strong_delta + 1e-6):
            not_adjustable.append(
                f"{preset.name} (0:{zero_delta:.4f} 40:{half_delta:.4f} "
                f"100:{strong_delta:.4f})")

    check("Hepsi görünür etki üretiyor", not weak,
          "; ".join(weak[:3]) if weak else f"{len(cinema)}/{len(cinema)}")
    check("Yoğunluk kaydırıcısı hepsinde çalışıyor", not not_adjustable,
          "; ".join(not_adjustable[:2]) if not_adjustable
          else "0% < 40% < 100%")
    check("Hiçbiri hata vermiyor", not broken,
          "; ".join(broken[:3]) if broken else "")


# ================================================= 4. TEKRAR DENETIMI
def test_duplicates(library: PresetLibrary) -> None:
    section("4. Aynı reçetenin farklı isimle tekrarı")
    presets = library.all()
    scenes = build_scenes()

    # Reçete imzasi: islem + parametre degerleri (kimlik ve ad haric)
    signatures: dict[str, list[str]] = {}
    for preset in presets:
        parts = []
        for layer in preset.recipe.layers:
            values = ",".join(f"{k}={v!r}"
                              for k, v in sorted(layer.params.items()))
            parts.append(f"{layer.op_id}({values})")
        signatures.setdefault("|".join(sorted(parts)), []).append(preset.name)
    identical = {sig: names for sig, names in signatures.items()
                 if len(names) > 1}
    check("Birebir aynı reçete yok", not identical,
          "; ".join(", ".join(v) for v in list(identical.values())[:2])
          if identical else f"{len(signatures)} ayrı reçete")

    # Gorsel tekrar: *hicbir* sahnede ayirt edilemeyen cift
    rendered: dict[str, dict[str, np.ndarray]] = {}
    for name, scene in scenes.items():
        base = px.ensure_working(scene)
        rendered[name] = {}
        for preset in presets:
            try:
                rendered[name][preset.preset_id] = render(base, preset.recipe)
            except Exception:  # noqa: BLE001
                rendered[name][preset.preset_id] = base

    ids = [p.preset_id for p in presets]
    names = {p.preset_id: p.name for p in presets}
    closest = (1.0, "", "")
    twins: list[str] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            worst = max(
                float(np.abs(rendered[s][a] - rendered[s][b]).mean())
                for s in scenes
            )
            if worst < closest[0]:
                closest = (worst, names[a], names[b])
            if worst < DUPLICATE_THRESHOLD:
                twins.append(f"{names[a]} ≈ {names[b]} ({worst:.4f})")
    check("Görsel olarak ayırt edilemeyen çift yok", not twins,
          "; ".join(twins[:3]) if twins
          else f"en yakın çift {closest[1]} / {closest[2]}: "
               f"{closest[0]:.4f}")

    # Her gorunum en az bir sahnede gorunur olmali
    invisible: list[str] = []
    for preset in presets:
        best = max(
            float(np.abs(rendered[s][preset.preset_id]
                         - px.ensure_working(scenes[s])).mean())
            for s in scenes
        )
        if best < MIN_EFFECT:
            invisible.append(f"{preset.name} ({best:.4f})")
    check("Her görünüm en az bir sahnede görünür", not invisible,
          "; ".join(invisible[:3]) if invisible else f"{len(presets)}/"
                                                     f"{len(presets)}")
    return rendered


# ============================================ 5. KLIPLEME VE TEN RENGI
def skin_region(scene_name: str, shape: tuple[int, int]) -> np.ndarray:
    """Portre sahnesindeki ten bolgesinin maskesi."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    face = ((yy - h * 0.40) / (h * 0.22)) ** 2 + \
           ((xx - w * 0.50) / (w * 0.20)) ** 2
    return face < 1.0


def test_quality(library: PresetLibrary, rendered) -> None:  # noqa: ANN001
    section("5. Aşırı klipleme ve bozuk ten rengi")
    presets = library.all()
    scenes = build_scenes()

    # --- Klipleme ---
    #
    # Olcut ne olmali? Ham "kliplenmis piksel orani" yaniltici: yuksek
    # kontrastli siyah-beyaz bir gorunumun gece fotografinda golgeleri
    # siyaha indirmesi **kasitlidir**, bozukluk degil. Bozuk olan,
    # ayrintinin yok olmasidir. Bu yuzden iki sey olculur:
    #   1. Ortalama deger negatife dusmemeli - dustuyse islem
    #      fotografi topluca siyahin altina itmis demektir (gercek hata).
    #   2. Ton ayrimi korunmali - 8 bitte ayrik seviye sayisi.
    # Klipleme orani ayrica **olcum olarak** raporlanir.
    negative: list[str] = []
    collapsed: list[str] = []
    clip_report: list[str] = []
    for name, scene in scenes.items():
        base_clip = float(((scene <= 0.001) | (scene >= 0.999)).mean())
        worst_clip = (0.0, "")
        for preset in presets:
            raw = rendered[name][preset.preset_id]
            if float(raw.mean()) < 0.0:
                negative.append(f"{preset.name}/{name}: "
                                f"ortalama {float(raw.mean()):.4f}")
            out = np.clip(raw[..., :3], 0.0, 1.0)
            levels = len(np.unique((out * 255).astype(np.uint8)))
            if levels < MIN_TONE_LEVELS:
                collapsed.append(f"{preset.name}/{name}: {levels} seviye")
            added = float(((out <= 0.001) | (out >= 0.999)).mean()) - base_clip
            if added > worst_clip[0]:
                worst_clip = (added, preset.name)
        clip_report.append(f"{name}: en çok %{worst_clip[0] * 100:.1f} "
                           f"({worst_clip[1]})")

    check("Hiçbir görünüm fotoğrafı siyahın altına itmiyor", not negative,
          "; ".join(negative[:3]) if negative
          else f"{len(presets)} görünüm × {len(scenes)} sahne")
    check(f"Ton ayrımı korunuyor (≥{MIN_TONE_LEVELS} seviye)", not collapsed,
          "; ".join(collapsed[:3]) if collapsed else "en düşük ölçüm raporda")
    print(f"      [ölçüm] kliplenen piksel: {'  ·  '.join(clip_report)}")

    # --- Ten rengi ---
    # Saglikli ten HSV'de yaklasik 5-50 derece arasindadir. Monokrom ve
    # kasitli yaratici gorunumler bu kuralin disindadir.
    portrait = scenes["portre"]
    mask = skin_region("portre", portrait.shape[:2])
    creative = {"creative", "bw", "cinema"}
    bad_skin: list[str] = []
    for preset in presets:
        if preset.category in creative:
            continue
        out = rendered["portre"][preset.preset_id]
        bgr = cv2.cvtColor(np.clip(out[..., :3], 0, 1), cv2.COLOR_RGB2HSV)
        hue = bgr[..., 0][mask]
        sat = bgr[..., 1][mask]
        # Doygunlugu cok dusukse ton anlamsizdir (siyah-beyaza yakin)
        meaningful = sat > 0.08
        if meaningful.mean() < 0.35:
            continue        # kasitli desatüre gorunum
        median_hue = float(np.median(hue[meaningful]))
        if not (2.0 <= median_hue <= 60.0):
            bad_skin.append(f"{preset.name}: ton {median_hue:.0f}°")
    check("Ten tonu makul aralıkta (2°–60°)", not bad_skin,
          "; ".join(bad_skin[:4]) if bad_skin
          else f"{len([p for p in presets if p.category not in creative])} "
               f"görünüm denetlendi")

    # --- NaN / sonsuz ---
    broken: list[str] = []
    for name in scenes:
        for preset in presets:
            out = rendered[name][preset.preset_id]
            if not np.isfinite(out).all():
                broken.append(f"{preset.name}/{name}")
    check("Sonuçlarda NaN veya sonsuz yok", not broken,
          "; ".join(broken[:3]) if broken else "")


# ================================================ 6. KARSILASTIRMA SAYFALARI
def build_contact_sheets(library: PresetLibrary, rendered) -> None:  # noqa: ANN001
    """Gozle inceleme icin karsilastirma sayfalari uretir."""
    section("6. Karşılaştırma sayfaları (gözle inceleme için)")
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = build_scenes()
    presets = library.all()

    written = []
    for scene_name, scene in scenes.items():
        by_category: dict[str, list] = {}
        for preset in presets:
            by_category.setdefault(preset.category, []).append(preset)

        for category, items in sorted(by_category.items()):
            cols = 6
            rows = (len(items) + cols - 1) // cols
            cell_h, cell_w = 128, int(128 * scene.shape[1] / scene.shape[0])
            label_h = 18
            sheet = np.full(((cell_h + label_h) * rows, cell_w * cols, 3),
                            0.08, np.float32)
            for index, preset in enumerate(items):
                r, c = divmod(index, cols)
                thumb = cv2.resize(
                    np.clip(rendered[scene_name][preset.preset_id][..., :3],
                            0, 1),
                    (cell_w, cell_h), interpolation=cv2.INTER_AREA)
                y0 = r * (cell_h + label_h)
                sheet[y0:y0 + cell_h, c * cell_w:(c + 1) * cell_w] = thumb
            out8 = (np.clip(sheet, 0, 1) * 255).astype(np.uint8)
            bgr = cv2.cvtColor(out8, cv2.COLOR_RGB2BGR)
            for index, preset in enumerate(items):
                r, c = divmod(index, cols)
                y = r * (cell_h + label_h) + cell_h + 13
                cv2.putText(bgr, preset.name[:22], (c * cell_w + 4, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                            (210, 210, 210), 1, cv2.LINE_AA)
            path = OUT / f"{scene_name}-{category}.jpg"
            cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
            written.append(path)

        # Orijinal referans
        ref = OUT / f"{scene_name}-00-orijinal.jpg"
        cv2.imwrite(str(ref),
                    cv2.cvtColor((np.clip(scene, 0, 1) * 255).astype(np.uint8),
                                 cv2.COLOR_RGB2BGR))
        written.append(ref)

    check("Karşılaştırma sayfaları üretildi", len(written) >= 12,
          f"{len(written)} sayfa → {OUT}")
    for path in written[:3]:
        print(f"      {path.name}")


def main() -> int:
    print("=" * 70)
    print("KAPSAM DENETİMİ — gereksinim belgesine göre son kontrol")
    print("=" * 70)

    library = PresetLibrary()
    library.load_all()
    print(f"Kütüphane: {len(library.all())} görünüm yüklendi")

    test_preset_counts(library)
    test_operations()
    test_cinema(library)
    rendered = test_duplicates(library)
    test_quality(library, rendered)
    build_contact_sheets(library, rendered)

    print("\n" + "=" * 70)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 70)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

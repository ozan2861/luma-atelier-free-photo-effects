"""Proje kaliciligini **iki ayri surecte** dogrular.

Ayni surec icinde kaydedip okumak, bellekte kalan durumun sonucu
gizlemesine acik. Gercek soru sudur: uygulama kapanip yeniden
acildiginda cikti ayni mi?

Bu yuzden arac kendini iki kez calistirir:

    1. asama  fotografi acar, maske + kirpma + grain uygular,
              `.luma` projesini ve referans PNG'yi yazar, **cikar**
    2. asama  yeni bir surecte projeyi acar, render eder ve
              referansla piksel piksel karsilastirir

Calistirma:
    .venv\\Scripts\\python.exe tools\\verify_project_roundtrip.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2                                          # noqa: E402
import numpy as np                                  # noqa: E402

PROJECT = "roundtrip.luma"
REFERENCE = "referans.png"
PHOTO = "kaynak.png"


def make_photo(path: Path) -> None:
    """Grain ve maskenin gorunecegi ayrintili bir sahne."""
    rng = np.random.default_rng(4242)
    h, w = 1200, 1600
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    image = np.stack([
        0.30 + 0.45 * (xx / w),
        0.35 + 0.30 * (yy / h),
        0.55 + 0.25 * np.sin(xx / 37.0) * np.cos(yy / 29.0),
    ], axis=-1)
    image += rng.normal(0, 0.01, image.shape).astype(np.float32)
    cv2.imwrite(str(path),
                cv2.cvtColor((np.clip(image, 0, 1) * 255).astype(np.uint8),
                             cv2.COLOR_RGB2BGR))


def build_recipe():  # noqa: ANN201
    """Maske + kirpma + grain iceren gercek bir tarif."""
    from dataclasses import replace

    from luma_atelier.imaging.geometry import Geometry
    from luma_atelier.imaging.masks import (
        BlendOp,
        BrushStroke,
        Mask,
        MaskKind,
        MaskStack,
    )
    from luma_atelier.imaging.recipe import Recipe

    radial = Mask(mask_id="m-rad", kind=MaskKind.RADIAL,
                  center=(0.62, 0.38), radius=(0.26, 0.20),
                  feather=0.06, angle=12.0)
    subtract = Mask(mask_id="m-sub", kind=MaskKind.LINEAR,
                    start=(0.0, 0.88), end=(0.0, 1.0),
                    blend=BlendOp.SUBTRACT, feather=0.03)
    brush = Mask(mask_id="m-brush", kind=MaskKind.BRUSH,
                 strokes=(BrushStroke(points=((0.18, 0.28), (0.32, 0.44),
                                              (0.46, 0.38)),
                                      radius=0.10, hardness=0.6),),
                 opacity=0.85)

    recipe = (Recipe()
              .set_or_add("tone.exposure", stops=0.60)
              .set_or_add("tone.contrast", amount=0.28)
              .set_or_add("color.vibrance", amount=0.35)
              .set_or_add("texture.grain", amount=55.0, size=2.4,
                          roughness=50.0)
              .set_or_add("lens.vignette", amount=-0.30))
    recipe = recipe.with_mask("maske1", MaskStack(masks=(radial, subtract)))
    recipe = recipe.with_mask("maske2", MaskStack(masks=(brush,)))

    ids = [l.instance_id for l in recipe.layers]
    recipe = recipe.assign_mask(ids[0], "maske1")
    recipe = recipe.assign_mask(ids[2], "maske2")
    recipe = recipe.with_geometry(
        Geometry(crop=(0.08, 0.10, 0.78, 0.74), rotation=90,
                 straighten=1.4, flip_h=True))
    return recipe.with_seed(20260918)


def render(recipe, pixels):  # noqa: ANN001, ANN201
    from luma_atelier.imaging.effects.base import RenderContext

    base = np.ascontiguousarray(recipe.geometry.apply(pixels))
    h, w = base.shape[:2]
    ctx = RenderContext(full_width=w, full_height=h, scale=1.0,
                        seed=recipe.seed, quality="final", purpose="export")
    return recipe.without_geometry().apply(base, ctx)


def stage_one(folder: Path) -> int:
    """Projeyi olusturur ve referansi yazar."""
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.imaging.saver import OutputFormat, SaveOptions, save_image
    from luma_atelier.storage.project import save_project

    photo = folder / PHOTO
    make_photo(photo)
    loaded = load_image(photo)
    recipe = build_recipe()

    out = render(recipe, loaded.pixels)
    save_image(out, folder / REFERENCE,
               SaveOptions(fmt=OutputFormat.PNG, overwrite=True))
    project = save_project(folder / PROJECT, photo, recipe, out)

    print("1. aşama — proje oluşturuldu")
    print(f"   katman        : {len(recipe.layers)}")
    print(f"   maske         : {len(recipe.masks)} "
          f"({sum(len(s.masks) for s in recipe.masks.values())} bileşen)")
    print(f"   kırpma        : {tuple(round(v, 3) for v in recipe.geometry.crop)}"
          f"  döndürme {recipe.geometry.rotation}°"
          f"  ufuk {recipe.geometry.straighten}°")
    print(f"   grain         : var (seed {recipe.seed})")
    print(f"   çıktı         : {out.shape[1]}×{out.shape[0]}")
    print(f"   proje dosyası : {project.path.name} "
          f"({project.path.stat().st_size / 1024:.0f} KB)")
    return 0


def stage_two(folder: Path) -> int:
    """Yeni surecte projeyi acar ve referansla karsilastirir."""
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.storage.project import load_project, resolve_source

    project = load_project(folder / PROJECT)
    source, status = resolve_source(project, search_dirs=[folder])
    if source is None:
        print("2. aşama — HATA: kaynak fotoğraf çözülemedi")
        return 1

    pixels = load_image(source).pixels
    out = render(project.recipe, pixels)

    reference = cv2.cvtColor(cv2.imread(str(folder / REFERENCE),
                                        cv2.IMREAD_UNCHANGED),
                             cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    produced = np.clip(out[..., :3], 0.0, 1.0)

    print("\n2. aşama — yeni süreçte açıldı")
    print(f"   kaynak durumu : {status}")
    print(f"   katman        : {len(project.recipe.layers)}")
    print(f"   maske         : {len(project.recipe.masks)} "
          f"({sum(len(s.masks) for s in project.recipe.masks.values())} bileşen)")
    print(f"   kırpma        : "
          f"{tuple(round(v, 3) for v in project.recipe.geometry.crop)}"
          f"  döndürme {project.recipe.geometry.rotation}°"
          f"  ufuk {project.recipe.geometry.straighten}°")
    print(f"   çıktı         : {produced.shape[1]}×{produced.shape[0]}")

    if produced.shape != reference.shape:
        print(f"   HATA: boyut değişti "
              f"{reference.shape[1::-1]} → {produced.shape[1::-1]}")
        return 1

    # PNG 8 bit oldugu icin yeniden kodlamadan gelen 1/255 fark normaldir
    diff = float(np.abs(produced - reference).max())
    mean = float(np.abs(produced - reference).mean())
    identical = diff <= 1.5 / 255.0
    print(f"   en büyük fark : {diff:.6f} ({diff * 255:.2f}/255)")
    print(f"   ortalama fark : {mean:.6f}")
    print(f"\n   SONUÇ: çıktı {'KORUNDU' if identical else 'DEĞİŞTİ'}")
    return 0 if identical else 1


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] in ("--asama1", "--asama2"):
        folder = Path(sys.argv[2])
        return stage_one(folder) if sys.argv[1] == "--asama1" \
            else stage_two(folder)

    folder = Path(tempfile.mkdtemp(prefix="luma_roundtrip_"))
    print("=" * 66)
    print("PROJE KALICILIĞI — iki ayrı süreçte doğrulama")
    print("=" * 66)
    print(f"Çalışma klasörü: {folder}\n")

    for flag in ("--asama1", "--asama2"):
        result = subprocess.run([sys.executable, __file__, flag, str(folder)],
                                check=False)
        if result.returncode != 0:
            print(f"\n{flag} başarısız (çıkış {result.returncode})")
            return result.returncode
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())

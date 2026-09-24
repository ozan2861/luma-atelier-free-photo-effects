"""Faz 0 ucdan uca teknik deneme.

Gercek bir fotograf dosyasini acar, bir ayar uygular, dort formata
export eder, ciktilari tekrar acip dogrular ve kaynak dosyanin SHA-256
ozetinin degismedigini kanitlar.

Kullanim:
    python tools/phase0_e2e.py [kaynak_fotograf]
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luma_atelier.imaging import pixels as px  # noqa: E402
from luma_atelier.imaging.loader import load_image  # noqa: E402
from luma_atelier.imaging.saver import (  # noqa: E402
    OutputFormat,
    SaveOptions,
    save_image,
)

DEFAULT_SOURCE = Path(r"C:/Windows/Web/Wallpaper/Windows/img0.jpg")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def exposure(img: np.ndarray, stops: float) -> np.ndarray:
    """Lineer isikta pozlama - Faz 0 icin tek gercek ayar."""
    rgb, alpha = px.split_alpha(img)
    lin = px.srgb_to_linear(rgb) * np.float32(2.0 ** stops)
    return px.join_alpha(px.linear_to_srgb(lin), alpha)


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        print(f"HATA: kaynak fotograf yok: {source}")
        return 1

    print("=" * 74)
    print("LUMA ATELIER - Faz 0 ucdan uca deneme")
    print("=" * 74)

    before_hash = sha256(source)
    t0 = time.perf_counter()
    loaded = load_image(source)
    t_load = (time.perf_counter() - t0) * 1000
    m = loaded.metadata
    print(f"Kaynak    : {source.name}")
    print(
        f"Okundu    : {m.source_format} {m.width}x{m.height} "
        f"({m.megapixels:.1f} MP), {m.source_bit_depth}-bit, "
        f"alpha={m.has_alpha}, ICC={m.icc_description or 'yok'}, "
        f"sRGB varsayildi={m.assumed_srgb}"
    )
    print(f"Sure      : {t_load:.0f} ms")

    t0 = time.perf_counter()
    edited = exposure(loaded.pixels, +0.55)
    t_edit = (time.perf_counter() - t0) * 1000
    delta = float(np.abs(edited[..., :3] - loaded.pixels[..., :3]).mean())
    print(f"Ayar      : pozlama +0.55 stop, {t_edit:.0f} ms, ortalama fark {delta:.4f}")
    if delta < 1e-4:
        print("HATA: ayarin goruntude olcultebilir bir etkisi yok")
        return 1

    # Dosyaya yazarken 0..1 disina tasan parlak alanlar kirpilir. Geri
    # okunan goruntuyle karsilastirirken referans da kirpilmis olmali;
    # aksi halde kliplemeyi kayip sanip yanlis sonuc cikarirdik.
    reference = np.clip(edited, 0.0, 1.0)
    clipped_ratio = float((edited[..., :3] > 1.0).mean())
    print(f"Kliplenen : piksellerin %{clipped_ratio*100:.1f} kadari 1.0 ustunde")

    tmpdir = Path(tempfile.mkdtemp(prefix="luma_phase0_"))
    checks: list[tuple[str, bool, str]] = []
    targets = [
        (OutputFormat.JPEG, SaveOptions(fmt=OutputFormat.JPEG, quality=92,
                                        icc_profile=m.icc_profile)),
        (OutputFormat.PNG, SaveOptions(fmt=OutputFormat.PNG,
                                       icc_profile=m.icc_profile)),
        (OutputFormat.WEBP, SaveOptions(fmt=OutputFormat.WEBP, quality=92,
                                        icc_profile=m.icc_profile)),
        (OutputFormat.TIFF, SaveOptions(fmt=OutputFormat.TIFF, bit_depth=16,
                                        icc_profile=m.icc_profile)),
    ]
    for fmt, opt in targets:
        out = tmpdir / f"cikti{fmt.extension}"
        t0 = time.perf_counter()
        res = save_image(edited, out, opt)
        ms = (time.perf_counter() - t0) * 1000
        back = load_image(res.path)
        size_ok = (back.width, back.height) == (m.width, m.height)
        depth_ok = back.metadata.source_bit_depth >= res.bit_depth
        # JPEG/WebP kayipli: tolerans genis; PNG/TIFF kayipsiz: dar
        tol = 0.012 if fmt in (OutputFormat.JPEG, OutputFormat.WEBP) else 0.0015
        diff = float(np.abs(back.pixels[..., :3] - reference[..., :3]).mean())
        color_ok = diff < tol
        ok = size_ok and depth_ok and color_ok
        checks.append((
            fmt.label, ok,
            f"{res.bytes_written/1024:.0f} KB, {res.bit_depth}-bit, "
            f"{back.width}x{back.height}, fark={diff:.4f} (<{tol}), {ms:.0f} ms",
        ))

    after_hash = sha256(source)
    checks.append((
        "Kaynak dosya degismedi", before_hash == after_hash,
        f"SHA-256 {before_hash[:16]}...",
    ))

    print("-" * 74)
    failed = 0
    for name, ok, detail in checks:
        if not ok:
            failed += 1
        print(f"[{'GECTI' if ok else 'KALDI'}] {name:24s} {detail}")
    print("-" * 74)
    print(f"Cikti klasoru: {tmpdir}")
    if failed == 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print("Gecici cikti klasoru temizlendi.")
    print(f"Sonuc: {len(checks) - failed}/{len(checks)} kontrol gecti")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

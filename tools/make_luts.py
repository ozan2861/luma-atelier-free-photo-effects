"""Yerlesik yaratici 3D LUT'lari uretir (resources/luts/*.cube).

Tum LUT'lar burada **kodla** hesaplanir. Ticari LUT paketleri veya
baska bir urunun dosyalari kopyalanmaz; bunlar kendi renk
donusumlerimizdir.

Her LUT sRGB giris/cikis varsayar (SDR). Log donusumu veya ACES iddia
edilmez.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from luma_atelier.imaging import lut3d  # noqa: E402
from luma_atelier.imaging import pixels as px  # noqa: E402

SIZE = 33


def _grid() -> np.ndarray:
    """(SIZE, SIZE, SIZE, 3) kimlik kafesi."""
    return lut3d.identity_table(SIZE)


def _apply_channel_curve(rgb: np.ndarray, channel: int,
                         points) -> np.ndarray:  # noqa: ANN001
    from luma_atelier.imaging import curves

    out = rgb.copy()
    lut = curves.build_lut(points)
    out[..., channel] = curves.apply_lut(out[..., channel], lut)
    return out


def _saturation(rgb: np.ndarray, factor: float) -> np.ndarray:
    grey = np.tensordot(rgb, px.LUMA_WEIGHTS_709, axes=([-1], [0]))[..., None]
    return np.clip(grey + (rgb - grey) * np.float32(factor), 0.0, 1.0)


def _tint_zones(rgb: np.ndarray, shadow, highlight,  # noqa: ANN001
                strength: float = 0.12) -> np.ndarray:
    grey = np.tensordot(rgb, px.LUMA_WEIGHTS_709, axes=([-1], [0]))
    sh_w = np.clip(1.0 - grey * 1.9, 0.0, 1.0)[..., None]
    hi_w = np.clip(grey * 1.9 - 0.9, 0.0, 1.0)[..., None]
    sh = np.asarray(shadow, np.float32).reshape(1, 1, 1, 3) - 0.5
    hi = np.asarray(highlight, np.float32).reshape(1, 1, 1, 3) - 0.5
    return np.clip(rgb + sh * sh_w * strength + hi * hi_w * strength, 0.0, 1.0)


def _contrast(rgb: np.ndarray, amount: float, pivot: float = 0.45) -> np.ndarray:
    return np.clip(pivot + (rgb - pivot) * np.float32(1.0 + amount), 0.0, 1.0)


# ------------------------------------------------------------------ LUT'lar
def teal_amber() -> np.ndarray:
    g = _grid()
    g = _tint_zones(g, (0.30, 0.55, 0.68), (1.0, 0.78, 0.46), 0.26)
    g = _contrast(g, 0.16)
    return _saturation(g, 1.06)


def bleach_steel() -> np.ndarray:
    g = _grid()
    g = _saturation(g, 0.42)
    g = _contrast(g, 0.34, pivot=0.48)
    return _tint_zones(g, (0.42, 0.50, 0.60), (0.92, 0.95, 1.0), 0.14)


def golden_memory() -> np.ndarray:
    g = _grid()
    g = _tint_zones(g, (0.52, 0.44, 0.34), (1.0, 0.88, 0.62), 0.22)
    g = _apply_channel_curve(
        g, 2, ((0.0, 0.05), (0.5, 0.48), (1.0, 0.94)))   # mavi sikisir
    return _saturation(g, 1.02)


def neon_night() -> np.ndarray:
    g = _grid()
    g = _tint_zones(g, (0.28, 0.34, 0.72), (0.92, 0.48, 0.86), 0.3)
    g = _contrast(g, 0.24, pivot=0.4)
    return _saturation(g, 1.22)


def emerald_thriller() -> np.ndarray:
    g = _grid()
    g = _tint_zones(g, (0.34, 0.58, 0.44), (0.88, 0.94, 0.82), 0.22)
    g = _apply_channel_curve(g, 0, ((0.0, 0.0), (0.5, 0.46), (1.0, 0.97)))
    return _contrast(g, 0.18)


def faded_print() -> np.ndarray:
    g = _grid()
    # Siyahlari kaldir, beyazlari dusur
    g = np.clip(0.08 + g * 0.86, 0.0, 1.0)
    g = _tint_zones(g, (0.55, 0.52, 0.44), (0.98, 0.94, 0.86), 0.12)
    return _saturation(g, 0.82)


def mono_silver() -> np.ndarray:
    g = _grid()
    grey = np.tensordot(g, px.LUMA_WEIGHTS_709, axes=([-1], [0]))
    mono = np.repeat(grey[..., None], 3, axis=-1)
    mono = _contrast(mono, 0.2, pivot=0.46)
    # Hafif soguk selenyum tonu
    return _tint_zones(mono, (0.46, 0.49, 0.56), (1.0, 0.99, 0.96), 0.08)


def vintage_western() -> np.ndarray:
    g = _grid()
    g = _tint_zones(g, (0.54, 0.46, 0.32), (1.0, 0.90, 0.66), 0.24)
    g = _saturation(g, 0.78)
    return _apply_channel_curve(
        g, 2, ((0.0, 0.08), (0.5, 0.44), (1.0, 0.88)))


LUTS: tuple[tuple[str, str], ...] = (
    ("Teal & Amber", "teal_amber"),
    ("Bleach Steel", "bleach_steel"),
    ("Golden Memory", "golden_memory"),
    ("Neon Night", "neon_night"),
    ("Emerald Thriller", "emerald_thriller"),
    ("Faded Print", "faded_print"),
    ("Mono Silver", "mono_silver"),
    ("Vintage Western", "vintage_western"),
)


def main() -> int:
    out_dir = ROOT / "resources" / "luts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Kimlik LUT'u: "LUT rengi bozmuyor" kontrolu icin kullanilir
    identity = lut3d.make_identity(SIZE, name="Kimlik (test)")
    lut3d.write_cube(identity, out_dir / "identity.cube")
    written = 1

    module = sys.modules[__name__]
    for title, fn_name in LUTS:
        table = getattr(module, fn_name)()
        lut = lut3d.Lut3D(name=title, size=SIZE,
                          table=table.astype(np.float32))
        path = out_dir / f"{fn_name}.cube"
        lut3d.write_cube(lut, path)
        # Yazdigimizi geri okuyup dogrula
        back = lut3d.load_cube(path)
        assert back.size == SIZE, path
        assert not back.is_identity, f"{title}: kimlik LUT uretti, etkisiz"
        written += 1
        print(f"  {title:20s} -> {path.name} ({path.stat().st_size // 1024} KB)")

    print(f"\n{written} LUT yazildi: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

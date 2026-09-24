"""Uygulama ikonunu uretir (resources/icons/app.ico + PNG boyutlari).

Ikon tamamen bu betikle cizilir; disaridan lisansli varlik kullanilmaz.

Tasarim: koyu grafit kare uzerine bakir bir diyafram (aperture) halkasi.
Fotograf makinesi diyaframi urunun ne oldugunu anlatir, "L" harfi
zorlamasindan kacinir ve kucuk boyutlarda da okunur kalir.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from luma_atelier.ui.theme.tokens import PALETTE  # noqa: E402

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SUPERSAMPLE = 4


def _hex(color: str) -> tuple[int, int, int]:
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def draw_icon(size: int) -> Image.Image:
    """Tek bir kare ikon uretir (RGBA)."""
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Yuvarlak kose koyu zemin
    radius = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius,
                        fill=_hex(PALETTE.bg_raised) + (255,))
    # Ince ust kenar isigi - yuzeyin katman hissi
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius,
                        outline=_hex(PALETTE.border_strong) + (255,),
                        width=max(1, int(s * 0.012)))

    cx = cy = s / 2.0
    outer = s * 0.315
    inner = s * 0.085

    accent = _hex(PALETTE.accent)
    accent_dim = _hex(PALETTE.accent_dim)

    # Diyafram: 6 bicak. Her bicak merkezden disa acilan ucgen dilim.
    blades = 6
    for i in range(blades):
        a0 = math.radians(i * 360.0 / blades - 90)
        a1 = math.radians((i + 1) * 360.0 / blades - 90)
        amid = (a0 + a1) / 2
        # Bicagin dis kenari cemberde, ic ucu merkeze yakin ofsetli
        p_outer_a = (cx + outer * math.cos(a0), cy + outer * math.sin(a0))
        p_outer_b = (cx + outer * math.cos(a1), cy + outer * math.sin(a1))
        p_inner = (cx + inner * math.cos(amid - 0.9),
                   cy + inner * math.sin(amid - 0.9))
        shade = accent if i % 2 == 0 else accent_dim
        d.polygon([p_outer_a, p_outer_b, p_inner], fill=shade + (255,))

    # Merkez acikligi ac - fotografin gectigi yer
    hole = s * 0.085
    d.ellipse([cx - hole, cy - hole, cx + hole, cy + hole],
              fill=_hex(PALETTE.bg_raised) + (255,))

    # Dis halka
    ring = max(1, int(s * 0.018))
    d.ellipse([cx - outer, cy - outer, cx + outer, cy + outer],
              outline=_hex(PALETTE.accent_hover) + (255,), width=ring)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def draw_chevron(size: int, direction: str, color: str) -> Image.Image:
    """Acilir menu / spin kutusu icin ok isareti.

    QSS'in kenarlik ucgeni numarasi Qt'de guvenilir cizilmedigi icin
    kucuk PNG varliklar uretilir. Varliklar bu betikle cizilir.
    """
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, int(s * 0.11))
    pad = s * 0.28
    mid = s / 2.0
    if direction == "down":
        pts = [(pad, mid - s * 0.10), (mid, mid + s * 0.14), (s - pad, mid - s * 0.10)]
    elif direction == "up":
        pts = [(pad, mid + s * 0.10), (mid, mid - s * 0.14), (s - pad, mid + s * 0.10)]
    elif direction == "right":
        pts = [(mid - s * 0.10, pad), (mid + s * 0.14, mid), (mid - s * 0.10, s - pad)]
    else:  # left
        pts = [(mid + s * 0.10, pad), (mid - s * 0.14, mid), (mid + s * 0.10, s - pad)]
    d.line(pts, fill=_hex(color) + (255,), width=w, joint="curve")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def draw_check(size: int, color: str) -> Image.Image:
    """Onay kutusu tiki."""
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, int(s * 0.14))
    d.line(
        [(s * 0.22, s * 0.52), (s * 0.42, s * 0.72), (s * 0.78, s * 0.28)],
        fill=_hex(color) + (255,), width=w, joint="curve",
    )
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "resources" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Kontrol suslemeleri - stil sayfasi bunlari yol ile kullanir
    glyphs = 0
    for direction in ("down", "up", "right", "left"):
        for tone, color in (("", PALETTE.text_secondary),
                            ("-muted", PALETTE.text_muted),
                            ("-accent", PALETTE.accent_hover),
                            ("-disabled", PALETTE.text_disabled)):
            draw_chevron(12, direction, color).save(
                out_dir / f"chevron-{direction}{tone}.png")
            glyphs += 1
    draw_check(12, PALETTE.text_on_accent).save(out_dir / "check.png")
    draw_check(12, PALETTE.text_disabled).save(out_dir / "check-disabled.png")
    glyphs += 2

    images = [draw_icon(n) for n in ICON_SIZES]
    ico_path = out_dir / "app.ico"
    images[-1].save(ico_path, format="ICO",
                    sizes=[(n, n) for n in ICON_SIZES])
    for n, im in zip(ICON_SIZES, images):
        if n in (32, 256):
            im.save(out_dir / f"app-{n}.png", format="PNG")

    print(f"Yazildi: {ico_path} ({ico_path.stat().st_size} bayt)")
    print(f"Boyutlar: {', '.join(str(n) for n in ICON_SIZES)}")
    print(f"Kontrol suslemesi: {glyphs} PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

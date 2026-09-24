"""Stil islemleri: duotone, bleach bypass, cross-process.

Bunlar *donusum* islemleridir: yigina eklendiginde gorunur bir etki
yaparlar (`identity_at_defaults=False`). Etkiyi kapatmak icin yogunluk
%0'a cekilir; o zaman sonuc birebir orijinaldir.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from luma_atelier.imaging import curves, pixels as px
from luma_atelier.imaging.effects.base import (
    Category,
    ParamKind,
    ParamSpec,
    RenderContext,
    amount_spec,
    apply_amount,
    operation,
)


def _rgb_alpha(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return px.split_alpha(image)


# =================================================================== DUOTONE
@operation(
    op_id="style.duotone",
    name="Duotone",
    description=(
        "Görüntüyü iki renk arasında eşler: gölgeler bir renge, parlak "
        "alanlar diğerine. Baskı ve afis estetiği için."
    ),
    category=Category.STYLE,
    params=(
        ParamSpec(key="shadow_color", label="Gölge rengi", kind=ParamKind.COLOR,
                  default=(0.08, 0.10, 0.26)),
        ParamSpec(key="highlight_color", label="Parlak alan rengi",
                  kind=ParamKind.COLOR, default=(0.99, 0.86, 0.62)),
        ParamSpec(key="balance", label="Denge", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  tooltip="İki renk arasındaki geçiş noktasını kaydırır."),
        ParamSpec(key="contrast", label="Geçiş kontrastı", minimum=-50.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0),
        amount_spec(),
    ),
    order_hint=41,
    identity_at_defaults=False,
    color_space="sRGB",
)
def duotone(image: np.ndarray, params: dict[str, Any],
            ctx: RenderContext) -> np.ndarray:
    rgb, alpha = _rgb_alpha(image)
    luma = np.clip(px.luminance(rgb), 0.0, 1.0)

    balance = float(params["balance"]) / 100.0
    if abs(balance) > 1e-4:
        gamma = np.float32(2.0 ** (-balance))
        luma = px._pow(luma, float(gamma))

    contrast = float(params["contrast"]) / 100.0
    if abs(contrast) > 1e-4:
        luma = np.clip(0.5 + (luma - 0.5) * np.float32(1.0 + contrast), 0.0, 1.0)

    lo = np.asarray(params["shadow_color"], np.float32).reshape(1, 1, 3)
    hi = np.asarray(params["highlight_color"], np.float32).reshape(1, 1, 3)
    out = lo + (hi - lo) * luma[..., None]

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ============================================================= BLEACH BYPASS
@operation(
    op_id="style.bleach_bypass",
    name="Bleach bypass",
    description=(
        "Banyoda ağartma adımının atlanması: gümüş görüntüde kaldığı "
        "için kontrast yükselir, doygunluk düşer ve metalik sert bir "
        "görünüm oluşur."
    ),
    category=Category.STYLE,
    params=(
        ParamSpec(key="strength", label="Şiddet", minimum=0.0, maximum=100.0,
                  default=70.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False),
        ParamSpec(key="contrast", label="Ek kontrast", minimum=0.0,
                  maximum=100.0, default=35.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="grit", label="Sertlik", minimum=0.0, maximum=100.0,
                  default=30.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False,
                  tooltip="Gölgeleri koyultup metalik his verir."),
        amount_spec(),
    ),
    order_hint=42,
    identity_at_defaults=False,
    color_space="sRGB",
)
def bleach_bypass(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    strength = float(params["strength"]) / 100.0
    rgb, alpha = _rgb_alpha(image)
    grey = px.luminance(rgb)[..., None]

    # Overlay benzeri birlesim: gri katman renkli katmanin uzerine
    base = np.clip(rgb, 0.0, 1.0)
    g = np.clip(grey, 0.0, 1.0)
    overlay = np.where(g < 0.5, 2.0 * base * g,
                       1.0 - 2.0 * (1.0 - base) * (1.0 - g))
    out = base + (overlay - base) * np.float32(strength)

    contrast = float(params["contrast"]) / 100.0
    if contrast > 1e-4:
        # Yumusak omuz (bkz. tone.contrast). Duz carpim -
        # `0.5 + (out - 0.5) * k` - karanlik fotografta degerleri
        # **sifirin altina** indiriyordu: gece sahnesinde piksellerin
        # %97'si tam siyaha eziliyor ve tum ayrinti kayboluyordu.
        # tanh ucları 0 ve 1'e asimptotik yaklastirir; golgelerde
        # ayrim korunur.
        slope = np.float32(1.0 + contrast * 0.55)
        softness = np.float32(0.5)
        out = 0.5 + softness * np.tanh((out - 0.5) * slope / softness)

    grit = float(params["grit"]) / 100.0
    if grit > 1e-4:
        out = out * (1.0 - np.float32(grit * 0.12) * (1.0 - g))

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ============================================================= CROSS PROCESS
#: Cross-process karakteri: golgeler yesil-cyan, parlak alanlar sari,
#: mavi kanal sikismis. Kanal egrileri bu karakteri uretir.
_CROSS_RED = ((0.0, 0.0), (0.25, 0.17), (0.5, 0.52), (0.75, 0.86), (1.0, 1.0))
_CROSS_GREEN = ((0.0, 0.04), (0.25, 0.24), (0.5, 0.5), (0.75, 0.78), (1.0, 0.98))
_CROSS_BLUE = ((0.0, 0.12), (0.3, 0.33), (0.6, 0.6), (1.0, 0.9))


@operation(
    op_id="style.cross_process",
    name="Cross-process",
    description=(
        "Filmi yanlış kimyada banyo etmenin sonucu: gölgelerde yeşil-"
        "cyan kayma, parlak alanlarda sarı, yükselmiş kontrast ve "
        "sıkışmış mavi kanal."
    ),
    category=Category.STYLE,
    params=(
        ParamSpec(key="strength", label="Şiddet", minimum=0.0, maximum=100.0,
                  default=75.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False),
        ParamSpec(key="shadow_shift", label="Gölge kayması", minimum=-100.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0,
                  tooltip="Negatif yeşile, pozitif magentaya."),
        ParamSpec(key="saturation", label="Doygunluk", minimum=-100.0,
                  maximum=100.0, default=18.0, decimals=0, step=1.0,
                  page_step=10.0),
        amount_spec(),
    ),
    order_hint=43,
    identity_at_defaults=False,
    color_space="sRGB",
)
def cross_process(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    strength = float(params["strength"]) / 100.0
    rgb, alpha = _rgb_alpha(image)

    out = rgb.copy()
    for index, points in ((0, _CROSS_RED), (1, _CROSS_GREEN), (2, _CROSS_BLUE)):
        lut = curves.build_lut(points)
        processed = curves.apply_lut(out[..., index], lut)
        out[..., index] = out[..., index] + (processed - out[..., index]) * strength

    shift = float(params["shadow_shift"]) / 100.0
    if abs(shift) > 1e-4:
        luma = np.clip(px.luminance(out), 0.0, 1.0)
        shadow_w = px._pow(1.0 - luma, 2.0)[..., None]
        tint = np.array([shift * 0.06, -shift * 0.05, shift * 0.04],
                        dtype=np.float32).reshape(1, 1, 3)
        out = out + tint * shadow_w * np.float32(strength)

    sat = float(params["saturation"]) / 100.0
    if abs(sat) > 1e-4:
        grey = px.luminance(out)[..., None]
        out = grey + (out - grey) * np.float32(1.0 + sat * strength)

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

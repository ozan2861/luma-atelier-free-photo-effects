"""Ayrinti islemleri: keskinlestirme, gurultu azaltma, posterize."""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from luma_atelier.imaging import pixels as px
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


# ============================================================ KESKINLESTIRME
def _sharpen_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    return 3.0 * float(params["radius"])


def _denoise_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    """Kroma bulanikligi ve bilateral pencere; ikisinin buyugu."""
    colour = float(params.get("colour", 0.0)) / 100.0
    luma = float(params.get("luminance", 0.0)) / 100.0
    return max(3.0 * (1.5 + colour * 9.0), 2.0 + luma * 6.0, 6.0)


@operation(
    op_id="detail.sharpen",
    name="Keskinleştirme",
    description=(
        "Unsharp mask: ayrıntı kenarlarını belirginleştirir. Eşik "
        "değeri düz alanlarda (gökyüzü, ten) gürültüyü artırmadan "
        "yalnızca gerçek kenarlara etki etmeyi sağlar."
    ),
    category=Category.DETAIL,
    params=(
        ParamSpec(key="amount", label="Miktar", minimum=0.0, maximum=200.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  suffix=" %", bipolar=False),
        ParamSpec(key="radius", label="Yarıçap", kind=ParamKind.PIXELS,
                  minimum=0.3, maximum=12.0, default=1.2, decimals=1,
                  step=0.1, page_step=1.0, suffix=" px", bipolar=False,
                  unit_note="tam boy piksel; onizlemede olceklenir"),
        ParamSpec(key="threshold", label="Eşik", minimum=0.0, maximum=50.0,
                  default=2.0, decimals=0, step=1.0, page_step=5.0,
                  bipolar=False,
                  tooltip="Bu farkın altındaki değişimler keskinleştirilmez."),
        ParamSpec(key="protect_highlights", label="Parlak alanları koru",
                  kind=ParamKind.BOOLEAN, default=True,
                  tooltip="Kırpılmış alanlarda hale oluşmasını engeller."),
    ),
    order_hint=30,
    supports_amount=False,
    color_space="sRGB parlaklık",
    neighbourhood=_sharpen_reach,
)
def sharpen(image: np.ndarray, params: dict[str, Any],
            ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if amount < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    radius = max(0.15, ctx.scaled(float(params["radius"])))
    luma = px.luminance(rgb)
    blurred = cv2.GaussianBlur(luma, (0, 0), sigmaX=radius,
                               borderType=cv2.BORDER_REFLECT)
    detail = luma - blurred

    threshold = float(params["threshold"]) / 255.0
    if threshold > 1e-5:
        # Esigin altindaki farklari yumusak sifirla (sert esik desen uretir)
        magnitude = np.abs(detail)
        gate = np.clip((magnitude - threshold) / max(1e-5, threshold), 0.0, 1.0)
        detail = detail * gate

    if bool(params.get("protect_highlights", True)):
        # 0.92 uzerinde etkiyi kademeli kes
        guard = np.clip((1.0 - luma) / 0.08, 0.0, 1.0)
        detail = detail * guard

    delta = (detail * np.float32(amount))[..., None]
    out = rgb + delta
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# =========================================================== GURULTU AZALTMA
@operation(
    op_id="detail.denoise",
    name="Gürültü azaltma",
    description=(
        "Kenarları koruyarak gürültüyü azaltır. Parlaklık ve renk "
        "gürültüsü ayrı ayarlanır; renk gürültüsü genelde daha güçlü "
        "bastırılabilir çünkü renk ayrıntısı göze daha az görünür."
    ),
    category=Category.DETAIL,
    params=(
        ParamSpec(key="luminance", label="Parlaklık gürültüsü", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="colour", label="Renk gürültüsü", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="detail", label="Ayrıntı koruma", minimum=0.0,
                  maximum=100.0, default=55.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="Yüksek değer kenarları daha çok korur."),
    ),
    order_hint=29,
    supports_amount=False,
    color_space="sRGB",
    performance_note="Bilateral filtre; büyük yaricapta pahali",
    neighbourhood=_denoise_reach,
)
def denoise(image: np.ndarray, params: dict[str, Any],
            ctx: RenderContext) -> np.ndarray:
    luma_amount = float(params["luminance"]) / 100.0
    colour_amount = float(params["colour"]) / 100.0
    if luma_amount < 1e-4 and colour_amount < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    detail_keep = float(params["detail"]) / 100.0
    out = rgb

    if colour_amount > 1e-4:
        # Renk gurultusu: kromatik bileseni bulaniklastir, parlakligi koru
        luma = px.luminance(rgb)
        chroma = rgb - luma[..., None]
        sigma = max(0.6, ctx.scaled(1.5 + colour_amount * 9.0))
        chroma = cv2.GaussianBlur(chroma, (0, 0), sigmaX=sigma,
                                  borderType=cv2.BORDER_REFLECT)
        out = luma[..., None] + chroma

    if luma_amount > 1e-4:
        # Bilateral: kenar koruyan yumusatma
        diameter = int(np.clip(ctx.scaled(3 + luma_amount * 8), 3, 11))
        if diameter % 2 == 0:
            diameter += 1
        sigma_colour = 0.02 + luma_amount * 0.12 * (1.0 - detail_keep * 0.7)
        sigma_space = max(1.0, ctx.scaled(2.0 + luma_amount * 6.0))
        smoothed = cv2.bilateralFilter(
            np.ascontiguousarray(out), d=diameter,
            sigmaColor=float(sigma_colour), sigmaSpace=float(sigma_space),
        )
        out = px.blend(out, smoothed, min(1.0, luma_amount))

    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ================================================================= POSTERIZE
@operation(
    op_id="style.posterize",
    name="Posterize",
    description=(
        "Ton sayısını azaltarak poster/serigrafi görünümü verir. "
        "Yumuşaklık ayarı ile sert bantlar yerine kademeli geçiş "
        "elde edilebilir."
    ),
    category=Category.STYLE,
    params=(
        ParamSpec(key="levels", label="Ton sayısı", minimum=2.0,
                  maximum=64.0, default=8.0, decimals=0, step=1.0,
                  page_step=4.0, bipolar=False),
        ParamSpec(key="softness", label="Yumuşaklık", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="Yüksek değer bantlar arası geçişi yumuşatır."),
        ParamSpec(key="per_channel", label="Kanal başına",
                  kind=ParamKind.BOOLEAN, default=True,
                  tooltip="Kapalıyken yalnızca parlaklık kademelenir."),
        amount_spec(),
    ),
    order_hint=44,
    identity_at_defaults=False,
    color_space="sRGB",
)
def posterize(image: np.ndarray, params: dict[str, Any],
              ctx: RenderContext) -> np.ndarray:
    levels = max(2.0, float(params["levels"]))
    rgb, alpha = _rgb_alpha(image)
    softness = float(params["softness"]) / 100.0

    def quantise(v: np.ndarray) -> np.ndarray:
        scaled = np.clip(v, 0.0, 1.0) * np.float32(levels - 1.0)
        floor = np.floor(scaled)
        frac = scaled - floor
        if softness > 1e-4:
            # Yumusak kademe: smoothstep ile gecis
            k = np.float32(1.0 / max(1e-3, softness))
            t = np.clip((frac - 0.5) * k + 0.5, 0.0, 1.0)
            frac = t * t * (3.0 - 2.0 * t)
        else:
            frac = np.round(frac)
        return (floor + frac) / np.float32(levels - 1.0)

    if bool(params.get("per_channel", True)):
        out = quantise(rgb)
    else:
        luma = px.luminance(rgb)
        out = rgb + (quantise(luma) - luma)[..., None]

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

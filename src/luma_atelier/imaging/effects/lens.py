"""Lens islemleri: vignette ve kromatik aberasyon."""
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


def _radial_distance(h: int, w: int, cx: float, cy: float,
                     roundness: float,
                     ctx: RenderContext | None = None) -> np.ndarray:
    """Merkeze normalize uzaklik alani.

    `roundness` 0'da kadraja uyan elips, 1'de tam daire verir.

    `ctx` verilirse izgara **tam kadraj** koordinatinda kurulur; %100
    gorunum karosunda vignette karonun degil fotografin merkezine
    gore olusur.
    """
    if ctx is not None:
        frame_h, frame_w = ctx.frame_size(h, w)
        yy, xx = ctx.coords(h, w)
    else:
        frame_h, frame_w = h, w
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - cx * frame_w) / max(1.0, frame_w * 0.5)
    ny = (yy - cy * frame_h) / max(1.0, frame_h * 0.5)
    w, h = frame_w, frame_h
    if roundness > 0.0:
        # Daireye dogru: kisa kenari referans al
        aspect = w / max(1.0, float(h))
        if aspect > 1.0:
            ny = ny / (1.0 + (aspect - 1.0) * roundness)
        else:
            nx = nx * (1.0 + (1.0 / max(1e-3, aspect) - 1.0) * roundness)
    return np.sqrt(nx * nx + ny * ny)


# ================================================================== VIGNETTE
@operation(
    op_id="lens.vignette",
    name="Vignette",
    description=(
        "Kenarları karartır veya aydınlatır. Bakışı merkeze toplar. "
        "Lineer ışıkta uygulanır; koyu kenarlarda renk kirliliği olmaz."
    ),
    category=Category.LENS,
    params=(
        ParamSpec(key="amount", label="Miktar", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  tooltip="Negatif karartır, pozitif aydınlatır."),
        ParamSpec(key="midpoint", label="Orta nokta", minimum=0.1,
                  maximum=1.5, default=0.62, decimals=2, step=0.01,
                  page_step=0.1, bipolar=False,
                  tooltip="Etkinin başladığı yarıçap."),
        ParamSpec(key="feather", label="Yumuşaklık", minimum=0.05,
                  maximum=2.0, default=0.7, decimals=2, step=0.05,
                  page_step=0.2, bipolar=False),
        ParamSpec(key="roundness", label="Yuvarlaklık", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="0 kadraja uyan elips, 100 tam daire."),
        ParamSpec(key="center_x", label="Merkez X", kind=ParamKind.NORMALISED,
                  minimum=0.0, maximum=1.0, default=0.5, decimals=2,
                  step=0.01, page_step=0.1, bipolar=False),
        ParamSpec(key="center_y", label="Merkez Y", kind=ParamKind.NORMALISED,
                  minimum=0.0, maximum=1.0, default=0.5, decimals=2,
                  step=0.01, page_step=0.1, bipolar=False),
    ),
    order_hint=80,
    supports_amount=False,
    domain="linear",
    color_space="lineer ışık",
)
def vignette(image: np.ndarray, params: dict[str, Any],
             ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if abs(amount) < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    dist = _radial_distance(h, w, float(params["center_x"]),
                            float(params["center_y"]),
                            float(params["roundness"]) / 100.0, ctx)

    mid = np.float32(params["midpoint"])
    feather = np.float32(max(0.02, float(params["feather"])))
    t = np.clip((dist - mid) / feather, 0.0, 1.0)
    falloff = t * t * (3.0 - 2.0 * t)          # smoothstep

    gain = 1.0 + falloff * np.float32(amount * (1.0 if amount > 0 else 1.0))
    gain = np.clip(gain, 0.0, 4.0)
    out = rgb * gain[..., None]
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ======================================================= KROMATIK ABERASYON
def _aberration_reach(params: dict[str, Any],
                      frame: tuple[int, int]) -> float:
    """Kanal kaydirmasi kadraj merkezinden uzakligi ile artar."""
    amount = float(params["amount"]) / 100.0
    w, h = frame
    return amount * 0.004 * float(np.hypot(w, h)) * 0.5


@operation(
    op_id="lens.chromatic_aberration",
    name="Kromatik aberasyon",
    description=(
        "Kanalları kenarlara doğru farklı ölçeklerde kaydırır: lens "
        "renk saçılması. Kenarlarda kırmızı-mavi ayrılma izi oluşur."
    ),
    category=Category.LENS,
    params=(
        ParamSpec(key="amount", label="Miktar", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False),
        ParamSpec(key="edge_only", label="Yalnızca kenarlarda",
                  kind=ParamKind.BOOLEAN, default=True,
                  tooltip="Merkez net kalır; gerçek lenslerde de böyledir."),
    ),
    order_hint=81,
    supports_amount=False,
    color_space="sRGB",
    neighbourhood=_aberration_reach,
)
def chromatic_aberration(image: np.ndarray, params: dict[str, Any],
                         ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if amount < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    # Olcek farki goruntu boyutuna gore; onizlemede ayni gorunur
    delta = amount * 0.004

    # Sacilma merkezi **kadrajin** ortasidir. Karo islenirken karonun
    # ortasi alinsaydi %100 gorunumde ayrilma yanlis yonde gorunurdu.
    frame_h, frame_w = ctx.frame_size(h, w)
    ox, oy = ctx.tile_origin
    cx = frame_w * 0.5 - ox
    cy = frame_h * 0.5 - oy

    out = np.empty_like(rgb)
    out[..., 1] = rgb[..., 1]
    for channel, sign in ((0, 1.0), (2, -1.0)):
        scale = 1.0 + delta * sign
        m = np.float32([
            [scale, 0.0, cx * (1.0 - scale)],
            [0.0, scale, cy * (1.0 - scale)],
        ])
        out[..., channel] = cv2.warpAffine(
            rgb[..., channel], m, (w, h), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )

    if bool(params.get("edge_only", True)):
        dist = np.clip(_radial_distance(h, w, 0.5, 0.5, 0.0, ctx), 0.0, 1.6)
        weight = np.clip((dist - 0.25) / 0.9, 0.0, 1.0)
        weight = (weight * weight)[..., None]
        out = rgb * (1.0 - weight) + out * weight

    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)

"""Bulaniklik islemleri: Gaussian, radyal, yonlu ve tilt-shift.

Yaricap parametreleri **tam boy piksel** cinsindendir ve
`RenderContext.scale` ile olceklenir; onizlemede gorulen karakter tam
boyda korunur.

Isik toplayan bulaniklik lineer isikta yapilir: sRGB kodlu degerlerin
ortalamasi fiziksel olarak yanlistir ve parlak kaynaklarin cevresini
gercekte oldugundan koyu gosterir.
"""
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

#: Gaussian cekirdegi bu sigma'nin altinda gorunur etki yapmaz.
MIN_SIGMA = 0.35


def _rgb_alpha(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return px.split_alpha(image)


def gaussian(image: np.ndarray, sigma: float) -> np.ndarray:
    """Kenar yansimali Gaussian bulaniklik.

    `BORDER_REFLECT`: kenarlarda karartma olmaz. Bu, karo (tile) tabanli
    render'da karo sinirlarinin gorunmemesi icin de onemlidir.
    """
    if sigma < MIN_SIGMA:
        return image
    return cv2.GaussianBlur(image, (0, 0), sigmaX=sigma, sigmaY=sigma,
                            borderType=cv2.BORDER_REFLECT)


def downsampled_blur(image: np.ndarray, sigma: float,
                     max_sigma: float = 14.0) -> np.ndarray:
    """Buyuk yaricapli bulaniklik icin kucult-bulanik-buyut.

    Genis sigma'da dogrudan Gaussian pahalidir. Goruntu once kucultulur,
    orantili kucuk sigma ile bulaniklastirilir, sonra buyutulur. Sonuc
    gorsel olarak ayirt edilemez (dusuk frekansli veri zaten kaybolmaz)
    ve olculen hizlanma 40 px sigma'da 8x'in uzerindedir.
    """
    if sigma < MIN_SIGMA:
        return image
    if sigma <= max_sigma:
        return gaussian(image, sigma)

    factor = float(np.ceil(sigma / max_sigma))
    h, w = image.shape[:2]
    small_size = (max(2, int(w / factor)), max(2, int(h / factor)))
    small = cv2.resize(image, small_size, interpolation=cv2.INTER_AREA)
    small = gaussian(small, sigma / factor)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)



#: Gaussian cekirdeginin gorunur erisimi ~3 sigma.
GAUSS_REACH = 3.0


def _gaussian_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    return GAUSS_REACH * float(params["radius"]) / 2.0


def _tilt_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    return GAUSS_REACH * float(params["radius"]) / 2.0


def _motion_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    """Yonlu kaydirma veya merkeze gore olcekleme mesafesi."""
    strength = float(params["strength"]) / 100.0
    if params.get("mode") == "linear":
        return max(1.0, strength * 90.0) * 0.5
    # Radyal/spin: en uzak piksel kadraj kosesindedir
    w, h = frame
    span = float(np.hypot(w, h)) * 0.5
    if params.get("mode") == "spin":
        return span * float(np.radians(strength * 14.0)) * 0.5
    return span * strength * 0.11


# ================================================================== GAUSSIAN
@operation(
    op_id="blur.gaussian",
    name="Gaussian bulanıklık",
    description=(
        "Görüntünün tamamını eşit olarak yumuşatır. Arka plan "
        "yumuşatma, yumuşak odak ve doku bastırma için temel işlem."
    ),
    category=Category.BLUR,
    params=(
        ParamSpec(key="radius", label="Yarıçap", kind=ParamKind.PIXELS,
                  minimum=0.0, maximum=300.0, default=0.0, decimals=1,
                  step=0.5, page_step=10.0, suffix=" px", bipolar=False,
                  unit_note="tam boy piksel; onizlemede olceklenir"),
        amount_spec(),
    ),
    order_hint=50,
    domain="linear",
    color_space="lineer ışık",
    performance_note="Büyük yaricapta kucult-bulanık-buyut yolu kullanılır",
    neighbourhood=_gaussian_reach,
)
def gaussian_blur(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    radius = ctx.scaled(float(params["radius"]))
    if radius < 0.2:
        return image
    rgb, alpha = _rgb_alpha(image)
    blurred = downsampled_blur(rgb, radius / 2.0)
    result = px.join_alpha(blurred, alpha)
    return apply_amount(image, result, params)


# =========================================================== RADYAL / YONLU
@operation(
    op_id="blur.motion",
    name="Radyal ve yönlü bulanıklık",
    description=(
        "Merkezden dışa doğru (radyal/zoom) veya belirli bir açıda "
        "(yönlü) bulanıklık. Hız ve derinlik hissi verir."
    ),
    category=Category.BLUR,
    params=(
        ParamSpec(key="mode", label="Tur", kind=ParamKind.CHOICE,
                  choices=(("Yönlü", "linear"), ("Radyal (zoom)", "radial"),
                           ("Dairesel (spin)", "spin")),
                  default="linear"),
        ParamSpec(key="strength", label="Şiddet", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False),
        ParamSpec(key="angle", label="Açı", kind=ParamKind.ANGLE,
                  minimum=-180.0, maximum=180.0, default=0.0, decimals=0,
                  step=1.0, page_step=15.0, suffix="°",
                  tooltip="Yalnızca yönlü türde kullanılır."),
        ParamSpec(key="center_x", label="Merkez X", kind=ParamKind.NORMALISED,
                  minimum=0.0, maximum=1.0, default=0.5, decimals=2,
                  step=0.01, page_step=0.1, bipolar=False),
        ParamSpec(key="center_y", label="Merkez Y", kind=ParamKind.NORMALISED,
                  minimum=0.0, maximum=1.0, default=0.5, decimals=2,
                  step=0.01, page_step=0.1, bipolar=False),
        ParamSpec(key="protect_center", label="Merkezi koru", minimum=0.0,
                  maximum=100.0, default=30.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="Merkeze yakın alan net kalır."),
        amount_spec(),
    ),
    order_hint=51,
    domain="linear",
    color_space="lineer ışık",
    performance_note="Çok ornekli; siddetle orantili maliyet",
    neighbourhood=_motion_reach,
)
def motion_blur(image: np.ndarray, params: dict[str, Any],
                ctx: RenderContext) -> np.ndarray:
    strength = float(params["strength"]) / 100.0
    if strength < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    mode = params["mode"]

    if mode == "linear":
        # Yonlu: tek yonde kaydirarak ortalama
        angle = np.radians(float(params["angle"]))
        length = max(1.0, ctx.scaled(strength * 90.0))
        dx = float(np.cos(angle))
        dy = float(np.sin(angle))
        samples = int(np.clip(length, 3, 48))
        acc = np.zeros_like(rgb)
        for i in range(samples):
            t = (i / (samples - 1) - 0.5) * length
            m = np.float32([[1, 0, dx * t], [0, 1, dy * t]])
            acc += cv2.warpAffine(rgb, m, (w, h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REFLECT)
        out = acc / samples
    else:
        # Merkez tam kadraja gore; karo islenirken warp icin karonun
        # kendi koordinatina tasinir (kadraj disina dusebilir, sorun degil).
        frame_h, frame_w = ctx.frame_size(h, w)
        ox, oy = ctx.tile_origin
        cx_frame = float(params["center_x"]) * frame_w
        cy_frame = float(params["center_y"]) * frame_h
        cx = cx_frame - ox
        cy = cy_frame - oy
        samples = int(np.clip(6 + strength * 26, 4, 32))
        acc = np.zeros_like(rgb)
        for i in range(samples):
            t = i / (samples - 1) - 0.5
            if mode == "radial":
                scale = 1.0 + t * strength * 0.22
                m = np.float32([
                    [scale, 0, cx * (1 - scale)],
                    [0, scale, cy * (1 - scale)],
                ])
            else:  # spin
                deg = t * strength * 14.0
                m = cv2.getRotationMatrix2D((cx, cy), deg, 1.0).astype(np.float32)
            acc += cv2.warpAffine(rgb, m, (w, h), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REFLECT)
        out = acc / samples

        protect = float(params["protect_center"]) / 100.0
        if protect > 1e-3:
            # Izgara tam kadrajda: karo islenirken merkez kaymaz
            yy, xx = ctx.coords(h, w)
            dist = np.sqrt(((xx - cx_frame) / max(1.0, frame_w * 0.5)) ** 2
                           + ((yy - cy_frame) / max(1.0, frame_h * 0.5)) ** 2)
            keep = np.clip((dist - protect) / max(1e-3, 1.0 - protect), 0.0, 1.0)
            keep = px._pow(keep, 1.4)[..., None]
            out = rgb * (1.0 - keep) + out * keep

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ================================================================ TILT-SHIFT
@operation(
    op_id="blur.tilt_shift",
    name="Tilt-shift",
    description=(
        "Belirli bir şeride net, dışında kademeli bulanık alan. "
        "Minyatür etkisi ve seçici odak için."
    ),
    category=Category.BLUR,
    params=(
        ParamSpec(key="radius", label="Bulanıklık", kind=ParamKind.PIXELS,
                  minimum=0.0, maximum=160.0, default=0.0, decimals=0,
                  step=1.0, page_step=10.0, suffix=" px", bipolar=False),
        ParamSpec(key="position", label="Odak konumu",
                  kind=ParamKind.NORMALISED, minimum=0.0, maximum=1.0,
                  default=0.5, decimals=2, step=0.01, page_step=0.1,
                  bipolar=False),
        ParamSpec(key="width", label="Net şerit genişliği",
                  kind=ParamKind.NORMALISED, minimum=0.02, maximum=0.9,
                  default=0.25, decimals=2, step=0.01, page_step=0.05,
                  bipolar=False),
        ParamSpec(key="feather", label="Geçiş yumuşaklığı",
                  kind=ParamKind.NORMALISED, minimum=0.01, maximum=0.6,
                  default=0.18, decimals=2, step=0.01, page_step=0.05,
                  bipolar=False),
        ParamSpec(key="angle", label="Açı", kind=ParamKind.ANGLE,
                  minimum=-90.0, maximum=90.0, default=0.0, decimals=0,
                  step=1.0, page_step=15.0, suffix="°"),
        amount_spec(),
    ),
    order_hint=52,
    domain="linear",
    color_space="lineer ışık",
    neighbourhood=_tilt_reach,
)
def tilt_shift(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    radius = ctx.scaled(float(params["radius"]))
    if radius < 0.5:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    blurred = downsampled_blur(rgb, radius / 2.0)

    angle = np.radians(float(params["angle"]))
    # Serit konumu tam kadraja gore hesaplanir; yoksa %100 gorunumde
    # net serit karonun ortasina kayar.
    frame_h, frame_w = ctx.frame_size(h, w)
    yy, xx = ctx.coords(h, w)
    # Serit eksenine dik mesafe (0..1 normalize)
    nx, ny = float(-np.sin(angle)), float(np.cos(angle))
    cx, cy = frame_w * 0.5, frame_h * float(params["position"])
    dist = np.abs((xx - cx) * nx + (yy - cy) * ny) / max(1.0, frame_h * 0.5)

    half = float(params["width"]) * 0.5
    feather = max(1e-3, float(params["feather"]))
    mask = np.clip((dist - half) / feather, 0.0, 1.0)
    mask = (mask * mask * (3.0 - 2.0 * mask))[..., None]  # smoothstep

    out = rgb * (1.0 - mask) + blurred * mask
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

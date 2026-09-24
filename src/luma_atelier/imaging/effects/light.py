"""Isik islemleri: bloom, halation, diffusion, anamorfik cizgi, light leak.

Halation ve bloom farki
-----------------------
Ikisi de parlak kaynaklarin cevresine isik yayar ama ayri seylerdir ve
sonuclari ayirt edilebilir olmalidir:

* **Bloom** optik saciimadir. Tum kanallara *esit* yayilir; sonuc notr
  bir parlamadir. Varsayilan yaricapi genistir (90 px).
* **Halation** film emulsiyonunda isigin taban katmanindan geri
  yansimasidir. Kirmizi isik emulsiyonda daha derine indigi icin
  kirmizi kanal daha genis yayilir; sonuc parlak kaynagin cevresinde
  *sicak* renkli bir haledir. Varsayilan yaricapi dardir (34 px) ama
  kirmizi kanali ayni yaricapta bloom'dan **daha uzaga** ulasir.

Olculen ayrim (koyu zeminde tek parlak nokta, ayni yaricap 60 px,
ayni yogunluk):

    bolge      bloom R-B    halation R-B
    15-30 px    0.00000       +0.00818
    30-60 px    0.00000       +0.00797
    60-100 px   0.00000       +0.00319

Bu degerler `TestLightSeparation` testlerinde dogrulanir.

Tumu lineer isikta calisir; isik toplamasi sRGB kodlu degerlerde
fiziksel olarak yanlistir.
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
    seed_spec,
)
from luma_atelier.imaging.effects.blur import downsampled_blur


def _rgb_alpha(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return px.split_alpha(image)


def _highlight_mask(rgb: np.ndarray, threshold: float,
                    softness: float = 0.18) -> np.ndarray:
    """Esigin uzerindeki parlakligi yumusak gecisle cikarir.

    Sert esik bant siniri uretir; smoothstep gecisi kullanilir.
    Girdi lineer isiktir.
    """
    luma = px.luminance(rgb)
    lo = np.float32(threshold)
    hi = np.float32(threshold + softness)
    t = np.clip((luma - lo) / max(1e-4, float(hi - lo)), 0.0, 1.0)
    weight = t * t * (3.0 - 2.0 * t)
    return (rgb * weight[..., None]).astype(px.WORKING_DTYPE, copy=False)



#: Gaussian cekirdeginin gorunur erisimi ~3 sigma. Karo render'inda
#: bu kadar kenar payi birakilmazsa sinirda dikis olusur.
GAUSS_REACH = 3.0


def _bloom_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    return GAUSS_REACH * float(params["radius"]) / 2.5


def _halation_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    # En genis kanal kirmizi: base * (1 + spread * 0.9) / 2
    spread = float(params["channel_spread"]) / 100.0
    return GAUSS_REACH * float(params["radius"]) * (1.0 + spread * 0.9) / 2.0


def _diffusion_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    return GAUSS_REACH * float(params["radius"]) / 2.2


def _anamorphic_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    # Cizgi yatayda uzun, dikeyde ince; buyugu belirleyicidir
    return GAUSS_REACH * max(float(params["length"]) / 4.0,
                             float(params["thickness"]) / 2.5)


# ===================================================================== BLOOM
@operation(
    op_id="light.bloom",
    name="Bloom",
    description=(
        "Parlak alanların yumuşak ışık yayılımı. Optik saçılmayı taklit "
        "eder: tüm kanallara eşit yayılır, nötr bir parlama verir. "
        "Halation'dan farkı renksiz ve daha geniş olmasıdır."
    ),
    category=Category.LIGHT,
    params=(
        ParamSpec(key="threshold", label="Eşik", minimum=0.0, maximum=1.0,
                  default=0.65, decimals=2, step=0.01, page_step=0.1,
                  bipolar=False,
                  tooltip="Bu parlaklığın üzerindeki alanlar ışık yayar."),
        ParamSpec(key="radius", label="Yarıçap", kind=ParamKind.PIXELS,
                  minimum=4.0, maximum=400.0, default=90.0, decimals=0,
                  step=2.0, page_step=20.0, suffix=" px", bipolar=False),
        ParamSpec(key="intensity", label="Yoğunluk", minimum=0.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %", bipolar=False),
        amount_spec(),
    ),
    order_hint=60,
    domain="linear",
    color_space="lineer ışık",
    performance_note="Kucult-bulanık-buyut; 2 MP'de ~20 ms",
    neighbourhood=_bloom_reach,
)
def bloom(image: np.ndarray, params: dict[str, Any],
          ctx: RenderContext) -> np.ndarray:
    intensity = float(params["intensity"]) / 100.0
    if intensity < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    highlights = _highlight_mask(rgb, float(params["threshold"]))
    radius = max(1.0, ctx.scaled(float(params["radius"])))
    glow = downsampled_blur(highlights, radius / 2.5)
    out = rgb + glow * np.float32(intensity)
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ================================================================== HALATION
@operation(
    op_id="light.halation",
    name="Halation",
    description=(
        "Parlak kaynakların çevresinde sıcak saçılma. Filmde ışığın "
        "taban katmanından geri yansımasından oluşur; kırmızı ışık daha "
        "derine indiği için hale sıcak renklidir. Bloom'dan dar ve "
        "renkli olmasıyla ayrılır."
    ),
    category=Category.LIGHT,
    params=(
        ParamSpec(key="threshold", label="Eşik", minimum=0.0, maximum=1.0,
                  default=0.72, decimals=2, step=0.01, page_step=0.1,
                  bipolar=False),
        ParamSpec(key="radius", label="Yarıçap", kind=ParamKind.PIXELS,
                  minimum=2.0, maximum=200.0, default=34.0, decimals=0,
                  step=1.0, page_step=10.0, suffix=" px", bipolar=False),
        ParamSpec(key="intensity", label="Yoğunluk", minimum=0.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %", bipolar=False),
        ParamSpec(key="color", label="Hale rengi", kind=ParamKind.COLOR,
                  default=(1.0, 0.36, 0.14),
                  tooltip="Klasik film halation'i turuncu-kırmızıdır."),
        ParamSpec(key="channel_spread", label="Kanal ayrımı", minimum=0.0,
                  maximum=100.0, default=55.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip=(
                      "Kırmızı kanalın maviden ne kadar geniş yayıldığı. "
                      "Halation'u bloom'dan ayıran asıl parametre."
                  )),
        amount_spec(),
    ),
    order_hint=61,
    domain="linear",
    color_space="lineer ışık",
    neighbourhood=_halation_reach,
)
def halation(image: np.ndarray, params: dict[str, Any],
             ctx: RenderContext) -> np.ndarray:
    intensity = float(params["intensity"]) / 100.0
    if intensity < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    highlights = _highlight_mask(rgb, float(params["threshold"]), softness=0.12)
    base_radius = max(1.0, ctx.scaled(float(params["radius"])))
    spread = float(params["channel_spread"]) / 100.0

    # Kanal basina farkli yaricap: kirmizi en genis, mavi en dar.
    # Bu, halation'un renkli karakterini uretir.
    factors = (1.0 + spread * 0.9, 1.0, max(0.25, 1.0 - spread * 0.55))
    glow = np.empty_like(highlights)
    for c, factor in enumerate(factors):
        glow[..., c] = downsampled_blur(
            highlights[..., c], base_radius * factor / 2.0
        )

    tint = np.asarray(params["color"], np.float32).reshape(1, 1, 3)
    # Tonu normalize et ki yogunluk parlakligi tek basina belirlesin
    tint = tint / max(1e-4, float(tint.max()))
    out = rgb + glow * tint * np.float32(intensity * 1.4)
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ================================================================= DIFFUSION
@operation(
    op_id="light.diffusion",
    name="Diffusion (mist)",
    description=(
        "Lens önüne takılan sis filtresinin etkisi: kontrast düşer, "
        "parlaklık komşu alanlara yayılır, ten tonları yumuşar. "
        "Bloom'dan farkı tüm görüntüye etki etmesi, yalnızca parlak "
        "alanlara değil."
    ),
    category=Category.LIGHT,
    params=(
        ParamSpec(key="strength", label="Şiddet", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False),
        ParamSpec(key="radius", label="Yayılma", kind=ParamKind.PIXELS,
                  minimum=4.0, maximum=200.0, default=42.0, decimals=0,
                  step=1.0, page_step=10.0, suffix=" px", bipolar=False),
        ParamSpec(key="lift", label="Siyah kaldırma", minimum=0.0,
                  maximum=100.0, default=25.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="Sis etkisinin gölgeleri açtığı miktar."),
        amount_spec(),
    ),
    order_hint=62,
    domain="linear",
    color_space="lineer ışık",
    neighbourhood=_diffusion_reach,
)
def diffusion(image: np.ndarray, params: dict[str, Any],
              ctx: RenderContext) -> np.ndarray:
    strength = float(params["strength"]) / 100.0
    if strength < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    radius = max(1.0, ctx.scaled(float(params["radius"])))
    soft = downsampled_blur(rgb, radius / 2.2)

    # Screen benzeri birlesim: yumusak kopya isik ekler, koyulastirmaz
    mixed = rgb + soft * np.float32(strength * 0.55)
    lift = float(params["lift"]) / 100.0 * strength * 0.06
    if lift > 1e-5:
        mixed = mixed + np.float32(lift)

    out = px.blend(rgb, mixed, min(1.0, 0.35 + strength * 0.65))
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ============================================================== ANAMORFIK
@operation(
    op_id="light.anamorphic",
    name="Anamorfik ışık çizgisi",
    description=(
        "Parlak ışık kaynaklarından yayılan yatay (veya seçilen açıda) "
        "ince çizgi. Anamorfik sinema lenslerinin karakteristik parlama "
        "izi."
    ),
    category=Category.LIGHT,
    params=(
        ParamSpec(key="threshold", label="Eşik", minimum=0.3, maximum=1.0,
                  default=0.82, decimals=2, step=0.01, page_step=0.05,
                  bipolar=False),
        ParamSpec(key="length", label="Uzunluk", kind=ParamKind.PIXELS,
                  minimum=10.0, maximum=1200.0, default=280.0, decimals=0,
                  step=10.0, page_step=50.0, suffix=" px", bipolar=False),
        ParamSpec(key="thickness", label="Kalınlık", kind=ParamKind.PIXELS,
                  minimum=1.0, maximum=60.0, default=6.0, decimals=0,
                  step=1.0, page_step=5.0, suffix=" px", bipolar=False),
        ParamSpec(key="intensity", label="Yoğunluk", minimum=0.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %", bipolar=False),
        ParamSpec(key="angle", label="Açı", kind=ParamKind.ANGLE,
                  minimum=-90.0, maximum=90.0, default=0.0, decimals=0,
                  step=1.0, page_step=15.0, suffix="°"),
        ParamSpec(key="color", label="Çizgi rengi", kind=ParamKind.COLOR,
                  default=(0.45, 0.68, 1.0),
                  tooltip="Klasik anamorfik çizgi mavimsidir."),
        amount_spec(),
    ),
    order_hint=63,
    domain="linear",
    color_space="lineer ışık",
    neighbourhood=_anamorphic_reach,
)
def anamorphic_flare(image: np.ndarray, params: dict[str, Any],
                     ctx: RenderContext) -> np.ndarray:
    intensity = float(params["intensity"]) / 100.0
    if intensity < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    highlights = _highlight_mask(rgb, float(params["threshold"]), softness=0.08)
    luma = px.luminance(highlights)

    length = max(3.0, ctx.scaled(float(params["length"])))
    thickness = max(1.0, ctx.scaled(float(params["thickness"])))

    # Yonlu cekirdek: uzun eksende genis, kisa eksende dar Gaussian.
    # Ayri ayri uygulanir, sonra aciya gore dondurulur.
    h, w = luma.shape
    angle = float(params["angle"])
    if abs(angle) > 0.5:
        m = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
        luma = cv2.warpAffine(luma, m, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    streak = cv2.GaussianBlur(luma, (0, 0), sigmaX=length / 4.0,
                              sigmaY=thickness / 2.5,
                              borderType=cv2.BORDER_CONSTANT)

    if abs(angle) > 0.5:
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        streak = cv2.warpAffine(streak, m, (w, h), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    tint = np.asarray(params["color"], np.float32).reshape(1, 1, 3)
    out = rgb + streak[..., None] * tint * np.float32(intensity * 2.2)
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# =============================================================== LIGHT LEAK
@operation(
    op_id="texture.light_leak",
    name="Işık sızıntısı",
    description=(
        "Film kutusuna sızan ışığın bıraktığı renkli parlama. Kenardan "
        "başlayan yumuşak, renkli bir gradyan. Seed değeri deseni "
        "belirler; aynı seed aynı sonucu verir."
    ),
    category=Category.TEXTURE,
    params=(
        ParamSpec(key="intensity", label="Yoğunluk", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %", bipolar=False),
        ParamSpec(key="color", label="Sızıntı rengi", kind=ParamKind.COLOR,
                  default=(1.0, 0.55, 0.22)),
        ParamSpec(key="size", label="Boyut", kind=ParamKind.NORMALISED,
                  minimum=0.1, maximum=1.5, default=0.6, decimals=2,
                  step=0.02, page_step=0.1, bipolar=False),
        ParamSpec(key="softness", label="Yumuşaklık", minimum=0.0,
                  maximum=100.0, default=70.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        seed_spec(3),
        amount_spec(),
    ),
    order_hint=92,
    domain="linear",
    color_space="lineer ışık",
    resolution_exact=False,
)
def light_leak(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    intensity = float(params["intensity"]) / 100.0
    if intensity < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    rng = ctx.rng("light_leak", int(params["seed"]))

    # Kenarlardan birinden baslayan, iki lobdan olusan yumusak gradyan.
    # Desen kaynak *goruntu oranina* gore uretilir; onizleme ve tam boy
    # ayni konumu verir.
    corner = int(rng.integers(0, 4))
    # Sizinti kadrajin kosesinden baslar; karo islenirken karonun
    # kosesinden degil.
    u, v = ctx.normalised_coords(h, w)[1], ctx.normalised_coords(h, w)[0]
    if corner == 1:
        u = 1.0 - u
    elif corner == 2:
        v = 1.0 - v
    elif corner == 3:
        u, v = 1.0 - u, 1.0 - v

    size = float(params["size"])
    softness = 0.25 + float(params["softness"]) / 100.0 * 1.6
    cx = float(rng.uniform(-0.15, 0.25))
    cy = float(rng.uniform(-0.15, 0.35))
    dist = np.sqrt((u - cx) ** 2 + (v - cy) ** 2) / max(1e-3, size)
    leak = np.exp(-px._pow(np.clip(dist, 0, 8), 1.0 + softness))

    # Ikinci, daha dar lob: tek lob duz gorunuyor
    cx2 = cx + float(rng.uniform(-0.1, 0.2))
    cy2 = cy + float(rng.uniform(0.05, 0.3))
    dist2 = np.sqrt((u - cx2) ** 2 + (v - cy2) ** 2) / max(1e-3, size * 0.55)
    leak = leak + 0.55 * np.exp(-px._pow(np.clip(dist2, 0, 8), 1.0 + softness))

    tint = np.asarray(params["color"], np.float32).reshape(1, 1, 3)
    out = rgb + leak[..., None] * tint * np.float32(intensity * 0.85)
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

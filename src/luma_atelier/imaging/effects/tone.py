"""Ton islemleri: pozlama, kontrast, golge/parlak alan, siyah/beyaz nokta.

Renk uzayi secimleri
--------------------
* **Pozlama** lineer isikta yapilir. Gercek bir stop, lineer isigin
  ikiye katlanmasidir; sRGB kodlu degeri carpmak yanlis sonuc verir.
* **Kontrast** sRGB (algisal) uzayda, orta gri pivotu etrafinda yapilir.
  Lineer uzayda kontrast artirmak golgeleri algisal olarak asiri ezer.
* **Golge/parlak alan** algisal parlakliga gore yumusak maskelerle
  calisir; bolge gecisleri bantlasma uretmeyecek kadar genistir.
* **Siyah/beyaz nokta** uc noktalari yeniden esler.
"""
from __future__ import annotations

from typing import Any

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

#: Kontrast ve ton egrilerinin dondugu orta gri (sRGB kodlu).
#: 18% lineer gri, sRGB'de yaklasik 0.466.
MIDDLE_GREY = np.float32(0.4663)


def _rgb_alpha(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return px.split_alpha(image)


# ===================================================================== POZLAMA
@operation(
    op_id="tone.exposure",
    name="Pozlama",
    description=(
        "Görüntünün genel parlaklığını stop cinsinden değiştirir. "
        "Lineer ışıkta çalışır; +1 stop ışığı iki katına çıkarır."
    ),
    category=Category.TONE,
    params=(
        ParamSpec(
            key="stops", label="Pozlama", minimum=-5.0, maximum=5.0,
            default=0.0, decimals=2, step=0.05, page_step=0.5, suffix=" EV",
            tooltip="Negatif değer karartır, pozitif değer aydınlatır.",
            unit_note="stop (lineer ışıkta 2^n carpani)",
        ),
    ),
    supports_amount=False,
    domain="linear",
    color_space="lineer ışık",
    performance_note=(
        "Tek çarpım. Transfer dönüşümü motor tarafindan yonetilir; "
        "ardisik lineer işlemler tek donusum paylasir."
    ),
    order_hint=11,
)
def exposure(image: np.ndarray, params: dict[str, Any],
             ctx: RenderContext) -> np.ndarray:
    # Girdi lineer isiktir (domain="linear"); donusum motor tarafinda.
    stops = float(params["stops"])
    if abs(stops) < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    return px.join_alpha(rgb * np.float32(2.0 ** stops), alpha)


# ==================================================================== KONTRAST
@operation(
    op_id="tone.contrast",
    name="Kontrast",
    description=(
        "Orta gri etrafında ton ayrımını artırır veya azaltır. "
        "Parlak alanlar yumuşak kıvrılır, sert kesilme olmaz."
    ),
    category=Category.TONE,
    params=(
        ParamSpec(
            key="amount", label="Kontrast", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
            tooltip="Negatif değer yumuşatır, pozitif değer sertleştirir.",
            unit_note="yuzde; sRGB uzayinda orta gri pivotu",
        ),
        ParamSpec(
            key="pivot", label="Pivot", minimum=0.15, maximum=0.85,
            default=float(MIDDLE_GREY), decimals=2, step=0.01, page_step=0.05,
            bipolar=False,
            tooltip="Kontrastın döndüğü ton. Düşük değer gölgeleri korur.",
        ),
    ),
    supports_amount=False,
    color_space="sRGB",
    order_hint=21,
)
def contrast(image: np.ndarray, params: dict[str, Any],
             ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"])
    if abs(amount) < 1e-6:
        return image
    pivot = np.float32(params["pivot"])
    rgb, alpha = _rgb_alpha(image)

    # S-egrisi: dogrusal egim + yumusak omuz. Duz carpim parlak alanlari
    # sert kliplerdi; tanh omuzu gecisi yumusatir.
    slope = np.float32(1.0 + amount / 100.0 * 0.85)
    if amount > 0:
        # Yumusak omuz: buyuk sapmalarda egim kademeli azalir.
        #
        # 1.0 ustu degerler (bloom/halation'in okudugu baslik payi)
        # tanh'in asimptotuna sikisiyordu: 1.5 ve 4.0 ayni cikiyor,
        # pay yok oluyordu. Bu yuzden 0..1 govdesi ile pay ayrilir;
        # govde aynen eskisi gibi islenir (presetlerin gorunumu
        # degismez), pay dogrusal gecirilir.
        core = np.minimum(rgb, np.float32(1.0))
        excess = rgb - core
        softness = np.float32(0.55)
        out = pivot + softness * np.tanh((core - pivot) * slope / softness)
        if float(excess.max()) > 0.0:
            out = out + excess * slope
    else:
        out = pivot + (rgb - pivot) * slope
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ======================================================= GOLGE / PARLAK ALAN
def _tone_masks(luma: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Golge ve parlak alan icin yumusak, ortusen maskeler.

    Gecisler bilerek genis: dar maske ton siniri cizgisi ve bantlasma
    uretir. Ust uslu egriler uc noktalarda 0/1'e duzgun oturur.
    """
    l = np.clip(luma, 0.0, 1.0)
    shadow = px._pow(1.0 - l, 2.6)
    highlight = px._pow(l, 2.6)
    return shadow, highlight


@operation(
    op_id="tone.shadows_highlights",
    name="Gölge ve parlak alan",
    description=(
        "Gölgeleri açar veya kapatır, parlak alanları geri getirir. "
        "Yumuşak ton maskeleriyle çalışır; hale bırakmaz."
    ),
    category=Category.TONE,
    params=(
        ParamSpec(
            key="shadows", label="Gölgeler", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
            tooltip="Pozitif değer gölgeleri açar.",
        ),
        ParamSpec(
            key="highlights", label="Parlak alanlar", minimum=-100.0,
            maximum=100.0, default=0.0, decimals=0, step=1.0, page_step=10.0,
            tooltip="Negatif değer parlak alan ayrıntısını geri getirir.",
        ),
    ),
    supports_amount=False,
    domain="linear",
    color_space="lineer ışık (kazanc), algısal maske",
    performance_note=(
        "Maske yalnızca tek kanalli parlakliktan turetilir; uç kanali "
        "ayrı ayrı donusturmekten ~3x ucuz."
    ),
    order_hint=12,
)
def shadows_highlights(image: np.ndarray, params: dict[str, Any],
                       ctx: RenderContext) -> np.ndarray:
    # Girdi lineer isiktir. Ton maskesi *algisal* olmali, bu yuzden
    # uc kanali degil yalnizca parlaklik kanalini sRGB'ye ceviririz;
    # bu, tum goruntuyu donusturmekten belirgin ucuz.
    sh = float(params["shadows"]) / 100.0
    hl = float(params["highlights"]) / 100.0
    if abs(sh) < 1e-6 and abs(hl) < 1e-6:
        return image

    rgb, alpha = _rgb_alpha(image)
    luma_perceptual = px.linear_to_srgb(px.luminance(rgb))
    shadow_mask, highlight_mask = _tone_masks(luma_perceptual)

    gain = np.ones_like(luma_perceptual)
    if abs(sh) > 1e-6:
        gain *= (1.0 + shadow_mask * np.float32(sh * 1.35))
    if abs(hl) > 1e-6:
        gain *= (1.0 + highlight_mask * np.float32(hl * 0.85))
    return px.join_alpha(rgb * gain[..., None], alpha)


# ======================================================= SIYAH / BEYAZ NOKTA
@operation(
    op_id="tone.black_white_point",
    name="Siyah ve beyaz nokta",
    description=(
        "Ton aralığının uç noktalarını yeniden eşler. Siyahı kaldırmak "
        "mat görünüm, beyazı düşürmek yumuşak parlaklık verir."
    ),
    category=Category.TONE,
    params=(
        ParamSpec(
            key="black", label="Siyah nokta", minimum=-50.0, maximum=50.0,
            default=0.0, decimals=0, step=1.0, page_step=5.0,
            tooltip="Pozitif değer siyahları koyulaştırır, negatif kaldırır.",
        ),
        ParamSpec(
            key="white", label="Beyaz nokta", minimum=-50.0, maximum=50.0,
            default=0.0, decimals=0, step=1.0, page_step=5.0,
            tooltip="Pozitif değer beyazları parlatır, negatif düşürür.",
        ),
    ),
    supports_amount=False,
    color_space="sRGB",
    order_hint=20,
)
def black_white_point(image: np.ndarray, params: dict[str, Any],
                      ctx: RenderContext) -> np.ndarray:
    black = float(params["black"]) / 100.0 * 0.35
    white = float(params["white"]) / 100.0 * 0.35
    if abs(black) < 1e-6 and abs(white) < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    lo = np.float32(black)
    hi = np.float32(1.0 + white)
    span = max(1e-4, float(hi - lo))
    out = (rgb - lo) / np.float32(span)
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ======================================================== PARLAKLIK (BASIT)
@operation(
    op_id="tone.brightness",
    name="Parlaklık",
    description=(
        "Algısal parlaklığı kaydırır. Pozlamadan farkı: lineer ışıkta "
        "çarpım değil, ton eğrisinde kaydırma yapar; gölgeler daha az "
        "etkilenir."
    ),
    category=Category.TONE,
    params=(
        ParamSpec(
            key="amount", label="Parlaklık", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
        ),
    ),
    supports_amount=False,
    color_space="sRGB",
    order_hint=22,
)
def brightness(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if abs(amount) < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    # Gamma kaydirmasi: parlak alanlar kliplenmeden acilir
    gamma = np.float32(1.0 / (1.0 + amount * 0.7)) if amount > 0 else \
        np.float32(1.0 - amount * 0.7)
    out = np.sign(rgb) * px._pow(np.abs(rgb), float(gamma))
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ============================================================= YEREL KONTRAST
def _clarity_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    """Yerel kontrast sigma = yaricap/3; gorunur erisim 3 sigma."""
    return float(params["radius"])


@operation(
    op_id="detail.clarity",
    name="Yerel kontrast",
    description=(
        "Orta ölçekli ayrıntı kontrastını artırır (clarity). Dokuyu "
        "belirginleştirir, genel kontrastı değiştirmez."
    ),
    category=Category.DETAIL,
    params=(
        ParamSpec(
            key="amount", label="Yerel kontrast", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
        ),
        ParamSpec(
            key="radius", label="Yarıçap", kind=ParamKind.PIXELS,
            minimum=4.0, maximum=200.0, default=48.0, decimals=0,
            step=1.0, page_step=10.0, suffix=" px", bipolar=False,
            tooltip="Etkilenen ayrıntı ölçeği. Büyük değer geniş alanları etkiler.",
            unit_note="tam boy piksel; onizlemede olceklenir",
        ),
    ),
    supports_amount=False,
    color_space="sRGB parlaklık",
    performance_note="Gaussian blur; yaricapla doğru orantili maliyet",
    order_hint=40,
    neighbourhood=_clarity_reach,
)
def clarity(image: np.ndarray, params: dict[str, Any],
            ctx: RenderContext) -> np.ndarray:
    import cv2

    amount = float(params["amount"]) / 100.0
    if abs(amount) < 1e-6:
        return image
    # Yaricap tam boy piksel cinsinden tanimli; onizlemede olceklenir ki
    # onizlemedeki karakter tam boyda ayni kalsin.
    radius = max(1.0, ctx.scaled(float(params["radius"])))
    rgb, alpha = _rgb_alpha(image)

    luma = px.luminance(rgb)
    sigma = radius / 3.0
    blurred = cv2.GaussianBlur(luma, (0, 0), sigmaX=sigma, sigmaY=sigma,
                               borderType=cv2.BORDER_REFLECT)
    detail = luma - blurred
    boosted = luma + detail * np.float32(amount * 1.6)

    # Parlaklik farkini renge tasi; doygunluk kaymasin
    delta = (boosted - luma)[..., None]
    out = rgb + delta
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ================================================================== FADE/MATTE
@operation(
    op_id="tone.fade",
    name="Soluk (fade)",
    description=(
        "Siyahları kaldırıp parlak alanları hafifçe düşürür; analog "
        "baskı ve mat görünüm için temel işlem."
    ),
    category=Category.STYLE,
    params=(
        ParamSpec(
            key="lift", label="Siyah kaldırma", minimum=0.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0, bipolar=False,
            tooltip="Siyahları griye taşır.",
        ),
        ParamSpec(
            key="rolloff", label="Parlak düşürme", minimum=0.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0, bipolar=False,
            tooltip="Beyazları aşağı çeker.",
        ),
        amount_spec(),
    ),
    color_space="sRGB",
    order_hint=45,
)
def fade(image: np.ndarray, params: dict[str, Any],
         ctx: RenderContext) -> np.ndarray:
    lift = float(params["lift"]) / 100.0 * 0.22
    rolloff = float(params["rolloff"]) / 100.0 * 0.18
    if lift < 1e-6 and rolloff < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    lo = np.float32(lift)
    hi = np.float32(1.0 - rolloff)
    out = lo + rgb * (hi - lo)
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

"""Egriler, uc bolgeli color grading ve kanal karistirici.

Bu modul "renk derecelendirme" isini ustlenir: ton egrisi, gölge/orta
ton/parlak alan renk carklari ve kanallar arasi karisim.
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


# ===================================================================== EGRILER
_CURVE_CHANNELS = (
    ("rgb", "RGB (tumu)"),
    ("red", "Kırmızı"),
    ("green", "Yeşil"),
    ("blue", "Mavi"),
)


@operation(
    op_id="tone.curves",
    name="Eğriler",
    description=(
        "Ton eğrisi: parlaklık dağılımını serbestçe şekillendirir. RGB "
        "eğrisi tüm kanalları birlikte, kanal eğrileri renk dengesini "
        "ton aralığına göre değiştirir. Eğri monoton kalır; ton tersine "
        "dönmesi ve hale oluşmaz."
    ),
    category=Category.TONE,
    params=(
        ParamSpec(key="rgb", label="RGB eğrisi", kind=ParamKind.CURVE,
                  default=list(curves.IDENTITY_CURVE),
                  tooltip="Tüm kanallara uygulanır."),
        ParamSpec(key="red", label="Kırmızı eğrisi", kind=ParamKind.CURVE,
                  default=list(curves.IDENTITY_CURVE)),
        ParamSpec(key="green", label="Yeşil eğrisi", kind=ParamKind.CURVE,
                  default=list(curves.IDENTITY_CURVE)),
        ParamSpec(key="blue", label="Mavi eğrisi", kind=ParamKind.CURVE,
                  default=list(curves.IDENTITY_CURVE)),
        amount_spec(),
    ),
    order_hint=23,
    color_space="sRGB",
    performance_note="Kanal başına 1024 girisli arama tablosu; 2 MP'de ~25 ms",
)
def curves_op(image: np.ndarray, params: dict[str, Any],
              ctx: RenderContext) -> np.ndarray:
    active = [(key, params.get(key)) for key, _label in _CURVE_CHANNELS
              if not curves.is_identity(params.get(key))]
    if not active:
        return image

    rgb, alpha = _rgb_alpha(image)
    out = rgb.copy()

    lookup = dict(active)
    if "rgb" in lookup:
        lut = curves.build_lut(lookup["rgb"])
        for c in range(3):
            out[..., c] = curves.apply_lut(out[..., c], lut)
    for index, key in enumerate(("red", "green", "blue")):
        if key in lookup:
            out[..., index] = curves.apply_lut(
                out[..., index], curves.build_lut(lookup[key])
            )

    result = px.join_alpha(out, alpha)
    return apply_amount(image, result, params)


# ======================================================== UC BOLGELI GRADING
def _zone_weights(luma: np.ndarray, balance: float) -> tuple[np.ndarray,
                                                             np.ndarray,
                                                             np.ndarray]:
    """Golge / orta ton / parlak alan agirliklari.

    Uc agirlik her pikselde toplami 1 olacak sekilde normallenir;
    boylece notr degerlerde toplam etki sifir kalir ve bolgeler
    arasinda gorunur sinir olusmaz.
    """
    l = np.clip(luma, 0.0, 1.0)
    # balance: -1..1, bolge sinirlarini kaydirir
    shift = np.float32(balance * 0.25)
    shadow = np.clip(1.0 - (l + shift) * 2.2, 0.0, 1.0)
    highlight = np.clip((l + shift) * 2.2 - 1.2, 0.0, 1.0)
    shadow = px._pow(shadow, 1.5)
    highlight = px._pow(highlight, 1.5)
    mid = np.clip(1.0 - shadow - highlight, 0.0, 1.0)
    total = np.maximum(1e-6, shadow + mid + highlight)
    return shadow / total, mid / total, highlight / total


@operation(
    op_id="color.grading",
    name="Renk derecelendirme",
    description=(
        "Gölge, orta ton ve parlak alanlara ayrı renk verir. Sinematik "
        "renk ayrımının temel aracıdır: soğuk gölgeler, sıcak parlak "
        "alanlar gibi. Bölge ağırlıkları normallendiğinden geçişler "
        "yumuşaktır."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(key="shadow_color", label="Gölge rengi", kind=ParamKind.COLOR,
                  default=(0.5, 0.5, 0.5),
                  tooltip="Gölgelere taşınacak renk. Gri = etkisiz."),
        ParamSpec(key="shadow_amount", label="Gölge şiddeti", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="midtone_color", label="Orta ton rengi",
                  kind=ParamKind.COLOR, default=(0.5, 0.5, 0.5)),
        ParamSpec(key="midtone_amount", label="Orta ton şiddeti", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="highlight_color", label="Parlak alan rengi",
                  kind=ParamKind.COLOR, default=(0.5, 0.5, 0.5)),
        ParamSpec(key="highlight_amount", label="Parlak alan şiddeti",
                  minimum=0.0, maximum=100.0, default=0.0, decimals=0,
                  step=1.0, page_step=10.0, bipolar=False),
        ParamSpec(key="balance", label="Denge", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  tooltip="Bölge sınırlarını gölgeye veya parlak alana kaydırır."),
        ParamSpec(key="preserve_luma", label="Parlaklığı koru",
                  kind=ParamKind.BOOLEAN, default=True,
                  tooltip="Renk kaydırması genel parlaklığı değiştirmesin."),
        amount_spec(),
    ),
    order_hint=35,
    color_space="sRGB",
)
def color_grading(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    amounts = (float(params["shadow_amount"]), float(params["midtone_amount"]),
               float(params["highlight_amount"]))
    if all(a < 1e-6 for a in amounts):
        return image

    rgb, alpha = _rgb_alpha(image)
    luma = px.luminance(rgb)
    w_sh, w_mid, w_hi = _zone_weights(luma, float(params["balance"]) / 100.0)

    out = rgb.copy()
    zones = (
        (params["shadow_color"], amounts[0], w_sh),
        (params["midtone_color"], amounts[1], w_mid),
        (params["highlight_color"], amounts[2], w_hi),
    )
    for color, amount, weight in zones:
        if amount < 1e-6:
            continue
        tint = np.asarray(color, np.float32).reshape(1, 1, 3) - np.float32(0.5)
        out = out + tint * (weight[..., None] * np.float32(amount / 100.0))

    if bool(params.get("preserve_luma", True)):
        new_luma = px.luminance(out)
        out = out + (luma - new_luma)[..., None]

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ======================================================== KANAL KARISTIRICI
@operation(
    op_id="color.channel_mixer",
    name="Kanal karıştırıcı",
    description=(
        "Her çıktı kanalını giriş kanallarının ağırlıklı toplamından "
        "oluşturur. Kızılötesi benzeri yorumlar, kanal değiştirme ve "
        "güçlü renk kaydırmaları için."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(key="rr", label="Kırmızı <- Kırmızı", minimum=-200.0,
                  maximum=200.0, default=100.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="rg", label="Kırmızı <- Yeşil", minimum=-200.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="rb", label="Kırmızı <- Mavi", minimum=-200.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="gr", label="Yeşil <- Kırmızı", minimum=-200.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="gg", label="Yeşil <- Yeşil", minimum=-200.0,
                  maximum=200.0, default=100.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="gb", label="Yeşil <- Mavi", minimum=-200.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="br", label="Mavi <- Kırmızı", minimum=-200.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="bg", label="Mavi <- Yeşil", minimum=-200.0,
                  maximum=200.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        ParamSpec(key="bb", label="Mavi <- Mavi", minimum=-200.0,
                  maximum=200.0, default=100.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %"),
        amount_spec(),
    ),
    order_hint=36,
    color_space="sRGB",
)
def channel_mixer(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    matrix = np.array([
        [params["rr"], params["rg"], params["rb"]],
        [params["gr"], params["gg"], params["gb"]],
        [params["br"], params["bg"], params["bb"]],
    ], dtype=np.float32) / 100.0
    if np.allclose(matrix, np.eye(3, dtype=np.float32), atol=1e-6):
        return image
    rgb, alpha = _rgb_alpha(image)
    out = rgb @ matrix.T
    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ============================================================ FILM TON EGRISI
@operation(
    op_id="film.tone_curve",
    name="Film tonu",
    description=(
        "Negatif filmin karakteristik ton tepkisi: gölgelerde yumuşak "
        "ayak (toe), parlak alanlarda kademeli omuz (shoulder). Sert "
        "kırpılma yerine kademeli doyum verir."
    ),
    category=Category.FILM,
    params=(
        ParamSpec(key="toe", label="Ayak (toe)", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  bipolar=False,
                  tooltip="Gölgelerin yumuşak sıkışması; siyahlar ezilmez."),
        ParamSpec(key="shoulder", label="Omuz (shoulder)", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="Parlak alanların kademeli doyumu; sert kesilme olmaz."),
        ParamSpec(key="pivot", label="Kontrast pivotu", minimum=0.2,
                  maximum=0.8, default=0.45, decimals=2, step=0.01,
                  page_step=0.05, bipolar=False),
        ParamSpec(key="strength", label="Kontrast", minimum=-50.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0),
        amount_spec(),
    ),
    order_hint=70,
    color_space="sRGB",
)
def film_tone_curve(image: np.ndarray, params: dict[str, Any],
                    ctx: RenderContext) -> np.ndarray:
    toe = float(params["toe"]) / 100.0
    shoulder = float(params["shoulder"]) / 100.0
    strength = float(params["strength"]) / 100.0
    if toe < 1e-6 and shoulder < 1e-6 and abs(strength) < 1e-6:
        return image

    rgb, alpha = _rgb_alpha(image)
    pivot = np.float32(params["pivot"])

    out = rgb
    if strength > 1e-6:
        # Yumusak omuz (bkz. tone.contrast). Duz carpim karanlik
        # fotografta degerleri sifirin altina indiriyor ve golgeleri
        # tek bir siyaha eziyordu; tanh uclari asimptotik tutar.
        slope = np.float32(1.0 + strength * 0.8)
        softness = np.float32(0.5)
        out = pivot + softness * np.tanh((out - pivot) * slope / softness)
    elif strength < -1e-6:
        # Negatif guc kontrasti *azaltir*; sikistirma zaten guvenli
        out = pivot + (out - pivot) * np.float32(1.0 + strength * 0.8)

    if toe > 1e-6:
        # Golge ayagi: dusuk degerleri yukari cekerek sikistir
        t = np.clip(out / max(1e-4, float(pivot)), 0.0, 1.0)
        lift = px._pow(1.0 - t, 3.0) * np.float32(toe * 0.14)
        out = out + lift

    if shoulder > 1e-6:
        # Omuz: 1.0'a yaklasirken kademeli doyum (yumusak tanh)
        knee = np.float32(1.0 - shoulder * 0.45)
        excess = np.maximum(0.0, out - knee)
        span = np.float32(max(1e-4, 1.0 - knee))
        out = np.where(out > knee,
                       knee + span * np.tanh(excess / span),
                       out)

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

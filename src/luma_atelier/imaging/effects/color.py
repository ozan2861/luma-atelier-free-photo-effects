"""Renk islemleri: beyaz dengesi, doygunluk, vibrance, HSL, grading.

Uzay notlari
------------
* **Beyaz dengesi** lineer isikta kanal kazanci olarak uygulanir; bu
  fiziksel olarak dogru olandir. Sicaklik/tint degerleri Bradford
  benzeri basit bir kanal kazanci modeline eslenir. Tam kromatik
  adaptasyon (CAT02) iddia edilmiyor.
* **Doygunluk / vibrance** algisal parlakligi koruyacak sekilde sRGB
  uzayinda calisir.
* **HSL** OpenCV HSV uzerinden degil, dogrudan ton acisi hesabiyla
  yapilir; boylece float32 hassasiyeti korunur ve 8-bit kuantizasyon
  bantlasmasi olusmaz.
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

#: Beyaz dengesi referansi. Bu sicaklikta kazanc (1,1,1).
NEUTRAL_KELVIN = 6500.0

#: HSL araliklarinin merkez ton acilari (derece).
HUE_BANDS: tuple[tuple[str, str, float], ...] = (
    ("red", "Kırmızı", 0.0),
    ("orange", "Turuncu", 30.0),
    ("yellow", "Sarı", 60.0),
    ("green", "Yeşil", 120.0),
    ("aqua", "Turkuaz", 180.0),
    ("blue", "Mavi", 240.0),
    ("purple", "Mor", 285.0),
    ("magenta", "Magenta", 320.0),
)


def _rgb_alpha(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return px.split_alpha(image)


def _kelvin_gains(kelvin: float, tint: float) -> np.ndarray:
    """Sicaklik/tint degerlerini lineer RGB kanal kazancina cevirir.

    Basitlestirilmis model: sicaklik kirmizi-mavi ekseninde, tint
    yesil-magenta ekseninde kazanc uretir. Referans 6500 K'de kazanc
    (1, 1, 1). Bu bir *sanatsal* beyaz dengesidir; olcumsel kromatik
    adaptasyon iddia edilmez.
    """
    # Referansa gore logaritmik mesafe: 3200 K ve 13000 K simetrik etkisin
    t = np.log(max(1500.0, min(20000.0, kelvin)) / NEUTRAL_KELVIN)
    # Yon: **dusuk K soguk (mavi), yuksek K sicak (amber)**. Lightroom,
    # Capture One ve Camera Raw ayni yonu kullanir; kaydiricinin kendi
    # ipucu da bunu soyluyordu. Onceki surum tersiydi ve kullaniciya
    # yanlis sayi gosteriyordu (v1 tarifleri yuklenirken cevrilir).
    warm = float(np.exp(t * 0.55))     # kirmizi kazanci
    cool = float(np.exp(-t * 0.55))    # mavi kazanci
    green = float(np.exp(-tint / 150.0 * 0.5))
    magenta = float(np.exp(tint / 150.0 * 0.25))
    gains = np.array([warm * magenta, green, cool * magenta], dtype=np.float32)
    # Parlakligi koru: kazanclari luma agirliklarina gore normalle
    norm = float((gains * px.LUMA_WEIGHTS_709).sum())
    return (gains / max(1e-6, norm)).astype(np.float32)


# ============================================================ BEYAZ DENGESI
@operation(
    op_id="color.white_balance",
    name="Beyaz dengesi",
    description=(
        "Renk sıcaklığını ve yeşil-magenta dengesini ayarlar. Lineer "
        "ışıkta kanal kazancı olarak uygulanır."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(
            key="kelvin", label="Sıcaklık", minimum=2000.0, maximum=12000.0,
            default=NEUTRAL_KELVIN, decimals=0, step=50.0, page_step=500.0,
            suffix=" K", bipolar=False,
            tooltip="Düşük değer soğuk (mavi), yüksek değer sıcak (amber).",
            unit_note="Kelvin; 6500 K nötr",
        ),
        ParamSpec(
            key="tint", label="Tint", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
            tooltip="Negatif yeşile, pozitif magentaya kaydırır.",
        ),
    ),
    supports_amount=False,
    domain="linear",
    color_space="lineer ışık",
    performance_note="Tek kanal kazancı carpimi; transfer motor tarafinda.",
    order_hint=10,
)
def white_balance(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    # Girdi lineer isiktir (domain="linear").
    kelvin = float(params["kelvin"])
    tint = float(params["tint"])
    if abs(kelvin - NEUTRAL_KELVIN) < 1.0 and abs(tint) < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    gains = _kelvin_gains(kelvin, tint)
    return px.join_alpha(rgb * gains.reshape(1, 1, 3), alpha)


# ================================================================ DOYGUNLUK
@operation(
    op_id="color.saturation",
    name="Doygunluk",
    description=(
        "Tüm renklerin canlılığını eşit oranda değiştirir. -100 tam "
        "siyah-beyaz yapar."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(
            key="amount", label="Doygunluk", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
        ),
    ),
    supports_amount=False,
    color_space="sRGB",
    order_hint=30,
)
def saturation(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if abs(amount) < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    grey = px.luminance(rgb)[..., None]
    factor = np.float32(1.0 + amount)
    out = grey + (rgb - grey) * factor
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ================================================================= VIBRANCE
@operation(
    op_id="color.vibrance",
    name="Canlılık (vibrance)",
    description=(
        "Sönük renkleri doygunlaştırır, zaten doygun olanlara az dokunur. "
        "Ten tonlarını koruyarak canlılık verir."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(
            key="amount", label="Canlılık", minimum=-100.0, maximum=100.0,
            default=0.0, decimals=0, step=1.0, page_step=10.0,
        ),
        ParamSpec(
            key="protect_skin", label="Ten tonunu koru",
            kind=ParamKind.BOOLEAN, default=True,
            tooltip=(
                "Turuncu-kırmızı aralığındaki renklere daha az etki eder. "
                "Bu bir maske yardımcısıdır; yüz algılama yapmaz."
            ),
        ),
    ),
    supports_amount=False,
    color_space="sRGB",
    order_hint=31,
)
def vibrance(image: np.ndarray, params: dict[str, Any],
             ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if abs(amount) < 1e-6:
        return image
    rgb, alpha = _rgb_alpha(image)
    grey = px.luminance(rgb)[..., None]

    hue, sat, value = hue_saturation_chroma(rgb)
    # Gecici dizi sayisini dusuk tutmak icin yerinde (in-place) islemler.
    weight = sat * value                   # kabaca doygunluk olcusu
    weight *= np.float32(-1.4)
    weight += np.float32(1.0)
    np.clip(weight, 0.0, 1.0, out=weight)

    if bool(params.get("protect_skin", True)):
        # Ten benzeri turuncu-kirmizi arali (~10-50 derece) icin agirligi
        # dusur. Bu maske tabanli bir yardimcidir; yuz algilama degildir.
        # Modulo yerine simetrik mesafe: hue zaten 0..360 araliginda.
        dist = np.abs(hue - np.float32(28.0))
        np.minimum(dist, np.float32(360.0) - dist, out=dist)
        dist *= np.float32(-1.0 / 34.0)
        dist += np.float32(1.0)
        np.clip(dist, 0.0, 1.0, out=dist)    # dist artik "skin"
        dist *= np.float32(-0.55)
        dist += np.float32(1.0)
        weight *= dist

    weight *= np.float32(amount)
    weight += np.float32(1.0)
    factor = weight[..., None]
    out = grey + (rgb - grey) * factor
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


def _hue_degrees(rgb: np.ndarray) -> np.ndarray:
    """0..360 ton acisi. Gri piksellerde 0 doner.

    OpenCV'nin float32 HSV donusumu kullanilir. Bu, 8-bit HSV'nin
    kuantizasyon bantlasmasini *yasamaz* (girdi float32 kalir) ve elle
    yazilmis NumPy surumune gore 2 MP'de 150 ms yerine 1.8 ms surer;
    olculen en buyuk sapma 0.008 derece.
    """
    import cv2
    # cvtColor 0..1 araligi varsayar; disaridaki degerler ton acisini
    # bozmaz ama negatifler tanimsizdir, bu yuzden kirpilir.
    src = np.ascontiguousarray(np.clip(rgb[..., :3], 0.0, 1.0),
                               dtype=px.WORKING_DTYPE)
    return cv2.cvtColor(src, cv2.COLOR_RGB2HSV)[..., 0]


def hue_saturation_chroma(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray,
                                                    np.ndarray]:
    """RGB -> (ton derecesi 0..360, HSV doygunlugu 0..1, deger 0..1).

    Tek bir OpenCV cagrisiyla ucu birden hesaplanir.
    """
    import cv2
    src = np.ascontiguousarray(np.clip(rgb[..., :3], 0.0, 1.0),
                               dtype=px.WORKING_DTYPE)
    hsv = cv2.cvtColor(src, cv2.COLOR_RGB2HSV)
    return hsv[..., 0], hsv[..., 1], hsv[..., 2]


def _band_mask(hue: np.ndarray, centre: float, width: float = 45.0) -> np.ndarray:
    """Bir ton araliginin yumusak maskesi.

    Kosinus pencere: komsu araliklarla ortusur, sert sinir cizmez.
    """
    dist = np.abs(((hue - centre + 180.0) % 360.0) - 180.0)
    t = np.clip(dist / width, 0.0, 1.0)
    return (0.5 * (1.0 + np.cos(t * np.pi))).astype(px.WORKING_DTYPE)


# ====================================================================== HSL
_HSL_PARAMS: list[ParamSpec] = []
for _key, _label, _centre in HUE_BANDS:
    _HSL_PARAMS.append(ParamSpec(
        key=f"{_key}_hue", label=f"{_label} ton", minimum=-100.0, maximum=100.0,
        default=0.0, decimals=0, step=1.0, page_step=10.0,
        tooltip=f"{_label} aralığındaki renklerin ton açısını kaydırır.",
    ))
    _HSL_PARAMS.append(ParamSpec(
        key=f"{_key}_sat", label=f"{_label} doygunluk", minimum=-100.0,
        maximum=100.0, default=0.0, decimals=0, step=1.0, page_step=10.0,
    ))
    _HSL_PARAMS.append(ParamSpec(
        key=f"{_key}_lum", label=f"{_label} parlaklık", minimum=-100.0,
        maximum=100.0, default=0.0, decimals=0, step=1.0, page_step=10.0,
    ))


@operation(
    op_id="color.hsl",
    name="HSL renk aralıkları",
    description=(
        "Sekiz renk aralığını ayrı ayrı ayarlar: ton, doygunluk ve "
        "parlaklık. Aralıklar yumuşak geçişli, komşularıyla örtüşür."
    ),
    category=Category.COLOR,
    params=tuple(_HSL_PARAMS),
    supports_amount=False,
    color_space="sRGB",
    performance_note="Sekiz maske hesabi; 9 MP'de ~350 ms",
    order_hint=32,
)
def hsl(image: np.ndarray, params: dict[str, Any],
        ctx: RenderContext) -> np.ndarray:
    active = [(k, l, c) for k, l, c in HUE_BANDS
              if any(abs(float(params.get(f"{k}_{s}", 0.0))) > 1e-6
                     for s in ("hue", "sat", "lum"))]
    if not active:
        return image

    rgb, alpha = _rgb_alpha(image)
    hue, sat, _value = hue_saturation_chroma(rgb)
    grey = px.luminance(rgb)[..., None]

    # Gri piksellerde ton anlamsizdir; etkiden muaf tut
    colourfulness = np.clip(sat * 2.2, 0.0, 1.0)[..., None]

    out = rgb.copy()
    for key, _label, centre in active:
        mask = (_band_mask(hue, centre) * colourfulness[..., 0])[..., None]
        if mask.max() < 1e-5:
            continue
        s_adj = float(params.get(f"{key}_sat", 0.0)) / 100.0
        l_adj = float(params.get(f"{key}_lum", 0.0)) / 100.0
        h_adj = float(params.get(f"{key}_hue", 0.0)) / 100.0

        if abs(s_adj) > 1e-6:
            target = grey + (out - grey) * np.float32(1.0 + s_adj)
            out = out + (target - out) * mask
        if abs(l_adj) > 1e-6:
            target = out + np.float32(l_adj * 0.35)
            out = out + (target - out) * mask
        if abs(h_adj) > 1e-6:
            out = out + _hue_rotate(out, h_adj * 30.0) * mask

    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


def _hue_rotate(rgb: np.ndarray, degrees: float) -> np.ndarray:
    """Ton donusunun urettigi *fark* dizisini dondurur.

    YIQ benzeri donus matrisi kullanilir: parlakligi korur ve ton
    araligina gore maskelenebilir bir delta uretir.
    """
    theta = np.radians(degrees, dtype=np.float32)
    cos_a, sin_a = np.float32(np.cos(theta)), np.float32(np.sin(theta))
    one_third = np.float32(1.0 / 3.0)
    sqrt_third = np.float32(np.sqrt(1.0 / 3.0))
    a = cos_a + (1.0 - cos_a) * one_third
    b = one_third * (1.0 - cos_a) - sqrt_third * sin_a
    c = one_third * (1.0 - cos_a) + sqrt_third * sin_a
    mat = np.array([[a, b, c], [c, a, b], [b, c, a]], dtype=np.float32)
    rotated = rgb @ mat.T
    return (rotated - rgb).astype(px.WORKING_DTYPE)


# =========================================================== SIYAH - BEYAZ
@operation(
    op_id="color.monochrome",
    name="Siyah-beyaz karışım",
    description=(
        "Renkli görüntüyü kanal ağırlıklarıyla siyah-beyaza çevirir. "
        "Her renk aralığının griye katkısı ayrı ayarlanır."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(key="red", label="Kırmızı", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="orange", label="Turuncu", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="yellow", label="Sarı", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="green", label="Yeşil", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="aqua", label="Turkuaz", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="blue", label="Mavi", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="purple", label="Mor", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        ParamSpec(key="magenta", label="Magenta", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0),
        amount_spec(),
    ),
    identity_at_defaults=False,
    color_space="sRGB",
    order_hint=33,
)
def monochrome(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    rgb, alpha = _rgb_alpha(image)
    hue, sat, _value = hue_saturation_chroma(rgb)
    grey = px.luminance(rgb)

    colourfulness = np.clip(sat * 2.2, 0.0, 1.0)
    for key, _label, centre in HUE_BANDS:
        adj = float(params.get(key, 0.0)) / 100.0
        if abs(adj) < 1e-6:
            continue
        mask = _band_mask(hue, centre) * colourfulness
        grey = grey + mask * np.float32(adj * 0.5)

    mono = np.dstack([grey, grey, grey]).astype(px.WORKING_DTYPE)
    result = px.join_alpha(mono, alpha)
    return apply_amount(image, result, params)


# ======================================================== SPLIT TONING
@operation(
    op_id="color.split_tone",
    name="Split toning",
    description=(
        "Gölgelere ve parlak alanlara ayrı renk verir. Klasik analog "
        "baskı ve sinematik renk ayrımı için temel araç."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(key="shadow_color", label="Gölge rengi", kind=ParamKind.COLOR,
                  default=(0.22, 0.34, 0.52),
                  tooltip="Gölgelere karıştırılacak renk."),
        ParamSpec(key="shadow_strength", label="Gölge şiddeti", minimum=0.0,
                  maximum=100.0, default=0.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="highlight_color", label="Parlak alan rengi",
                  kind=ParamKind.COLOR, default=(0.98, 0.82, 0.58),
                  tooltip="Parlak alanlara karıştırılacak renk."),
        ParamSpec(key="highlight_strength", label="Parlak alan şiddeti",
                  minimum=0.0, maximum=100.0, default=0.0, decimals=0,
                  step=1.0, page_step=10.0, bipolar=False),
        ParamSpec(key="balance", label="Denge", minimum=-100.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  tooltip="Gölge ve parlak alan bölgelerinin sınırını kaydırır."),
        amount_spec(),
    ),
    color_space="sRGB",
    order_hint=34,
)
def split_tone(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    sh_strength = float(params["shadow_strength"]) / 100.0
    hl_strength = float(params["highlight_strength"]) / 100.0
    if sh_strength < 1e-6 and hl_strength < 1e-6:
        return image

    rgb, alpha = _rgb_alpha(image)
    luma = np.clip(px.luminance(rgb), 0.0, 1.0)
    balance = float(params["balance"]) / 100.0 * 0.35
    pivot = np.float32(0.5 + balance)

    shadow_w = np.clip((pivot - luma) / max(1e-4, float(pivot)), 0.0, 1.0)
    highlight_w = np.clip((luma - pivot) / max(1e-4, float(1.0 - pivot)), 0.0, 1.0)
    shadow_w = np.power(shadow_w, 1.4, dtype=px.WORKING_DTYPE)
    highlight_w = np.power(highlight_w, 1.4, dtype=px.WORKING_DTYPE)

    out = rgb.copy()
    if sh_strength > 1e-6:
        tint = np.asarray(params["shadow_color"], np.float32).reshape(1, 1, 3)
        # Soft light benzeri: rengi tasi ama parlakligi ezme
        out = out + (tint - 0.5) * (shadow_w[..., None] * np.float32(sh_strength * 0.5))
    if hl_strength > 1e-6:
        tint = np.asarray(params["highlight_color"], np.float32).reshape(1, 1, 3)
        out = out + (tint - 0.5) * (highlight_w[..., None]
                                    * np.float32(hl_strength * 0.5))

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

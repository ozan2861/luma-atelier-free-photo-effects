"""Film dokusu: grain, toz/cizik, procedurel kagit dokusu.

Determinizm
-----------
Tumu `RenderContext.derive_seed` ile turetilmis seed kullanir. Ayni
tarif + ayni seed + ayni cozunurluk = ayni sonuc. Desen *tam boy
koordinatlarda* uretilip cozunurluge uyarlanir; onizlemedeki grain
boyutu tam boyda ayni karakteri korur.

Grain neden duz beyaz gurultu degil
-----------------------------------
Gercek film graini su ozellikleri tasir ve bunlarin hepsi modellenir:

1. **Tonlara gore degisir.** Orta tonlarda en belirgin, siyahta ve
   parlak alanda azdir; cunku kristal yogunlugu poz miktarina baglidir.
2. **Boyutu vardir.** Tek piksel degil, bir kac piksel genisliginde
   kumeler halindedir. Bulaniklikla degil, *dusuk cozunurlukte uretip
   buyuterek* elde edilir; boylece tanenin kendi kenari kalir.
3. **Kanallar bagimsizdir** (renkli filmde uc ayri emulsiyon katmani).
   Monokrom secenekte tek kanal uretilip paylasilir.
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


def _rgb_alpha(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return px.split_alpha(image)


def _frame_geometry(ctx: RenderContext, h: int,
                    w: int) -> tuple[int, int, int, int]:
    """(frame_h, frame_w, oy, ox) - karo disinda islenen boyutla aynidir."""
    frame_h, frame_w = ctx.frame_size(h, w)
    ox, oy = ctx.tile_origin
    return frame_h, frame_w, oy, ox


def _bilinear_axis(size_src: int, size_dst: int, start: int,
                   count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """cv2.resize'in tek eksenli bilinear orneklemesi, kismi aralik icin.

    `cv2.remap` kesirli konumu 1/32'ye yuvarlar; karo ile tam boy render
    arasinda bu gorunur bir tane farki birakiyordu. Bu yuzden orneklem
    dogrudan kurulur: cv2.resize ile ayni eslemedir
    (`src = (dst + 0.5) * src_boy / dst_boy - 0.5`), kenarda kopyalama.
    """
    pos = ((np.arange(start, start + count, dtype=np.float64) + 0.5)
           * (size_src / float(size_dst)) - 0.5)
    i0 = np.floor(pos).astype(np.int64)
    frac = (pos - i0).astype(np.float32)
    i1 = np.clip(i0 + 1, 0, size_src - 1)
    i0c = np.clip(i0, 0, size_src - 1)
    # Kenar disinda kalan orneklerde agirlik tamamen kenara gitmeli
    frac = np.where(i0 < 0, 0.0, frac).astype(np.float32)
    frac = np.where(i0 >= size_src - 1, 0.0, frac).astype(np.float32)
    return i0c, i1, frac


def _sample_field(field: np.ndarray, frame_h: int, frame_w: int,
                  oy: int, ox: int, h: int, w: int) -> np.ndarray:
    """Izgarayi kadraj koordinatinda bilinear ornekler (karo bolgesi)."""
    sh, sw = field.shape
    y0, y1, fy = _bilinear_axis(sh, frame_h, oy, h)
    x0, x1, fx = _bilinear_axis(sw, frame_w, ox, w)
    top = (field[np.ix_(y0, x0)] * (1.0 - fx)[None, :]
           + field[np.ix_(y0, x1)] * fx[None, :])
    bottom = (field[np.ix_(y1, x0)] * (1.0 - fx)[None, :]
              + field[np.ix_(y1, x1)] * fx[None, :])
    out = top * (1.0 - fy)[:, None] + bottom * fy[:, None]
    return np.ascontiguousarray(out, dtype=np.float32)


def _upsample_gain(field: np.ndarray, frame_h: int, frame_w: int) -> float:
    """Buyutulmus gurultu alaninin standart sapmasi.

    Bilinear buyutme varyansi dusurur ve geri normallenmesi gerekir.
    Normalleme carpani **tum kadrajdan** tahmin edilir: karonun kendi
    bolgesinden hesaplansaydi %100 gorunum ile disa aktarim arasinda
    yuzde birkac tane siddeti farki kalirdi.
    """
    sh, sw = field.shape
    ny = min(frame_h, 192)
    nx = min(frame_w, 192)
    ys = np.linspace(0.0, frame_h - 1.0, ny, dtype=np.float32)
    xs = np.linspace(0.0, frame_w - 1.0, nx, dtype=np.float32)
    map_x = np.repeat((((xs + 0.5) * (sw / frame_w)) - 0.5)[None, :], ny, 0)
    map_y = np.repeat((((ys + 0.5) * (sh / frame_h)) - 0.5)[:, None], nx, 1)
    probe = cv2.remap(field, map_x, map_y, cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_REPLICATE)
    return float(probe.std())


def _grain_field(shape: tuple[int, int], size_px: float,
                 rng: np.random.Generator, *,
                 frame: tuple[int, int] | None = None,
                 origin: tuple[int, int] = (0, 0)) -> np.ndarray:
    """Verilen tane boyutunda gurultu alani uretir (ortalama 0).

    Dusuk cozunurlukte uretilip buyutulur: taneler gercek boyutunu
    korur ve bulaniklastirilmis gurultuye gore daha "filmsi" bir kenar
    verir.

    `frame` = (frame_h, frame_w) verilirse desen **tam kadraj** icin
    kurulur ve yalnizca `origin` ile `shape` arasindaki bolge dondurulur.
    %100 gorunum karosu boylece dista aktarilan dosyayla ayni taneyi
    gosterir. Varyans normallemesi karoda kendi bolgesinden hesaplanir;
    yeterince genis bir karoda sapma yuzde bir mertebesindedir.
    """
    h, w = shape
    frame_h, frame_w = frame if frame is not None else (h, w)
    oy, ox = origin
    factor = max(1.0, size_px)
    sh = max(2, int(round(frame_h / factor)))
    sw = max(2, int(round(frame_w / factor)))
    field = rng.standard_normal((sh, sw), dtype=np.float32)
    if (sh, sw) == (frame_h, frame_w):
        # Olcek 1: buyutme yok, normalleme de gerekmez
        return np.ascontiguousarray(field[oy:oy + h, ox:ox + w])
    gain = _upsample_gain(field, frame_h, frame_w)
    if (h, w) == (frame_h, frame_w) and (oy, ox) == (0, 0):
        field = cv2.resize(field, (frame_w, frame_h),
                           interpolation=cv2.INTER_LINEAR)
    else:
        # Karo: cv2.resize'in orneklemesini yalnizca bu bolge icin kur
        field = _sample_field(field, frame_h, frame_w, oy, ox, h, w)
    # Buyutme varyansi dusurur; geri normalle
    if gain > 1e-6:
        field = field / gain
    return field


# ================================================================ FILM GRAIN
@operation(
    op_id="texture.grain",
    name="Film grain",
    description=(
        "Film emülsiyonunun tanecikli dokusu. Tonlara göre dağılır "
        "(orta tonlarda en belirgin), tane boyutu ayarlanabilir, renkli "
        "veya monokrom olabilir. Seed ile tekrarlanabilir."
    ),
    category=Category.TEXTURE,
    params=(
        ParamSpec(key="amount", label="Miktar", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  suffix=" %", bipolar=False),
        ParamSpec(key="size", label="Tane boyutu", kind=ParamKind.PIXELS,
                  minimum=1.0, maximum=12.0, default=2.2, decimals=1,
                  step=0.1, page_step=1.0, suffix=" px", bipolar=False,
                  unit_note="tam boy piksel; onizlemede olceklenir"),
        ParamSpec(key="roughness", label="Sertlik", minimum=0.0,
                  maximum=100.0, default=45.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False,
                  tooltip="Yüksek değer daha kontrastlı, keskin tane."),
        ParamSpec(key="colour", label="Renkli tane", kind=ParamKind.BOOLEAN,
                  default=False,
                  tooltip=(
                      "Açıkken kanallar bağımsız (renkli film), "
                      "kapalıyken tek kanal paylaşılır (monokrom)."
                  )),
        ParamSpec(key="shadow_weight", label="Gölgelerde", minimum=0.0,
                  maximum=200.0, default=70.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %", bipolar=False),
        ParamSpec(key="highlight_weight", label="Parlak alanlarda",
                  minimum=0.0, maximum=200.0, default=45.0, decimals=0,
                  step=1.0, page_step=10.0, suffix=" %", bipolar=False),
        seed_spec(1),
    ),
    order_hint=90,
    supports_amount=False,
    color_space="sRGB",
    performance_note="Kanal başına gurultu alanı; 2 MP renkli tanede ~35 ms",
    resolution_exact=False,
)
def film_grain(image: np.ndarray, params: dict[str, Any],
               ctx: RenderContext) -> np.ndarray:
    amount = float(params["amount"]) / 100.0
    if amount < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    size = max(1.0, ctx.scaled(float(params["size"])))
    # Seed ve desen **kadraja** baglidir: %100 gorunum karosu, dista
    # aktarilan dosyayla ayni taneyi gostermelidir.
    frame_h, frame_w, oy, ox = _frame_geometry(ctx, h, w)
    rng = ctx.rng("grain", int(params["seed"]), frame_w, frame_h)
    geom = {"frame": (frame_h, frame_w), "origin": (oy, ox)}

    colour = bool(params.get("colour", False))
    if colour:
        field = np.dstack([_grain_field((h, w), size, rng, **geom)
                           for _ in range(3)])
    else:
        mono = _grain_field((h, w), size, rng, **geom)
        field = np.dstack([mono, mono, mono])

    roughness = float(params["roughness"]) / 100.0
    if roughness > 0.02:
        # Sertlik: dagilimi uc degerlere iter (kontrastli tane)
        field = np.tanh(field * np.float32(1.0 + roughness * 2.2))

    # Ton agirligi: orta tonlarda 1, uclarda parametrelerle azalan
    luma = np.clip(px.luminance(rgb), 0.0, 1.0)
    sh_w = float(params["shadow_weight"]) / 100.0
    hi_w = float(params["highlight_weight"]) / 100.0
    mid = 1.0 - np.abs(luma - 0.5) * 2.0          # 0..1, ortada 1
    mid = px._pow(np.clip(mid, 0.0, 1.0), 0.65)
    shadow_side = np.clip(1.0 - luma * 2.0, 0.0, 1.0)
    highlight_side = np.clip(luma * 2.0 - 1.0, 0.0, 1.0)
    weight = (mid + shadow_side * np.float32(sh_w)
              + highlight_side * np.float32(hi_w))
    weight = np.clip(weight, 0.0, 2.0)[..., None]

    out = rgb + field * weight * np.float32(amount * 0.085)
    return px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)


# ============================================================ TOZ VE CIZIK
def _dust_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    """Benek bulanikligi ve cizik yayilmasi."""
    return max(3.0 * float(params["dust_size"]) / 3.0, 6.0)


def _paper_reach(params: dict[str, Any], frame: tuple[int, int]) -> float:
    """Lif uzatmasi yatayda sigma = olcek * 1.8."""
    return 3.0 * float(params["scale"]) * 1.8


@operation(
    op_id="texture.dust",
    name="Toz ve çizik",
    description=(
        "Eski film ve taranmış baskı izlenimi: küçük toz benekleri ve "
        "ince dikey çizikler. Seed ile tekrarlanabilir; her açılışta "
        "aynı yerde çıkar."
    ),
    category=Category.TEXTURE,
    params=(
        ParamSpec(key="dust", label="Toz", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  suffix=" %", bipolar=False),
        ParamSpec(key="scratches", label="Çizik", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  suffix=" %", bipolar=False),
        ParamSpec(key="dust_size", label="Toz boyutu", kind=ParamKind.PIXELS,
                  minimum=1.0, maximum=14.0, default=3.0, decimals=1,
                  step=0.5, page_step=2.0, suffix=" px", bipolar=False),
        ParamSpec(key="dark_ratio", label="Koyu leke oranı", minimum=0.0,
                  maximum=100.0, default=55.0, decimals=0, step=1.0,
                  page_step=10.0, suffix=" %", bipolar=False,
                  tooltip="Beneklerin ne kadarı koyu (negatifte toz) olsun."),
        seed_spec(2),
        amount_spec(),
    ),
    order_hint=91,
    color_space="sRGB",
    resolution_exact=False,
    neighbourhood=_dust_reach,
)
def dust_and_scratches(image: np.ndarray, params: dict[str, Any],
                       ctx: RenderContext) -> np.ndarray:
    dust = float(params["dust"]) / 100.0
    scratches = float(params["scratches"]) / 100.0
    if dust < 1e-4 and scratches < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    # Benekler ve cizikler kadraj koordinatinda uretilir; karo yalnizca
    # kendi bolgesine dusenleri cizer. Boylece %100 gorunumdeki toz,
    # dista aktarilan dosyadakiyle ayni yerdedir.
    frame_h, frame_w, oy, ox = _frame_geometry(ctx, h, w)
    rng = ctx.rng("dust", int(params["seed"]), frame_w, frame_h)
    out = rgb.copy()

    if dust > 1e-4:
        # Benek sayisi *tam boy* alana gore; onizlemede yogunluk ayni
        full_area = max(1, ctx.full_width * ctx.full_height)
        count = int(dust * full_area / 42_000)
        count = min(count, 60_000)
        if count:
            xs = rng.integers(0, frame_w, count) - ox
            ys = rng.integers(0, frame_h, count) - oy
            dark = rng.random(count) < (float(params["dark_ratio"]) / 100.0)
            size = max(1.0, ctx.scaled(float(params["dust_size"])))
            spots = np.zeros((h, w), np.float32)
            values = np.where(dark, -1.0, 1.0).astype(np.float32)
            values = values * rng.uniform(0.3, 1.0, count).astype(np.float32)
            inside = ((xs >= 0) & (xs < w) & (ys >= 0) & (ys < h))
            if not inside.all():
                xs, ys, values = xs[inside], ys[inside], values[inside]
            np.add.at(spots, (ys, xs), values)
            if size > 1.2:
                spots = cv2.GaussianBlur(spots, (0, 0), sigmaX=size / 3.0,
                                         borderType=cv2.BORDER_REFLECT)
                spots *= size * 0.9
            out = out + spots[..., None] * np.float32(0.55)

    if scratches > 1e-4:
        count = max(1, int(scratches * 14))
        field = np.zeros((h, w), np.float32)
        for _ in range(count):
            x = int(rng.integers(0, max(1, frame_w)))
            thickness = max(1, int(ctx.scaled(float(rng.uniform(1.0, 2.6)))))
            y0 = int(rng.integers(0, max(1, frame_h)))
            y1 = int(np.clip(y0 + rng.uniform(0.2, 1.0) * frame_h,
                             0, frame_h))
            strength = float(rng.uniform(0.25, 0.8))
            drift = float(rng.uniform(-0.02, 0.02)) * frame_w
            for k in range(thickness):
                xi = min(x + k, frame_w - 1)
                rows = np.arange(y0, y1)
                if rows.size == 0:
                    continue
                cols = np.clip(
                    (xi + drift * (rows - y0) / max(1, y1 - y0)).astype(np.int32),
                    0, frame_w - 1,
                )
                # Kadraj koordinatindan karo koordinatina
                rows = rows - oy
                cols = cols - ox
                keep = ((rows >= 0) & (rows < h) & (cols >= 0) & (cols < w))
                if not keep.any():
                    continue
                field[rows[keep], cols[keep]] += strength
        field = cv2.GaussianBlur(field, (0, 0), sigmaX=0.7, sigmaY=2.0,
                                 borderType=cv2.BORDER_REFLECT)
        out = out + field[..., None] * np.float32(0.35)

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)


# ============================================================ KAGIT DOKUSU
@operation(
    op_id="texture.paper",
    name="Kağıt dokusu",
    description=(
        "Yordamsal baskı kağıdı dokusu: ince lif deseni ve hafif "
        "düzensiz yüzey. Fotoğrafa basılmış hissi verir. Doku kodla "
        "üretilir; dışarıdan doku dosyası kullanılmaz."
    ),
    category=Category.TEXTURE,
    params=(
        ParamSpec(key="strength", label="Şiddet", minimum=0.0, maximum=100.0,
                  default=0.0, decimals=0, step=1.0, page_step=10.0,
                  suffix=" %", bipolar=False),
        ParamSpec(key="scale", label="Doku ölçeği", kind=ParamKind.PIXELS,
                  minimum=1.0, maximum=24.0, default=5.0, decimals=1,
                  step=0.5, page_step=2.0, suffix=" px", bipolar=False),
        ParamSpec(key="fibre", label="Lif belirginliği", minimum=0.0,
                  maximum=100.0, default=50.0, decimals=0, step=1.0,
                  page_step=10.0, bipolar=False),
        ParamSpec(key="warmth", label="Kağıt sıcaklığı", minimum=-100.0,
                  maximum=100.0, default=15.0, decimals=0, step=1.0,
                  page_step=10.0,
                  tooltip="Pozitif değer kağıdı kremleştirir."),
        seed_spec(4),
        amount_spec(),
    ),
    order_hint=93,
    color_space="sRGB",
    resolution_exact=False,
    neighbourhood=_paper_reach,
)
def paper_texture(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    strength = float(params["strength"]) / 100.0
    if strength < 1e-4:
        return image

    rgb, alpha = _rgb_alpha(image)
    h, w = rgb.shape[:2]
    frame_h, frame_w, oy, ox = _frame_geometry(ctx, h, w)
    rng = ctx.rng("paper", int(params["seed"]), frame_w, frame_h)
    geom = {"frame": (frame_h, frame_w), "origin": (oy, ox)}
    scale = max(1.0, ctx.scaled(float(params["scale"])))

    # Iki oktav: kaba yuzey + ince lif
    coarse = _grain_field((h, w), scale * 2.6, rng, **geom)
    fine = _grain_field((h, w), max(1.0, scale * 0.8), rng, **geom)
    fibre = float(params["fibre"]) / 100.0

    # Lif: yatayda uzatilmis gurultu
    if fibre > 0.02:
        stretched = cv2.GaussianBlur(fine, (0, 0), sigmaX=scale * 1.8,
                                     sigmaY=scale * 0.25,
                                     borderType=cv2.BORDER_REFLECT)
        std = float(stretched.std())
        if std > 1e-6:
            stretched = stretched / std
        fine = fine * (1.0 - fibre) + stretched * fibre

    texture = (coarse * 0.6 + fine * 0.4)
    out = rgb + texture[..., None] * np.float32(strength * 0.055)

    warmth = float(params["warmth"]) / 100.0
    if abs(warmth) > 1e-3:
        tint = np.array([warmth * 0.018, warmth * 0.008, -warmth * 0.014],
                        dtype=np.float32).reshape(1, 1, 3)
        out = out + tint * np.float32(strength)

    result = px.join_alpha(out.astype(px.WORKING_DTYPE, copy=False), alpha)
    return apply_amount(image, result, params)

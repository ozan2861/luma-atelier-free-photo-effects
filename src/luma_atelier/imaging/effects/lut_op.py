"""3D LUT uygulama islemi ve kadraj (aspect) araci."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from luma_atelier.imaging import lut3d, pixels as px
from luma_atelier.imaging.effects.base import (
    Category,
    ParamKind,
    ParamSpec,
    RenderContext,
    operation,
)

log = logging.getLogger(__name__)

#: Yuklenmis LUT onbellegi. Ayni LUT her karede yeniden okunmaz.
_CACHE: dict[str, lut3d.Lut3D] = {}
#: Okunamayan dosyalar: her karede tekrar denenip gunluk doldurmasin.
_FAILED: set[str] = set()


def clear_lut_cache() -> None:
    _CACHE.clear()
    _FAILED.clear()


#: Tasinabilir kimlik onekleri. Preset ve proje dosyalarina **mutlak
#: yol yazilmaz**: kurulum klasoru degisince veya dosya baska bir
#: bilgisayarda acilinca mutlak yol kirilirdi.
BUILTIN_PREFIX = "builtin:"
USER_PREFIX = "user:"


def available_luts() -> list[tuple[str, str]]:
    """Kullanilabilir LUT'lar: (gorunen ad, kimlik).

    Kimlik ya "" (LUT yok), ya `builtin:ad`, ya `user:ad`, ya da
    kullanicinin dogrudan sectigi mutlak bir dosya yoludur. Yerlesik ve
    kullanici LUT'lari onekli kimlikle bildirilir ki presetler
    tasinabilir olsun.
    """
    from luma_atelier.core.paths import luts_user_dir, resources_dir

    out: list[tuple[str, str]] = [("LUT yok", "")]
    for folder, prefix in ((resources_dir() / "luts", BUILTIN_PREFIX),
                           (luts_user_dir(), USER_PREFIX)):
        try:
            for f in sorted(folder.glob("*.cube")):
                out.append((f.stem, f"{prefix}{f.stem}"))
        except OSError:
            continue
    return out


def resolve_lut_path(identifier: str) -> Path | None:
    """Kimligi gercek dosya yoluna cevirir.

    `builtin:` ve `user:` onekleri calisma anindaki klasorlere gore
    cozulur; boylece preset dosyasi kurulum konumundan bagimsizdir.
    """
    from luma_atelier.core.paths import luts_user_dir, resources_dir

    if not identifier:
        return None
    if identifier.startswith(BUILTIN_PREFIX):
        name = identifier[len(BUILTIN_PREFIX):]
        return resources_dir() / "luts" / f"{name}.cube"
    if identifier.startswith(USER_PREFIX):
        name = identifier[len(USER_PREFIX):]
        return luts_user_dir() / f"{name}.cube"
    return Path(identifier)


def _startup_luts() -> list[tuple[str, str]]:
    """Kayit aninda bulunan LUT'lar.

    Calisma sirasinda ice aktarilanlar `allow_free_choice` sayesinde
    kabul edilir; arayuz listeyi `available_luts()` ile tazeler.
    """
    try:
        return available_luts()
    except Exception:  # noqa: BLE001 - kayit hicbir kosulda cokmemeli
        return [("LUT yok", "")]


def get_lut(identifier: str) -> lut3d.Lut3D | None:
    """Kimlikten LUT dondurur; okunamazsa None (render cokmez)."""
    if not identifier:
        return None
    cached = _CACHE.get(identifier)
    if cached is not None:
        return cached
    if identifier in _FAILED:
        return None
    path = resolve_lut_path(identifier)
    if path is None:
        return None
    try:
        lut = lut3d.load_cube(path)
    except lut3d.LutError as exc:
        log.warning("LUT yüklenemedi (%s): %s", identifier, exc)
        _FAILED.add(identifier)
        return None
    _CACHE[identifier] = lut
    return lut


@operation(
    op_id="color.lut3d",
    name="3D LUT",
    description=(
        "İçe aktarılan .cube renk tablosunu uygular. Yaratıcı SDR/sRGB "
        "LUT'ları içindir; log kamera dönüşümü veya ACES desteği "
        "iddia edilmez. Kimlik LUT'u rengi bozmaz."
    ),
    category=Category.COLOR,
    params=(
        ParamSpec(key="lut", label="LUT dosyası", kind=ParamKind.CHOICE,
                  choices=tuple(_startup_luts()), default="",
                  allow_free_choice=True,
                  tooltip=(
                      "Yerleşik LUT'lardan seçin veya Sinema "
                      "Laboratuvarı'ndan kendi .cube dosyanızı içe aktarın."
                  )),
        ParamSpec(key="amount", label="Yoğunluk", minimum=0.0, maximum=100.0,
                  default=100.0, decimals=0, step=1.0, page_step=10.0,
                  suffix=" %", bipolar=False),
    ),
    order_hint=37,
    supports_amount=False,
    color_space="sRGB",
    performance_note="Trilineer interpolasyon; 2 MP'de ~45 ms",
)
def lut_operation(image: np.ndarray, params: dict[str, Any],
                  ctx: RenderContext) -> np.ndarray:
    identifier = str(params.get("lut") or "")
    amount = float(params["amount"]) / 100.0
    if not identifier or amount < 1e-4:
        return image
    lut = get_lut(identifier)
    if lut is None:
        return image           # okunamayan LUT sessizce atlanir, gunluge yazildi
    return lut3d.apply_lut3d(image, lut, amount)


# ==================================================================== KADRAJ
#: Sinema kadraj oranlari. Deger: genislik/yukseklik
ASPECT_RATIOS: tuple[tuple[str, float], ...] = (
    ("2.39:1 (anamorfik)", 2.39),
    ("2.00:1", 2.00),
    ("1.85:1 (sinema)", 1.85),
    ("16:9", 16 / 9),
    ("3:2", 1.5),
    ("4:3", 4 / 3),
    ("1:1 (kare)", 1.0),
    ("4:5 (dikey)", 0.8),
)


@operation(
    op_id="geometry.letterbox",
    name="Sinema kadrajı",
    description=(
        "Seçilen orana siyah bant ekler (letterbox). Bu işlem görüntüye "
        "*gerçekten* bant yazar ve çıktıya işlenir. Yalnızca rehber "
        "çizgisi görmek istiyorsanız tuvaldeki kadraj rehberini "
        "kullanın; rehber çıktıya işlenmez."
    ),
    category=Category.GEOMETRY,
    params=(
        ParamSpec(key="ratio", label="Oran", kind=ParamKind.CHOICE,
                  choices=tuple((label, value) for label, value in ASPECT_RATIOS),
                  default=2.39),
        ParamSpec(key="mode", label="Biçim", kind=ParamKind.CHOICE,
                  choices=(("Siyah bant ekle", "bars"),
                           ("Gerçekten kirp", "crop")),
                  default="bars",
                  tooltip=(
                      "Bant ekleme görüntü boyutunu korur; kırpma "
                      "görüntüyü küçültür."
                  )),
        ParamSpec(key="bar_color", label="Bant rengi", kind=ParamKind.COLOR,
                  default=(0.0, 0.0, 0.0)),
        ParamSpec(key="enabled", label="Uygula", kind=ParamKind.BOOLEAN,
                  default=False),
    ),
    order_hint=95,
    supports_amount=False,
    supports_mask=False,
    color_space="sRGB",
    changes_size=True,
)
def letterbox(image: np.ndarray, params: dict[str, Any],
              ctx: RenderContext) -> np.ndarray:
    if not bool(params.get("enabled", False)):
        return image

    rgb, alpha = px.split_alpha(image)
    h, w = rgb.shape[:2]
    target = float(params["ratio"])
    current = w / max(1.0, float(h))
    if abs(current - target) < 1e-3:
        return image

    mode = params.get("mode", "bars")
    if mode == "crop":
        if current > target:
            new_w = int(round(h * target))
            x0 = max(0, (w - new_w) // 2)
            out = rgb[:, x0:x0 + new_w]
            a = alpha[:, x0:x0 + new_w] if alpha is not None else None
        else:
            new_h = int(round(w / target))
            y0 = max(0, (h - new_h) // 2)
            out = rgb[y0:y0 + new_h]
            a = alpha[y0:y0 + new_h] if alpha is not None else None
        return px.join_alpha(np.ascontiguousarray(out),
                             np.ascontiguousarray(a) if a is not None else None)

    # Bant ekleme: boyut korunur, disari kalan alan doldurulur
    colour = np.asarray(params["bar_color"], np.float32).reshape(1, 1, 3)
    out = rgb.copy()
    if current > target:
        keep = int(round(h * target))
        pad = max(0, (w - keep) // 2)
        if pad:
            out[:, :pad] = colour
            out[:, w - pad:] = colour
    else:
        keep = int(round(w / target))
        pad = max(0, (h - keep) // 2)
        if pad:
            out[:pad, :] = colour
            out[h - pad:, :] = colour
    return px.join_alpha(out, alpha)

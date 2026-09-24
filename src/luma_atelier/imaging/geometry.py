"""Kirpma, dondurme, cevirme ve ufuk duzeltme.

Geometri, efekt yiginindan **ayri** tutulur ve her zaman ilk uygulanir.
Nedeni: kirpma goruntu boyutunu degistirir; yigin ortasinda boyut
degisikligi maskeleri, detay karosunu ve onizleme/tam boy eslemesini
bozar. Ayri bir asama olarak tutmak bunlarin hepsini basitlestirir.

Koordinatlar **normalize** saklanir (0..1). Bu sayede ayni kirpma hem
onizlemede hem tam boyda ayni yeri gosterir.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import cv2
import numpy as np

from luma_atelier.imaging import pixels as px

#: Yaygin en-boy oranlari (gereksinim belgesi Bolum 6)
ASPECT_PRESETS: tuple[tuple[str, float | None], ...] = (
    ("Serbest", None),
    ("Orijinal", 0.0),          # 0.0 = kaynak orani
    ("1:1", 1.0),
    ("4:5", 0.8),
    ("3:2", 1.5),
    ("2:3", 2 / 3),
    ("16:9", 16 / 9),
    ("9:16", 9 / 16),
    ("2.39:1", 2.39),
)


@dataclass(frozen=True)
class Geometry:
    """Kirpma ve yonelim durumu.

    `crop` normalize (x, y, genislik, yukseklik); tam kadraj (0,0,1,1).
    `rotation` 90 derecelik adimlar, `straighten` ufuk duzeltme acisi.
    """

    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    rotation: int = 0
    flip_h: bool = False
    flip_v: bool = False
    straighten: float = 0.0
    aspect: float | None = None
    """Kilitli en-boy orani; None serbest."""

    @property
    def is_identity(self) -> bool:
        return (self.crop == (0.0, 0.0, 1.0, 1.0)
                and self.rotation % 360 == 0
                and not self.flip_h and not self.flip_v
                and abs(self.straighten) < 1e-4)

    def output_size(self, width: int, height: int) -> tuple[int, int]:
        """Bu geometriyle uretilecek cikti boyutu.

        `apply` ile **ayni aritmetigi** kullanir: once dondurme, sonra
        kirpma, ve kirpma iki kenari ayri ayri yuvarlar. Uzunluk uzerinden
        yuvarlamak tek piksel sapma yaratir ve "cikti: X x Y" etiketini
        yanlis gosterirdi.

        Not: ufuk duzeltme bu hesaba girmez; acisal kirpma yalnizca
        gercek dizi uzerinde belirlenebilir.
        """
        w, h = width, height
        if (self.rotation // 90) % 2 == 1:
            w, h = h, w
        x0, x1 = _crop_edges(self.crop[0], self.crop[2], w)
        y0, y1 = _crop_edges(self.crop[1], self.crop[3], h)
        return (x1 - x0, y1 - y0)

    def apply(self, image: np.ndarray) -> np.ndarray:
        """Geometriyi goruntuye uygular."""
        if self.is_identity:
            return image

        out = image
        # 1) Ufuk duzeltme - en once, bos koseler sonraki kirpmayla gitsin
        if abs(self.straighten) > 1e-4:
            out = _rotate_free(out, self.straighten)

        # 2) Cevirme
        if self.flip_h:
            out = out[:, ::-1]
        if self.flip_v:
            out = out[::-1, :]

        # 3) 90 derecelik dondurme
        steps = (self.rotation // 90) % 4
        if steps:
            out = np.rot90(out, k=-steps)

        # 4) Kirpma - **en son**. Kirpma koordinatlari kullanicinin
        #    ekranda gordugu (dondurulmus, cevrilmis) kadrajdadir.
        out = crop_array(out, self.crop)
        return np.ascontiguousarray(out)

    # ---------------------------------------------------------- degisim
    def with_crop(self, crop: tuple[float, float, float, float]) -> Geometry:
        x, y, w, h = crop
        x = float(np.clip(x, 0.0, 0.999))
        y = float(np.clip(y, 0.0, 0.999))
        w = float(np.clip(w, 0.001, 1.0 - x))
        h = float(np.clip(h, 0.001, 1.0 - y))
        return replace(self, crop=(x, y, w, h))

    def rotated(self, degrees: int) -> Geometry:
        """90 derecelik adimlarla dondurur ve **kirpmayi da dondurur**.

        Kirpma en son uygulandigi icin dondurulmezse ayni sayilar baska
        bir bolgeyi gosterirdi; kullanici kadrajin icerigiyle birlikte
        donmesini bekler.
        """
        steps = ((degrees // 90) % 4 + 4) % 4
        crop = self.crop
        for _ in range(steps):
            x, y, w, h = crop
            crop = (1.0 - y - h, x, h, w)   # saat yonunde 90
        aspect = self.aspect
        if aspect is not None and aspect > 0 and steps % 2 == 1:
            aspect = 1.0 / aspect
        return replace(self, rotation=(self.rotation + degrees) % 360,
                       crop=crop, aspect=aspect)

    def reset(self) -> Geometry:
        return Geometry()

    # ----------------------------------------------------- serilestirme
    def to_dict(self) -> dict[str, Any]:
        return {
            "crop": list(self.crop),
            "rotation": self.rotation,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "straighten": self.straighten,
            "aspect": self.aspect,
        }

    @staticmethod
    def from_dict(data: Any) -> Geometry:
        if not isinstance(data, dict):
            return Geometry()
        crop = data.get("crop", [0.0, 0.0, 1.0, 1.0])
        try:
            x, y, w, h = (float(v) for v in crop)
        except (TypeError, ValueError):
            x, y, w, h = 0.0, 0.0, 1.0, 1.0
        if not all(np.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
            x, y, w, h = 0.0, 0.0, 1.0, 1.0

        try:
            rotation = int(data.get("rotation", 0)) % 360
        except (TypeError, ValueError):
            rotation = 0
        rotation = (rotation // 90) * 90

        try:
            straighten = float(data.get("straighten", 0.0))
        except (TypeError, ValueError):
            straighten = 0.0
        if not np.isfinite(straighten):
            straighten = 0.0

        aspect = data.get("aspect")
        try:
            aspect = float(aspect) if aspect is not None else None
        except (TypeError, ValueError):
            aspect = None

        return Geometry(
            crop=(float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1)),
                  float(np.clip(w, 0.001, 1)), float(np.clip(h, 0.001, 1))),
            rotation=rotation,
            flip_h=bool(data.get("flip_h", False)),
            flip_v=bool(data.get("flip_v", False)),
            straighten=float(np.clip(straighten, -45.0, 45.0)),
            aspect=aspect,
        )



def _crop_edges(start: float, length: float, extent: int) -> tuple[int, int]:
    """Normalize kirpmayi piksel kenarlarina cevirir.

    Sonuc her zaman en az 1 piksel genisligindedir ve diziyi asmaz;
    boylece kirpma hicbir girdide bos dizi uretemez.
    """
    if extent <= 1:
        return (0, max(1, extent))
    lo = int(round(float(np.clip(start, 0.0, 1.0)) * extent))
    hi = int(round(float(np.clip(start + length, 0.0, 1.0)) * extent))
    lo = min(lo, extent - 1)
    hi = min(extent, max(lo + 1, hi))
    return (lo, hi)


def crop_array(image: np.ndarray,
               crop: tuple[float, float, float, float]) -> np.ndarray:
    """Normalize kirpmayi diziye uygular. Tam kadrajda diziyi aynen doner."""
    x, y, cw, ch = crop
    if (x, y, cw, ch) == (0.0, 0.0, 1.0, 1.0):
        return image
    h, w = image.shape[:2]
    x0, x1 = _crop_edges(x, cw, w)
    y0, y1 = _crop_edges(y, ch, h)
    return image[y0:y1, x0:x1]

def _rotate_free(image: np.ndarray, degrees: float) -> np.ndarray:
    """Serbest acida dondurur ve bos koseleri kirpar.

    Dondurme sonrasi kalan bos koseler goruntuye dahil edilmez; en buyuk
    ic dikdortgen hesaplanip kirpilir. Boylece kullanici siyah ucgenler
    gormez.
    """
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), degrees, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)

    # En buyuk ic dikdortgen (donmus dikdortgen icine sigan)
    rad = abs(np.radians(degrees))
    cos_a, sin_a = abs(np.cos(rad)), abs(np.sin(rad))
    if w <= 0 or h <= 0:
        return rotated
    long_side, short_side = (w, h) if w >= h else (h, w)
    if short_side <= 2 * sin_a * cos_a * long_side or abs(cos_a - sin_a) < 1e-9:
        x = 0.5 * short_side
        wr, hr = (x / sin_a, x / cos_a) if w >= h else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr = (w * cos_a - h * sin_a) / cos_2a
        hr = (h * cos_a - w * sin_a) / cos_2a

    wr = int(max(1, min(w, wr)))
    hr = int(max(1, min(h, hr)))
    x0 = (w - wr) // 2
    y0 = (h - hr) // 2
    return np.ascontiguousarray(rotated[y0:y0 + hr, x0:x0 + wr])


def fit_crop_to_aspect(crop: tuple[float, float, float, float],
                       aspect: float, image_aspect: float
                       ) -> tuple[float, float, float, float]:
    """Kirpma dikdortgenini istenen en-boy oranina uyarlar.

    `aspect` cikti genislik/yukseklik, `image_aspect` kaynak orani.
    Merkez korunur, dikdortgen kadrajin disina tasmaz.
    """
    x, y, w, h = crop
    cx, cy = x + w / 2.0, y + h / 2.0
    # Normalize koordinatlarda oran, kaynak oranina gore duzeltilir
    target = aspect / max(1e-6, image_aspect)
    if w / max(1e-6, h) > target:
        w = h * target
    else:
        h = w / max(1e-6, target)
    w = min(w, 1.0)
    h = min(h, 1.0)
    x = float(np.clip(cx - w / 2.0, 0.0, 1.0 - w))
    y = float(np.clip(cy - h / 2.0, 0.0, 1.0 - h))
    return (x, y, w, h)

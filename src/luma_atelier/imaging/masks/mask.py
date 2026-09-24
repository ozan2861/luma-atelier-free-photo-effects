"""Yerel maskeler: fircadan renk araligina.

Koordinat sozlesmesi
--------------------
Maske verisi **daima goruntu uzayinda** saklanir ve `0..1` normalize
koordinatlar kullanir. Boylece:

* Zoom/pan maskeyi kaydirmaz (tuval yalnizca cizim donusumunu degistirir).
* Onizleme ve tam boy render ayni maskeyi uretir; yalnizca hedef
  cozunurluk degisir.
* Kirpma/dondurme sonrasi maske `transform()` ile birlikte tasinir.

Firca maskesi bir *vuruslar* listesi olarak saklanir, piksel dizisi
olarak degil: boylece proje dosyasi kucuk kalir, cozunurluk bagimsizdir
ve kirpma/dondurme sonrasi yeniden hesaplanabilir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

import cv2
import numpy as np

from luma_atelier.imaging import pixels as px

log = logging.getLogger(__name__)

#: Maske yumusatmasinin en kucuk sigma degeri
MIN_FEATHER = 0.4


class MaskKind(str, Enum):
    """Maske turleri."""

    BRUSH = "brush"
    LINEAR = "linear"
    RADIAL = "radial"
    LUMINANCE = "luminance"
    COLOR_RANGE = "color_range"

    @property
    def label(self) -> str:
        return {
            MaskKind.BRUSH: "Fırça",
            MaskKind.LINEAR: "Doğrusal gradyan",
            MaskKind.RADIAL: "Radyal gradyan",
            MaskKind.LUMINANCE: "Parlaklık aralığı",
            MaskKind.COLOR_RANGE: "Renk aralığı",
        }[self]


class BlendOp(str, Enum):
    """Maskelerin birlesme bicimi."""

    ADD = "add"        # birlestir (union)
    SUBTRACT = "sub"   # cikar

    @property
    def label(self) -> str:
        return "Ekle" if self is BlendOp.ADD else "Çıkar"


@dataclass(frozen=True)
class BrushStroke:
    """Tek bir firca vurusu.

    Noktalar 0..1 normalize goruntu koordinatlaridir. `radius` goruntu
    genisliginin orani olarak saklanir; boylece cozunurlukten bagimsiz.
    """

    points: tuple[tuple[float, float], ...]
    radius: float = 0.05
    hardness: float = 0.5
    flow: float = 1.0
    erase: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [list(p) for p in self.points],
            "radius": self.radius,
            "hardness": self.hardness,
            "flow": self.flow,
            "erase": self.erase,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> BrushStroke:
        raw = data.get("points", [])
        points: list[tuple[float, float]] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                x, y = float(item[0]), float(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if np.isfinite(x) and np.isfinite(y):
                points.append((x, y))
        return BrushStroke(
            points=tuple(points),
            radius=_clamped(data.get("radius"), 0.002, 0.6, 0.05),
            hardness=_clamped(data.get("hardness"), 0.0, 1.0, 0.5),
            flow=_clamped(data.get("flow"), 0.0, 1.0, 1.0),
            erase=bool(data.get("erase", False)),
        )



def _grid(h: int, w: int,
          geom: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Islenen bolgenin (yy, xx) izgarasi, **tam kadraj** pikselinde.

    `geom` = (ox, oy, frame_w, frame_h). Karo disinda ox=oy=0 ve
    frame boyutu islenen boyutla ayni oldugu icin sonuc degismez.
    """
    ox, oy, _fw, _fh = geom
    yy, xx = np.mgrid[oy:oy + h, ox:ox + w]
    return yy.astype(np.float32), xx.astype(np.float32)

def _clamped(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(v):
        return default
    return min(hi, max(lo, v))


@dataclass(frozen=True)
class Mask:
    """Tek bir maske tanimi.

    Degismezdir; her duzenleme yeni bir Mask dondurur (tarif gibi).
    """

    mask_id: str
    kind: MaskKind = MaskKind.BRUSH
    label: str = ""
    inverted: bool = False
    feather: float = 0.02
    """Kenar yumusakligi, goruntu genisliginin orani."""
    opacity: float = 1.0
    blend: BlendOp = BlendOp.ADD
    enabled: bool = True

    # --- firca ---
    strokes: tuple[BrushStroke, ...] = ()

    # --- dogrusal gradyan ---
    start: tuple[float, float] = (0.5, 0.0)
    end: tuple[float, float] = (0.5, 1.0)

    # --- radyal gradyan ---
    center: tuple[float, float] = (0.5, 0.5)
    radius: tuple[float, float] = (0.35, 0.35)
    angle: float = 0.0

    # --- parlaklik araligi ---
    luma_low: float = 0.0
    luma_high: float = 1.0
    luma_softness: float = 0.15

    # --- renk araligi ---
    target_color: tuple[float, float, float] = (0.8, 0.4, 0.3)
    hue_tolerance: float = 30.0
    sat_tolerance: float = 0.45

    @property
    def display_name(self) -> str:
        return self.label or self.kind.label

    # ------------------------------------------------------------ uretim
    def render(self, shape: tuple[int, int],
               image: np.ndarray | None = None, *,
               origin: tuple[int, int] = (0, 0),
               frame: tuple[int, int] | None = None) -> np.ndarray:
        """Maskeyi verilen cozunurlukte float32 (Y, X) olarak uretir.

        `image` yalnizca parlaklik ve renk araligi maskeleri icin gerekir.
        Deger araligi 0..1; 1 tam etki demektir.

        `origin` ve `frame` yalnizca **karo** render'inda kullanilir:
        maske gecmisi tam kadrajin normalize uzayinda tanimlidir, karo
        ise kadrajin bir parcasidir. Verilmezse islenen dizi tam kadraj
        kabul edilir.
        """
        h, w = shape
        if h <= 0 or w <= 0:
            return np.zeros((max(1, h), max(1, w)), np.float32)

        frame_w, frame_h = frame if frame is not None else (w, h)
        geom = (origin[0], origin[1], frame_w, frame_h)
        if self.kind is MaskKind.BRUSH:
            mask = self._render_brush(h, w, geom)
        elif self.kind is MaskKind.LINEAR:
            mask = self._render_linear(h, w, geom)
        elif self.kind is MaskKind.RADIAL:
            mask = self._render_radial(h, w, geom)
        elif self.kind is MaskKind.LUMINANCE:
            mask = self._render_luminance(h, w, image)
        elif self.kind is MaskKind.COLOR_RANGE:
            mask = self._render_color_range(h, w, image)
        else:
            mask = np.ones((h, w), np.float32)

        if self.feather > 1e-4 and self.kind is not MaskKind.BRUSH:
            # Yumusatma kadraj genisligine gore; karoda daha dar olmamali
            sigma = max(MIN_FEATHER, self.feather * frame_w * 0.5)
            mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma,
                                    borderType=cv2.BORDER_REPLICATE)

        if self.inverted:
            mask = 1.0 - mask
        if self.opacity < 1.0:
            mask = mask * np.float32(max(0.0, self.opacity))
        return np.clip(mask, 0.0, 1.0).astype(px.WORKING_DTYPE, copy=False)

    def _render_brush(self, h: int, w: int,
                      geom: tuple[int, int, int, int]) -> np.ndarray:
        ox, oy, frame_w, frame_h = geom
        mask = np.zeros((h, w), np.float32)
        for stroke in self.strokes:
            if len(stroke.points) == 0:
                continue
            layer = np.zeros((h, w), np.float32)
            radius_px = max(1.0, stroke.radius * frame_w)
            thickness = max(1, int(round(radius_px * 2)))
            # Noktalar kadraj pikseline cevrilir, sonra karo kaydirilir
            pts = [(int(round(x * frame_w)) - ox, int(round(y * frame_h)) - oy)
                   for x, y in stroke.points]
            if len(pts) == 1:
                cv2.circle(layer, pts[0], max(1, int(radius_px)), 1.0, -1,
                           lineType=cv2.LINE_AA)
            else:
                cv2.polylines(layer, [np.array(pts, np.int32)], False, 1.0,
                              thickness, lineType=cv2.LINE_AA)
            # Sertlik: 1 keskin kenar, 0 tamamen yumusak
            softness = (1.0 - stroke.hardness) * radius_px * 0.8
            if softness > MIN_FEATHER:
                layer = cv2.GaussianBlur(layer, (0, 0), sigmaX=softness,
                                         borderType=cv2.BORDER_REPLICATE)
            layer *= np.float32(stroke.flow)
            if stroke.erase:
                mask = np.clip(mask - layer, 0.0, 1.0)
            else:
                # Uzerine binen vuruslar toplanmaz, en yuksek deger alinir;
                # aksi halde ayni yerden iki kez gecmek sert leke yapardi.
                mask = np.maximum(mask, layer)
        return mask

    def _render_linear(self, h: int, w: int,
                       geom: tuple[int, int, int, int]) -> np.ndarray:
        _ox, _oy, frame_w, frame_h = geom
        yy, xx = _grid(h, w, geom)
        x0, y0 = self.start[0] * frame_w, self.start[1] * frame_h
        x1, y1 = self.end[0] * frame_w, self.end[1] * frame_h
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-6:
            return np.ones((h, w), np.float32)
        t = ((xx - x0) * dx + (yy - y0) * dy) / length_sq
        t = np.clip(t, 0.0, 1.0)
        return (t * t * (3.0 - 2.0 * t)).astype(np.float32)   # smoothstep

    def _render_radial(self, h: int, w: int,
                       geom: tuple[int, int, int, int]) -> np.ndarray:
        _ox, _oy, frame_w, frame_h = geom
        yy, xx = _grid(h, w, geom)
        cx, cy = self.center[0] * frame_w, self.center[1] * frame_h
        rx = max(1.0, self.radius[0] * frame_w)
        ry = max(1.0, self.radius[1] * frame_h)
        theta = np.radians(self.angle, dtype=np.float32)
        cos_a, sin_a = np.float32(np.cos(theta)), np.float32(np.sin(theta))
        px_ = (xx - cx) * cos_a + (yy - cy) * sin_a
        py_ = -(xx - cx) * sin_a + (yy - cy) * cos_a
        dist = np.sqrt((px_ / rx) ** 2 + (py_ / ry) ** 2)
        t = np.clip(1.0 - dist, 0.0, 1.0)
        return (t * t * (3.0 - 2.0 * t)).astype(np.float32)

    def _render_luminance(self, h: int, w: int,
                          image: np.ndarray | None) -> np.ndarray:
        if image is None:
            return np.ones((h, w), np.float32)
        luma = np.clip(px.luminance(image[..., :3]), 0.0, 1.0)
        if luma.shape != (h, w):
            luma = cv2.resize(luma, (w, h), interpolation=cv2.INTER_LINEAR)
        lo, hi = min(self.luma_low, self.luma_high), max(self.luma_low,
                                                         self.luma_high)
        soft = max(1e-3, self.luma_softness)
        rising = np.clip((luma - (lo - soft)) / soft, 0.0, 1.0)
        falling = np.clip(((hi + soft) - luma) / soft, 0.0, 1.0)
        mask = np.minimum(rising, falling)
        return (mask * mask * (3.0 - 2.0 * mask)).astype(np.float32)

    def _render_color_range(self, h: int, w: int,
                            image: np.ndarray | None) -> np.ndarray:
        if image is None:
            return np.ones((h, w), np.float32)
        rgb = image[..., :3]
        if rgb.shape[:2] != (h, w):
            rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
        src = np.ascontiguousarray(np.clip(rgb, 0.0, 1.0), np.float32)
        hsv = cv2.cvtColor(src, cv2.COLOR_RGB2HSV)
        target = np.asarray(self.target_color, np.float32).reshape(1, 1, 3)
        t_hsv = cv2.cvtColor(np.clip(target, 0, 1), cv2.COLOR_RGB2HSV)[0, 0]

        hue_diff = np.abs(hsv[..., 0] - float(t_hsv[0]))
        hue_diff = np.minimum(hue_diff, 360.0 - hue_diff)
        hue_weight = np.clip(1.0 - hue_diff / max(1.0, self.hue_tolerance),
                             0.0, 1.0)
        sat_diff = np.abs(hsv[..., 1] - float(t_hsv[1]))
        sat_weight = np.clip(1.0 - sat_diff / max(1e-3, self.sat_tolerance),
                             0.0, 1.0)
        # Gri piksellerde ton anlamsizdir
        colourful = np.clip(hsv[..., 1] * 3.0, 0.0, 1.0)
        mask = hue_weight * sat_weight * colourful
        return (mask * mask * (3.0 - 2.0 * mask)).astype(np.float32)

    # ---------------------------------------------------------- donusum
    def transformed(self, crop: tuple[float, float, float, float] | None = None,
                    *, rotation: int = 0, flip_h: bool = False,
                    flip_v: bool = False) -> Mask:
        """Kirpma/dondurme sonrasi maskeyi yeni kadraja tasir.

        `crop` normalize (x, y, w, h). Gereksinim: "Kirpma/dondurme
        sonrasi maskeler dogru donusumu izlesin."
        """
        # Sira `Geometry.apply` ile **ayni** olmali: cevir, dondur, kirp.
        # Farkli olursa maske kirpma sonrasi yanlis yere duser.
        mask = self
        if flip_h:
            mask = mask._map_points(lambda x, y: (1.0 - x, y))
        if flip_v:
            mask = mask._map_points(lambda x, y: (x, 1.0 - y))

        steps = (rotation // 90) % 4
        for _ in range(steps):
            # Saat yonunde 90: (x, y) -> (1 - y, x)
            mask = mask._map_points(lambda x, y: (1.0 - y, x), swap_axes=True)

        if crop is not None:
            cx, cy, cw, ch = crop
            if cw > 1e-6 and ch > 1e-6:
                mask = mask._map_points(
                    lambda x, y: ((x - cx) / cw, (y - cy) / ch),
                    scale_x=1.0 / cw, scale_y=1.0 / ch,
                )
        return mask

    def _map_points(self, fn, *, scale_x: float = 1.0,  # noqa: ANN001
                    scale_y: float = 1.0, swap_axes: bool = False) -> Mask:
        strokes = tuple(
            replace(s, points=tuple(fn(x, y) for x, y in s.points),
                    radius=s.radius * (scale_y if swap_axes else scale_x))
            for s in self.strokes
        )
        rx, ry = self.radius
        if swap_axes:
            rx, ry = ry, rx
        return replace(
            self, strokes=strokes,
            start=fn(*self.start), end=fn(*self.end),
            center=fn(*self.center),
            radius=(rx * scale_x, ry * scale_y),
        )

    # ------------------------------------------------------ serilestirme
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.mask_id,
            "kind": self.kind.value,
            "label": self.label,
            "inverted": self.inverted,
            "feather": self.feather,
            "opacity": self.opacity,
            "blend": self.blend.value,
            "enabled": self.enabled,
        }
        # Konum alanlari **her zaman** yazilir, maskenin turu ne olursa
        # olsun. Nedeni: `transformed()` kirpma/dondurme sonrasi tum
        # konumlari yeni kadraja tasir. Yalnizca turun kullandigi alani
        # kaydetmek, projeyi acinca digerlerini varsayilana dondururdu;
        # kullanici maskenin turunu sonradan degistirdiginde gradyan
        # eski kadrajin yerini gosterirdi. Alti sayi, ihmal edilebilir.
        data["start"] = list(self.start)
        data["end"] = list(self.end)
        data["center"] = list(self.center)
        data["radius"] = list(self.radius)
        data["angle"] = self.angle

        if self.kind is MaskKind.BRUSH:
            data["strokes"] = [s.to_dict() for s in self.strokes]
        elif self.kind is MaskKind.LUMINANCE:
            data["luma_low"] = self.luma_low
            data["luma_high"] = self.luma_high
            data["luma_softness"] = self.luma_softness
        elif self.kind is MaskKind.COLOR_RANGE:
            data["target_color"] = list(self.target_color)
            data["hue_tolerance"] = self.hue_tolerance
            data["sat_tolerance"] = self.sat_tolerance
        return data

    @staticmethod
    def from_dict(data: Any) -> Mask:
        """Sozlukten maske okur. Gecersiz veri varsayilana duser."""
        if not isinstance(data, dict):
            raise ValueError("Maske verisi sozluk olmali")
        try:
            kind = MaskKind(str(data.get("kind", "brush")))
        except ValueError:
            log.info("Bilinmeyen maske turu, firca varsayildi: %s",
                     data.get("kind"))
            kind = MaskKind.BRUSH
        try:
            blend = BlendOp(str(data.get("blend", "add")))
        except ValueError:
            blend = BlendOp.ADD

        raw_strokes = data.get("strokes", [])
        strokes = tuple(
            BrushStroke.from_dict(s) for s in raw_strokes
            if isinstance(s, dict)
        ) if isinstance(raw_strokes, list) else ()

        return Mask(
            mask_id=str(data.get("id") or "mask"),
            kind=kind,
            label=str(data.get("label", "")),
            inverted=bool(data.get("inverted", False)),
            feather=_clamped(data.get("feather"), 0.0, 0.5, 0.02),
            opacity=_clamped(data.get("opacity"), 0.0, 1.0, 1.0),
            blend=blend,
            enabled=bool(data.get("enabled", True)),
            strokes=strokes,
            start=_point(data.get("start"), (0.5, 0.0)),
            end=_point(data.get("end"), (0.5, 1.0)),
            center=_point(data.get("center"), (0.5, 0.5)),
            radius=_point(data.get("radius"), (0.35, 0.35)),
            angle=_clamped(data.get("angle"), -180.0, 180.0, 0.0),
            luma_low=_clamped(data.get("luma_low"), 0.0, 1.0, 0.0),
            luma_high=_clamped(data.get("luma_high"), 0.0, 1.0, 1.0),
            luma_softness=_clamped(data.get("luma_softness"), 0.001, 0.5, 0.15),
            target_color=_colour(data.get("target_color"), (0.8, 0.4, 0.3)),
            hue_tolerance=_clamped(data.get("hue_tolerance"), 1.0, 180.0, 30.0),
            sat_tolerance=_clamped(data.get("sat_tolerance"), 0.01, 1.0, 0.45),
        )


def _point(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError, IndexError):
        return default


def _colour(value: Any,
            default: tuple[float, float, float]) -> tuple[float, float, float]:
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError, IndexError):
        return default


@dataclass(frozen=True)
class MaskStack:
    """Bir katmana bagli maskelerin birlesimi."""

    masks: tuple[Mask, ...] = ()

    def __len__(self) -> int:
        return len(self.masks)

    @property
    def is_empty(self) -> bool:
        return not any(m.enabled for m in self.masks)

    def render(self, shape: tuple[int, int],
               image: np.ndarray | None = None, *,
               origin: tuple[int, int] = (0, 0),
               frame: tuple[int, int] | None = None) -> np.ndarray | None:
        """Tum maskeleri birlestirip tek maske dondurur.

        Hicbir etkin maske yoksa None doner; cagiran katman maskesiz
        uygular (ek hesap yapilmaz).
        """
        active = [m for m in self.masks if m.enabled]
        if not active:
            return None
        h, w = shape
        result = np.zeros((h, w), np.float32)
        first = True
        for mask in active:
            layer = mask.render(shape, image, origin=origin, frame=frame)
            if first and mask.blend is BlendOp.SUBTRACT:
                # Ilk maske cikarma ise tabandan baslanir
                result = np.ones((h, w), np.float32)
            first = False
            if mask.blend is BlendOp.ADD:
                result = np.maximum(result, layer)
            else:
                result = np.clip(result - layer, 0.0, 1.0)
        return result

    def to_dict(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.masks]

    @staticmethod
    def from_list(data: Any) -> MaskStack:
        if not isinstance(data, list):
            return MaskStack()
        masks = []
        for entry in data:
            try:
                masks.append(Mask.from_dict(entry))
            except ValueError as exc:
                log.warning("Maske okunamadı, atlandı: %s", exc)
        return MaskStack(masks=tuple(masks))


def apply_masked(original: np.ndarray, processed: np.ndarray,
                 mask: np.ndarray | None) -> np.ndarray:
    """Islenmis goruntuyu maskeye gore orijinalle karistirir."""
    if mask is None:
        return processed
    m = mask[..., None].astype(px.WORKING_DTYPE, copy=False)
    return (original + (processed - original) * m).astype(
        px.WORKING_DTYPE, copy=False
    )

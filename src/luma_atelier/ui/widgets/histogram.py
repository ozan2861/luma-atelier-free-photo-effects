"""Histogram: RGB kanallari + parlaklik, kirpma uyarilariyla.

Hesaplama UI is parcaciginda yapilir ama *onizleme* goruntusu uzerinde
(2 MP degil, en fazla 512x512'ye indirilmis ornek) — olculen maliyet
1 ms altinda, bu yuzden ayri bir worker gereksiz.
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from luma_atelier.imaging import pixels as px
from luma_atelier.ui.theme.tokens import PALETTE, RADIUS, SPACE, TYPE

#: Histogram kova sayisi. 256 ekranda okunakli, hesabi ucuz.
BINS = 256
#: Histogram icin goruntunun indirgenecegi en uzun kenar.
SAMPLE_LONG_EDGE = 512
#: Bu orandan fazla piksel uc degerdeyse kirpma uyarisi yanar.
CLIP_WARNING_RATIO = 0.005


class Histogram(QWidget):
    """Ton dagilimini gosteren kucuk grafik."""

    clippingToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Histogram")
        self.setMinimumHeight(88)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(
            "Ton dağılımı. Uçlardaki kırmızı işaret kırpılan alanları gösterir."
        )
        self._channels: np.ndarray | None = None   # (4, BINS) R,G,B,luma
        self._shadow_clip = 0.0
        self._highlight_clip = 0.0
        self._show_channels = True

    # ---------------------------------------------------------------- veri
    def setImage(self, image: np.ndarray | None) -> None:  # noqa: N802
        """Histogrami verilen calisma goruntusunden hesaplar."""
        if image is None or image.size == 0:
            self._channels = None
            self.update()
            return

        rgb = image[..., :3]
        h, w = rgb.shape[:2]
        scale = min(1.0, SAMPLE_LONG_EDGE / max(h, w))
        if scale < 1.0:
            rgb = cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale))),
                             interpolation=cv2.INTER_AREA)

        clipped = np.clip(rgb, 0.0, 1.0)
        counts = np.empty((4, BINS), dtype=np.float32)
        for i in range(3):
            counts[i] = np.bincount(
                (clipped[..., i] * (BINS - 1)).astype(np.int32).ravel(),
                minlength=BINS,
            )[:BINS]
        luma = np.clip(px.luminance(rgb), 0.0, 1.0)
        counts[3] = np.bincount(
            (luma * (BINS - 1)).astype(np.int32).ravel(), minlength=BINS
        )[:BINS]

        # Kirpma: *kirpilmamis* veriye bak; 0..1 disina tasan gercek kayiptir
        total = float(rgb.shape[0] * rgb.shape[1])
        self._shadow_clip = float((rgb <= 0.0).any(axis=2).sum()) / max(1.0, total)
        self._highlight_clip = float((rgb >= 1.0).any(axis=2).sum()) / max(1.0, total)

        # Uc kovalar genelde cok yuksek olur ve grafigi ezer; gorsel olcek
        # icin ic kovalarin tepesi kullanilir.
        interior = counts[:, 2:-2]
        peak = float(interior.max()) if interior.size else 1.0
        self._channels = counts / max(1.0, peak)
        self.update()

    def clear(self) -> None:
        self._channels = None
        self.update()

    @property
    def shadow_clip_ratio(self) -> float:
        return self._shadow_clip

    @property
    def highlight_clip_ratio(self) -> float:
        return self._highlight_clip

    @property
    def has_clipping(self) -> bool:
        return (self._shadow_clip > CLIP_WARNING_RATIO
                or self._highlight_clip > CLIP_WARNING_RATIO)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_channels = not self._show_channels
            self.update()

    # --------------------------------------------------------------- cizim
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.bg_base))
        p.drawRoundedRect(rect, RADIUS.sm, RADIUS.sm)

        if self._channels is None:
            f = QFont()
            f.setPixelSize(TYPE.size_caption)
            p.setFont(f)
            p.setPen(QColor(PALETTE.text_disabled))
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "Histogram yok")
            p.end()
            return

        plot = rect.adjusted(SPACE.xs, SPACE.xs, -SPACE.xs, -SPACE.xs)

        # Dortte birlik dikey rehberler
        p.setPen(QPen(QColor(PALETTE.border_subtle), 1.0))
        for i in (1, 2, 3):
            x = plot.left() + plot.width() * i / 4.0
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        colors = (PALETTE.hist_red, PALETTE.hist_green, PALETTE.hist_blue)
        if self._show_channels:
            # Kanallar ustuste, ekleyici hisli yarisaydam dolgu
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for i, color in enumerate(colors):
                self._draw_curve(p, plot, self._channels[i], QColor(color), 0.55)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        else:
            self._draw_curve(p, plot, self._channels[3],
                             QColor(PALETTE.hist_luma), 0.5)

        # Kirpma uyarilari
        if self._shadow_clip > CLIP_WARNING_RATIO:
            self._draw_clip_marker(p, plot, left=True)
        if self._highlight_clip > CLIP_WARNING_RATIO:
            self._draw_clip_marker(p, plot, left=False)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(PALETTE.border_subtle), 1.0))
        p.drawRoundedRect(rect, RADIUS.sm, RADIUS.sm)
        p.end()

    @staticmethod
    def _draw_curve(p: QPainter, plot: QRectF, values: np.ndarray,
                    color: QColor, alpha: float) -> None:
        path = QPainterPath()
        path.moveTo(plot.left(), plot.bottom())
        n = len(values)
        for i, v in enumerate(values):
            x = plot.left() + plot.width() * i / (n - 1)
            y = plot.bottom() - plot.height() * min(1.0, float(v))
            path.lineTo(x, y)
        path.lineTo(plot.right(), plot.bottom())
        path.closeSubpath()

        fill = QColor(color)
        fill.setAlphaF(alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(path)

    @staticmethod
    def _draw_clip_marker(p: QPainter, plot: QRectF, *, left: bool) -> None:
        w = 3.0
        x = plot.left() if left else plot.right() - w
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.danger))
        p.drawRect(QRectF(x, plot.top(), w, plot.height()))

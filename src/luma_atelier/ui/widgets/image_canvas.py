"""Fotograf tuvali: yakinlastirma, kaydirma, once/sonra karsilastirmasi.

Koordinat sistemleri
--------------------
* **Goruntu uzayi**: kaynak fotografin pikselleri, (0,0) sol ust.
  Maskeler, kirpma ve efekt yariciplari *daima* bu uzayda saklanir.
* **Widget uzayi**: ekranda gorunun pikselleri.

Donusum `zoom` ve `pan` ile tanimlanir:

    widget = (goruntu - pan) * zoom + widget_merkezi

Boylece zoom/pan degistiginde maske veya kirpma koordinatlari kaymaz;
yalnizca cizim donusumu degisir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from luma_atelier.imaging import pixels as px
from luma_atelier.ui.theme.tokens import PALETTE, SPACE, TYPE

log = logging.getLogger(__name__)

MIN_ZOOM = 0.02
MAX_ZOOM = 16.0
#: Fare tekerlegi bir kertiginin zoom carpani
ZOOM_STEP = 1.18
#: "Ekrana sigdir" modunda birakilan kenar boslugu (oran)
FIT_MARGIN = 0.035


class CompareMode(Enum):
    """Once/sonra gosterim bicimi."""

    OFF = auto()          # yalnizca duzenlenmis
    ORIGINAL = auto()     # yalnizca orijinal
    SPLIT = auto()        # surgu ile bolunmus
    SIDE_BY_SIDE = auto() # yan yana


@dataclass
class _Frame:
    """Ekranda gosterilen bir goruntunun hazirlanmis hali."""

    pixmap: QPixmap
    width: int
    height: int


def numpy_to_qimage(arr: np.ndarray) -> QImage:
    """float32 calisma tamponunu QImage'e cevirir.

    `.copy()` zorunlu: QImage kendi tamponunu sahiplenmezse NumPy dizisi
    serbest kaldiginda serbest bellek okunur ve rastgele cokme olur.
    Saydam goruntude alpha korunur.
    """
    work = px.ensure_working(arr)
    clipped = np.clip(work, 0.0, 1.0)
    if clipped.shape[2] == 4:
        u8 = np.ascontiguousarray(px.to_uint8(clipped))
        fmt = QImage.Format.Format_RGBA8888
    else:
        u8 = np.ascontiguousarray(px.to_uint8(clipped[..., :3]))
        fmt = QImage.Format.Format_RGB888
    h, w = u8.shape[:2]
    return QImage(u8.data, w, h, u8.strides[0], fmt).copy()


class ImageCanvas(QWidget):
    """Fotografi gosteren, yakinlastirilabilir ve kaydirilabilir tuval."""

    zoomChanged = Signal(float)
    #: Zoom *veya* kaydirma degistiginde; detay karosu bunu dinler.
    #: Yalnizca zoom'u dinlemek yetmiyordu: kaydirma sonrasi karo
    #: gecersiz kaliyor ama yeniden istenmiyordu.
    viewChanged = Signal()
    #: Kullanici tuval uzerinde gezinirken goruntu uzayindaki konum
    cursorMoved = Signal(QPointF)
    compareModeChanged = Signal(CompareMode)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CanvasHost")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(False)  # birakma olayi ana pencerede toplanir
        self.setMinimumSize(240, 180)

        self._edited: _Frame | None = None
        self._original: _Frame | None = None
        #: `_original` icin kaynak dizi; kimlik karsilastirmasiyla
        #: gereksiz QPixmap donusumunu onler.
        self._original_source: np.ndarray | None = None
        self._zoom = 1.0
        self._fit_mode = True
        self._pan = QPointF(0.0, 0.0)   # goruntu uzayinda gorunen merkez
        self._panning = False
        self._pan_anchor = QPoint()
        self._pan_start = QPointF()
        self._compare = CompareMode.OFF
        self._split_ratio = 0.5
        self._dragging_split = False
        # Tam cozunurluklu detay karosu. Tuval onizleme uzerinde calisir;
        # onizleme buyutulerek gosterilirse kullanici gercek kaliteyi
        # goremez. %100 ve uzerinde gorunen bolge kaynaktan yeniden
        # uretilir ve onizlemenin uzerine cizilir.
        self._detail: _Frame | None = None
        self._detail_rect: QRectF | None = None
        self._source_size: tuple[int, int] = (0, 0)
        self._placeholder = "Fotoğraf eklemek için sürükleyip bırakın"
        self._checker: QPixmap | None = None

    # ------------------------------------------------------------- icerik
    def setImage(  # noqa: N802
        self, edited: np.ndarray | None, original: np.ndarray | None = None,
        *, source_size: tuple[int, int] | None = None,
    ) -> None:
        """Gosterilecek goruntuyu ayarlar.

        `original` verilirse once/sonra karsilastirmasi kullanilabilir.
        `source_size` tam cozunurluklu kaynagin (genislik, yukseklik)
        boyutudur; verilmezse gosterilen goruntununki kullanilir. Zoom
        yuzdesi ve %100 gorunumu bu boyuta gore hesaplanir.
        Boyut degistiyse gorunum otomatik olarak ekrana sigdirilir.
        """
        previous = (self._edited.width, self._edited.height) if self._edited else None
        self._edited = self._make_frame(edited)

        # Orijinal kare kaydirici surukleme boyunca **degismez**: kaynak
        # ve kadraj ayni oldugu surece cagiran ayni diziyi verir. Her
        # sonucta yeniden QPixmap'e cevirmek 1920 px'de ~35 ms bosa is
        # demekti; dizi kimligi ayniysa mevcut kare korunur.
        if original is None:
            self._original = None
            self._original_source = None
        elif self._original is None or original is not self._original_source:
            self._original = self._make_frame(original)
            self._original_source = original
        self._detail = None
        self._detail_rect = None
        if self._edited is not None:
            self._source_size = source_size or (self._edited.width,
                                                self._edited.height)
        current = (self._edited.width, self._edited.height) if self._edited else None
        if current != previous:
            self.zoomToFit()
        self.update()

    @property
    def sourceSize(self) -> tuple[int, int]:  # noqa: N802
        """Tam cozunurluklu kaynagin boyutu (onizlemeninki degil)."""
        return self._source_size

    @property
    def previewScale(self) -> float:  # noqa: N802
        """Gosterilen onizlemenin kaynaga orani."""
        if self._edited is None or not self._source_size[0]:
            return 1.0
        return self._edited.width / float(self._source_size[0])

    def effectiveZoom(self) -> float:  # noqa: N802
        """Kaynak piksel basina ekran pikseli.

        Kullaniciya gosterilen yuzde *kaynak* piksellere gore olmali;
        %100 gercekten 1:1 demektir.
        """
        return self._zoom * self.previewScale

    def needsDetailTile(self) -> bool:  # noqa: N802
        """Onizleme buyutulerek mi gosteriliyor?

        Buyutuluyorsa gorunen alan tam cozunurlukten yeniden
        uretilmelidir; aksi halde %100 gorunumu bulanik olur.
        """
        # Esik neden bu kadar dusuk: onizleme 1.0'in *uzerinde* herhangi
        # bir oranda gerilirse ayrinti kaybolur. Tam %100 gorunumde
        # tuval zoom'u 1/onizleme_orani olur (orn. 2.13) ama kucuk
        # fotograflarda onizleme zaten tam boydur ve 1.0 kalir; o
        # durumda karoya gerek yoktur.
        return self._edited is not None and self._zoom > 1.001

    def visibleImageRect(self) -> QRectF:  # noqa: N802
        """Ekranda gorunen bolge, *kaynak* goruntu koordinatlarinda."""
        if self._edited is None:
            return QRectF()
        vp = self._viewport()
        top_left = self.widgetToImage(vp.topLeft())
        bottom_right = self.widgetToImage(vp.bottomRight())
        inv = 1.0 / max(1e-6, self.previewScale)
        rect = QRectF(
            top_left.x() * inv, top_left.y() * inv,
            (bottom_right.x() - top_left.x()) * inv,
            (bottom_right.y() - top_left.y()) * inv,
        )
        return rect.intersected(
            QRectF(0, 0, float(self._source_size[0]), float(self._source_size[1]))
        )

    def setDetailTile(self, image: np.ndarray | None,  # noqa: N802
                      source_rect: QRectF) -> None:
        """Gorunen bolgenin tam cozunurluklu render'ini yerlestirir."""
        if image is None:
            self._detail = None
            self._detail_rect = None
        else:
            self._detail = self._make_frame(image)
            self._detail_rect = QRectF(source_rect)
        self.update()

    def clearDetailTile(self) -> None:  # noqa: N802
        if self._detail is not None:
            self._detail = None
            self._detail_rect = None
            self.update()

    def setPlaceholder(self, text: str) -> None:  # noqa: N802
        self._placeholder = text
        self.update()

    def clear(self) -> None:
        self._edited = None
        self._original = None
        self._original_source = None
        self.update()

    @staticmethod
    def _make_frame(arr: np.ndarray | None) -> _Frame | None:
        if arr is None:
            return None
        qim = numpy_to_qimage(arr)
        return _Frame(QPixmap.fromImage(qim), qim.width(), qim.height())

    @property
    def hasImage(self) -> bool:  # noqa: N802
        return self._edited is not None

    @property
    def imageSize(self) -> tuple[int, int]:  # noqa: N802
        if self._edited is None:
            return (0, 0)
        return (self._edited.width, self._edited.height)

    # ---------------------------------------------------------------- zoom
    def zoom(self) -> float:
        return self._zoom

    def isFitMode(self) -> bool:  # noqa: N802
        return self._fit_mode

    def fitScale(self) -> float:  # noqa: N802
        """Goruntunun tamamini gosteren olcek."""
        if self._edited is None:
            return 1.0
        aw = self.width() * (1.0 - FIT_MARGIN * 2)
        ah = self.height() * (1.0 - FIT_MARGIN * 2)
        if self._compare is CompareMode.SIDE_BY_SIDE:
            aw = (aw - SPACE.sm) / 2.0
        return max(
            MIN_ZOOM,
            min(aw / max(1, self._edited.width), ah / max(1, self._edited.height)),
        )

    def zoomToFit(self) -> None:  # noqa: N802
        if self._edited is None:
            return
        self._fit_mode = True
        self._zoom = self.fitScale()
        self._pan = QPointF(self._edited.width / 2.0, self._edited.height / 2.0)
        self._detail = None
        self._detail_rect = None
        self.zoomChanged.emit(self.effectiveZoom())
        self.viewChanged.emit()
        self.update()

    def zoomToActualPixels(self) -> None:  # noqa: N802
        """%100 gorunum: bir kaynak pikseli = bir ekran pikseli.

        Tuval onizleme uzerinde calistigi icin gereken tuval zoom'u
        1 / onizleme_orani olur. Detay karosu bu seviyede devreye girer
        ve gercek kalite gorunur.
        """
        self.setZoom(1.0 / max(1e-6, self.previewScale))

    def setZoom(self, value: float, focus: QPointF | None = None) -> None:  # noqa: N802
        """Yakinlastirma orani. `focus` widget uzayinda sabit kalacak nokta."""
        if self._edited is None:
            return
        new = float(np.clip(value, MIN_ZOOM, MAX_ZOOM))
        if abs(new - self._zoom) < 1e-6:
            return
        anchor = focus or QPointF(self.width() / 2.0, self.height() / 2.0)
        before = self.widgetToImage(anchor)
        self._zoom = new
        self._fit_mode = False
        after = self.widgetToImage(anchor)
        self._pan += before - after
        self._clampPan()
        self._detail = None
        self._detail_rect = None
        self.zoomChanged.emit(self.effectiveZoom())
        self.viewChanged.emit()
        self.update()

    def zoomIn(self, focus: QPointF | None = None) -> None:  # noqa: N802
        self.setZoom(self._zoom * ZOOM_STEP, focus)

    def zoomOut(self, focus: QPointF | None = None) -> None:  # noqa: N802
        self.setZoom(self._zoom / ZOOM_STEP, focus)

    # --------------------------------------------------------- donusumler
    def _viewport(self) -> QRectF:
        """Goruntunun cizilecegi widget bolgesi."""
        if self._compare is CompareMode.SIDE_BY_SIDE:
            half = (self.width() - SPACE.sm) / 2.0
            return QRectF(half + SPACE.sm, 0, half, self.height())
        return QRectF(0, 0, self.width(), self.height())

    def imageToWidget(self, point: QPointF) -> QPointF:  # noqa: N802
        vp = self._viewport()
        return QPointF(
            (point.x() - self._pan.x()) * self._zoom + vp.center().x(),
            (point.y() - self._pan.y()) * self._zoom + vp.center().y(),
        )

    def widgetToImage(self, point: QPointF) -> QPointF:  # noqa: N802
        """Ekran noktasini goruntu pikseline cevirir.

        Maske cizimi ve renk secici bu donusumu kullanir; zoom/pan
        degisse de sonuc ayni goruntu pikselini gosterir.
        """
        vp = self._viewport()
        return QPointF(
            (point.x() - vp.center().x()) / self._zoom + self._pan.x(),
            (point.y() - vp.center().y()) / self._zoom + self._pan.y(),
        )

    def _imageRect(self, viewport: QRectF, frame: _Frame) -> QRectF:
        w = frame.width * self._zoom
        h = frame.height * self._zoom
        cx = viewport.center().x() - (self._pan.x() - frame.width / 2.0) * self._zoom
        cy = viewport.center().y() - (self._pan.y() - frame.height / 2.0) * self._zoom
        return QRectF(cx - w / 2.0, cy - h / 2.0, w, h)

    def _clampPan(self) -> None:
        """Goruntunun tamamen ekran disina kacmasini engeller."""
        if self._edited is None:
            return
        iw, ih = self._edited.width, self._edited.height
        vp = self._viewport()
        # Goruntu gorunurden kucukse ortala, buyukse kenarlari serbest birak
        margin_x = max(0.0, (iw - vp.width() / self._zoom) / 2.0)
        margin_y = max(0.0, (ih - vp.height() / self._zoom) / 2.0)
        self._pan = QPointF(
            float(np.clip(self._pan.x(), iw / 2.0 - margin_x, iw / 2.0 + margin_x)),
            float(np.clip(self._pan.y(), ih / 2.0 - margin_y, ih / 2.0 + margin_y)),
        )

    # ------------------------------------------------------ karsilastirma
    def compareMode(self) -> CompareMode:  # noqa: N802
        return self._compare

    def setCompareMode(self, mode: CompareMode) -> None:  # noqa: N802
        if mode is self._compare:
            return
        if mode is not CompareMode.OFF and self._original is None:
            log.debug("Karsilastirma istendi ama orijinal goruntu yok")
            return
        self._compare = mode
        if self._fit_mode:
            self.zoomToFit()
        self.compareModeChanged.emit(mode)
        self.update()

    def splitRatio(self) -> float:  # noqa: N802
        return self._split_ratio

    # ---------------------------------------------------------------- olay
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_mode:
            self.zoomToFit()
        else:
            self._clampPan()
            self._detail = None
            self._detail_rect = None
            self.viewChanged.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._edited is None:
            return
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.setZoom(self._zoom * (ZOOM_STEP ** steps), event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._edited is None:
            return
        if (self._compare is CompareMode.SPLIT
                and event.button() == Qt.MouseButton.LeftButton
                and abs(event.position().x() - self._split_x()) < 12):
            self._dragging_split = True
            self.setCursor(Qt.CursorShape.SplitHCursor)
            return
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._panning = True
            self._pan_anchor = event.position().toPoint()
            self._pan_start = QPointF(self._pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._edited is None:
            return
        if self._dragging_split:
            self._split_ratio = float(
                np.clip(event.position().x() / max(1, self.width()), 0.02, 0.98)
            )
            self.update()
            return
        if self._panning:
            delta = event.position().toPoint() - self._pan_anchor
            self._pan = QPointF(
                self._pan_start.x() - delta.x() / self._zoom,
                self._pan_start.y() - delta.y() / self._zoom,
            )
            self._fit_mode = False
            self._clampPan()
            self._detail = None
            self._detail_rect = None
            self.update()
            return
        if (self._compare is CompareMode.SPLIT
                and abs(event.position().x() - self._split_x()) < 12):
            self.setCursor(Qt.CursorShape.SplitHCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.cursorMoved.emit(self.widgetToImage(event.position()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        was_panning = self._panning
        self._panning = False
        self._dragging_split = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if was_panning:
            # Kaydirma bitti: gorunen bolge degisti, detay karosu
            # yeniden uretilmeli.
            self.viewChanged.emit()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Cift tiklama: sigdir <-> %100 arasinda gecis."""
        if self._edited is None:
            return
        if self._fit_mode:
            self.setZoom(1.0, event.position())
        else:
            self.zoomToFit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoomIn()
        elif key == Qt.Key.Key_Minus:
            self.zoomOut()
        elif key == Qt.Key.Key_0:
            self.zoomToFit()
        elif key == Qt.Key.Key_1:
            self.zoomToActualPixels()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    # --------------------------------------------------------------- cizim
    def _split_x(self) -> float:
        return self.width() * self._split_ratio

    def _checkerboard(self) -> QPixmap:
        """Saydam alanlarin arkasina cizilen damali desen."""
        if self._checker is None:
            size = 16
            pm = QPixmap(size * 2, size * 2)
            pm.fill(QColor(PALETTE.bg_raised))
            p = QPainter(pm)
            p.fillRect(0, 0, size, size, QColor(PALETTE.bg_overlay))
            p.fillRect(size, size, size, size, QColor(PALETTE.bg_overlay))
            p.end()
            self._checker = pm
        return self._checker

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(PALETTE.canvas_void))

        if self._edited is None:
            self._paint_placeholder(p)
            p.end()
            return

        # Yakinlastirmada keskin piksel, uzaklastirmada yumusak orneklem
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 1.0)

        if self._compare is CompareMode.SIDE_BY_SIDE and self._original is not None:
            half = (self.width() - SPACE.sm) / 2.0
            self._paint_frame(p, self._original, QRectF(0, 0, half, self.height()))
            self._paint_frame(p, self._edited,
                              QRectF(half + SPACE.sm, 0, half, self.height()))
            p.fillRect(QRectF(half, 0, SPACE.sm, self.height()),
                       QColor(PALETTE.border_subtle))
            self._paint_badge(p, "ORIJINAL", QRectF(0, 0, half, self.height()))
            self._paint_badge(p, "DÜZENLENMIŞ",
                              QRectF(half + SPACE.sm, 0, half, self.height()))
        elif self._compare is CompareMode.ORIGINAL and self._original is not None:
            self._paint_frame(p, self._original, self._viewport())
            self._paint_badge(p, "ORIJINAL", self._viewport())
        elif self._compare is CompareMode.SPLIT and self._original is not None:
            sx = self._split_x()
            p.save()
            p.setClipRect(QRectF(0, 0, sx, self.height()))
            self._paint_frame(p, self._original, self._viewport())
            p.restore()
            p.save()
            p.setClipRect(QRectF(sx, 0, self.width() - sx, self.height()))
            self._paint_frame(p, self._edited, self._viewport())
            # Karsilastirmada da gercek kalite gorunmeli; karo yalnizca
            # duzenlenmis tarafa cizilir.
            self._paint_detail(p)
            p.restore()
            self._paint_split_handle(p, sx)
        else:
            self._paint_frame(p, self._edited, self._viewport())
            self._paint_detail(p)

        p.end()

    def _paint_detail(self, p: QPainter) -> None:
        """Tam cozunurluklu karoyu onizlemenin uzerine cizer."""
        if self._detail is None or self._detail_rect is None:
            return
        scale = self.previewScale
        preview_rect = QRectF(
            self._detail_rect.left() * scale, self._detail_rect.top() * scale,
            self._detail_rect.width() * scale, self._detail_rect.height() * scale,
        )
        target = QRectF(self.imageToWidget(preview_rect.topLeft()),
                        self.imageToWidget(preview_rect.bottomRight()))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(target, self._detail.pixmap,
                     QRectF(self._detail.pixmap.rect()))

    def _paint_frame(self, p: QPainter, frame: _Frame, viewport: QRectF) -> None:
        rect = self._imageRect(viewport, frame)
        if frame.pixmap.hasAlphaChannel():
            p.save()
            p.setClipRect(rect.intersected(viewport))
            p.drawTiledPixmap(rect, self._checkerboard())
            p.restore()
        p.drawPixmap(rect, frame.pixmap, QRectF(frame.pixmap.rect()))

    def _paint_split_handle(self, p: QPainter, x: float) -> None:
        p.setPen(QPen(QColor(PALETTE.text_primary), 1.0))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        cy = self.height() / 2.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.text_primary))
        p.drawRoundedRect(QRectF(x - 9, cy - 18, 18, 36), 9, 9)
        p.setPen(QPen(QColor(PALETTE.bg_base), 1.4))
        for dx in (-3, 3):
            p.drawLine(QPointF(x + dx, cy - 7), QPointF(x + dx, cy + 7))

    def _paint_badge(self, p: QPainter, text: str, viewport: QRectF) -> None:
        f = QFont()
        f.setPixelSize(TYPE.size_micro)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + SPACE.md
        rect = QRectF(viewport.left() + SPACE.sm, viewport.top() + SPACE.sm, w, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 165))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QColor(PALETTE.text_secondary))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def _paint_placeholder(self, p: QPainter) -> None:
        f = QFont()
        f.setPixelSize(TYPE.size_body)
        p.setFont(f)
        p.setPen(QColor(PALETTE.text_muted))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._placeholder)

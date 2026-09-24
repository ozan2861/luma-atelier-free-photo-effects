"""Faz 0 paketleme kaniti: gercek is yapan kucuk pencere.

Amaci arayuz gelistirmek degil, *paketlenmis exe'nin* tum kritik
bagimliliklari (Qt widget'lari, NumPy, OpenCV, Pillow, tifffile, ICC)
gercekten calistirdigini kanitlamaktir. Faz 1'de yerini tam uygulama
kabugu alir.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from luma_atelier.core.branding import APP_NAME, APP_VERSION
from luma_atelier.core.paths import default_output_dir, pictures_dir
from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.loader import ImageLoadError, load_image
from luma_atelier.imaging.saver import (
    ImageSaveError,
    OutputFormat,
    SaveOptions,
    save_image,
)
from luma_atelier.ui.theme.stylesheet import build_stylesheet
from luma_atelier.ui.theme.tokens import METRICS, SPACE

log = logging.getLogger(__name__)

PREVIEW_LONG_EDGE = 1400


def to_qimage(arr: np.ndarray) -> QImage:
    """float32 calisma tamponunu ekranda gosterilebilir QImage'e cevirir.

    `.copy()` sart: aksi halde QImage serbest kalan NumPy bellegine
    isaret eder ve rastgele cokme uretir.
    """
    rgb = np.clip(arr[..., :3], 0.0, 1.0)
    u8 = np.ascontiguousarray(px.to_uint8(rgb))
    h, w = u8.shape[:2]
    return QImage(u8.data, w, h, u8.strides[0], QImage.Format.Format_RGB888).copy()


class SmokeWindow(QWidget):
    """Ac - ayarla - kaydet. Uc adim, gercek dosyalar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} - Faz 0 teknik denemesi")
        self.resize(1080, 760)
        self.setAcceptDrops(True)

        self._source: np.ndarray | None = None
        self._preview_base: np.ndarray | None = None
        self._path: Path | None = None

        self.canvas = QLabel("Fotoğrafı buraya sürükleyin veya 'Fotoğraf aç' deyin")
        self.canvas.setObjectName("CanvasHost")
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumHeight(420)

        self.info = QLabel("Henüz fotoğraf yüklenmedi.")
        self.info.setObjectName("Caption")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-300, 300)  # -3.00 .. +3.00 stop
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_exposure)

        self.value_label = QLabel("0.00 stop")
        self.value_label.setObjectName("ValueReadout")
        self.value_label.setMinimumWidth(78)

        open_btn = QPushButton("Fotoğraf aç")
        open_btn.clicked.connect(self._choose_file)
        self.save_btn = QPushButton("JPEG olarak kaydet")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)

        controls = QHBoxLayout()
        controls.setSpacing(SPACE.md)
        controls.addWidget(QLabel("Pozlama"))
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.value_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACE.sm)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.save_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.xl, SPACE.xl, SPACE.xl, SPACE.xl)
        root.setSpacing(SPACE.md)
        root.addWidget(self.canvas, 1)
        root.addWidget(self.info)
        root.addLayout(controls)
        root.addLayout(buttons)

    # ---------------------------------------------------------------- surukle
    def dragEnterEvent(self, event):  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # type: ignore[no-untyped-def]
        urls = event.mimeData().urls()
        if urls:
            self._load(Path(urls[0].toLocalFile()))

    # ---------------------------------------------------------------- eylemler
    def _choose_file(self) -> None:
        start = str(pictures_dir())
        path, _ = QFileDialog.getOpenFileName(
            self, "Fotoğraf seç", start,
            "Fotoğraflar (*.jpg *.jpeg *.png *.webp *.tif *.tiff)",
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        try:
            t0 = time.perf_counter()
            loaded = load_image(path)
            ms = (time.perf_counter() - t0) * 1000
        except ImageLoadError as exc:
            QMessageBox.warning(self, "Fotoğraf açılamadı", str(exc))
            return

        self._source = loaded.pixels
        self._path = path
        m = loaded.metadata

        # Onizleme icin kucult - tam boy her slider hareketinde islenmez
        h, w = loaded.pixels.shape[:2]
        scale = min(1.0, PREVIEW_LONG_EDGE / max(h, w))
        if scale < 1.0:
            import cv2
            self._preview_base = cv2.resize(
                loaded.pixels, (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            self._preview_base = loaded.pixels

        self.slider.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.info.setText(
            f"{path.name}  |  {m.width}x{m.height} ({m.megapixels:.1f} MP)  |  "
            f"{m.source_format} {m.source_bit_depth}-bit  |  "
            f"alpha: {'var' if m.has_alpha else 'yok'}  |  "
            f"EXIF yon: {m.exif_orientation}"
            f"{' (uygulandi)' if m.orientation_applied else ''}  |  "
            f"ICC: {m.icc_description or 'yok, sRGB varsayildi'}  |  {ms:.0f} ms"
        )
        self._render()

    def _on_exposure(self, value: int) -> None:
        self.value_label.setText(f"{value / 100:+.2f} stop")
        self._render()

    def _render(self) -> None:
        if self._preview_base is None:
            return
        stops = self.slider.value() / 100.0
        t0 = time.perf_counter()
        out = self._apply(self._preview_base, stops)
        ms = (time.perf_counter() - t0) * 1000
        pix = QPixmap.fromImage(to_qimage(out))
        self.canvas.setPixmap(
            pix.scaled(self.canvas.size(), Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        )
        self.setWindowTitle(
            f"{APP_NAME} {APP_VERSION} - Faz 0  |  önizleme {ms:.0f} ms"
        )

    @staticmethod
    def _apply(img: np.ndarray, stops: float) -> np.ndarray:
        if abs(stops) < 1e-6:
            return img
        rgb, alpha = px.split_alpha(img)
        lin = px.srgb_to_linear(rgb) * np.float32(2.0 ** stops)
        return px.join_alpha(px.linear_to_srgb(lin), alpha)

    def _save(self) -> None:
        if self._source is None or self._path is None:
            return
        out_dir = default_output_dir()
        target = out_dir / f"{self._path.stem}-luma.jpg"
        try:
            full = self._apply(self._source, self.slider.value() / 100.0)
            res = save_image(full, target, SaveOptions(fmt=OutputFormat.JPEG, quality=94))
        except ImageSaveError as exc:
            QMessageBox.critical(self, "Kaydedilemedi", str(exc))
            return
        QMessageBox.information(
            self, "Kaydedildi",
            f"Dosya yazıldı:\n{res.path}\n\n{res.bytes_written / 1024:.0f} KB",
        )

    def resizeEvent(self, event):  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._render()


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(build_stylesheet())
    win = SmokeWindow()
    win.setMinimumSize(METRICS.window_min_width - 200, 600)
    win.show()
    return app.exec()

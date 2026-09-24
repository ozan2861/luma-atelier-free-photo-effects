"""Faz 0 - Teknik yigin dogrulama.

Secilen bilesenlerin gercekten birlikte calistigini kanitlar:
  - surum raporu
  - 16-bit TIFF yazma/okuma (sessiz 8-bit kaybi var mi?)
  - float32 islem hatti ve bantlasma kontrolu
  - EXIF yon etiketi okuma
  - ICC profil zinciri (Pillow ImageCms)
  - Qt offscreen pencere + QImage/NumPy koprusu
Cikti: her kontrol icin GECTI / KALDI satiri, exit kodu 0/1.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import traceback
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str):
    def deco(fn):
        try:
            detail = fn() or ""
            RESULTS.append((name, True, str(detail)))
        except Exception as exc:  # noqa: BLE001 - tanilama betigi
            RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()
        return fn
    return deco


@check("Surumler")
def _versions():
    import cv2
    import numpy as np
    import PIL
    import PySide6
    import tifffile
    return (
        f"Python {sys.version.split()[0]} | PySide6 {PySide6.__version__} | "
        f"NumPy {np.__version__} | OpenCV {cv2.__version__} | "
        f"Pillow {PIL.__version__} | tifffile {tifffile.__version__}"
    )


@check("16-bit TIFF gidis-donus (veri kaybi yok)")
def _tiff16():
    import numpy as np
    import tifffile

    # 16-bit hassasiyeti test eden ince rampa: komsu degerler 1 LSB farkli
    ramp = np.arange(65536, dtype=np.uint16).reshape(256, 256)
    rgb = np.dstack([ramp, ramp[::-1], ramp.T]).astype(np.uint16)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test16.tif"
        tifffile.imwrite(p, rgb, photometric="rgb")
        back = tifffile.imread(p)
    assert back.dtype == np.uint16, f"dtype {back.dtype} (uint16 bekleniyordu)"
    assert np.array_equal(back, rgb), "piksel degerleri degisti"
    uniq = len(np.unique(back[..., 0]))
    assert uniq == 65536, f"benzersiz ton sayisi {uniq} (65536 bekleniyordu)"
    return f"65536 benzersiz ton korundu, dtype={back.dtype}"


@check("float32 hatti 8-bit ara yuvarlamaya karsi")
def _float_pipeline():
    import numpy as np

    # 16-bit cozunurlukte giris rampasi
    x = np.linspace(0.0, 1.0, 65536, dtype=np.float32)

    def chain(v, quantize_each_step=False):
        """Tipik efekt zinciri. quantize=True ise her adimda 8-bit'e doner."""
        def step(a):
            if quantize_each_step:
                return (np.clip(a, 0, 1) * 255).round().astype(np.uint8) / np.float32(255.0)
            return a
        v = step(v * np.float32(1.18))              # pozlama
        v = step((v - 0.5) * np.float32(1.12) + 0.5)  # kontrast
        v = step(np.clip(v, 0, 1) ** np.float32(1 / 1.06))  # ton egrisi
        v = step(v * np.float32(0.94) + np.float32(0.03))   # fade / matte
        return np.clip(v, 0, 1)

    f32 = chain(x, False)
    u8 = chain(x, True)
    assert f32.dtype == np.float32, f32.dtype
    assert np.isfinite(f32).all(), "float32 hattinda NaN/Inf uretildi"

    to16 = lambda v: len(np.unique((v * 65535).round().astype(np.uint16)))
    n_f32, n_u8 = to16(f32), to16(u8)
    # 8-bit ara adimlar en fazla 256 seviye birakir; float32 hatti binlerce korumali
    assert n_u8 <= 256, f"8-bit referans hatti beklenenden fazla seviye verdi: {n_u8}"
    assert n_f32 > 20000, f"float32 hattinda sadece {n_f32} ton kaldi (bantlasma)"
    return f"float32 hatti {n_f32} ton korudu; her adimda 8-bit'e donen hat {n_u8} tona dustu"


@check("EXIF yon etiketi okuma")
def _exif():
    import piexif
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "exif.jpg"
        Image.new("RGB", (120, 60), (200, 80, 40)).save(p, quality=95)
        exif = {"0th": {piexif.ImageIFD.Orientation: 6}, "Exif": {}, "GPS": {},
                "1st": {}, "thumbnail": None}
        piexif.insert(piexif.dump(exif), str(p))
        with Image.open(p) as im:
            tags = im.getexif()
            orient = tags.get(274)
    assert orient == 6, f"orientation {orient} (6 bekleniyordu)"
    return "Orientation=6 dogru okundu"


@check("ICC profil zinciri (ImageCms)")
def _icc():
    from PIL import Image, ImageCms

    srgb = ImageCms.createProfile("sRGB")
    blob = ImageCms.ImageCmsProfile(srgb).tobytes()
    im = Image.new("RGB", (32, 32), (10, 120, 200))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "icc.jpg"
        im.save(p, icc_profile=blob, quality=95)
        with Image.open(p) as back:
            got = back.info.get("icc_profile")
    assert got, "ICC profili dosyada bulunamadi"
    prof = ImageCms.getOpenProfile(io.BytesIO(got))
    return f"profil yazildi/okundu ({len(got)} bayt), desc={ImageCms.getProfileDescription(prof).strip()}"


@check("Qt pencere + QImage/NumPy koprusu")
def _qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance() or QApplication(sys.argv)
    arr = np.zeros((64, 96, 3), dtype=np.uint8)
    arr[..., 0] = 255
    arr = np.ascontiguousarray(arr)
    qim = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0],
                 QImage.Format.Format_RGB888).copy()  # copy(): NumPy omru bagimsiz
    assert qim.width() == 96 and qim.height() == 64
    px = qim.pixelColor(10, 10)
    assert (px.red(), px.green(), px.blue()) == (255, 0, 0), px
    w = QLabel("Luma Atelier")
    w.resize(320, 200)
    w.show()
    app.processEvents()
    ok = w.isVisible()
    w.close()
    assert ok, "pencere gorunur olmadi"
    return f"QImage {qim.width()}x{qim.height()} RGB888, pencere acildi (platform={QApplication.platformName()})"


def main() -> int:
    width = max(len(n) for n, _, _ in RESULTS)
    print("\n" + "=" * 72)
    print("LUMA ATELIER - Faz 0 teknik yigin dogrulamasi")
    print("=" * 72)
    failed = 0
    for name, ok, detail in RESULTS:
        flag = "GECTI" if ok else "KALDI"
        if not ok:
            failed += 1
        print(f"[{flag}] {name.ljust(width)}  {detail}")
    print("=" * 72)
    print(f"Sonuc: {len(RESULTS) - failed}/{len(RESULTS)} kontrol gecti")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

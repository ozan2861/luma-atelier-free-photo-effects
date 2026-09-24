"""Ortak test fikstürleri.

Test goruntuleri burada uretilir; disaridan indirilen veya lisansi
belirsiz fotograf kullanilmaz. Uretilen desenler hedefli:

* `gradient_rgb`   - bantlasma ve ton hassasiyeti icin duz rampa
* `gray_ramp16`    - 16-bit hassasiyet testleri
* `color_patches`  - renk kaymasi ve doygunluk testleri
* `alpha_edge`     - saydam kenar / premultiply hale testleri
* `portrait_like`  - ten rengi benzeri bolgeli sentetik sahne
* `night_like`     - yuksek kontrastli, parlak isik kaynakli sahne
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def data_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Testler kullanicinin gercek uygulama verisine dokunmaz."""
    root = tmp_path_factory.mktemp("luma_data_home")
    os.environ["LUMA_DATA_HOME"] = str(root)
    return root


@pytest.fixture(scope="session")
def rng() -> np.random.Generator:
    return np.random.default_rng(20260917)


def _as_float(arr: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(arr.astype(np.float32))


@pytest.fixture(scope="session")
def gradient_rgb() -> np.ndarray:
    """Yatay 0..1 rampa, dikeyde hafif renk kaymasi. (512, 1024, 3)"""
    h, w = 512, 1024
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    y = np.linspace(-0.05, 0.05, h, dtype=np.float32)[:, None]
    r = np.clip(x + y, 0, 1)
    g = np.clip(x, 0, 1) * np.ones((h, 1), dtype=np.float32)
    b = np.clip(x - y, 0, 1)
    return _as_float(np.dstack([r, g, b]))


@pytest.fixture(scope="session")
def gray_ramp16() -> np.ndarray:
    """65536 farkli ton iceren gri rampa; 16-bit kaybini yakalar."""
    ramp = np.arange(65536, dtype=np.uint16).reshape(256, 256)
    return np.dstack([ramp, ramp, ramp])


@pytest.fixture(scope="session")
def color_patches() -> np.ndarray:
    """6x4 renk yamasi tablosu. (480, 720, 3)"""
    colors = [
        (0.95, 0.95, 0.95), (0.75, 0.75, 0.75), (0.50, 0.50, 0.50),
        (0.25, 0.25, 0.25), (0.10, 0.10, 0.10), (0.02, 0.02, 0.02),
        (0.85, 0.15, 0.12), (0.12, 0.65, 0.22), (0.10, 0.25, 0.80),
        (0.92, 0.80, 0.12), (0.75, 0.15, 0.62), (0.10, 0.72, 0.78),
        (0.82, 0.62, 0.48), (0.68, 0.45, 0.32), (0.45, 0.30, 0.22),
        (0.30, 0.42, 0.28), (0.22, 0.34, 0.52), (0.55, 0.52, 0.42),
        (0.98, 0.72, 0.60), (0.88, 0.58, 0.45), (0.70, 0.42, 0.30),
        (0.40, 0.55, 0.70), (0.62, 0.70, 0.45), (0.35, 0.20, 0.45),
    ]
    rows, cols, cell = 4, 6, 120
    img = np.zeros((rows * cell, cols * cell, 3), dtype=np.float32)
    for i, c in enumerate(colors):
        r, q = divmod(i, cols)
        img[r * cell:(r + 1) * cell, q * cell:(q + 1) * cell] = c
    return _as_float(img)


@pytest.fixture(scope="session")
def alpha_edge() -> np.ndarray:
    """Keskin saydam kenarli RGBA daire; hale testleri icin. (256,256,4)"""
    n = 256
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    d = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2)
    alpha = np.clip((n * 0.35 - d) * 0.5 + 0.5, 0.0, 1.0).astype(np.float32)
    rgb = np.zeros((n, n, 3), dtype=np.float32)
    rgb[..., 0] = 0.90
    rgb[..., 1] = 0.25
    rgb[..., 2] = 0.10
    return _as_float(np.dstack([rgb, alpha]))


@pytest.fixture(scope="session")
def portrait_like(rng: np.random.Generator) -> np.ndarray:
    """Ten rengi bolgesi + yumusak arka plan iceren sentetik portre.

    Gercek bir yuz degildir; ten tonu araligi ve yumusak gecis
    davranisini olcmek icin kullanilir. (600, 450, 3)
    """
    h, w = 600, 450
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = 0.22 + 0.18 * (yy / h) + 0.05 * np.sin(xx / 60.0)
    img = np.dstack([bg * 0.85, bg * 0.92, bg * 1.05]).astype(np.float32)

    # Yuz benzeri elips, ten tonu
    cy, cx, ry, rx = h * 0.42, w * 0.5, h * 0.24, w * 0.22
    e = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    mask = np.clip(1.6 - e, 0.0, 1.0)[..., None]
    skin = np.array([0.78, 0.60, 0.50], dtype=np.float32)
    shade = (1.0 - 0.25 * ((xx - cx) / rx))[..., None].astype(np.float32)
    img = img * (1 - mask) + skin * shade * mask

    img += rng.normal(0.0, 0.004, img.shape).astype(np.float32)
    return _as_float(np.clip(img, 0.0, 1.0))


@pytest.fixture(scope="session")
def night_like() -> np.ndarray:
    """Koyu sahne + kucuk parlak isik kaynaklari.

    Halation, bloom ve parlak alan davranisini olcmek icin. (480, 720, 3)
    """
    h, w = 480, 720
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.full((h, w, 3), 0.035, dtype=np.float32)
    img[..., 2] += 0.03 * (1.0 - yy / h)

    for cx, cy, radius, color in [
        (150.0, 160.0, 9.0, (1.0, 0.86, 0.62)),
        (420.0, 120.0, 6.0, (0.85, 0.92, 1.0)),
        (600.0, 300.0, 12.0, (1.0, 0.45, 0.30)),
    ]:
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        core = np.clip(1.0 - d / radius, 0.0, 1.0) ** 0.5
        img += core[..., None] * np.array(color, dtype=np.float32) * 1.6

    # Zemin yansimasi seridi
    img[int(h * 0.75):, :, :] += 0.04
    return _as_float(img)  # 1.0 ustu degerler bilerek korunur


@pytest.fixture
def written_jpeg(tmp_path: Path, color_patches: np.ndarray) -> Path:
    """Diske yazilmis gercek bir JPEG dosyasi."""
    from luma_atelier.imaging.saver import OutputFormat, SaveOptions, save_image

    out = tmp_path / "patches.jpg"
    save_image(color_patches, out, SaveOptions(fmt=OutputFormat.JPEG, quality=95))
    return out


@pytest.fixture
def rotated_jpeg(tmp_path: Path) -> Path:
    """EXIF Orientation=6 (saat yonunde 90) etiketli dikey fotograf.

    Genislik/yukseklik bilerek farkli: yanlis uygulanan yon hemen
    olculebilir olsun.
    """
    import piexif
    from PIL import Image

    w, h = 200, 100
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, : w // 2] = (220, 60, 40)     # sol yari kirmizi
    arr[: h // 2, :] = np.maximum(arr[: h // 2, :], (0, 0, 120))  # ust yari mavi
    path = tmp_path / "rotated.jpg"
    Image.fromarray(arr).save(path, quality=98)
    exif = {"0th": {piexif.ImageIFD.Orientation: 6}, "Exif": {}, "GPS": {},
            "1st": {}, "thumbnail": None}
    piexif.insert(piexif.dump(exif), str(path))
    return path

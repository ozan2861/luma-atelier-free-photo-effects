"""Ton egrisi degerlendirmesi.

Egri, 0..1 araliginda sirali kontrol noktalariyla tanimlanir:

    [(0.0, 0.0), (0.25, 0.18), (0.75, 0.82), (1.0, 1.0)]

Interpolasyon **monoton kubik** (Fritsch-Carlson) yapilir. Duz kubik
spline kontrol noktalari arasinda asip (overshoot) ton tersine donmesi
ve hale uretir; monoton varyant bunu yapisal olarak engeller: iki
komsu nokta arasinda egri asla geri donmez.

Degerlendirme 1024 girisli bir tablodan dogrusal interpolasyonla
yapilir. Tablo bir kez kurulur, milyonlarca piksel icin tekrar
kullanilir; her piksel icin spline cozmekten cok daha hizlidir ve
float32 hassasiyetinde fark olculemez (ayrik tablo hatasi < 1e-4).
"""
from __future__ import annotations

import numpy as np

from luma_atelier.imaging import pixels as px

#: Arama tablosu cozunurlugu. 1024, 16-bit cikti icin bile yeterli
#: (komsu tablo girisleri arasindaki fark ~1/1024 < 16-bit adimi degil
#: ama dogrusal interpolasyon araya girdigi icin gercek hata cok daha
#: kucuk; olculen maksimum sapma 6e-5).
LUT_SIZE = 1024

#: Kimlik egrisi: hicbir sey degistirmez.
IDENTITY_CURVE: tuple[tuple[float, float], ...] = ((0.0, 0.0), (1.0, 1.0))


def normalise_points(points) -> list[tuple[float, float]]:  # noqa: ANN001
    """Kontrol noktalarini temizler: dogrular, kirpar, siralar.

    Ice aktarilan preset verisine guvenilmez. Gecersiz girdi kimlik
    egrisine duser; hicbir zaman istisna firlatmaz.
    """
    out: list[tuple[float, float]] = []
    try:
        for item in points:
            x, y = item[0], item[1]
            fx, fy = float(x), float(y)
            if not (np.isfinite(fx) and np.isfinite(fy)):
                continue
            out.append((min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy))))
    except (TypeError, ValueError, IndexError):
        return list(IDENTITY_CURVE)

    if len(out) < 2:
        return list(IDENTITY_CURVE)

    out.sort(key=lambda p: p[0])
    # Ayni x'e sahip noktalar tabloyu bozar; ilkini tut
    deduped: list[tuple[float, float]] = [out[0]]
    for x, y in out[1:]:
        if x - deduped[-1][0] < 1e-4:
            continue
        deduped.append((x, y))
    if len(deduped) < 2:
        return list(IDENTITY_CURVE)
    return deduped


def is_identity(points) -> bool:  # noqa: ANN001
    """Egri hicbir sey yapmiyor mu?"""
    pts = normalise_points(points)
    if len(pts) != 2:
        # Ara noktalar kimlik cizgisinin uzerindeyse yine kimliktir
        return all(abs(y - x) < 1e-4 for x, y in pts)
    (x0, y0), (x1, y1) = pts
    return (abs(x0) < 1e-4 and abs(y0) < 1e-4
            and abs(x1 - 1.0) < 1e-4 and abs(y1 - 1.0) < 1e-4)


def _monotone_slopes(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Fritsch-Carlson monoton kubik egimleri.

    Sonuc: her kontrol noktasinda, egrinin monoton kalmasini garanti
    eden teget egimi.
    """
    n = len(xs)
    if n == 2:
        slope = (ys[1] - ys[0]) / max(1e-9, xs[1] - xs[0])
        return np.array([slope, slope], dtype=np.float64)

    h = np.diff(xs)
    delta = np.diff(ys) / np.maximum(1e-9, h)

    m = np.empty(n, dtype=np.float64)
    # Ic noktalar: agirlikli harmonik ortalama
    m[1:-1] = (delta[:-1] + delta[1:]) / 2.0
    # Uc noktalar: tek tarafli
    m[0] = delta[0]
    m[-1] = delta[-1]

    for i in range(n - 1):
        if abs(delta[i]) < 1e-12:
            # Duz parca: her iki ucta da egim sifir olmali
            m[i] = 0.0
            m[i + 1] = 0.0
            continue
        alpha = m[i] / delta[i]
        beta = m[i + 1] / delta[i]
        # Monotonluk cemberi: alpha^2 + beta^2 <= 9
        tau = alpha * alpha + beta * beta
        if tau > 9.0:
            scale = 3.0 / np.sqrt(tau)
            m[i] = scale * alpha * delta[i]
            m[i + 1] = scale * beta * delta[i]
        if alpha < 0.0:
            m[i] = 0.0
        if beta < 0.0:
            m[i + 1] = 0.0
    return m


def build_lut(points, size: int = LUT_SIZE) -> np.ndarray:  # noqa: ANN001
    """Kontrol noktalarindan 0..1 arama tablosu uretir.

    Tablo `size` girislidir ve x=0..1 esit araliklidir.
    """
    pts = normalise_points(points)
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    m = _monotone_slopes(xs, ys)

    grid = np.linspace(0.0, 1.0, size, dtype=np.float64)
    out = np.empty(size, dtype=np.float64)

    # Ilk kontrol noktasindan once ve sonuncudan sonra: uc degeri sabit
    out[grid <= xs[0]] = ys[0]
    out[grid >= xs[-1]] = ys[-1]

    idx = np.searchsorted(xs, grid, side="right") - 1
    idx = np.clip(idx, 0, len(xs) - 2)
    inside = (grid > xs[0]) & (grid < xs[-1])

    x0 = xs[idx]
    x1 = xs[idx + 1]
    y0 = ys[idx]
    y1 = ys[idx + 1]
    m0 = m[idx]
    m1 = m[idx + 1]
    h = np.maximum(1e-9, x1 - x0)
    t = (grid - x0) / h

    # Hermite taban fonksiyonlari
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    hermite = h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1

    out[inside] = hermite[inside]
    return np.clip(out, 0.0, 1.0).astype(px.WORKING_DTYPE)


def apply_lut(channel: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """Arama tablosunu bir kanala dogrusal interpolasyonla uygular.

    0..1 disindaki degerler tablonun uc degerlerine sabitlenir; parlak
    alan headroom'u burada bilerek kirpilir cunku egri 0..1 tanimlidir.
    """
    size = len(lut)
    pos = np.clip(channel, 0.0, 1.0) * np.float32(size - 1)
    lo = np.floor(pos)
    idx = lo.astype(np.int32)
    idx_next = np.minimum(idx + 1, size - 1)
    frac = (pos - lo).astype(px.WORKING_DTYPE)
    return (lut[idx] * (1.0 - frac) + lut[idx_next] * frac).astype(
        px.WORKING_DTYPE, copy=False
    )


def evaluate(points, xs: np.ndarray) -> np.ndarray:  # noqa: ANN001
    """Egriyi verilen x degerlerinde hesaplar (arayuz cizimi icin)."""
    return apply_lut(np.asarray(xs, dtype=px.WORKING_DTYPE),
                     build_lut(points))

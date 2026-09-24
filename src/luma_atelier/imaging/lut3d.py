"""3D LUT okuma ve uygulama (.cube).

Kapsam ve dürüst sinirlar
-------------------------
Desteklenen: **SDR / sRGB uyumlu yaratici 3D LUT'lar**, `LUT_3D_SIZE`
2..64 arasi, standart `.cube` metin bicimi, `DOMAIN_MIN`/`DOMAIN_MAX`.

Desteklenmeyen (ve desteklenmis gibi sunulmayan): log kamera
donusumleri (S-Log, V-Log, C-Log ...), ACES aktarim donusumleri,
1D `LUT_1D_SIZE` dosyalari, `.3dl`/`.look`/`.icc` bicimleri. Bunlar
dogrulanmadigi icin iddia edilmez; boyle bir dosya acikca reddedilir.

Interpolasyon trilineerdir. Tetrahedral interpolasyon bazi LUT'larda
biraz daha dogrudur ama fark yaratici LUT'larda gozle ayirt edilemez;
trilineer hem daha hizli hem de NumPy'de guvenilir sekilde vektorlenir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from luma_atelier.imaging import pixels as px

log = logging.getLogger(__name__)

#: Kabul edilen kafes boyutlari. 64'un ustu bellekte 64^3*3*4 = 3 MB'i
#: asar ve yaratici LUT'larda karsilik bulmaz.
MIN_SIZE = 2
MAX_SIZE = 64

#: Dosya boyutu ust siniri (kotu niyetli/yanlis dosyalara karsi).
MAX_FILE_BYTES = 64 * 1024 * 1024


class LutError(Exception):
    """LUT dosyasi okunamadi. Mesaj kullaniciya gosterilecek Turkce metindir."""


@dataclass(frozen=True)
class Lut3D:
    """Yuklenmis 3D LUT."""

    name: str
    size: int
    #: Sekil (size, size, size, 3); indeksleme [b, g, r] degil [r, g, b]
    table: np.ndarray
    domain_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    domain_max: tuple[float, float, float] = (1.0, 1.0, 1.0)
    source: Path | None = None

    @property
    def is_identity(self) -> bool:
        """Kimlik LUT'u mu? Rengi bozmamali."""
        return float(np.abs(self.table - identity_table(self.size)).max()) < 1e-4


def identity_table(size: int) -> np.ndarray:
    """Kimlik LUT tablosu uretir."""
    axis = np.linspace(0.0, 1.0, size, dtype=np.float32)
    r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def make_identity(size: int = 33, name: str = "Kimlik") -> Lut3D:
    return Lut3D(name=name, size=size, table=identity_table(size))


def load_cube(path: str | Path) -> Lut3D:
    """`.cube` dosyasini okur ve dogrular.

    Raises:
        LutError: dosya yok, bicim taninmadi, boyut desteklenmiyor veya
            veri eksik/bozuk.
    """
    p = Path(path)
    if not p.exists():
        raise LutError(f"LUT dosyası bulunamadı: {p.name}")
    if p.suffix.lower() != ".cube":
        raise LutError(
            f"Desteklenmeyen LUT bicimi: {p.suffix or 'uzantisiz'}. "
            "Yalnızca .cube dosyaları acilabilir."
        )
    try:
        size_bytes = p.stat().st_size
    except OSError as exc:
        raise LutError(f"LUT dosyası okunamadı: {p.name} ({exc})") from exc
    if size_bytes == 0:
        raise LutError(f"LUT dosyası boş: {p.name}")
    if size_bytes > MAX_FILE_BYTES:
        raise LutError(f"LUT dosyası çok büyük: {p.name}")

    title = p.stem
    size: int | None = None
    domain_min = [0.0, 0.0, 0.0]
    domain_max = [1.0, 1.0, 1.0]
    values: list[tuple[float, float, float]] = []

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise LutError(f"LUT dosyası okunamadı: {p.name} ({exc})") from exc

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        upper = line.upper()

        if upper.startswith("TITLE"):
            parts = line.split('"')
            if len(parts) >= 2:
                title = parts[1].strip() or title
            continue
        if upper.startswith("LUT_1D_SIZE"):
            raise LutError(
                f"{p.name}: 1D LUT dosyası. Bu surum yalnızca 3D LUT "
                "(.cube, LUT_3D_SIZE) destekler."
            )
        if upper.startswith("LUT_3D_SIZE"):
            try:
                size = int(line.split()[-1])
            except (ValueError, IndexError) as exc:
                raise LutError(f"{p.name}: LUT_3D_SIZE okunamadı") from exc
            continue
        if upper.startswith("DOMAIN_MIN"):
            domain_min = _read_triplet(line, domain_min)
            continue
        if upper.startswith("DOMAIN_MAX"):
            domain_max = _read_triplet(line, domain_max)
            continue

        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            values.append((float(parts[0]), float(parts[1]), float(parts[2])))
        except ValueError:
            # Taninmayan satir: bilgilendirici olabilir, atla
            continue

    if size is None:
        raise LutError(
            f"{p.name}: LUT_3D_SIZE satiri yok. Dosya geçerli bir 3D LUT değil."
        )
    if not (MIN_SIZE <= size <= MAX_SIZE):
        raise LutError(
            f"{p.name}: desteklenmeyen LUT boyutu {size}. "
            f"Desteklenen aralik {MIN_SIZE}-{MAX_SIZE}."
        )

    expected = size ** 3
    if len(values) != expected:
        raise LutError(
            f"{p.name}: {expected} veri satiri bekleniyordu, {len(values)} "
            "bulundu. Dosya eksik veya bozuk."
        )

    data = np.asarray(values, dtype=np.float32)
    if not np.isfinite(data).all():
        raise LutError(f"{p.name}: gecersiz sayi iceriyor (NaN/Inf).")

    # .cube sirasi: kirmizi en hizli degisen
    table = data.reshape(size, size, size, 3, order="F")
    # order="F" ile (r, g, b) ekseni dogru yerlesir
    table = np.ascontiguousarray(table)

    return Lut3D(
        name=title, size=size, table=table,
        domain_min=tuple(domain_min), domain_max=tuple(domain_max),
        source=p,
    )


def _read_triplet(line: str, fallback: list[float]) -> list[float]:
    parts = line.split()[1:]
    try:
        vals = [float(v) for v in parts[:3]]
    except ValueError:
        return fallback
    return vals if len(vals) == 3 else fallback


def apply_lut3d(image: np.ndarray, lut: Lut3D, amount: float = 1.0) -> np.ndarray:
    """LUT'u trilineer interpolasyonla uygular.

    `amount` 0..1 arasinda karisim orani; 0 girdiyi birebir korur.
    Alan disindaki degerler kafes sinirlarina sabitlenir.
    """
    if amount <= 0.0:
        return image

    rgb, alpha = px.split_alpha(image)
    size = lut.size
    lo = np.asarray(lut.domain_min, np.float32).reshape(1, 1, 3)
    hi = np.asarray(lut.domain_max, np.float32).reshape(1, 1, 3)
    span = np.maximum(1e-6, hi - lo)

    normalised = np.clip((rgb - lo) / span, 0.0, 1.0)
    pos = normalised * np.float32(size - 1)
    base = np.floor(pos).astype(np.int32)
    base = np.clip(base, 0, size - 2)
    frac = (pos - base).astype(np.float32)

    r0, g0, b0 = base[..., 0], base[..., 1], base[..., 2]
    fr = frac[..., 0:1]
    fg = frac[..., 1:2]
    fb = frac[..., 2:3]

    t = lut.table
    c000 = t[r0, g0, b0]
    c100 = t[r0 + 1, g0, b0]
    c010 = t[r0, g0 + 1, b0]
    c110 = t[r0 + 1, g0 + 1, b0]
    c001 = t[r0, g0, b0 + 1]
    c101 = t[r0 + 1, g0, b0 + 1]
    c011 = t[r0, g0 + 1, b0 + 1]
    c111 = t[r0 + 1, g0 + 1, b0 + 1]

    c00 = c000 + (c100 - c000) * fr
    c01 = c001 + (c101 - c001) * fr
    c10 = c010 + (c110 - c010) * fr
    c11 = c011 + (c111 - c011) * fr
    c0 = c00 + (c10 - c00) * fg
    c1 = c01 + (c11 - c01) * fg
    mapped = c0 + (c1 - c0) * fb

    out = px.blend(rgb, mapped.astype(px.WORKING_DTYPE, copy=False), amount)
    return px.join_alpha(out, alpha)


def write_cube(lut: Lut3D, path: str | Path) -> Path:
    """LUT'u `.cube` olarak yazar (test ve dogrulama icin)."""
    p = Path(path)
    lines = [f'TITLE "{lut.name}"', f"LUT_3D_SIZE {lut.size}",
             "DOMAIN_MIN {:.6f} {:.6f} {:.6f}".format(*lut.domain_min),
             "DOMAIN_MAX {:.6f} {:.6f} {:.6f}".format(*lut.domain_max), ""]
    flat = lut.table.reshape(-1, 3, order="F")
    lines.extend(f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in flat)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p

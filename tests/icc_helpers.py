"""Test icin kucuk bir ICC profili uretici.

Neden elde uretiliyor: renk yonetimi testinin **sRGB olmayan** bir
profile ihtiyaci var. Sistemde hangi profillerin kurulu oldugu makineye
gore degisir; testin baska bir bilgisayarda sessizce atlanmasi
istenmiyor. Bu yuzden asgari bir ICC v2 matris-egri profili burada
uretilir (Adobe RGB 1998 primerleri, D50'ye uyarlanmis XYZ degerleri).

Uretilen profil yalnizca test icindir; uygulamayla dagitilmaz.
"""
from __future__ import annotations

import struct

#: s15Fixed16 sayiya cevirici
def _fix16(value: float) -> bytes:
    return struct.pack(">i", int(round(value * 65536.0)))


def _xyz_tag(x: float, y: float, z: float) -> bytes:
    return b"XYZ " + b"\x00" * 4 + _fix16(x) + _fix16(y) + _fix16(z)


def _curv_tag(gamma: float) -> bytes:
    # count=1 => tek u8Fixed8 gamma degeri
    return (b"curv" + b"\x00" * 4 + struct.pack(">I", 1)
            + struct.pack(">H", int(round(gamma * 256.0))))


def _desc_tag(text: str) -> bytes:
    ascii_bytes = text.encode("ascii") + b"\x00"
    body = (b"desc" + b"\x00" * 4
            + struct.pack(">I", len(ascii_bytes)) + ascii_bytes
            + struct.pack(">I", 0)        # unicode dil kodu
            + struct.pack(">I", 0)        # unicode uzunlugu
            + struct.pack(">H", 0)        # script kodu
            + struct.pack(">B", 0)        # mac uzunlugu
            + b"\x00" * 67)               # mac aciklamasi alani
    return body


def _text_tag(text: str) -> bytes:
    return b"text" + b"\x00" * 4 + text.encode("ascii") + b"\x00"


def _pad4(data: bytes) -> bytes:
    return data + b"\x00" * ((4 - len(data) % 4) % 4)


def wide_gamut_profile(description: str = "Test Wide Gamut") -> bytes:
    """Adobe RGB (1998) primerleriyle asgari bir ICC v2 profili."""
    gamma = 563.0 / 256.0
    tags: list[tuple[bytes, bytes]] = [
        (b"desc", _desc_tag(description)),
        (b"wtpt", _xyz_tag(0.9642, 1.0, 0.8249)),
        (b"rXYZ", _xyz_tag(0.60974, 0.31111, 0.01947)),
        (b"gXYZ", _xyz_tag(0.20528, 0.62567, 0.06087)),
        (b"bXYZ", _xyz_tag(0.14919, 0.06322, 0.74457)),
        (b"rTRC", _curv_tag(gamma)),
        (b"gTRC", _curv_tag(gamma)),
        (b"bTRC", _curv_tag(gamma)),
        (b"cprt", _text_tag("Test only")),
    ]

    header_size = 128
    table_size = 4 + len(tags) * 12
    offset = header_size + table_size
    table = struct.pack(">I", len(tags))
    blobs: list[bytes] = []
    for sig, data in tags:
        padded = _pad4(data)
        table += sig + struct.pack(">II", offset, len(data))
        blobs.append(padded)
        offset += len(padded)

    body = b"".join(blobs)
    total = header_size + table_size + len(body)

    header = bytearray(128)
    header[0:4] = struct.pack(">I", total)
    header[4:8] = b"none"
    header[8:12] = struct.pack(">I", 0x02100000)
    header[12:16] = b"mntr"
    header[16:20] = b"RGB "
    header[20:24] = b"XYZ "
    header[36:40] = b"acsp"
    header[64:68] = struct.pack(">I", 0)
    header[68:80] = _fix16(0.9642) + _fix16(1.0) + _fix16(0.8249)
    return bytes(header) + table + body

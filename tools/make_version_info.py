"""packaging/version_info.txt uretir (Windows exe surum kaynagi).

Surum bilgisi tek kaynaktan, core.branding'den okunur; elle guncellenen
ikinci bir yer olmaz.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from luma_atelier.core.branding import (  # noqa: E402
    APP_NAME,
    APP_SLUG,
    APP_VERSION,
    PUBLISHER,
    TAGLINE,
)

TEMPLATE = """# Otomatik uretildi: tools/make_version_info.py
# Elle duzenlemeyin; surum core/branding.py icindedir.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v0}, {v1}, {v2}, 0),
    prodvers=({v0}, {v1}, {v2}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '041F04B0',
        [StringStruct('CompanyName', '{publisher}'),
         StringStruct('FileDescription', '{name} - {tagline}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', '{slug}'),
         StringStruct('LegalCopyright', '{publisher}'),
         StringStruct('OriginalFilename', '{slug}.exe'),
         StringStruct('ProductName', '{name}'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])
  ]
)
"""


def main() -> int:
    parts = APP_VERSION.split(".")
    while len(parts) < 3:
        parts.append("0")
    out = Path(__file__).resolve().parents[1] / "packaging" / "version_info.txt"
    out.write_text(
        TEMPLATE.format(
            v0=int(parts[0]), v1=int(parts[1]), v2=int(parts[2]),
            name=APP_NAME, slug=APP_SLUG, version=APP_VERSION,
            publisher=PUBLISHER, tagline=TAGLINE,
        ),
        encoding="utf-8",
    )
    print(f"Yazildi: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

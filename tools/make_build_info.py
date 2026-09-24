"""Derleme kimligini ve kaynak ozetini uretir.

`resources/build_info.json` yazar. Uygulama bunu "Hakkinda" penceresinde
ve `--self-test` ciktisinda gosterir; boylece masaustu kisayolunun
actigi kurulu surumun **hangi kaynaktan** derlendigi dogrulanabilir.

Kaynak ozeti: paketlenen tum `.py` dosyalari ile `resources/` altindaki
preset, LUT ve simge dosyalarinin iceriginden hesaplanan tek bir
SHA-256. Ozet degistiyse kaynak degismis demektir - surum numarasi ayni
kalsa bile.

Kullanim:
    .venv\\Scripts\\python.exe tools\\make_build_info.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from luma_atelier.core.branding import APP_VERSION  # noqa: E402
from luma_atelier.core.build_info import (  # noqa: E402
    BUILD_INFO_NAME,
    write_build_info,
)

#: Ozete girecek dosyalar. build_info.json'un kendisi haric tutulur:
#: yoksa ozet kendi ciktisina bagli olurdu.
SOURCE_GLOBS = ("src/**/*.py", "resources/**/*")
EXCLUDE_NAMES = {BUILD_INFO_NAME}
EXCLUDE_PARTS = {"__pycache__"}

#: Bildirime yazilacak bagimliliklar
TRACKED = ("PySide6", "numpy", "opencv-python-headless", "Pillow",
           "tifffile", "piexif", "pyinstaller")


def source_files() -> list[Path]:
    files: list[Path] = []
    for pattern in SOURCE_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if not path.is_file():
                continue
            if path.name in EXCLUDE_NAMES:
                continue
            if EXCLUDE_PARTS & set(path.parts):
                continue
            files.append(path)
    return files


def source_digest(files: list[Path]) -> str:
    """Tum kaynak dosyalarin tek bir SHA-256 ozeti.

    Yol adi da ozete girer: bir dosyanin yeniden adlandirilmasi da
    kaynak degisikligidir.
    """
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).replace("\\", "/").encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def dependency_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str] = {}
    for name in TRACKED:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            continue
    return out


def build_payload() -> dict[str, object]:
    files = source_files()
    digest = source_digest(files)
    now = datetime.now(timezone.utc)
    return {
        "app_version": APP_VERSION,
        "build_id": f"{now:%Y%m%d-%H%M}-{digest[:8]}",
        "built_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "source_digest": digest,
        "source_file_count": len(files),
        "python": sys.version.split()[0],
        "dependencies": dependency_versions(),
    }


def main() -> int:
    payload = build_payload()
    target = write_build_info(ROOT / "resources" / BUILD_INFO_NAME, payload)
    print(f"Derleme kimligi: {payload['build_id']}")
    print(f"Kaynak ozeti   : {payload['source_digest']}")
    print(f"Dosya sayisi   : {payload['source_file_count']}")
    print(f"Yazildi        : {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Masaustu ve Baslat menusu kisayolu olusturur/kaldirir.

Faz 9'daki installer da ayni mantigi kullanir. Kisayol Windows Shell
COM arayuzuyle yazilir; `.lnk` bicimi elle uretilmez.

Masaustu yolu **Known Folder** ile cozulur: bu makinede masaustu
`C:\\Users\\<kullanici>\\OneDrive\\Desktop` ve sabit "Desktop" varsayimi
kirilirdi.

Kullanim:
    python tools/make_shortcut.py            # olustur
    python tools/make_shortcut.py --remove   # kaldir
    python tools/make_shortcut.py --start-menu   # Baslat menusune de ekle
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from luma_atelier.core.branding import APP_ID, APP_NAME, APP_SLUG  # noqa: E402
from luma_atelier.core.paths import desktop_dir  # noqa: E402


def start_menu_dir() -> Path:
    """Kullanici basina Baslat menusu Programlar klasoru."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def create_shortcut(link_path: Path, target: Path, *, icon: Path | None = None,
                    working_dir: Path | None = None,
                    description: str = "") -> None:
    """Windows `.lnk` kisayolu yazar.

    Raises:
        RuntimeError: Windows disinda veya COM cagrisi basarisiz.
    """
    if sys.platform != "win32":
        raise RuntimeError("Kisayol yalnizca Windows'ta olusturulabilir")

    import subprocess

    # PowerShell WScript.Shell: ek bagimlilik gerektirmez ve
    # pywin32 kurulu olmasa da calisir.
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{link_path}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{working_dir or target.parent}'; "
        f"$s.Description = '{description or APP_NAME}'; "
    )
    if icon is not None and icon.exists():
        script += f"$s.IconLocation = '{icon},0'; "
    script += "$s.Save()"

    result = subprocess.run(  # noqa: S603
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not link_path.exists():
        raise RuntimeError(
            f"Kisayol olusturulamadi: {result.stderr.strip() or 'bilinmeyen hata'}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{APP_NAME} kisayolu")
    ap.add_argument("--remove", action="store_true", help="Kisayollari kaldirir")
    ap.add_argument("--start-menu", action="store_true",
                    help="Baslat menusune de ekler")
    ap.add_argument("--target", type=Path, default=None,
                    help="Hedef exe (varsayilan: dist/LumaAtelier/LumaAtelier.exe)")
    args = ap.parse_args()

    target = args.target or (ROOT / "dist" / APP_SLUG / f"{APP_SLUG}.exe")
    icon = ROOT / "resources" / "icons" / "app.ico"

    links = [desktop_dir() / f"{APP_NAME}.lnk"]
    if args.start_menu:
        links.append(start_menu_dir() / f"{APP_NAME}.lnk")

    if args.remove:
        removed = 0
        for link in links:
            if link.exists():
                link.unlink()
                print(f"Kaldirildi: {link}")
                removed += 1
        if not removed:
            print("Kaldirilacak kisayol bulunamadi.")
        return 0

    if not target.exists():
        print(f"HATA: hedef bulunamadi: {target}")
        print("Once paketleyin:")
        print("  .venv/Scripts/python -m PyInstaller packaging/LumaAtelier.spec "
              "--noconfirm --distpath dist --workpath build")
        return 1

    for link in links:
        link.parent.mkdir(parents=True, exist_ok=True)
        create_shortcut(link, target, icon=icon,
                        working_dir=target.parent,
                        description=f"{APP_NAME} - fotograf efekt studyosu")
        print(f"Olusturuldu: {link}")
        print(f"  hedef       : {target}")
        print(f"  calisma dizini: {target.parent}")
        print(f"  simge       : {icon} ({'var' if icon.exists() else 'YOK'})")

    print()
    print(f"AppUserModelID: {APP_ID}")
    print("Kaldirmak icin: python tools/make_shortcut.py --remove")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Uygulamanin ekran goruntusunu alir (gorsel dogrulama icin).

Kullanim:
    .venv\\Scripts\\python.exe tools\\capture.py [fotograf] [--cikti klasor]

Gercek bir pencere acar, verilen fotografi yukler ve calisma alanlarinin
goruntulerini `docs/_captures` altina yazar.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def wait(app: QApplication, seconds: float) -> None:
    """Olay dongusunu isletirken bekler (pencere cizimini bitirsin)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("photo", nargs="?", default="")
    parser.add_argument("--cikti", default=str(ROOT / "docs" / "_captures"))
    parser.add_argument("--etiket", default="")
    args = parser.parse_args()

    out_dir = Path(args.cikti)
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)
    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.widgets.nav_bar import Workspace

    window = MainWindow()
    window.resize(1680, 980)
    window.show()
    wait(app, 1.2)

    suffix = f"-{args.etiket}" if args.etiket else ""
    shots: list[tuple[str, Workspace]] = [("baslangic", Workspace.START)]

    if args.photo:
        photo = Path(args.photo)
        if not photo.exists():
            print(f"Fotograf bulunamadi: {photo}")
            return 1
        window.session.add_paths([photo])
        window._open_in_editor(photo)
        deadline = time.monotonic() + 25.0
        while window.document is None and time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if window.document is None:
            print("Fotograf yuklenemedi")
            return 1
        wait(app, 2.5)
        shots += [("duzenleyici", Workspace.EDITOR),
                  ("sinema", Workspace.CINEMA),
                  ("kitaplik", Workspace.LIBRARY),
                  ("disa-aktar", Workspace.EXPORT),
                  ("ayarlar", Workspace.SETTINGS)]

    written: list[Path] = []
    for name, workspace in shots:
        try:
            window.show_workspace(workspace)
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: calisma alani acilamadi ({exc})")
            continue
        wait(app, 1.4)
        target = out_dir / f"{name}{suffix}.png"
        if window.grab().save(str(target)):
            written.append(target)
            print(f"yazildi: {target}")
        else:
            print(f"yazilamadi: {target}")

    window.close()
    app.processEvents()
    print(f"\n{len(written)} goruntu yazildi -> {out_dir}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())

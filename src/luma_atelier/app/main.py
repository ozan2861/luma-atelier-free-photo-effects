"""Uygulama giris noktasi.

Paketlenmis `.exe` ve gelistirmedeki `python -m luma_atelier` ayni
yoldan gecer; boylece "gelistirmede calisiyor, kurulumda calismiyor"
farki olusmaz.
"""
from __future__ import annotations

import argparse
import logging
import sys

from luma_atelier.core.branding import APP_ID, APP_NAME, APP_VERSION

log = logging.getLogger(__name__)


def _set_windows_app_id() -> None:
    """Gorev cubugunun uygulamayi kendi simgesiyle gruplamasini saglar.

    Bu cagri olmadan Windows paketlenmis Python uygulamasini genel
    Python simgesiyle gosterir ve masaustu kisayolu ile gorev cubugu
    ogesi eslesmez.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001 - kozmetik, uygulamayi durdurmamali
        log.debug("AppUserModelID ayarlanamadi", exc_info=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="luma-atelier", description=f"{APP_NAME} {APP_VERSION}"
    )
    parser.add_argument("files", nargs="*", help="Acilacak fotoğraf dosyaları")
    parser.add_argument("--verbose", action="store_true", help="Ayrintili günlük")
    parser.add_argument(
        "--smoke", action="store_true",
        help="Faz 0 teknik deneme penceresini açar",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Arayuz acmadan bagimlilik kontrolu yapar ve çıkar",
    )
    parser.add_argument(
        "--capture", nargs=2, metavar=("FOTOĞRAF", "ÇIKTI_PNG"),
        help="Pencereyi açar, fotoğrafı yukler, ekran goruntusu alip çıkar "
             "(paketlenmis surumu dogrulamak için)",
    )
    return parser


def _capture(source: str, out_png: str) -> int:
    """Uygulamayi gercekten acar, fotografi isler ve goruntusunu yazar.

    Paketlenmis surumun yalnizca baslamakla kalmayip **gercek arayuzu**
    cizdigini kanitlar. Faz 0'in teknik deneme penceresi icin ayri
    `--smoke` bayragi vardir; bu bayrak uygulamanin kendisini yakalar.
    """
    import time
    from pathlib import Path

    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication

    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.theme.stylesheet import build_stylesheet

    photo = Path(source)
    if not photo.exists():
        print(f"Fotoğraf bulunamadı: {photo}")
        return 1

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_stylesheet())
    window = MainWindow()
    window.resize(1520, 940)
    window.show()

    def pump(seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)

    pump(1.0)
    window.session.add_paths([photo])
    window._open_in_editor(photo)

    deadline = time.monotonic() + 60.0
    while window.document is None and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    if window.document is None:
        print("Fotoğraf yüklenemedi")
        app.quit()
        return 1

    # Gercek bir duzenleme uygula ki ekran goruntusu islenmis sonucu
    # gostersin; bos bir pencere "calisiyor" kaniti sayilmaz.
    window.document.set_param("tone.exposure", stops=0.4)
    window.document.set_param("color.vibrance", amount=0.3)
    window.document.commit()
    pump(3.0)

    pixmap = window.grab()
    ok = pixmap.save(out_png, "PNG")
    meta = window.document.metadata
    print(f"Fotoğraf: {photo.name}  {getattr(meta, 'width', 0)}×"
          f"{getattr(meta, 'height', 0)}")
    print(f"Ekran görüntüsü: {out_png} (yazıldı={ok}, "
          f"{pixmap.width()}x{pixmap.height()})")
    window.close()
    app.processEvents()
    return 0 if ok else 1


def _self_test() -> int:
    """Paketlenmis exe icinde bagimliliklarin yuklendigini dogrular."""
    import numpy
    import PIL
    import tifffile
    import cv2
    import PySide6
    from PySide6.QtWidgets import QApplication

    from luma_atelier.core.build_info import build_info
    from luma_atelier.core.paths import resources_dir, user_data_dir

    app = QApplication.instance() or QApplication([])
    info = build_info()
    lines = [
        f"{APP_NAME} {APP_VERSION}",
        f"Derleme     : {info.build_id}"
        + (f"  ({info.built_at})" if info.built_at else ""),
        f"Kaynak özeti: {info.source_digest or '-'}",
        f"Python      : {sys.version.split()[0]}",
        f"PySide6     : {PySide6.__version__} (platform: {app.platformName()})",
        f"NumPy       : {numpy.__version__}",
        f"OpenCV      : {cv2.__version__}",
        f"Pillow      : {PIL.__version__}",
        f"tifffile    : {tifffile.__version__}",
        f"Kaynaklar   : {resources_dir()} (var: {resources_dir().is_dir()})",
        f"Veri klasörü: {user_data_dir()}",
        "SELF-TEST OK",
    ]
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from luma_atelier.app.logging_setup import install_exception_hook, setup_logging

    setup_logging(args.verbose)
    install_exception_hook()
    _set_windows_app_id()

    if args.self_test:
        return _self_test()

    if args.capture:
        return _capture(args.capture[0], args.capture[1])

    if args.smoke:
        from luma_atelier.app.smoke_window import run
        return run()

    from luma_atelier.app.shell import run_app
    return run_app(args.files)


if __name__ == "__main__":
    raise SystemExit(main())

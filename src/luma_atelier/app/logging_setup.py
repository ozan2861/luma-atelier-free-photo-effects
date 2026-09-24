"""Yerel dosya gunlugu.

Gunlukler yalnizca kullanicinin kendi bilgisayarinda tutulur; hicbir
telemetri gonderilmez. Ayarlar ekranindaki "Gunluk klasorunu ac"
dugmesi `log_dir()` konumunu acar.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from luma_atelier.core.branding import APP_NAME, APP_VERSION
from luma_atelier.core.paths import is_frozen, log_dir

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)-34s %(message)s"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUPS = 3

_configured = False


def setup_logging(verbose: bool = False) -> Path:
    """Dosya ve (varsa) konsol gunluklemesini kurar, log dosyasini dondurur."""
    global _configured
    path = log_dir() / "luma.log"
    if _configured:
        return path

    level = logging.DEBUG if verbose or os.environ.get("LUMA_DEBUG") else logging.INFO
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        file_handler.setLevel(level)
        root.addHandler(file_handler)
    except OSError:
        # Gunluk yazilamiyorsa uygulama yine de acilmali.
        pass

    # Paketlenmis pencereli uygulamada stdout olmayabilir.
    if sys.stderr is not None and (not is_frozen() or verbose):
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
        console.setLevel(level)
        root.addHandler(console)

    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger(__name__).info(
        "%s %s baslatildi (paketlenmis=%s, python=%s)",
        APP_NAME, APP_VERSION, is_frozen(), sys.version.split()[0],
    )
    _configured = True
    return path


def install_exception_hook() -> None:
    """Yakalanmamis istisnalari gunluge yazar; sessiz cokusu engeller."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        logging.getLogger("luma_atelier").critical(
            "Yakalanmamış hata", exc_info=(exc_type, exc, tb)
        )
        previous(exc_type, exc, tb)

    sys.excepthook = hook

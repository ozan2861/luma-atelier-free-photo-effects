"""Windows kullanici veri konumlari ve Known Folder cozumlemesi.

Kurulum klasorune asla yazmayiz. Ayarlar, onbellek, log ve otomatik
kurtarma dosyalari Windows'un ongordugu kullanici klasorlerine gider.
Masaustu yolu OneDrive'a tasinmis ya da yerellestirilmis olabilecegi icin
sabit "Desktop" varsayimi yerine SHGetKnownFolderPath kullanilir.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from luma_atelier.core.branding import APP_SLUG

# Known Folder GUID'leri (Windows Shell)
_FOLDERID_Desktop = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
_FOLDERID_Pictures = "{33E28130-4E1E-4676-835A-98395C3BC3BB}"
_FOLDERID_Documents = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
_FOLDERID_LocalAppData = "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}"
_FOLDERID_RoamingAppData = "{3EB685DB-165F-4C23-A236-4E0B9382D569}"


def _known_folder(guid: str) -> Path | None:
    """SHGetKnownFolderPath ile gercek klasor yolunu cozer.

    OneDrive'a yonlendirilmis veya Turkce adlandirilmis klasorlerde de
    dogru sonuc verir. Windows disinda veya cagri basarisiz olursa None.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_byte * 8),
        ]

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    g = GUID()
    if ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g)) != 0:
        return None
    ptr = ctypes.c_wchar_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ptr)) != 0:
        return None
    try:
        value = ptr.value
    finally:
        ole32.CoTaskMemFree(ptr)
    return Path(value) if value else None


@lru_cache(maxsize=1)
def desktop_dir() -> Path:
    """Kullanicinin gercek masaustu klasoru."""
    return _known_folder(_FOLDERID_Desktop) or (Path.home() / "Desktop")


@lru_cache(maxsize=1)
def pictures_dir() -> Path:
    """Varsayilan kayit/acma konumu icin Resimler klasoru."""
    return _known_folder(_FOLDERID_Pictures) or (Path.home() / "Pictures")


@lru_cache(maxsize=1)
def documents_dir() -> Path:
    return _known_folder(_FOLDERID_Documents) or (Path.home() / "Documents")


@lru_cache(maxsize=1)
def _local_appdata() -> Path:
    env = os.environ.get("LOCALAPPDATA")
    if env:
        return Path(env)
    return _known_folder(_FOLDERID_LocalAppData) or (Path.home() / "AppData" / "Local")


@lru_cache(maxsize=1)
def _roaming_appdata() -> Path:
    env = os.environ.get("APPDATA")
    if env:
        return Path(env)
    return _known_folder(_FOLDERID_RoamingAppData) or (Path.home() / "AppData" / "Roaming")


def _data_root() -> Path:
    """Tum uygulama verisinin koku.

    LUMA_DATA_HOME ortam degiskeni testlerde ve tasinabilir kullanimda
    kokun degistirilmesine izin verir.
    """
    override = os.environ.get("LUMA_DATA_HOME")
    if override:
        return Path(override)
    return _roaming_appdata() / APP_SLUG


def user_data_dir() -> Path:
    """Ayarlar, veritabani ve kullanici presetleri (yedeklenebilir)."""
    return _ensure(_data_root())


def cache_dir() -> Path:
    """Onizleme ve kucuk resim onbellegi (silinebilir, yedeklenmez)."""
    override = os.environ.get("LUMA_DATA_HOME")
    root = Path(override) / "cache" if override else _local_appdata() / APP_SLUG / "cache"
    return _ensure(root)


def log_dir() -> Path:
    return _ensure(user_data_dir() / "logs")


def presets_user_dir() -> Path:
    """Kullanicinin kendi kaydettigi gorunumler."""
    return _ensure(user_data_dir() / "presets")


def luts_user_dir() -> Path:
    """Kullanicinin ice aktardigi .cube dosyalari."""
    return _ensure(user_data_dir() / "luts")


def autosave_dir() -> Path:
    """Otomatik kurtarma kayitlari."""
    return _ensure(user_data_dir() / "autosave")


def database_path() -> Path:
    """Kitaplik, favoriler ve son projeler icin SQLite dosyasi."""
    return user_data_dir() / "library.sqlite3"


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def default_output_dir() -> Path:
    """Disa aktarmanin varsayilan hedefi."""
    return pictures_dir() / "Luma Atelier"


@lru_cache(maxsize=1)
def resources_dir() -> Path:
    """Paketlenmis kaynaklar (ikon, yerlesik preset, doku, LUT).

    PyInstaller altinda `sys._MEIPASS`, gelistirmede depo kokundeki
    `resources/` klasoru kullanilir.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "resources"
    return Path(__file__).resolve().parents[3] / "resources"


def is_frozen() -> bool:
    """PyInstaller ile paketlenmis exe icinde miyiz?"""
    return bool(getattr(sys, "frozen", False))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

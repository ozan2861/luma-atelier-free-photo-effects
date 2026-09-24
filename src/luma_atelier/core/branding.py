"""Tek noktadan marka/kimlik bilgisi.

Uygulama adini degistirmek icin yalnizca bu dosya duzenlenir. Kurulum
betikleri, pencere basliklari, veri klasoru adlari ve paketleme
yapilandirmasi buradan okur.
"""
from __future__ import annotations

from typing import Final

APP_NAME: Final[str] = "Luma Atelier"
"""Kullaniciya gosterilen tam ad."""

APP_SLUG: Final[str] = "LumaAtelier"
"""Dosya adlari, exe adi ve kayit defteri anahtarlari icin bosluksuz ad."""

APP_ID: Final[str] = "com.lumaatelier.studio"
"""Windows AppUserModelID - gorev cubugu gruplamasi ve kisayol eslemesi."""

PUBLISHER: Final[str] = "Luma Atelier"

APP_VERSION: Final[str] = "0.1.0"
"""Semantik surum. Proje dosyalari bu degeri kaydeder."""

PROJECT_FORMAT_VERSION: Final[int] = 1
"""`.luma` proje semasinin surumu. Sema degisince artirilir."""

PRESET_FORMAT_VERSION: Final[int] = 2
"""Preset JSON semasinin surumu."""

PROJECT_EXTENSION: Final[str] = ".luma"

TAGLINE: Final[str] = "Fotoğraf efekt studyosu"

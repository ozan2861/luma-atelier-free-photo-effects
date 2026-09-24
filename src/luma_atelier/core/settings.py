"""Kullanici ayarlari: okuma, yazma ve dogrulama.

Ayarlar `settings.json` icinde tutulur. Dosya bozuksa veya bir alan
beklenmedik turdeyse **uygulama acilmaya devam eder**: bozuk alan
varsayilana doner ve gunluge yazilir. Ayar dosyasi yuzunden uygulamanin
acilmamasi kabul edilemez.

Yazma atomiktir (gecici dosya + `os.replace`); kesinti onceki saglam
ayarlari bozmaz.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

from luma_atelier.core.paths import (
    cache_dir,
    default_output_dir,
    settings_path,
)

log = logging.getLogger(__name__)

#: Onizleme uzun kenari secenekleri (piksel)
PREVIEW_SIZES: tuple[tuple[str, int], ...] = (
    ("Hızlı (1280 px)", 1280),
    ("Dengeli (1920 px)", 1920),
    ("Keskin (2560 px)", 2560),
)

#: Onbellek ust siniri secenekleri (MB)
CACHE_LIMITS: tuple[tuple[str, int], ...] = (
    ("256 MB", 256),
    ("512 MB", 512),
    ("1 GB", 1024),
    ("2 GB", 2048),
)

#: Otomatik kurtarma araligi (saniye)
AUTOSAVE_INTERVALS: tuple[tuple[str, int], ...] = (
    ("Kapalı", 0),
    ("30 saniye", 30),
    ("45 saniye", 45),
    ("2 dakika", 120),
    ("5 dakika", 300),
)


@dataclass(frozen=True)
class Settings:
    """Kullanici tercihleri. Degismez; her degisiklik yeni kopya uretir."""

    preview_long_edge: int = 1920
    cache_limit_mb: int = 512
    autosave_seconds: int = 45
    output_folder: str = ""
    """Bos ise `default_output_dir()` kullanilir."""
    confirm_large_export: bool = True
    show_tooltips: bool = True
    remember_window: bool = True
    window_geometry: str = ""
    """Base64 kodlu `QMainWindow.saveGeometry()` ciktisi."""
    last_import_folder: str = ""
    high_contrast: bool = False
    keyboard_hints: bool = True

    @property
    def output_path(self) -> Path:
        return Path(self.output_folder) if self.output_folder \
            else default_output_dir()

    @property
    def cache_bytes(self) -> int:
        return max(1, self.cache_limit_mb) * 1024 * 1024

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: Alan adi -> (tur, gecerli mi)
def _coerce(name: str, value: Any, default: Any) -> Any:
    """Bir alani beklenen ture cevirir; olmazsa varsayilana doner."""
    try:
        if isinstance(default, bool):
            return bool(value)
        if isinstance(default, int):
            number = int(value)
            return number if number >= 0 else default
        if isinstance(default, str):
            return str(value)
    except (TypeError, ValueError):
        pass
    return default


def load_settings(path: Path | None = None) -> Settings:
    """Ayarlari okur. Hatada varsayilanlara doner, **yukselmez**."""
    target = path or settings_path()
    if not target.exists():
        return Settings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Ayar dosyasi okunamadi, varsayilanlar kullanilacak: %s",
                    exc)
        return Settings()
    if not isinstance(raw, dict):
        log.warning("Ayar dosyasi beklenen bicimde degil; varsayilanlar")
        return Settings()

    defaults = Settings()
    values: dict[str, Any] = {}
    for field in fields(Settings):
        default = getattr(defaults, field.name)
        values[field.name] = (_coerce(field.name, raw[field.name], default)
                              if field.name in raw else default)
    settings = Settings(**values)
    return _validated(settings)


def _validated(settings: Settings) -> Settings:
    """Deger araliklarini gecerli sinirlara cekar."""
    sizes = [value for _label, value in PREVIEW_SIZES]
    limits = [value for _label, value in CACHE_LIMITS]
    intervals = [value for _label, value in AUTOSAVE_INTERVALS]

    changes: dict[str, Any] = {}
    if settings.preview_long_edge not in sizes:
        changes["preview_long_edge"] = min(
            sizes, key=lambda s: abs(s - settings.preview_long_edge))
    if settings.cache_limit_mb not in limits:
        changes["cache_limit_mb"] = min(
            limits, key=lambda s: abs(s - settings.cache_limit_mb))
    if settings.autosave_seconds not in intervals:
        changes["autosave_seconds"] = min(
            intervals, key=lambda s: abs(s - settings.autosave_seconds))
    if settings.output_folder:
        try:
            Path(settings.output_folder)
        except (TypeError, ValueError):
            changes["output_folder"] = ""
    return replace(settings, **changes) if changes else settings


def save_settings(settings: Settings, path: Path | None = None) -> bool:
    """Ayarlari atomik olarak yazar. Basarisizlik uygulamayi kesmez."""
    target = path or settings_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False,
            dir=str(target.parent), prefix=".ayar-", suffix=".tmp")
        try:
            json.dump(settings.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, target)
        return True
    except OSError:
        log.exception("Ayarlar yazilamadi: %s", target)
        return False


def cache_folder_size() -> int:
    """Onbellek klasorunun toplam boyutu (bayt)."""
    total = 0
    try:
        for item in cache_dir().rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except OSError:
        log.debug("Onbellek boyutu olculemedi")
    return total


def clear_cache() -> tuple[int, int]:
    """Onbellegi temizler. (silinen dosya, bosalan bayt) dondurur.

    Kullanici projelerine ve fotograflarina **dokunmaz**; yalnizca
    yeniden uretilebilir onbellek dosyalarini siler.
    """
    removed = freed = 0
    folder = cache_dir()
    try:
        for item in sorted(folder.rglob("*"), reverse=True):
            try:
                if item.is_file():
                    size = item.stat().st_size
                    item.unlink()
                    removed += 1
                    freed += size
                elif item.is_dir():
                    item.rmdir()
            except OSError:
                log.debug("Onbellek ogesi silinemedi: %s", item)
    except OSError:
        log.exception("Onbellek temizlenemedi")
    return removed, freed

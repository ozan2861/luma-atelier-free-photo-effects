"""Oturum modeli: acilan fotograflar, secim ve gezinme.

Qt'ye bagimli degildir; sinyaller yerine geri cagirma listeleri kullanir.
Boylece kitaplik mantigi arayuzsuz test edilebilir.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from luma_atelier.imaging.loader import (
    SUPPORTED_INPUT_EXTENSIONS,
    ImageMetadata,
    probe_image,
)

log = logging.getLogger(__name__)


class SortKey(str, Enum):
    """Kitaplik siralama olcutu."""

    NAME = "name"
    DATE_MODIFIED = "modified"
    SIZE = "size"
    FOLDER = "folder"

    @property
    def label(self) -> str:
        return {
            SortKey.NAME: "Dosya adı",
            SortKey.DATE_MODIFIED: "Degistirilme tarihi",
            SortKey.SIZE: "Dosya boyutu",
            SortKey.FOLDER: "Klasör",
        }[self]


@dataclass
class PhotoEntry:
    """Kitaplikta tek bir fotograf.

    Piksel verisi *tutulmaz*; yalnizca yol ve hafif metadata. Tum
    fotograflari tam boy bellege almak gereksinim disidir.
    """

    path: Path
    metadata: ImageMetadata | None = None
    favourite: bool = False
    missing: bool = False
    size_bytes: int = 0
    modified: float = 0.0
    error: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def folder(self) -> str:
        return self.path.parent.name

    @property
    def key(self) -> str:
        """Karsilastirma ve tekillestirme anahtari."""
        return str(self.path).casefold()

    @property
    def dimensions_label(self) -> str:
        if self.metadata is None:
            return "—"
        return f"{self.metadata.width} × {self.metadata.height}"

    @property
    def size_label(self) -> str:
        if self.size_bytes <= 0:
            return "—"
        mb = self.size_bytes / (1024 * 1024)
        if mb < 1.0:
            return f"{self.size_bytes / 1024:.0f} KB"
        return f"{mb:.1f} MB"


@dataclass
class ImportReport:
    """Bir ice aktarma isleminin sonucu.

    Basarisizliklar gizlenmez; kullaniciya kac dosyanin neden
    alinamadigi gosterilir.
    """

    added: list[PhotoEntry] = field(default_factory=list)
    skipped_duplicates: int = 0
    unsupported: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total_seen(self) -> int:
        return (len(self.added) + self.skipped_duplicates
                + len(self.unsupported) + len(self.failed))

    @property
    def has_problems(self) -> bool:
        return bool(self.unsupported or self.failed)

    def summary(self) -> str:
        """Durum cubugunda gosterilecek kisa Turkce ozet."""
        parts: list[str] = []
        if self.added:
            parts.append(f"{len(self.added)} fotoğraf eklendi")
        if self.skipped_duplicates:
            parts.append(f"{self.skipped_duplicates} zaten ekliydi")
        if self.unsupported:
            parts.append(f"{len(self.unsupported)} desteklenmeyen biçim")
        if self.failed:
            parts.append(f"{len(self.failed)} dosya okunamadı")
        return ", ".join(parts) if parts else "Eklenecek fotoğraf bulunamadı"


class Session:
    """Acik fotograf kumesini ve secimi yonetir."""

    def __init__(self) -> None:
        self._entries: list[PhotoEntry] = []
        self._index_by_key: dict[str, int] = {}
        self._current: int = -1
        self._selection: set[int] = set()
        self._sort_key = SortKey.NAME
        self._sort_descending = False
        self._search = ""
        self._favourites_only = False
        self._listeners: list[Callable[[], None]] = []

    # --------------------------------------------------------- bildirimler
    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001 - bir dinleyici digerlerini engellemesin
                log.exception("Oturum dinleyicisi hata verdi")

    # ------------------------------------------------------- ice aktarma
    def add_paths(
        self, paths: Iterable[str | Path], *, recursive: bool = False
    ) -> ImportReport:
        """Dosya ve klasorleri kitapliga ekler.

        Klasorler icin `recursive` alt klasorleri de tarar. Bu acik bir
        secenektir; sessizce tum disk taranmaz.
        """
        report = ImportReport()
        files: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                files.extend(self._scan_folder(p, recursive))
            else:
                files.append(p)

        for f in files:
            if f.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
                report.unsupported.append(f)
                continue
            key = str(f).casefold()
            if key in self._index_by_key:
                report.skipped_duplicates += 1
                continue
            entry = self._build_entry(f)
            if entry.error:
                report.failed.append((f, entry.error))
                continue
            self._index_by_key[key] = len(self._entries)
            self._entries.append(entry)
            report.added.append(entry)

        if report.added:
            self._resort()
            if self._current < 0 and self._entries:
                # set_current cagirilmaz: o da bildirim yayar ve kitaplik
                # tek bir ice aktarmada iki kez yeniden kurulurdu.
                self._current = 0
                self._selection = {0}
        self._notify()
        log.info("Ice aktarma: %s", report.summary())
        return report

    @staticmethod
    def _scan_folder(folder: Path, recursive: bool) -> list[Path]:
        pattern = "**/*" if recursive else "*"
        found: list[Path] = []
        try:
            for p in sorted(folder.glob(pattern)):
                if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
                    found.append(p)
        except OSError as exc:
            log.warning("Klasör taranamadı: %s (%s)", folder, exc)
        return found

    @staticmethod
    def _build_entry(path: Path) -> PhotoEntry:
        try:
            stat = path.stat()
        except OSError as exc:
            return PhotoEntry(path=path, error=f"Dosya bilgisi okunamadı: {exc}")
        meta = probe_image(path)
        if meta is None:
            return PhotoEntry(
                path=path, size_bytes=stat.st_size, modified=stat.st_mtime,
                error="Fotoğraf çözümlenemedi veya bozuk",
            )
        return PhotoEntry(
            path=path, metadata=meta,
            size_bytes=stat.st_size, modified=stat.st_mtime,
        )

    # ---------------------------------------------------------- erisim
    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[PhotoEntry]:
        return iter(self._entries)

    @property
    def entries(self) -> Sequence[PhotoEntry]:
        """Tum girisler (filtre uygulanmamis)."""
        return tuple(self._entries)

    @property
    def visible(self) -> list[PhotoEntry]:
        """Arama ve favori filtresinden gecen girisler."""
        needle = self._search.casefold().strip()
        out = []
        for e in self._entries:
            if self._favourites_only and not e.favourite:
                continue
            if needle and needle not in e.name.casefold() \
                    and needle not in e.folder.casefold():
                continue
            out.append(e)
        return out

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def current(self) -> PhotoEntry | None:
        if 0 <= self._current < len(self._entries):
            return self._entries[self._current]
        return None

    def index_of(self, path: str | Path) -> int:
        return self._index_by_key.get(str(Path(path)).casefold(), -1)

    # ----------------------------------------------------------- gezinme
    def set_current(self, index: int) -> bool:
        if not self._entries:
            self._current = -1
            return False
        clamped = max(0, min(len(self._entries) - 1, index))
        if clamped == self._current:
            return False
        self._current = clamped
        self._selection = {clamped}
        self._notify()
        return True

    def next_photo(self) -> bool:
        """Sonraki fotografa gecer; sonda sarmaz."""
        return self.set_current(self._current + 1)

    def previous_photo(self) -> bool:
        return self.set_current(self._current - 1)

    def can_go_next(self) -> bool:
        return 0 <= self._current < len(self._entries) - 1

    def can_go_previous(self) -> bool:
        return self._current > 0

    # ------------------------------------------------------------- secim
    @property
    def selection(self) -> list[PhotoEntry]:
        return [self._entries[i] for i in sorted(self._selection)
                if 0 <= i < len(self._entries)]

    def set_selection(self, indices: Iterable[int]) -> None:
        self._selection = {i for i in indices if 0 <= i < len(self._entries)}
        if self._selection and self._current not in self._selection:
            self._current = min(self._selection)
        self._notify()

    def toggle_selection(self, index: int) -> None:
        if index in self._selection:
            self._selection.discard(index)
        else:
            self._selection.add(index)
        self._notify()

    def select_all(self) -> None:
        self._selection = set(range(len(self._entries)))
        self._notify()

    # -------------------------------------------------------- favoriler
    def toggle_favourite(self, index: int) -> bool:
        if not (0 <= index < len(self._entries)):
            return False
        e = self._entries[index]
        self._entries[index] = replace(e, favourite=not e.favourite)
        self._reindex()
        self._notify()
        return self._entries[index].favourite

    @property
    def favourites_only(self) -> bool:
        return self._favourites_only

    def set_favourites_only(self, value: bool) -> None:
        if value != self._favourites_only:
            self._favourites_only = value
            self._notify()

    # -------------------------------------------------- arama ve siralama
    @property
    def search_text(self) -> str:
        return self._search

    def set_search(self, text: str) -> None:
        if text != self._search:
            self._search = text
            self._notify()

    @property
    def sort_key(self) -> SortKey:
        return self._sort_key

    @property
    def sort_descending(self) -> bool:
        return self._sort_descending

    def set_sort(self, key: SortKey, descending: bool = False) -> None:
        self._sort_key, self._sort_descending = key, descending
        self._resort()
        self._notify()

    def _resort(self) -> None:
        current_key = self.current.key if self.current else None
        keyfn = {
            SortKey.NAME: lambda e: e.name.casefold(),
            SortKey.DATE_MODIFIED: lambda e: e.modified,
            SortKey.SIZE: lambda e: e.size_bytes,
            SortKey.FOLDER: lambda e: (e.folder.casefold(), e.name.casefold()),
        }[self._sort_key]
        self._entries.sort(key=keyfn, reverse=self._sort_descending)
        self._reindex()
        if current_key is not None:
            self._current = self._index_by_key.get(current_key, self._current)
            self._selection = {self._current}

    def _reindex(self) -> None:
        self._index_by_key = {e.key: i for i, e in enumerate(self._entries)}

    # ------------------------------------------------ kayip dosya yonetimi
    def refresh_missing(self) -> list[PhotoEntry]:
        """Silinmis veya tasinmis dosyalari isaretler."""
        changed: list[PhotoEntry] = []
        for i, e in enumerate(self._entries):
            missing = not e.path.exists()
            if missing != e.missing:
                self._entries[i] = replace(e, missing=missing)
                changed.append(self._entries[i])
        if changed:
            self._notify()
        return changed

    def relocate(self, old: str | Path, new: str | Path) -> bool:
        """Tasinmis bir fotografin yeni konumunu kaydeder."""
        idx = self.index_of(old)
        if idx < 0:
            return False
        new_path = Path(new)
        if not new_path.exists():
            return False
        self._entries[idx] = self._build_entry(new_path)
        self._reindex()
        self._notify()
        return True

    def remove(self, indices: Iterable[int]) -> int:
        """Kitapliktan cikarir. Diskteki dosyayi **silmez**."""
        drop = {i for i in indices if 0 <= i < len(self._entries)}
        if not drop:
            return 0
        self._entries = [e for i, e in enumerate(self._entries) if i not in drop]
        self._reindex()
        self._current = min(self._current, len(self._entries) - 1)
        self._selection = {self._current} if self._current >= 0 else set()
        self._notify()
        return len(drop)

    def clear(self) -> None:
        self._entries.clear()
        self._index_by_key.clear()
        self._current = -1
        self._selection.clear()
        self._notify()

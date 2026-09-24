"""Geri alma / yineleme yigini.

Tasarim: tarif degismez (immutable) oldugu icin gecmis yalnizca onceki
tarifleri tutar. Diff hesabi, ters islem uretimi veya piksel kopyasi
gerekmez.

Kritik davranis: **slider suruklemesi tek adim uretir.** Kaydirici her
piksel hareketinde `valueChanged` yayar (onizleme tazelensin) ama
gecmise yalnizca `editingFinished` sinyalinde yazilir. Ayrica ayni
parametrenin arka arkaya gelen degisiklikleri zaman penceresi icinde
birlestirilir.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

#: Ayni etiketli ardisik degisiklikler bu sure icinde birlestirilir (sn).
COALESCE_WINDOW = 0.9

#: Gereksinim: en az 50 adim. Bellek maliyeti dusuk (tarifler kucuk).
DEFAULT_LIMIT = 120


@dataclass(frozen=True)
class HistoryEntry(Generic[T]):
    state: T
    label: str
    """Kullaniciya gosterilecek Turkce eylem adi: "Pozlama", "Preset: Teal & Amber"."""
    merge_key: str = ""
    """Bos degilse ayni anahtarli ardisik adimlar birlestirilir."""
    timestamp: float = 0.0


class History(Generic[T]):
    """Sinirli derinlikte geri al/yinele yigini."""

    def __init__(self, initial: T, *, limit: int = DEFAULT_LIMIT) -> None:
        self._entries: list[HistoryEntry[T]] = [
            HistoryEntry(state=initial, label="Başlangıç", timestamp=time.monotonic())
        ]
        self._index = 0
        self._limit = max(10, limit)
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------ bildirim
    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                log.exception("Gecmis dinleyicisi hata verdi")

    # --------------------------------------------------------------- durum
    @property
    def current(self) -> T:
        return self._entries[self._index].state

    @property
    def current_label(self) -> str:
        return self._entries[self._index].label

    @property
    def depth(self) -> int:
        return len(self._entries)

    @property
    def position(self) -> int:
        return self._index

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._entries) - 1

    def undo_label(self) -> str:
        """Geri alinacak eylemin adi; arayuz ipucunda gosterilir."""
        return self._entries[self._index].label if self.can_undo() else ""

    def redo_label(self) -> str:
        return self._entries[self._index + 1].label if self.can_redo() else ""

    def labels(self) -> list[str]:
        return [e.label for e in self._entries]

    # ------------------------------------------------------------- islemler
    def push(self, state: T, label: str, *, merge_key: str = "") -> bool:
        """Yeni durumu kaydeder.

        Ayni `merge_key` ile kisa sure icinde gelen degisiklikler tek
        adimda birlestirilir; slider suruklemesi yuzlerce adim uretmez.

        Returns:
            Yeni bir adim olusturulduysa True, birlestirildiyse False.
        """
        now = time.monotonic()
        head = self._entries[self._index]

        if state == head.state:
            return False  # gercek bir degisiklik yok

        can_merge = (
            merge_key
            and head.merge_key == merge_key
            and (now - head.timestamp) < COALESCE_WINDOW
            and self._index == len(self._entries) - 1
            and self._index > 0
        )
        if can_merge:
            self._entries[self._index] = HistoryEntry(
                state=state, label=label, merge_key=merge_key, timestamp=now
            )
            self._notify()
            return False

        # Yeni dal: ileri gecmis atilir
        del self._entries[self._index + 1:]
        self._entries.append(HistoryEntry(
            state=state, label=label, merge_key=merge_key, timestamp=now
        ))
        if len(self._entries) > self._limit:
            drop = len(self._entries) - self._limit
            del self._entries[:drop]
        self._index = len(self._entries) - 1
        self._notify()
        return True

    def undo(self) -> T | None:
        if not self.can_undo():
            return None
        self._index -= 1
        self._notify()
        return self.current

    def redo(self) -> T | None:
        if not self.can_redo():
            return None
        self._index += 1
        self._notify()
        return self.current

    def reset(self, state: T, label: str = "Başlangıç") -> None:
        """Gecmisi temizler; yeni fotograf acildiginda kullanilir."""
        self._entries = [
            HistoryEntry(state=state, label=label, timestamp=time.monotonic())
        ]
        self._index = 0
        self._notify()

    def seal(self) -> None:
        """Birlestirme penceresini kapatir.

        Sonraki degisiklik ayni parametreden bile gelse yeni adim olur.
        Kaydirici birakildiginda cagrilir.
        """
        head = self._entries[self._index]
        if head.merge_key:
            self._entries[self._index] = HistoryEntry(
                state=head.state, label=head.label, merge_key="",
                timestamp=head.timestamp,
            )

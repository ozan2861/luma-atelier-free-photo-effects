"""Preset (hazir gorunum) saklama, dogrulama ve yukleme.

Preset nedir
------------
Preset, kaydedilmis bir *tariftir* (recipe). 120 preset 120 algoritma
degil; 38 goruntu isleminin duzenlenebilir birlesimleridir. Her preset
yuklendiginde tarif olarak yigina girer ve kullanici her parametresini
degistirebilir.

Guvenlik
--------
Ice aktarilan JSON'a guvenilmez. `Preset.from_dict` yalnizca veri okur;
hicbir kod calistirilmaz, bilinmeyen anahtarlar atilir, parametreler
islem semasina gore kirpilir. Bozuk bir preset dosyasi tum koleksiyonun
yuklenmesini engellemez.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from luma_atelier.core.branding import APP_VERSION, PRESET_FORMAT_VERSION
from luma_atelier.imaging.recipe import Recipe, RecipeError

log = logging.getLogger(__name__)

#: Preset dosyalarinin uzantisi
PRESET_EXTENSION = ".luma-preset.json"

#: Tek bir preset dosyasi icin ust sinir (kotu niyetli dosyalara karsi)
MAX_PRESET_BYTES = 2 * 1024 * 1024


class PresetError(Exception):
    """Preset okunamadi. Mesaj kullaniciya gosterilecek Turkce metindir."""


#: Genel koleksiyon kategorileri (gereksinim belgesi Bolum 8)
GENERAL_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("natural", "Doğal ve temiz"),
    ("portrait", "Portre"),
    ("landscape", "Manzara"),
    ("street", "Sokak ve şehir"),
    ("analog", "Analog ve vintage"),
    ("mono", "Siyah-beyaz"),
    ("light", "Işık ve atmosfer"),
    ("creative", "Yaratıcı renk"),
    ("texture", "Doku ve stil"),
)

#: Sinema Laboratuvari kategorisi
CINEMA_CATEGORY = ("cinema", "Sinema")

ALL_CATEGORIES: tuple[tuple[str, str], ...] = GENERAL_CATEGORIES + (CINEMA_CATEGORY,)

CATEGORY_LABELS: dict[str, str] = dict(ALL_CATEGORIES)


def slugify(text: str) -> str:
    """Turkce metni dosya adina uygun kimlige cevirir."""
    normalised = unicodedata.normalize("NFKD", text)
    replacements = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g",
                    "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o",
                    "ç": "c", "Ç": "c"}
    for src, dst in replacements.items():
        normalised = normalised.replace(src, dst)
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return ascii_text or "preset"


@dataclass(frozen=True)
class Preset:
    """Kaydedilmis bir gorunum."""

    preset_id: str
    name: str
    category: str
    description: str
    recipe: Recipe
    tags: tuple[str, ...] = ()
    #: Amaclanan fotograf turu; arayuzde ipucu olarak gosterilir
    intent: str = ""
    builtin: bool = True
    version: int = PRESET_FORMAT_VERSION
    app_version: str = APP_VERSION
    source: Path | None = None
    #: Kullanicinin tercih ettigi genel yogunluk (0..100)
    default_intensity: float = 100.0

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)

    @property
    def is_cinema(self) -> bool:
        return self.category == CINEMA_CATEGORY[0]

    def operations(self) -> list[str]:
        """"Bu gorunum nasil olusuyor?" alani icin islem adlari."""
        return [op.name for op in self.recipe.used_operations()]

    def search_text(self) -> str:
        return " ".join([self.name, self.description, self.intent,
                         self.category_label, *self.tags]).casefold()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "app_version": self.app_version,
            "id": self.preset_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "intent": self.intent,
            "tags": list(self.tags),
            "default_intensity": self.default_intensity,
            "recipe": self.recipe.to_dict(),
        }

    @staticmethod
    def from_dict(data: Any, *, builtin: bool = False,
                  source: Path | None = None) -> Preset:
        """Sozlukten preset okur ve dogrular.

        Raises:
            PresetError: veri gecersiz veya surum desteklenmiyor.
        """
        if not isinstance(data, dict):
            raise PresetError("Preset verisi sozluk olmali")

        version = data.get("version", PRESET_FORMAT_VERSION)
        if not isinstance(version, int):
            raise PresetError("Preset surumu sayi olmali")
        if version > PRESET_FORMAT_VERSION:
            raise PresetError(
                f"Bu preset daha yeni bir surumle olusturulmus (v{version}). "
                "Uygulamayı guncelleyin."
            )

        name = str(data.get("name", "")).strip()
        if not name:
            raise PresetError("Presetin adı yok")

        category = str(data.get("category", "creative"))
        if category not in CATEGORY_LABELS:
            log.info("Bilinmeyen preset kategorisi '%s' -> 'creative'", category)
            category = "creative"

        try:
            recipe = Recipe.from_dict(data.get("recipe", {}))
        except RecipeError as exc:
            raise PresetError(f"{name}: tarif okunamadı ({exc})") from exc

        raw_tags = data.get("tags", [])
        tags = tuple(str(t) for t in raw_tags) if isinstance(raw_tags, list) else ()

        try:
            intensity = float(data.get("default_intensity", 100.0))
        except (TypeError, ValueError):
            intensity = 100.0
        intensity = min(100.0, max(0.0, intensity))

        return Preset(
            preset_id=str(data.get("id") or slugify(name)),
            name=name,
            category=category,
            description=str(data.get("description", "")),
            recipe=recipe,
            tags=tags,
            intent=str(data.get("intent", "")),
            builtin=builtin,
            version=version,
            app_version=str(data.get("app_version", APP_VERSION)),
            source=source,
            default_intensity=intensity,
        )

    def with_intensity(self, intensity: float) -> Recipe:
        """Presetin tarifini verilen genel yogunlukla dondurur.

        Iki yol kullanilir:

        1. `amount` parametresi olan katmanlarda yalnizca o parametre
           olceklenir. Ucuz ve tam sonuc verir.
        2. `amount`'i olmayan katmanlarda (pozlama, beyaz dengesi, HSL)
           **parametreler varsayilanlarina dogru tasinir**. Islemler
           varsayilanlarinda kimlik oldugu icin (`identity_at_defaults`)
           yogunluk %0'da katman etkisiz kalir.

        Ikinci yol olmadan yogunlugu %0'a cekmek bazi gorunumlerde
        fotografi degistirmeye devam ediyordu; kullanici "yoğunluk yok"
        dedigi halde pozlama ve renk kaymasi kaliyordu.

        `identity_at_defaults` olmayan islemler (monokrom, bleach bypass
        gibi) bu yolla zayiflatilamaz; onlarin zaten `amount`'i vardir.
        """
        factor = min(100.0, max(0.0, intensity)) / 100.0
        if abs(factor - 1.0) < 1e-6:
            return self.recipe

        layers = []
        for layer in self.recipe.layers:
            op = layer.operation()
            if op is None:
                layers.append(layer)
            elif op.param("amount") is not None:
                base = float(layer.params.get("amount", 100.0))
                layers.append(layer.with_param("amount", base * factor))
            elif op.identity_at_defaults:
                layers.append(_faded_towards_defaults(layer, op, factor))
            else:
                layers.append(layer)
        return replace(self.recipe, layers=tuple(layers))


def _faded_towards_defaults(layer, op, factor: float):  # noqa: ANN001, ANN201
    """Katmanin parametrelerini varsayilanlarina dogru tasir.

    `factor` 1.0 iken katman aynen kalir, 0.0 iken islemin varsayilan
    degerlerine iner. Islem varsayilanlarinda kimlik oldugundan sonuc
    etkisiz bir katmandir.

    Yalnizca sayisal ve renk parametreleri tasinir. Secim, onay kutusu
    ve egri parametreleri ara deger kabul etmez; onlar oldugu gibi
    birakilir (egri iceren islemlerin zaten `amount`'i vardir).
    """
    defaults = op.defaults()
    faded: dict[str, Any] = {}
    for key, value in layer.params.items():
        target = defaults.get(key)
        if isinstance(value, bool) or isinstance(target, bool):
            faded[key] = value
        elif isinstance(value, (int, float)) and isinstance(
                target, (int, float)):
            faded[key] = target + (value - target) * factor
        elif (isinstance(value, (tuple, list))
                and isinstance(target, (tuple, list))
                and len(value) == len(target)
                and all(isinstance(v, (int, float)) for v in value)
                and all(isinstance(v, (int, float)) for v in target)):
            faded[key] = tuple(t + (v - t) * factor
                               for v, t in zip(value, target))
        else:
            faded[key] = value
    return replace(layer, params=faded)


@dataclass
class PresetLoadReport:
    """Bir klasorden yukleme sonucu."""

    loaded: list[Preset] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{len(self.loaded)} görünüm yuklendi"]
        if self.failed:
            parts.append(f"{len(self.failed)} dosya okunamadı")
        return ", ".join(parts)


class PresetLibrary:
    """Yerlesik ve kullanici presetlerinin birlesik kataloğu."""

    def __init__(self) -> None:
        self._presets: dict[str, Preset] = {}
        self._order: list[str] = []
        self._failed: list[tuple[Path, str]] = []

    # --------------------------------------------------------------- yukleme
    def add(self, preset: Preset) -> Preset:
        """Preseti kataloğa ekler. Ayni kimlik varsa ustune yazar.

        Kullanici preseti yerlesik bir kimlikle cakisirsa kullanicininki
        oncelikli olur; boylece kullanici bir gorunumu kendi zevkine
        gore degistirebilir.
        """
        if preset.preset_id not in self._presets:
            self._order.append(preset.preset_id)
        self._presets[preset.preset_id] = preset
        return preset

    def load_folder(self, folder: Path, *, builtin: bool) -> PresetLoadReport:
        """Klasordeki tum preset dosyalarini yukler.

        Bir dosyanin bozuk olmasi digerlerinin yuklenmesini engellemez.
        """
        report = PresetLoadReport()
        if not folder.is_dir():
            return report

        for path in sorted(folder.glob("*.json")):
            try:
                if path.stat().st_size > MAX_PRESET_BYTES:
                    raise PresetError(f"{path.name}: dosya çok büyük")
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                report.failed.append((path, f"Dosya okunamadı: {exc}"))
                continue
            except PresetError as exc:
                report.failed.append((path, str(exc)))
                continue

            # Bir dosya birden fazla preset icerebilir (koleksiyon dosyasi)
            entries = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "presets" in data:
                entries = data["presets"]
            for entry in entries:
                try:
                    preset = Preset.from_dict(entry, builtin=builtin, source=path)
                except PresetError as exc:
                    report.failed.append((path, str(exc)))
                    continue
                self.add(preset)
                report.loaded.append(preset)

        self._failed.extend(report.failed)
        if report.failed:
            log.warning("Preset yüklemede %d hata: %s",
                        len(report.failed), report.failed[:3])
        return report

    def load_all(self) -> PresetLoadReport:
        """Yerlesik ve kullanici presetlerini yukler."""
        from luma_atelier.core.paths import presets_user_dir, resources_dir

        report = PresetLoadReport()
        builtin = self.load_folder(resources_dir() / "presets", builtin=True)
        user = self.load_folder(presets_user_dir(), builtin=False)
        report.loaded = builtin.loaded + user.loaded
        report.failed = builtin.failed + user.failed
        return report

    # ---------------------------------------------------------------- erisim
    def __len__(self) -> int:
        return len(self._presets)

    def __iter__(self):  # noqa: ANN204
        return iter(self.all())

    def all(self) -> list[Preset]:
        return [self._presets[i] for i in self._order if i in self._presets]

    def get(self, preset_id: str) -> Preset | None:
        return self._presets.get(preset_id)

    def by_category(self, category: str) -> list[Preset]:
        return [p for p in self.all() if p.category == category]

    def categories(self) -> list[tuple[str, str, int]]:
        """(kimlik, etiket, adet) - yalnizca dolu kategoriler."""
        out: list[tuple[str, str, int]] = []
        for key, label in ALL_CATEGORIES:
            count = len(self.by_category(key))
            if count:
                out.append((key, label, count))
        return out

    def cinema(self) -> list[Preset]:
        return self.by_category(CINEMA_CATEGORY[0])

    def general(self) -> list[Preset]:
        return [p for p in self.all() if not p.is_cinema]

    def search(self, needle: str, *, category: str = "") -> list[Preset]:
        pool = self.by_category(category) if category else self.all()
        text = needle.casefold().strip()
        if not text:
            return pool
        return [p for p in pool if text in p.search_text()]

    def failures(self) -> list[tuple[Path, str]]:
        return list(self._failed)

    # ---------------------------------------------------------- kullanici
    def save_user_preset(self, preset: Preset,
                         folder: Path | None = None) -> Path:
        """Kullanici presetini diske yazar ve kataloğa ekler.

        Once gecici dosyaya yazip tasir: kesinti yarim dosya birakmaz.
        """
        from luma_atelier.core.paths import presets_user_dir

        target_dir = folder or presets_user_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{preset.preset_id}{PRESET_EXTENSION}"

        payload = json.dumps(preset.to_dict(), ensure_ascii=False, indent=2)
        tmp = path.with_suffix(".part")
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise PresetError(
                f"Görünüm kaydedilemedi: {exc.strerror or exc}"
            ) from exc

        self.add(replace(preset, source=path, builtin=False))
        return path

    def delete_user_preset(self, preset_id: str) -> bool:
        """Kullanici presetini siler. Yerlesik presetler silinmez."""
        preset = self._presets.get(preset_id)
        if preset is None or preset.builtin:
            return False
        if preset.source is not None:
            try:
                preset.source.unlink(missing_ok=True)
            except OSError as exc:
                raise PresetError(f"Dosya silinemedi: {exc}") from exc
        self._presets.pop(preset_id, None)
        if preset_id in self._order:
            self._order.remove(preset_id)
        return True

    def export_preset(self, preset_id: str, path: Path) -> Path:
        """Preseti disariya JSON olarak yazar."""
        preset = self._presets.get(preset_id)
        if preset is None:
            raise PresetError(f"Görünüm bulunamadı: {preset_id}")
        payload = json.dumps(preset.to_dict(), ensure_ascii=False, indent=2)
        try:
            path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise PresetError(f"Dışa aktarılamadı: {exc}") from exc
        return path

    def import_preset(self, path: Path) -> Preset:
        """Disaridan preset okur, dogrular ve kullanici presetine cevirir.

        Kod calistirilmaz; yalnizca veri okunur ve semaya gore kirpilir.
        """
        try:
            if path.stat().st_size > MAX_PRESET_BYTES:
                raise PresetError(f"{path.name}: dosya çok büyük")
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PresetError(f"Dosya okunamadı: {exc}") from exc

        preset = Preset.from_dict(data, builtin=False, source=path)
        # Ice aktarilan preset kullanici koleksiyonuna kopyalanir
        if self.get(preset.preset_id) is not None:
            preset = replace(preset,
                             preset_id=f"{preset.preset_id}-{len(self._order)}")
        self.save_user_preset(preset)
        return preset

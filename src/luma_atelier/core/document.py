"""Duzenleme belgesi: kaynak fotograf + tarif + gecmis.

Belge *tahribatsizdir*: kaynak pikseller hicbir zaman degistirilmez.
Duzenleme yalnizca tarifi degistirir; goruntu her seferinde kaynaktan
yeniden hesaplanir. Bu yuzden projeyi acip yeniden kaydetmek ek kalite
kaybi yaratmaz.

Qt'ye bagimli degildir; gecmis ve tarif mantigi arayuzsuz test edilir.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from luma_atelier.core.history import History
from luma_atelier.imaging.geometry import Geometry
from luma_atelier.imaging.loader import ImageMetadata, LoadedImage
from luma_atelier.imaging.masks import BlendOp, Mask, MaskKind, MaskStack
from luma_atelier.imaging.recipe import Recipe

log = logging.getLogger(__name__)

#: Preset katmanlarinin grup adi. Bu gruptaki katmanlar yeni preset
#: uygulandiginda topluca degistirilir.
PRESET_GROUP = "preset"


@dataclass(frozen=True)
class EditAction:
    """Gecmise yazilacak bir duzenleme.

    `merge_key` ayni kaydiricinin ardisik hareketlerini tek adimda
    birlestirmek icin kullanilir.
    """

    label: str
    merge_key: str = ""


class Document:
    """Acik bir fotografin duzenleme durumu."""

    def __init__(self, loaded: LoadedImage) -> None:
        self._source = loaded.pixels
        self._metadata = loaded.metadata
        self._history: History[Recipe] = History(Recipe())
        self._saved_recipe: Recipe = Recipe()
        self._listeners: list[Callable[[], None]] = []
        self._source_hash: str | None = None
        self._active_preset: str = ""
        self._geo_cache: np.ndarray | None = None
        self._geo_cache_key: Geometry | None = None

    # ---------------------------------------------------------- bildirim
    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                log.exception("Belge dinleyicisi hata verdi")

    # ------------------------------------------------------------- erisim
    @property
    def source(self) -> np.ndarray:
        """Kaynak pikseller. **Salt okunur kabul edilir.**"""
        return self._source

    @property
    def metadata(self) -> ImageMetadata:
        return self._metadata

    @property
    def path(self) -> Path:
        return self._metadata.path

    @property
    def recipe(self) -> Recipe:
        return self._history.current

    @property
    def history(self) -> History[Recipe]:
        return self._history

    @property
    def is_modified(self) -> bool:
        """Son kayittan bu yana degisiklik var mi?"""
        return self.recipe != self._saved_recipe

    @property
    def has_edits(self) -> bool:
        return not self.recipe.is_empty

    def mark_saved(self) -> None:
        self._saved_recipe = self.recipe
        self._notify()

    def source_hash(self) -> str:
        """Kaynak dosyanin SHA-256'si.

        Orijinalin degismedigini kanitlamak ve projede kaynak
        dogrulamasi yapmak icin. Ilk cagrida hesaplanip onbelleklenir.
        """
        if self._source_hash is None:
            h = hashlib.sha256()
            try:
                with self.path.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                self._source_hash = h.hexdigest()
            except OSError:
                self._source_hash = ""
        return self._source_hash

    # ---------------------------------------------------------- duzenleme
    def apply_recipe(self, recipe: Recipe, action: EditAction) -> None:
        """Yeni tarifi uygular ve gecmise yazar."""
        self._history.push(recipe, action.label, merge_key=action.merge_key)
        self._notify()

    def set_param(self, op_id: str, action_label: str = "", **params: Any) -> None:
        """Bir islemin parametresini ayarlar; islem yoksa ekler.

        Kaydirici hareketleri bunu cagirir. `merge_key` islem kimligi ve
        parametre adlarindan turetildigi icin ayni kaydiricinin ardisik
        hareketleri tek geri alma adimi olur.
        """
        op = self.recipe.first_of(op_id)
        new_recipe = self.recipe.set_or_add(op_id, **params)
        if new_recipe == self.recipe:
            return
        from luma_atelier.imaging.effects.base import REGISTRY
        operation = REGISTRY.get(op_id)
        label = action_label or (operation.name if operation else op_id)
        merge = f"{op_id}:{','.join(sorted(params))}"
        self.apply_recipe(new_recipe, EditAction(label=label, merge_key=merge))

    def add_layer(self, op_id: str, params: dict[str, Any] | None = None) -> None:
        from luma_atelier.imaging.effects.base import REGISTRY
        operation = REGISTRY.get(op_id)
        name = operation.name if operation else op_id
        self.apply_recipe(self.recipe.add(op_id, params),
                          EditAction(label=f"{name} eklendi"))

    def remove_layer(self, instance_id: str) -> None:
        layer = self.recipe.find(instance_id)
        name = layer.display_name() if layer else "Katman"
        self.apply_recipe(self.recipe.remove(instance_id),
                          EditAction(label=f"{name} kaldırıldı"))

    def set_layer_enabled(self, instance_id: str, enabled: bool) -> None:
        layer = self.recipe.find(instance_id)
        name = layer.display_name() if layer else "Katman"
        verb = "açıldı" if enabled else "kapatildi"
        self.apply_recipe(self.recipe.set_enabled(instance_id, enabled),
                          EditAction(label=f"{name} {verb}"))

    def move_layer(self, instance_id: str, new_index: int) -> None:
        layer = self.recipe.find(instance_id)
        name = layer.display_name() if layer else "Katman"
        self.apply_recipe(self.recipe.move(instance_id, new_index),
                          EditAction(label=f"{name} taşındı"))

    def reset_operation(self, op_id: str) -> None:
        """Tek bir aracin ayarlarini sifirlar."""
        layer = self.recipe.first_of(op_id)
        if layer is None:
            return
        from luma_atelier.imaging.effects.base import REGISTRY
        operation = REGISTRY.get(op_id)
        name = operation.name if operation else op_id
        self.apply_recipe(self.recipe.remove(layer.instance_id),
                          EditAction(label=f"{name} sıfırlandı"))

    def reset_all(self) -> None:
        """Tum ayarlari sifirlar. Geri alinabilir."""
        if self.recipe.is_empty:
            return
        self.apply_recipe(self.recipe.clear(),
                          EditAction(label="Tüm ayarlar sıfırlandı"))

    def set_seed(self, seed: int) -> None:
        self.apply_recipe(self.recipe.with_seed(seed),
                          EditAction(label="Desen değiştirildi"))

    # ---------------------------------------------------------- geometri
    @property
    def geometry(self) -> Geometry:
        return self.recipe.geometry

    def set_geometry(self, geometry: Geometry, *, label: str = "Kadraj",
                     merge_key: str = "") -> None:
        """Kadraji degistirir ve **maskeleri yeni kadraja tasir**.

        Maskeler kirpma sonrasi kadrajin normalize uzayinda yasar. Kirpma
        degisince ayni fotograf bolgesini gostermeye devam etmeleri icin
        eski kadrajdan yeniye goturulmeleri gerekir. Donusum iki kadraj
        arasindaki *bagil* kirpmadan hesaplanir.
        """
        old = self.recipe.geometry
        if geometry == old:
            return
        recipe = self.recipe.with_geometry(geometry)
        if self.recipe.masks:
            recipe = recipe.transform_masks(_relative_geometry(old, geometry))
        self.apply_recipe(recipe, EditAction(label=label,
                                             merge_key=merge_key))

    def reset_geometry(self) -> None:
        if self.recipe.geometry.is_identity:
            return
        self.set_geometry(Geometry(), label="Kadraj sıfırlandı")

    def output_size(self) -> tuple[int, int]:
        """Geometri uygulandiktan sonraki cikti boyutu."""
        h, w = self._source.shape[:2]
        return self.recipe.geometry.output_size(w, h)

    def geometry_source(self, geometry: Geometry | None = None) -> np.ndarray:
        """Geometri uygulanmis kaynak. **Salt okunur kabul edilir.**

        Sonuc onbelleklenir; kaydirici hareketi sirasinda ayni kadraj
        tekrar tekrar hesaplanmaz. Kimlik geometride kaynagin kendisi
        doner (kopya yok).
        """
        geo = self.recipe.geometry if geometry is None else geometry
        if geo.is_identity:
            return self._source
        if self._geo_cache_key != geo or self._geo_cache is None:
            self._geo_cache = np.ascontiguousarray(geo.apply(self._source))
            self._geo_cache_key = geo
        return self._geo_cache

    # ---------------------------------------------------------- maskeler
    @property
    def masks(self) -> dict[str, MaskStack]:
        return self.recipe.masks

    def mask_stack(self, mask_id: str) -> MaskStack | None:
        return self.recipe.masks.get(mask_id)

    def create_mask(self, kind: MaskKind, *, label: str = "") -> str:
        """Yeni bir maske yigini olusturur ve kimligini dondurur."""
        mask_id = _unique_mask_id(self.recipe.masks)
        component = Mask(mask_id=f"{mask_id}-1", kind=kind,
                         label=label or kind.label)
        stack = MaskStack(masks=(component,))
        self.apply_recipe(self.recipe.with_mask(mask_id, stack),
                          EditAction(label=f"{component.display_name} eklendi"))
        return mask_id

    def delete_mask(self, mask_id: str) -> None:
        if mask_id not in self.recipe.masks:
            return
        self.apply_recipe(self.recipe.remove_mask(mask_id),
                          EditAction(label="Maske silindi"))

    def add_mask_component(self, mask_id: str, kind: MaskKind,
                           blend: BlendOp = BlendOp.ADD) -> int:
        """Var olan maskeye bilesen ekler; yeni bilesenin sirasini dondurur."""
        stack = self.recipe.masks.get(mask_id)
        if stack is None:
            return -1
        index = len(stack.masks)
        component = Mask(mask_id=f"{mask_id}-{index + 1}", kind=kind,
                         label=kind.label, blend=blend)
        new_stack = MaskStack(masks=stack.masks + (component,))
        verb = "eklendi" if blend is BlendOp.ADD else "cikarildi"
        self.apply_recipe(self.recipe.with_mask(mask_id, new_stack),
                          EditAction(label=f"{kind.label} {verb}"))
        return index

    def update_mask_component(self, mask_id: str, index: int, component: Mask,
                              *, label: str = "Maske", merge_key: str = ""
                              ) -> None:
        """Bir maske bilesenini degistirir."""
        stack = self.recipe.masks.get(mask_id)
        if stack is None or not 0 <= index < len(stack.masks):
            return
        if stack.masks[index] == component:
            return
        masks = list(stack.masks)
        masks[index] = component
        new_stack = MaskStack(masks=tuple(masks))
        self.apply_recipe(self.recipe.with_mask(mask_id, new_stack),
                          EditAction(label=label, merge_key=merge_key))

    def remove_mask_component(self, mask_id: str, index: int) -> None:
        """Bilesen siler; son bilesen silinirse maskenin tamami gider."""
        stack = self.recipe.masks.get(mask_id)
        if stack is None or not 0 <= index < len(stack.masks):
            return
        masks = tuple(m for i, m in enumerate(stack.masks) if i != index)
        if not masks:
            self.delete_mask(mask_id)
            return
        self.apply_recipe(self.recipe.with_mask(mask_id, MaskStack(masks=masks)),
                          EditAction(label="Maske bileşeni silindi"))

    def assign_mask(self, instance_id: str, mask_id: str | None) -> None:
        """Katmani maskeye baglar (veya bagi kaldirir)."""
        layer = self.recipe.find(instance_id)
        if layer is None or layer.mask_id == (mask_id or None):
            return
        name = layer.display_name()
        text = f"{name} maskeye baglandi" if mask_id else f"{name} maskesi kaldırıldı"
        self.apply_recipe(self.recipe.assign_mask(instance_id, mask_id),
                          EditAction(label=text))

    def layers_using_mask(self, mask_id: str) -> tuple[str, ...]:
        return tuple(l.instance_id for l in self.recipe.layers
                     if l.mask_id == mask_id)

    def commit(self) -> None:
        """Birlestirme penceresini kapatir (kaydirici birakildiginda)."""
        self._history.seal()

    # ------------------------------------------------------------- gecmis
    def undo(self) -> bool:
        if self._history.undo() is None:
            return False
        self._notify()
        return True

    def redo(self) -> bool:
        if self._history.redo() is None:
            return False
        self._notify()
        return True

    def can_undo(self) -> bool:
        return self._history.can_undo()

    def can_redo(self) -> bool:
        return self._history.can_redo()

    # ---------------------------------------------------------- presetler
    def apply_preset(self, preset, intensity: float = 100.0, *,  # noqa: ANN001
                     accumulate: bool = False) -> None:
        """Preseti uygular.

        `accumulate=False` (varsayilan, karta tiklama): onceki preset
        katmanlari kaldirilir, yenileri gelir. Ayni presete tekrar
        tiklamak yigini cogaltmaz.

        `accumulate=True` ("Yigina ekle"): preset katmanlari mevcut
        yiginin sonuna eklenir ve preset grubuna dahil olmaz; boylece
        sonraki preset secimi bunlari silmez.
        """
        recipe = preset.with_intensity(intensity)
        entries = [(l.op_id, dict(l.params)) for l in recipe.layers]

        if accumulate:
            # Birikimli ekleme: katmanlar yiginin sonuna gider ve
            # **grupsuz** kalir; sonraki preset tiklamasi bunlari
            # kaldirmaz, kullanicinin bilerek biriktirdigi katmanlardir.
            new = self.recipe
            for op_id, params in entries:
                new = new.add(op_id, params)
            label = f"{preset.name} yığına eklendi"
        else:
            new = self.recipe.replace_group(PRESET_GROUP, entries)
            label = f"Görünüm: {preset.name}"
            self._active_preset = preset.preset_id

        new = new.with_seed(recipe.seed)
        self.apply_recipe(new, EditAction(
            label=label, merge_key=f"preset:{preset.preset_id}"))

    def preview_preset(self, preset, intensity: float = 100.0):  # noqa: ANN001
        """Gecici onizleme tarifi dondurur; **belgeyi degistirmez**.

        Hover onizlemesi bunu kullanir: kullanici fareyle gezerken
        projesi degismemeli.
        """
        recipe = preset.with_intensity(intensity)
        entries = [(l.op_id, dict(l.params)) for l in recipe.layers]
        return self.recipe.replace_group(PRESET_GROUP, entries)                    .with_seed(recipe.seed)

    def clear_preset(self) -> None:
        """Preset katmanlarini kaldirir, elle ayarlari korur."""
        if not self.recipe.layers_in_group(PRESET_GROUP):
            return
        self._active_preset = ""
        self.apply_recipe(self.recipe.remove_group(PRESET_GROUP),
                          EditAction(label="Görünüm kaldırıldı"))

    @property
    def active_preset_id(self) -> str:
        return self._active_preset

    @property
    def has_manual_edits(self) -> bool:
        """Preset disinda elle yapilmis ayar var mi?"""
        return any(l.group != PRESET_GROUP for l in self.recipe.layers)

    # ------------------------------------------------------ tarif kopyala
    def copy_recipe(self) -> Recipe:
        """Tarifi baska fotografa uygulamak icin dondurur."""
        return self.recipe

    def paste_recipe(self, recipe: Recipe) -> None:
        self.apply_recipe(recipe, EditAction(label="Tarif yapıştırıldı"))


def _unique_mask_id(existing: dict[str, Any]) -> str:
    """Var olanlarla cakismayan kisa bir maske kimligi uretir."""
    index = 1
    while f"maske{index}" in existing:
        index += 1
    return f"maske{index}"


def _relative_geometry(old: Geometry, new: Geometry) -> Geometry:
    """Iki kadraj arasindaki bagil donusum.

    Maskeler `old` kadrajin normalize uzayindadir; sonuc onlari `new`
    kadrajin uzayina goturur. Yeni kirpma, eski kirpmanin koordinat
    sisteminde ifade edilir.
    """
    ox, oy, ow, oh = old.crop
    nx, ny, nw, nh = new.crop
    ow = max(1e-6, ow)
    oh = max(1e-6, oh)
    return Geometry(
        crop=((nx - ox) / ow, (ny - oy) / oh, nw / ow, nh / oh),
        rotation=(new.rotation - old.rotation) % 360,
        flip_h=new.flip_h != old.flip_h,
        flip_v=new.flip_v != old.flip_v,
    )

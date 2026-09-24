"""Tahribatsiz duzenleme tarifi (recipe).

Tarif, bir fotografa uygulanacak islemlerin *sirali* listesidir.
Piksel icermez; JSON'a serilesir, projeye kaydedilir, baska fotografa
kopyalanir ve her seferinde kaynaktan yeniden hesaplanir. Bu yuzden
projeyi acip yeniden kaydetmek ek kalite kaybi yaratmaz.

Sira onemlidir ve sonucu gercekten degistirir: once doygunluk sonra
siyah-beyaz baska, tersi baska sonuc verir.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from luma_atelier.core.branding import APP_VERSION, PRESET_FORMAT_VERSION
from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.effects.base import (
    REGISTRY,
    Operation,
    RenderContext,
)
from luma_atelier.imaging.geometry import Geometry
from luma_atelier.imaging.masks import MaskStack, apply_masked

log = logging.getLogger(__name__)



#: Beyaz dengesi kaydiricisinin yonu v2'de duzeltildi. v1 tariflerinde
#: sayi tersti; goruntu ayni kalsin diye deger 6500 K ekseninde
#: yansitilir (kazanc log(K/6500) ile orantili oldugu icin bu birebir
#: ayni sonucu verir).
NEUTRAL_KELVIN = 6500.0


def _migrate_layer(raw: dict[str, Any], version: int) -> dict[str, Any]:
    """Eski surumden gelen katmani bu surumun anlamina cevirir."""
    if version >= 2 or raw.get("op") != "color.white_balance":
        return raw
    params = raw.get("params")
    if not isinstance(params, dict):
        return raw
    try:
        kelvin = float(params.get("kelvin", NEUTRAL_KELVIN))
    except (TypeError, ValueError):
        return raw
    if kelvin <= 0.0:
        return raw
    mirrored = NEUTRAL_KELVIN * NEUTRAL_KELVIN / kelvin
    log.info("v1 beyaz dengesi cevrildi: %.0f K -> %.0f K", kelvin, mirrored)
    return {**raw, "params": {**params, "kelvin": round(mirrored, 1)}}


class RecipeError(Exception):
    """Tarif okunamadi veya gecersiz."""


@dataclass(frozen=True)
class Layer:
    """Yigindaki tek bir islem ornegi.

    `instance_id` ayni islemin birden fazla kez kullanilabilmesini
    saglar (orn. iki farkli yaricapta bulaniklik).
    """

    op_id: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    mask_id: str | None = None
    label: str = ""
    """Kullanicinin verdigi ad; bos ise islemin adi kullanilir."""
    group: str = ""
    """Katmanin ait oldugu grup.

    Preset uygulandiginda tum katmanlari ayni gruba yazilir. Baska bir
    presete tiklandiginda **once eski grup kaldirilir**, sonra yenisi
    eklenir; boylece tekrar tiklama yigini cogaltmaz. Kullanicinin elle
    ekledigi katmanlarin grubu bostur ve preset degisiminden
    etkilenmez.
    """

    def operation(self) -> Operation | None:
        return REGISTRY.get(self.op_id)

    def display_name(self) -> str:
        if self.label:
            return self.label
        op = self.operation()
        return op.name if op else self.op_id

    def with_param(self, key: str, value: Any) -> Layer:
        return replace(self, params={**self.params, key: value})

    def with_params(self, values: dict[str, Any]) -> Layer:
        return replace(self, params={**self.params, **values})

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "op": self.op_id,
            "instance": self.instance_id,
            "params": _jsonify(self.params),
        }
        if not self.enabled:
            data["enabled"] = False
        if self.mask_id:
            data["mask"] = self.mask_id
        if self.label:
            data["label"] = self.label
        if self.group:
            data["group"] = self.group
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Layer:
        op_id = data.get("op")
        if not isinstance(op_id, str) or not op_id:
            raise RecipeError("Katmanda geçerli bir işlem kimligi yok")
        params = data.get("params", {})
        if not isinstance(params, dict):
            raise RecipeError(f"{op_id}: parametreler sozluk olmali")
        return Layer(
            op_id=op_id,
            params=dict(params),
            enabled=bool(data.get("enabled", True)),
            instance_id=str(data.get("instance") or uuid.uuid4().hex[:12]),
            mask_id=data.get("mask") or None,
            label=str(data.get("label", "")),
            group=str(data.get("group", "")),
        )


@dataclass(frozen=True)
class Recipe:
    """Sirali islem listesi.

    Degismezdir: her duzenleme yeni bir Recipe dondurur. Bu, geri
    alma/yineleme yiginini onemsiz hale getirir - gecmis yalnizca
    onceki tarifleri tutar.
    """

    layers: tuple[Layer, ...] = ()
    seed: int = 1
    """Tarif seviyesindeki temel seed; grain/toz/leak bundan turer."""
    version: int = PRESET_FORMAT_VERSION
    app_version: str = APP_VERSION
    unknown_layers: tuple[dict[str, Any], ...] = ()
    """Bu surumun tanimadigi katmanlar. **Silinmez**, saklanir ve
    yeniden kaydedilirken geri yazilir; boylece eski surumle acilan bir
    proje yeni efektleri kaybetmez."""
    geometry: Geometry = field(default_factory=Geometry)
    """Kirpma, dondurme, cevirme ve ufuk duzeltme.

    Yiginin *disinda* ve her zaman **once** uygulanir. Kirpma goruntu
    boyutunu degistirir; yigin ortasinda boyut degisikligi maskeleri,
    detay karosunu ve onizleme/tam boy eslemesini bozardi.
    """
    masks: dict[str, MaskStack] = field(default_factory=dict)
    """maske kimligi -> maske yigini. Katmanlar `mask_id` ile baglanir."""

    # ------------------------------------------------------------ sorgular
    def __len__(self) -> int:
        return len(self.layers)

    def __iter__(self) -> Iterator[Layer]:
        return iter(self.layers)

    @property
    def is_empty(self) -> bool:
        return not self.layers

    @property
    def active_layers(self) -> tuple[Layer, ...]:
        return tuple(l for l in self.layers if l.enabled)

    def index_of(self, instance_id: str) -> int:
        for i, l in enumerate(self.layers):
            if l.instance_id == instance_id:
                return i
        return -1

    def find(self, instance_id: str) -> Layer | None:
        i = self.index_of(instance_id)
        return self.layers[i] if i >= 0 else None

    def first_of(self, op_id: str) -> Layer | None:
        for l in self.layers:
            if l.op_id == op_id:
                return l
        return None

    def has(self, op_id: str) -> bool:
        return any(l.op_id == op_id for l in self.layers)

    def used_operations(self) -> list[Operation]:
        """"Bu gorunum nasil olusuyor?" alani icin kullanilan islemler."""
        seen: dict[str, Operation] = {}
        for l in self.layers:
            if not l.enabled:
                continue
            op = l.operation()
            if op is not None:
                seen.setdefault(op.op_id, op)
        return list(seen.values())

    # ----------------------------------------------------------- degisimler
    def add(self, op_id: str, params: dict[str, Any] | None = None,
            *, at: int | None = None, label: str = "") -> Recipe:
        """Yigina yeni islem ekler ve **yeni** tarif dondurur."""
        op = REGISTRY.get(op_id)
        if op is None:
            raise RecipeError(f"Bilinmeyen işlem: {op_id}")
        layer = Layer(op_id=op_id, params=op.validate(params or {}), label=label)
        layers = list(self.layers)
        layers.insert(len(layers) if at is None else at, layer)
        return replace(self, layers=tuple(layers))

    def remove(self, instance_id: str) -> Recipe:
        return replace(self, layers=tuple(
            l for l in self.layers if l.instance_id != instance_id
        ))

    def update(self, instance_id: str, **params: Any) -> Recipe:
        """Bir katmanin parametrelerini degistirir."""
        i = self.index_of(instance_id)
        if i < 0:
            return self
        layers = list(self.layers)
        layers[i] = layers[i].with_params(params)
        return replace(self, layers=tuple(layers))

    def set_enabled(self, instance_id: str, enabled: bool) -> Recipe:
        i = self.index_of(instance_id)
        if i < 0:
            return self
        layers = list(self.layers)
        layers[i] = replace(layers[i], enabled=enabled)
        return replace(self, layers=tuple(layers))

    def move(self, instance_id: str, new_index: int) -> Recipe:
        """Katmani yiginda tasir. Sira sonucu gercekten degistirir."""
        i = self.index_of(instance_id)
        if i < 0:
            return self
        layers = list(self.layers)
        layer = layers.pop(i)
        layers.insert(max(0, min(len(layers), new_index)), layer)
        return replace(self, layers=tuple(layers))

    def set_or_add(self, op_id: str, **params: Any) -> Recipe:
        """Islem yiginda varsa gunceller, yoksa **kanonik konuma** ekler.

        Ton/renk kaydiricilari bunu kullanir; kaydirici her hareketinde
        yeni katman eklenmemeli.

        Kanonik konum `Operation.stack_order` ile belirlenir. Bu hem
        fotograf duzenleme akisina uygun bir sira verir (beyaz dengesi ->
        pozlama -> ton -> renk -> ayrinti) hem de ayni veri alaninda
        calisan islemleri bir araya toplar; motor boylece transfer
        donusumunu tekrar tekrar yapmaz.

        Kullanicinin efekt listesinden elle ekledigi islemler `add()`
        ile yiginin sonuna gider ve bu siralamaya tabi degildir.
        """
        existing = self.first_of(op_id)
        if existing is not None:
            return self.update(existing.instance_id, **params)

        op = REGISTRY.get(op_id)
        if op is None:
            raise RecipeError(f"Bilinmeyen işlem: {op_id}")
        position = len(self.layers)
        for i, layer in enumerate(self.layers):
            other = layer.operation()
            if other is not None and other.stack_order > op.stack_order:
                position = i
                break
        return self.add(op_id, params, at=position)

    def layers_in_group(self, group: str) -> tuple[Layer, ...]:
        return tuple(l for l in self.layers if l.group == group)

    def remove_group(self, group: str) -> Recipe:
        """Bir gruba ait tum katmanlari kaldirir."""
        if not group:
            return self
        return replace(self, layers=tuple(
            l for l in self.layers if l.group != group
        ))

    def replace_group(self, group: str,
                      entries: list[tuple[str, dict[str, Any]]]) -> Recipe:
        """Grubu yeni katmanlarla degistirir.

        Preset tiklamasi bunu kullanir: eski preset katmanlari kalkar,
        yenileri gelir. Kullanicinin elle ekledigi katmanlar (grup bos)
        korunur ve yeni preset katmanlarindan *sonra* uygulanmaya devam
        eder; boylece kullanicinin kendi ayari preset tarafindan
        ezilmez.
        """
        kept = [l for l in self.layers if l.group != group]
        new_layers = []
        for op_id, params in entries:
            op = REGISTRY.get(op_id)
            if op is None:
                log.info("Preset bilinmeyen islem iceriyor, atlandi: %s", op_id)
                continue
            new_layers.append(Layer(op_id=op_id, params=op.validate(params),
                                    group=group))
        # Preset katmanlari once, kullanicinin elle ayarlari sonra
        return replace(self, layers=tuple(new_layers + kept))

    def clear(self) -> Recipe:
        """Tum katmanlari kaldirir; seed ve bilinmeyen katmanlar korunur."""
        return replace(self, layers=())

    def with_seed(self, seed: int) -> Recipe:
        return replace(self, seed=int(seed) & 0x7FFFFFFF)

    # ------------------------------------------------------------- render
    def apply(self, image: np.ndarray, ctx: RenderContext, *,
              failures: list[str] | None = None) -> np.ndarray:
        """Tarifi goruntuye uygular.

        **Alan gruplamasi:** her islem hangi veri alaninda calistigini
        (`Operation.domain`) bildirir. Motor alani takip eder ve transfer
        donusumunu yalnizca alan *degistiginde* yapar. Pozlama ve beyaz
        dengesi pespese geldiginde iki ayri gidis-donus yerine tek bir
        donusum olur.

        Bilinmeyen islemler atlanir ama tariften silinmez. Bir katman
        hata verirse o katman atlanir ve gunluge yazilir; tum render
        cokmemelidir.

        `failures` verilirse atlanan katmanlarin adlari oraya yazilir.
        Cagiran bunu kullaniciya bildirmelidir: aksi halde bir efekt
        sessizce calismaz ve kullanici bunu yalnizca sonuca bakarak
        anlamaya calisir.
        """
        out = px.ensure_working(image)

        # 1) Geometri - her zaman once. Sonraki her sey yeni kadraj
        #    uzerinde calisir; maskeler de bu kadraja gore uretilir.
        if not self.geometry.is_identity:
            out = px.ensure_working(self.geometry.apply(out))

        local_ctx = replace(ctx, seed=self.seed)
        domain = "srgb"
        shape = out.shape[:2]
        #: Ayni maske birden fazla katmanda kullanilabilir; bir kez uret.
        mask_cache: dict[str, np.ndarray | None] = {}
        #: Maske karistirmasi icin sRGB alanindaki son goruntu
        srgb_reference = out

        for layer in self.layers:
            if not layer.enabled:
                continue
            op = layer.operation()
            if op is None:
                log.debug("Bilinmeyen islem atlandi: %s", layer.op_id)
                if failures is not None:
                    failures.append(layer.op_id)
                continue

            if op.domain != domain:
                out = _convert_domain(out, domain, op.domain)
                domain = op.domain

            before = out
            try:
                processed = op.apply(out, layer.params, local_ctx)
            except Exception:  # noqa: BLE001 - tek katman render'i cokertmesin
                log.exception("Katman uygulanamadi, atlandi: %s (%s)",
                              layer.op_id, layer.instance_id)
                if failures is not None:
                    failures.append(op.name or layer.op_id)
                continue

            mask = self._mask_for(layer, shape, srgb_reference, mask_cache,
                                  local_ctx)
            out = apply_masked(before, processed, mask) if mask is not None \
                else processed

            if domain == "srgb":
                srgb_reference = out

        if domain != "srgb":
            out = _convert_domain(out, domain, "srgb")
        return out

    def tile_reach(self, frame: tuple[int, int]) -> float:
        """Karo render'i icin gereken kenar payi (tam boy piksel).

        Yigindaki bulanikliklar birbirini besler: ilk katmanin okudugu
        uzaklik, ikincinin okuyacagi veriyi de etkiler. Bu yuzden paylar
        **toplanir**; en buyugunu almak yetersiz kalirdi.
        """
        total = 0.0
        for layer in self.layers:
            if not layer.enabled:
                continue
            op = layer.operation()
            if op is None:
                continue
            total += op.tile_reach(layer.params, frame)
        return total

    def _mask_for(self, layer: Layer, shape: tuple[int, int],
                  reference: np.ndarray,
                  cache: dict[str, np.ndarray | None],
                  ctx: RenderContext | None = None) -> np.ndarray | None:
        """Katmanin maskesini uretir (varsa) ve onbellekler.

        `ctx` karo bilgisi tasir: %100 gorunumde yalnizca kadrajin bir
        parcasi islenir, maske ise tum kadrajin normalize uzayinda
        tanimlidir. Konum bildirilmezse maske karonun icine sigdirilirdi.
        """
        if not layer.mask_id:
            return None
        if layer.mask_id in cache:
            return cache[layer.mask_id]
        stack = self.masks.get(layer.mask_id)
        if stack is None:
            log.debug("Katman var olmayan maskeye baglanmis: %s", layer.mask_id)
            cache[layer.mask_id] = None
            return None
        origin = ctx.tile_origin if ctx is not None else (0, 0)
        frame = ctx.tile_frame if ctx is not None else None
        try:
            mask = stack.render(shape, reference, origin=origin, frame=frame)
        except Exception:  # noqa: BLE001 - maske hatasi render'i cokertmesin
            log.exception("Maske uretilemedi: %s", layer.mask_id)
            mask = None
        cache[layer.mask_id] = mask
        return mask

    # -------------------------------------------------------- geometri
    def with_geometry(self, geometry: Geometry) -> Recipe:
        return replace(self, geometry=geometry)

    def without_geometry(self) -> Recipe:
        """Geometrisi bos bir kopya.

        Geometri kaynaga *ayrica* uygulandiginda kullanilir; yoksa
        kirpma iki kez islenirdi.
        """
        if self.geometry.is_identity:
            return self
        return replace(self, geometry=Geometry())

    # --------------------------------------------------------- maskeler
    def with_mask(self, mask_id: str, stack: MaskStack) -> Recipe:
        """Maske yiginini ekler veya degistirir."""
        masks = dict(self.masks)
        masks[mask_id] = stack
        return replace(self, masks=masks)

    def remove_mask(self, mask_id: str) -> Recipe:
        """Maskeyi kaldirir ve ona bagli katmanlarin bagini koparir."""
        masks = {k: v for k, v in self.masks.items() if k != mask_id}
        layers = tuple(
            replace(l, mask_id=None) if l.mask_id == mask_id else l
            for l in self.layers
        )
        return replace(self, masks=masks, layers=layers)

    def assign_mask(self, instance_id: str, mask_id: str | None) -> Recipe:
        """Bir katmani maskeye baglar veya bagini kaldirir."""
        i = self.index_of(instance_id)
        if i < 0:
            return self
        layers = list(self.layers)
        layers[i] = replace(layers[i], mask_id=mask_id or None)
        return replace(self, layers=tuple(layers))

    def transform_masks(self, geometry: Geometry) -> Recipe:
        """Kirpma/dondurme sonrasi tum maskeleri yeni kadraja tasir.

        Gereksinim: "Kirpma/dondurme sonrasi maskeler dogru donusumu
        izlesin."
        """
        if geometry.is_identity or not self.masks:
            return self
        moved = {
            key: MaskStack(masks=tuple(
                m.transformed(geometry.crop, rotation=geometry.rotation,
                              flip_h=geometry.flip_h, flip_v=geometry.flip_v)
                for m in stack.masks
            ))
            for key, stack in self.masks.items()
        }
        return replace(self, masks=moved)

    # ------------------------------------------------------- serilestirme
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": self.version,
            "app_version": self.app_version,
            "seed": self.seed,
            "layers": [l.to_dict() for l in self.layers]
                      + list(self.unknown_layers),
        }
        if not self.geometry.is_identity:
            data["geometry"] = self.geometry.to_dict()
        if self.masks:
            data["masks"] = {k: v.to_dict() for k, v in self.masks.items()}
        return data

    @staticmethod
    def from_dict(data: dict[str, Any], *, strict: bool = False) -> Recipe:
        """Sozlukten tarif okur ve **dogrular**.

        Ice aktarilan JSON'a guvenilmez: kod calistirilmaz, bilinmeyen
        anahtarlar atilir, degerler semaya gore kirpilir.

        Args:
            strict: True ise bilinmeyen islem hata verir. False (varsayilan)
                ise saklanir ve yeniden kaydedilirken geri yazilir.
        """
        if not isinstance(data, dict):
            raise RecipeError("Tarif bir sozluk olmali")

        version = data.get("version", PRESET_FORMAT_VERSION)
        if not isinstance(version, int):
            raise RecipeError("Tarif surumu sayi olmali")
        if version > PRESET_FORMAT_VERSION:
            raise RecipeError(
                f"Bu tarif daha yeni bir surumle olusturulmus "
                f"(v{version}, bu surum v{PRESET_FORMAT_VERSION}). "
                "Uygulamayı guncelleyin."
            )

        raw_layers = data.get("layers", [])
        if not isinstance(raw_layers, list):
            raise RecipeError("Katman listesi dizi olmali")

        layers: list[Layer] = []
        unknown: list[dict[str, Any]] = []
        for raw in raw_layers:
            if not isinstance(raw, dict):
                raise RecipeError("Her katman bir sozluk olmali")
            raw = _migrate_layer(raw, version)
            layer = Layer.from_dict(raw)
            op = layer.operation()
            if op is None:
                if strict:
                    raise RecipeError(f"Bilinmeyen işlem: {layer.op_id}")
                log.info("Bilinmeyen islem saklandi (silinmedi): %s", layer.op_id)
                unknown.append(raw)
                continue
            layers.append(replace(layer, params=op.validate(layer.params)))

        seed = data.get("seed", 1)
        try:
            seed = int(seed) & 0x7FFFFFFF
        except (TypeError, ValueError):
            seed = 1

        raw_masks = data.get("masks", {})
        masks: dict[str, MaskStack] = {}
        if isinstance(raw_masks, dict):
            for key, entries in raw_masks.items():
                masks[str(key)] = MaskStack.from_list(entries)

        return Recipe(
            # Tasinan tarif artik guncel semaya uyar; eski surumle
            # kaydedilirse ikinci kez cevrilirdi.
            layers=tuple(layers), seed=seed, version=PRESET_FORMAT_VERSION,
            app_version=str(data.get("app_version", APP_VERSION)),
            unknown_layers=tuple(unknown),
            geometry=Geometry.from_dict(data.get("geometry")),
            masks=masks,
        )


def _convert_domain(image: np.ndarray, source: str, target: str) -> np.ndarray:
    """Calisma verisini bir alandan digerine cevirir.

    Alpha kanali transfer fonksiyonundan gecmez; opaklik dogrusaldir.
    """
    if source == target:
        return image
    rgb, alpha = px.split_alpha(image)
    if target == "linear":
        converted = px.srgb_to_linear(rgb)
    else:
        converted = px.linear_to_srgb(rgb)
    return px.join_alpha(converted, alpha)


def _jsonify(value: Any) -> Any:
    """NumPy tiplerini JSON'un anladigi tiplere cevirir."""
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value

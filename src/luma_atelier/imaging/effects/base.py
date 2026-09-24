"""Efekt altyapisi: parametre semasi, render baglami ve kayit sistemi.

Tasarim sozlesmesi
------------------
Bir *islem* (operation) goruntuyu degistiren tek bir algoritmadir.
Bir *tarif* (recipe) sirali islem ornekleridir. Bir *preset* kaydedilmis
bir tariftir. Bu ayrim onemli: "120 preset" 120 algoritma degil,
35+ islemin duzenlenebilir birlesimleridir.

Her islem su sozlesmeye uyar:

1. **Cozunurlukten bagimsiz sonuc.** Onizleme (orn. 2048 px) ile tam boy
   (orn. 6000 px) *ayni* kodu ve ayni parametreleri kullanir. Piksel
   cinsinden olculen parametreler (blur yaricapi, grain boyutu)
   `RenderContext.scale` ile olceklenir; boylece onizlemedeki karakter
   tam boyda korunur.
2. **Deterministik.** Rastgelelik kullanan islemler `RenderContext`
   uzerinden turetilmis seed alir; ayni seed + ayni tarif = ayni sonuc.
3. **Yogunluk 0 kimliktir.** `amount=0` girdiyi *birebir* dondurur.
4. **Girdiyi degistirmez.** Islem yeni dizi dondurur.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Protocol

import numpy as np

from luma_atelier.imaging import pixels as px

log = logging.getLogger(__name__)


class Category(str, Enum):
    """Islem kategorileri - arayuzde sol panelde gruplanir."""

    TONE = "tone"
    COLOR = "color"
    DETAIL = "detail"
    BLUR = "blur"
    LIGHT = "light"
    FILM = "film"
    TEXTURE = "texture"
    LENS = "lens"
    STYLE = "style"
    GEOMETRY = "geometry"

    @property
    def label(self) -> str:
        return {
            Category.TONE: "Ton",
            Category.COLOR: "Renk",
            Category.DETAIL: "Ayrıntı",
            Category.BLUR: "Bulanıklık",
            Category.LIGHT: "Işık",
            Category.FILM: "Film",
            Category.TEXTURE: "Doku",
            Category.LENS: "Lens",
            Category.STYLE: "Stil",
            Category.GEOMETRY: "Geometri",
        }[self]

    @property
    def order(self) -> int:
        """Yiginda onerilen sira. Kucuk once uygulanir."""
        return {
            Category.GEOMETRY: 0,
            Category.TONE: 10,
            Category.COLOR: 20,
            Category.DETAIL: 30,
            Category.STYLE: 40,
            Category.BLUR: 50,
            Category.LIGHT: 60,
            Category.FILM: 70,
            Category.LENS: 80,
            Category.TEXTURE: 90,
        }[self]


class ParamKind(str, Enum):
    """Parametrenin arayuzde nasil gosterilecegi ve nasil olceklenecegi."""

    SCALAR = "scalar"
    """Olceklenmez; pozlama, kontrast gibi."""
    PIXELS = "pixels"
    """Piksel cinsinden; onizlemede `scale` ile carpilir (blur yaricapi)."""
    NORMALISED = "normalised"
    """0..1 goruntu genisliginin orani; olceklenmez ama konum bildirir."""
    ANGLE = "angle"
    CHOICE = "choice"
    BOOLEAN = "boolean"
    COLOR = "color"
    SEED = "seed"
    CURVE = "curve"
    """Kontrol noktasi listesi."""


@dataclass(frozen=True)
class ParamSpec:
    """Tek bir parametrenin dogrulanmis tanimi.

    Arayuz kaydiricisi, JSON serilestirme ve dogrulama hep buradan
    turer; parametre sinirlari tek yerde tanimlanir.
    """

    key: str
    label: str
    kind: ParamKind = ParamKind.SCALAR
    minimum: float = -100.0
    maximum: float = 100.0
    default: Any = 0.0
    decimals: int = 0
    step: float = 1.0
    page_step: float = 10.0
    suffix: str = ""
    bipolar: bool | None = None
    choices: tuple[tuple[str, Any], ...] = ()
    allow_free_choice: bool = False
    """CHOICE turunde listede olmayan deger kabul edilsin mi?

    LUT secimi icin gerekli: kullanici uygulama acikken yeni bir .cube
    dosyasi ice aktarabilir ve bu deger kayit anindaki listede yoktur.
    Deger yine de dogrulanir (bos olmayan metin olmali).
    """
    tooltip: str = ""
    unit_note: str = ""
    """Parametrenin birimi ve etkidigi renk uzayi (belgeleme icin)."""

    @property
    def is_bipolar(self) -> bool:
        if self.bipolar is not None:
            return self.bipolar
        return self.minimum < 0.0 < self.maximum

    def clamp(self, value: Any) -> Any:
        """Degeri gecerli araliga getirir; gecersiz girdide varsayilana doner."""
        if self.kind is ParamKind.BOOLEAN:
            return bool(value)
        if self.kind is ParamKind.CHOICE:
            valid = {v for _, v in self.choices}
            if value in valid:
                return value
            if self.allow_free_choice and isinstance(value, str) and value:
                return value
            return self.default
        if self.kind is ParamKind.COLOR:
            try:
                r, g, b = (float(c) for c in value)
            except (TypeError, ValueError):
                return self.default
            return (min(1.0, max(0.0, r)), min(1.0, max(0.0, g)),
                    min(1.0, max(0.0, b)))
        if self.kind is ParamKind.SEED:
            try:
                return int(value) & 0x7FFFFFFF
            except (TypeError, ValueError):
                return self.default
        if self.kind is ParamKind.CURVE:
            return value if isinstance(value, (list, tuple)) else self.default
        try:
            v = float(value)
        except (TypeError, ValueError):
            return self.default
        if not np.isfinite(v):
            return self.default
        return min(self.maximum, max(self.minimum, v))


@dataclass(frozen=True)
class RenderContext:
    """Islemin hangi kosullarda calistigini bildirir.

    `scale` en kritik alan: onizleme tam boyun kacta kaci oldugunu
    soyler. Piksel cinsinden parametreler bununla carpilir ki onizlemede
    gorulen karakter tam boyda ayni kalsin.
    """

    full_width: int
    full_height: int
    scale: float = 1.0
    """Islenen goruntunun tam boya orani (0..1]."""
    seed: int = 0
    """Tarif seviyesindeki temel seed."""
    quality: str = "final"
    """"interactive" (surukleme sirasinda) veya "final"."""
    purpose: str = "preview"
    """"preview", "export", "thumbnail" - gunluk ve onbellek anahtari."""
    tile_origin: tuple[int, int] = (0, 0)
    """Islenen bolgenin tam kadrajdaki sol-ust kosesi (islenen olcekte).

    Yalnizca %100 gorunum karosu icin sifirdan farklidir.
    """
    tile_frame: tuple[int, int] | None = None
    """Karonun ait oldugu tam kadrajin (genislik, yukseklik).

    None ise islenen dizi zaten tam kadrajdir. Konuma bagli efektler
    bu alani `frame_size()` / `coords()` uzerinden kullanir.
    """

    @property
    def is_interactive(self) -> bool:
        return self.quality == "interactive"

    def scaled(self, pixel_value: float) -> float:
        """Piksel cinsinden bir degeri bu cozunurluge uyarlar."""
        return pixel_value * self.scale

    # ------------------------------------------------------- konum bilgisi
    def frame_size(self, height: int, width: int) -> tuple[int, int]:
        """Islenen verinin ait oldugu **tam kadrajin** (yukseklik, genislik).

        Normal render'da islenen dizi zaten tam kadrajdir. %100 gorunum
        icin yalnizca bir *karo* islenir; o durumda konuma bagli efektler
        (vignette, tilt-shift, isik sizintisi, maskeler) karoyu tum
        fotograf sanmamali - yoksa vignette karonun ortasinda olusur.
        """
        if self.tile_frame is None:
            return height, width
        return self.tile_frame[1], self.tile_frame[0]

    def coords(self, height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
        """Islenen bolgenin (yy, xx) izgarasi, **tam kadraj** koordinatinda.

        Karo islenirken izgara karonun kadraj icindeki konumundan baslar.
        """
        ox, oy = self.tile_origin
        yy, xx = np.mgrid[oy:oy + height, ox:ox + width]
        return yy.astype(np.float32), xx.astype(np.float32)

    def normalised_coords(self, height: int,
                          width: int) -> tuple[np.ndarray, np.ndarray]:
        """(yy, xx) izgarasi 0..1 araliginda, tam kadraja gore."""
        frame_h, frame_w = self.frame_size(height, width)
        yy, xx = self.coords(height, width)
        return (yy / max(1.0, float(frame_h - 1)),
                xx / max(1.0, float(frame_w - 1)))

    @property
    def is_tile(self) -> bool:
        """Tam kadrajin yalnizca bir bolumu mu isleniyor?"""
        return self.tile_frame is not None

    def derive_seed(self, *parts: str | int) -> int:
        """Islem basina kararli, tekrarlanabilir seed uretir.

        Ayni tarif + ayni islem = ayni seed, cozunurlukten bagimsiz.
        """
        raw = "|".join(str(p) for p in (self.seed, *parts)).encode()
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    def rng(self, *parts: str | int) -> np.random.Generator:
        return np.random.default_rng(self.derive_seed(*parts))


class OperationFn(Protocol):
    """Islem fonksiyonunun imzasi."""

    def __call__(self, image: np.ndarray, params: dict[str, Any],
                 ctx: RenderContext) -> np.ndarray: ...


class NeighbourhoodFn(Protocol):
    """Islemin okudugu en uzak komsu mesafesi (tam boy piksel)."""

    def __call__(self, params: dict[str, Any],
                 frame: tuple[int, int]) -> float: ...


@dataclass(frozen=True)
class Operation:
    """Kayitli bir goruntu islemi."""

    op_id: str
    name: str
    description: str
    category: Category
    params: tuple[ParamSpec, ...]
    fn: OperationFn
    supports_mask: bool = True
    supports_amount: bool = True
    """Yogunluk (opaklik) karistirmasi uygulanabilir mi?"""
    domain: str = "srgb"
    """Islemin calistigi veri alani: "srgb" veya "linear".

    Motor ardisik ayni alandaki islemleri gruplar ve transfer
    donusumunu yalnizca alan degistiginde yapar. Pozlama + beyaz
    dengesi gibi iki lineer islem pespese geldiginde iki degil **bir**
    gidis-donus olur; olculen kazanc 2 MP onizlemede islem basina
    ~67 ms.

    "linear" bildiren bir islem `fn` icinde lineer isik verisi alir ve
    lineer isik dondurur; kendi donusumunu yapmaz.
    """
    changes_size: bool = False
    """Islem goruntu boyutunu degistirebilir mi?

    Neredeyse tum islemler boyutu korur; maskeler, detay karosu ve
    onizleme/tam boy esleme buna dayanir. Kirpma gibi *bilerek* boyut
    degistiren islemler bunu acikca bildirir ve sozlesmenin
    "boyut korunur" maddesinden muaf tutulur.
    """
    resolution_exact: bool = True
    """Onizleme, tam boyun kucultulmusuyle piksel duzeyinde eslesir mi?

    Deterministik islemler icin True. Stokastik doku islemleri (grain,
    toz, kagit) icin False: desen *cozunurluge bagli* uretilir, bu
    yuzden yari cozunurlukte piksel piksel ayni olamaz. Bu bilinen ve
    belgelenmis bir istisnadir; gereksinim belgesi de "kucuk onizleme,
    ozellikle grain icin tam boy detayin yaklasik temsili olabilir"
    diyor. Bu islemler yine de *istatistiksel* olarak test edilir:
    ortalama ve standart sapma esit kalmali.
    """
    identity_at_defaults: bool = True
    """Varsayilan parametreler goruntuyu aynen birakir mi?

    *Ayar* islemleri (pozlama, kontrast) icin True: notr degerde hicbir
    sey degismemeli. *Donusum* islemleri (siyah-beyaz, duotone, bleach
    bypass) icin False: yigina eklendiginde gorunur bir sey yapmalari
    beklenir, aksi halde "calismayan dugme" hissi olusur. Bu islemlerde
    de `amount=0` birebir kimliktir; sozlesme orada dogrulanir.
    """
    color_space: str = "sRGB"
    """Islemin etkili oldugu uzay - belgeleme ve dogrulama icin."""
    performance_note: str = ""
    order_hint: int | None = None
    """None ise kategori sirasi kullanilir."""
    neighbourhood: NeighbourhoodFn | None = None
    """Islem kac piksel uzaktaki komsuyu okuyor? (tam boy piksel)

    %100 gorunum yalnizca gorunen bolgeyi isler. Bulaniklik, bloom,
    halation gibi islemler karo disindaki pikselleri de okur; yeterli
    kenar payi birakilmazsa karo sinirinda dikis olusur ve ekrandaki
    goruntu cikti dosyasindan farkli olur. Bu geri cagri, verilen
    parametrelerde gereken payi bildirir. None = yalnizca kendi
    pikselini okur.
    """

    @property
    def stack_order(self) -> int:
        return self.order_hint if self.order_hint is not None else self.category.order

    def param(self, key: str) -> ParamSpec | None:
        for p in self.params:
            if p.key == key:
                return p
        return None

    def defaults(self) -> dict[str, Any]:
        return {p.key: p.default for p in self.params}

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Gelen parametreleri semaya gore temizler.

        Bilinmeyen anahtarlar atilir, eksikler varsayilanla doldurulur,
        araliga sigmayanlar kirpilir. Ice aktarilan preset dosyasina
        guvenilmez; bu fonksiyon tek giris kapisidir.
        """
        out: dict[str, Any] = {}
        for spec in self.params:
            if spec.key in params:
                out[spec.key] = spec.clamp(params[spec.key])
            else:
                out[spec.key] = spec.default
        unknown = set(params) - {p.key for p in self.params}
        if unknown:
            log.debug("%s: bilinmeyen parametre yok sayildi: %s",
                      self.op_id, sorted(unknown))
        return out

    def tile_reach(self, params: dict[str, Any],
                   frame: tuple[int, int]) -> float:
        """Karo render'i icin gereken kenar payi (tam boy piksel).

        Hata durumunda 0 degil, guvenli taraf secilemez: pay bilinmiyorsa
        cagiran taban payi kullanir. Bu yuzden hata sessizce yutulmaz,
        gunluge yazilir.
        """
        if self.neighbourhood is None:
            return 0.0
        try:
            return max(0.0, float(self.neighbourhood(self.validate(params),
                                                     frame)))
        except Exception:  # noqa: BLE001 - pay hesabi render'i cokertmesin
            log.exception("%s: kenar payi hesaplanamadi", self.op_id)
            return 0.0

    def apply(self, image: np.ndarray, params: dict[str, Any],
              ctx: RenderContext) -> np.ndarray:
        """Islemi uygular. Girdi degistirilmez."""
        clean = self.validate(params)
        out = self.fn(image, clean, ctx)
        if out.dtype != px.WORKING_DTYPE:
            out = out.astype(px.WORKING_DTYPE, copy=False)
        return out


class OperationRegistry:
    """Tum islemlerin merkezi kaydi.

    Kimlikler benzersizdir; ayni kimligi iki kez kaydetmek hatadir
    (sessizce ustune yazmak, "adi farkli ayni efekt" sorununu gizler).
    """

    def __init__(self) -> None:
        self._ops: dict[str, Operation] = {}

    def register(self, operation: Operation) -> Operation:
        if operation.op_id in self._ops:
            raise ValueError(f"İşlem kimligi zaten kayıtlı: {operation.op_id}")
        self._ops[operation.op_id] = operation
        return operation

    def get(self, op_id: str) -> Operation | None:
        return self._ops.get(op_id)

    def require(self, op_id: str) -> Operation:
        op = self._ops.get(op_id)
        if op is None:
            raise KeyError(f"Bilinmeyen işlem: {op_id}")
        return op

    def __contains__(self, op_id: object) -> bool:
        return op_id in self._ops

    def __len__(self) -> int:
        return len(self._ops)

    def __iter__(self) -> Iterator[Operation]:
        return iter(self._ops.values())

    def all(self) -> list[Operation]:
        return sorted(self._ops.values(), key=lambda o: (o.category.order, o.name))

    def by_category(self) -> dict[Category, list[Operation]]:
        out: dict[Category, list[Operation]] = {}
        for op in self.all():
            out.setdefault(op.category, []).append(op)
        return out

    def search(self, needle: str) -> list[Operation]:
        n = needle.casefold().strip()
        if not n:
            return self.all()
        return [o for o in self.all()
                if n in o.name.casefold() or n in o.description.casefold()
                or n in o.op_id]


REGISTRY = OperationRegistry()


def operation(
    op_id: str, name: str, description: str, category: Category,
    params: tuple[ParamSpec, ...] = (), *,
    supports_mask: bool = True, supports_amount: bool = True,
    domain: str = "srgb", identity_at_defaults: bool = True,
    changes_size: bool = False, resolution_exact: bool = True,
    color_space: str = "sRGB", performance_note: str = "",
    order_hint: int | None = None,
    neighbourhood: NeighbourhoodFn | None = None,
) -> Callable[[OperationFn], Operation]:
    """Bir fonksiyonu islem olarak kaydeden dekorator."""

    def decorator(fn: OperationFn) -> Operation:
        return REGISTRY.register(Operation(
            op_id=op_id, name=name, description=description, category=category,
            params=params, fn=fn, supports_mask=supports_mask,
            supports_amount=supports_amount, domain=domain,
            identity_at_defaults=identity_at_defaults,
            changes_size=changes_size, resolution_exact=resolution_exact,
            color_space=color_space,
            performance_note=performance_note, order_hint=order_hint,
            neighbourhood=neighbourhood,
        ))

    return decorator


# --------------------------------------------------------------- yardimcilar

def amount_spec(default: float = 100.0, label: str = "Yoğunluk") -> ParamSpec:
    """Standart yogunluk parametresi. 0 = kimlik."""
    return ParamSpec(
        key="amount", label=label, kind=ParamKind.SCALAR,
        minimum=0.0, maximum=100.0, default=default, decimals=0,
        step=1.0, page_step=10.0, suffix=" %", bipolar=False,
        tooltip="Etkinin şiddeti. %0 orijinali birebir korur.",
    )


def seed_spec(default: int = 1) -> ParamSpec:
    """Deterministik rastgelelik icin seed."""
    return ParamSpec(
        key="seed", label="Desen", kind=ParamKind.SEED,
        minimum=0, maximum=2 ** 31 - 1, default=default, decimals=0,
        step=1.0, page_step=1.0, bipolar=False,
        tooltip="Rastgele deseni belirler. Aynı değer aynı sonucu verir.",
    )


def apply_amount(original: np.ndarray, processed: np.ndarray,
                 params: dict[str, Any]) -> np.ndarray:
    """Yogunluk karistirmasini uygular.

    `amount` parametresi yoksa islenmis goruntu aynen doner.
    """
    amount = params.get("amount")
    if amount is None:
        return processed
    return px.blend(original, processed, float(amount) / 100.0)

"""%100 gorunum karosu, dista aktarilan dosyayla ayni goruntuyu vermeli.

Neden ayri bir dosya
--------------------
`test_detail_tile.py` karonun **cozunurlugunu** kanitlar (ince desen
korunuyor mu). Buradaki soru farkli: karo *dogru yerde* mi? Konuma
bagli efektler (vignette, tilt-shift, isik sizintisi, maskeler, film
grain, toz) izgaralarini islenen dizinin boyutundan kurarsa, %100
gorunumde islenen karo kendini "tum fotograf" sanir. Kullanici o zaman
ekranda, cikti dosyasinda olmayan bir karartma veya farkli bir tane
deseni gorur.

Bu test **kullanici acisindan beklenen sonucu** olcer: karonun
pikselleri, ayni tarifin tam boy sonucundaki ayni bolgeyle esit
olmalidir. Her durum ayrica "efekt bu bolgede gercekten bir sey
degistiriyor mu" diye denetlenir; yoksa etkisiz bir efektle test
kendiliginden gecerdi - bu hata bir kez gerceklesti.
"""
from __future__ import annotations

import numpy as np
import pytest

from luma_atelier.imaging.effects.base import RenderContext
from luma_atelier.imaging.masks.mask import BlendOp, Mask, MaskKind, MaskStack
from luma_atelier.imaging.recipe import Layer, Recipe
from luma_atelier.services.render import RenderService

#: Karo kadrajin ortasinda **degil**: merkezde olsaydi merkeze bagli
#: efektlerin kaymasi fark etmezdi.
RECT = (700, 120, 420, 320)

#: Izin verilen sapma. Sifir degil: kagit dokusunun lif adimi karo
#: icinde yeniden normallenir (olculen en buyuk sapma 0.0003).
TOLERANCE = 0.002


@pytest.fixture(scope="module")
def source() -> np.ndarray:
    h, w = 900, 1400
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([
        0.25 + 0.5 * xx / w,
        0.35 + 0.3 * yy / h,
        0.55 - 0.25 * xx / w,
    ]).astype(np.float32)
    # Duz alanda konum kaymasi gorunmez; doku ekle
    img += 0.05 * np.sin(xx / 17.0)[..., None].astype(np.float32)
    # Parlak kaynaklar: bloom, halation ve anamorfik esik uzeri
    # piksellere ihtiyac duyar. Biri karonun **disinda** (yayilim karoya
    # disaridan gelmeli), biri icinde.
    for cx, cy, r in ((420, 560, 55), (980, 260, 40)):
        d = (xx - cx) ** 2 + (yy - cy) ** 2
        img[d < r * r] = 1.0
    return np.clip(img, 0.0, 1.0)


def _simple(op_id: str, params: dict) -> Recipe:
    return Recipe(layers=(Layer(op_id=op_id, instance_id="l1",
                                params=params),), seed=7)


def _masked() -> Recipe:
    # Maske merkezi karonun **icinde**; disinda olsaydi fark olcumu
    # maskeyi degil tesadufu olcerdi.
    mask = Mask(mask_id="m1", kind=MaskKind.RADIAL, center=(0.65, 0.31),
                radius=(0.18, 0.18), feather=0.03, blend=BlendOp.ADD)
    layer = Layer(op_id="tone.exposure", instance_id="l1",
                  params={"stops": 1.6}, mask_id="m1")
    return Recipe(layers=(layer,), masks={"m1": MaskStack(masks=(mask,))})


CASES = [
    ("vignette", _simple("lens.vignette", {"amount": -100.0})),
    ("radyal maske", _masked()),
    ("film grain", _simple("texture.grain", {"amount": 100.0})),
    ("toz ve cizik", _simple("texture.dust",
                             {"dust": 60.0, "scratches": 50.0})),
    ("kagit dokusu", _simple("texture.paper", {"strength": 80.0})),
    ("tilt-shift", _simple("blur.tilt_shift",
                           {"radius": 60.0, "position": 0.35,
                            "width": 0.10, "feather": 0.05})),
    ("isik sizintisi", _simple("texture.light_leak", {"intensity": 80.0})),
    ("radyal bulaniklik", _simple("blur.motion",
                                  {"mode": "radial", "strength": 70.0,
                                   "protect_center": 60.0})),
    # Genis yaricapli islemler: 96 px taban pay bunlara yetmez, tarif
    # gereken payi bildirmeli. Olculen dikis 96 px payla anamorfikte
    # 0.46, halation'da 0.13 idi.
    ("genis gaussian", _simple("blur.gaussian", {"radius": 200.0})),
    ("bloom r=300", _simple("light.bloom", {"radius": 300.0,
                                            "intensity": 150.0,
                                            "threshold": 0.6})),
    ("halation r=150", _simple("light.halation", {"radius": 150.0,
                                                  "intensity": 150.0,
                                                  "threshold": 0.6})),
    ("anamorfik l=800", _simple("light.anamorphic", {"length": 800.0,
                                                     "intensity": 150.0,
                                                     "threshold": 0.6})),
    ("kromatik aberasyon", _simple("lens.chromatic_aberration",
                                   {"amount": 100.0, "edge_only": False})),
]


@pytest.fixture(scope="module")
def service() -> RenderService:
    svc = RenderService()
    yield svc
    svc.shutdown()


class TestTileMatchesFullRender:
    """Karo, tam boy render'in ayni bolgesiyle ayni olmali."""

    @pytest.mark.parametrize("name,recipe", CASES,
                             ids=[c[0] for c in CASES])
    def test_tile_equals_full_region(self, name: str, recipe: Recipe,
                                     source: np.ndarray,
                                     service: RenderService) -> None:
        h, w = source.shape[:2]
        x, y, rw, rh = RECT
        ctx = RenderContext(full_width=w, full_height=h, scale=1.0,
                            seed=recipe.seed, quality="final",
                            purpose="export")
        full = recipe.apply(source, ctx)
        region = full[y:y + rh, x:x + rw, :3].astype(np.float64)
        original = source[y:y + rh, x:x + rw, :3].astype(np.float64)

        effect = float(np.abs(region - original).mean())
        assert effect > 1e-4, (
            f"{name}: efekt bu bolgede hic piksel degistirmiyor; "
            "test kendiliginden gecerdi"
        )

        tile = service.render_tile(source, recipe, RECT)[..., :3]
        assert tile.shape[:2] == (rh, rw)
        diff = float(np.abs(tile.astype(np.float64) - region).mean())
        assert diff < TOLERANCE, (
            f"{name}: karo tam boy sonuctan sapiyor (ortalama {diff:.4f}); "
            "%100 gorunum cikti dosyasindan farkli gorunur"
        )


#: Maskenin kendi `render`'inda kenar payi yoktur: yumusatma bulanikligi
#: karo sinirinda kesilir. Gercek yolda `render_tile` 96 piksel pay
#: birakarak bunu onler (yukaridaki uctan uca testler bunu kanitlar).
#: Buradaki birim testler bu yuzden ic bolgeyi karsilastirir.
EDGE = 64


class TestMaskTileGeometry:
    """Maske uretimi karo konumunu dogru ele almali."""

    def test_tile_mask_matches_full_frame_region(self) -> None:
        mask = Mask(mask_id="m1", kind=MaskKind.RADIAL, center=(0.65, 0.31),
                    radius=(0.18, 0.18), feather=0.03)
        full = mask.render((900, 1400))
        x, y, rw, rh = RECT
        tile = mask.render((rh, rw), origin=(x, y), frame=(1400, 900))
        region = full[y:y + rh, x:x + rw]
        assert region.max() > 0.5, "maske karo bolgesine hic dusmuyor"
        inner = (slice(EDGE, rh - EDGE), slice(EDGE, rw - EDGE))
        assert float(np.abs(tile[inner] - region[inner]).max()) < 0.002

    def test_brush_mask_follows_frame(self) -> None:
        from luma_atelier.imaging.masks.mask import BrushStroke

        stroke = BrushStroke(points=((0.62, 0.28), (0.72, 0.36)),
                             radius=0.05)
        mask = Mask(mask_id="b1", kind=MaskKind.BRUSH, strokes=(stroke,))
        full = mask.render((900, 1400))
        x, y, rw, rh = RECT
        tile = mask.render((rh, rw), origin=(x, y), frame=(1400, 900))
        region = full[y:y + rh, x:x + rw]
        assert region.max() > 0.5, "firca izi karo bolgesine hic dusmuyor"
        inner = (slice(EDGE, rh - EDGE), slice(EDGE, rw - EDGE))
        assert float(np.abs(tile[inner] - region[inner]).max()) < 0.002

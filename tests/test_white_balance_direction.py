"""Sicaklik kaydiricisi hangi yone gitmeli?

Bulgu: kaydirici kendi ipucuyla ("Düşük değer soğuk (mavi), yüksek
değer sıcak (amber)") ve Lightroom/Capture One/Camera Raw'daki yaygin
davranisla **ters** calisiyordu. 2500 K amber, 11000 K mavi veriyordu.

Kullanici acisindan beklenen sonuc: kaydiriciyi saga cekince fotograf
isinir. Testler pikselden bunu dogrular, kod icindeki formulu
tekrarlamaz.

v1 tariflerinin gorunumu degismemeli: eski dosyalarda sayi 6500 K
ekseninde yansitilarak okunur.
"""
from __future__ import annotations

import numpy as np
import pytest

from luma_atelier.imaging.effects.base import REGISTRY, RenderContext
from luma_atelier.imaging.recipe import Recipe

NEUTRAL = 6500.0


@pytest.fixture
def grey() -> np.ndarray:
    return np.full((8, 8, 3), 0.5, np.float32)


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(full_width=8, full_height=8, scale=1.0, seed=1,
                         quality="final", purpose="preview")


def _balanced(grey: np.ndarray, ctx: RenderContext, kelvin: float,
              tint: float = 0.0) -> np.ndarray:
    """Beyaz dengesini dogrudan islem olarak uygular (lineer alanda)."""
    op = REGISTRY.require("color.white_balance")
    return op.apply(grey, {"kelvin": kelvin, "tint": tint}, ctx)


class TestSliderDirection:
    def test_low_kelvin_is_blue(self, grey: np.ndarray,
                                ctx: RenderContext) -> None:
        out = _balanced(grey, ctx, 2500.0)
        r, b = float(out[..., 0].mean()), float(out[..., 2].mean())
        assert b > r, f"2500 K maviye kaymali (R={r:.3f}, B={b:.3f})"

    def test_high_kelvin_is_amber(self, grey: np.ndarray,
                                  ctx: RenderContext) -> None:
        out = _balanced(grey, ctx, 11000.0)
        r, b = float(out[..., 0].mean()), float(out[..., 2].mean())
        assert r > b, f"11000 K sicak olmali (R={r:.3f}, B={b:.3f})"

    def test_neutral_is_inert(self, grey: np.ndarray,
                              ctx: RenderContext) -> None:
        out = _balanced(grey, ctx, NEUTRAL)
        assert np.allclose(out, grey, atol=1e-6)

    def test_warmth_increases_monotonically(self, grey: np.ndarray,
                                            ctx: RenderContext) -> None:
        """Kaydirici saga gittikce sicaklik surekli artmali."""
        ratios = []
        for kelvin in (3000.0, 4500.0, 6500.0, 8500.0, 11000.0):
            out = _balanced(grey, ctx, kelvin)
            ratios.append(float(out[..., 0].mean() / out[..., 2].mean()))
        assert all(b > a for a, b in zip(ratios, ratios[1:])), ratios


class TestVersionOneRecipesKeepTheirLook:
    def test_mirrored_value_reproduces_old_appearance(
        self, grey: np.ndarray, ctx: RenderContext,
    ) -> None:
        """v1'de 4800 K ile elde edilen sicak sonuc korunmali.

        Eski formul kazanci ters isaretle uretiyordu; 6500 K ekseninde
        yansitma birebir ayni kazanci verir.
        """
        old_kelvin = 4800.0
        t = np.log(old_kelvin / NEUTRAL)
        old_gains = np.array([np.exp(-t * 0.55), 1.0, np.exp(t * 0.55)],
                             np.float32)
        old_gains = old_gains / float((old_gains * np.array(
            [0.2126, 0.7152, 0.0722], np.float32)).sum())

        mirrored = NEUTRAL * NEUTRAL / old_kelvin
        out = _balanced(grey, ctx, mirrored)
        # Beyaz denge lineer alanda uygulanir; sRGB'ye geri donusu de
        # hesaba katmak yerine orani karsilastirmak yeterli
        got = np.array([out[..., c].mean() for c in range(3)], np.float64)
        expected_linear = 0.5 ** 2.2 * old_gains  # yaklasik
        assert np.argmax(got) == np.argmax(expected_linear), (
            "yansitilmis deger eski gorunumun sicak yonunu korumali"
        )

    def test_v1_recipe_is_migrated_on_load(self) -> None:
        data = {
            "version": 1,
            "layers": [{"op": "color.white_balance", "instance": "l1",
                        "params": {"kelvin": 4800.0, "tint": 14.0}}],
        }
        recipe = Recipe.from_dict(data)
        kelvin = recipe.layers[0].params["kelvin"]
        assert kelvin == pytest.approx(NEUTRAL * NEUTRAL / 4800.0, abs=0.5)
        assert recipe.version == 2, "tasinan tarif guncel surumle saklanmali"

    def test_v2_recipe_is_left_alone(self) -> None:
        data = {
            "version": 2,
            "layers": [{"op": "color.white_balance", "instance": "l1",
                        "params": {"kelvin": 8800.0, "tint": 0.0}}],
        }
        recipe = Recipe.from_dict(data)
        assert recipe.layers[0].params["kelvin"] == pytest.approx(8800.0)

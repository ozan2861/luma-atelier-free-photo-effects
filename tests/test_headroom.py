"""1.0 ustu ara degerler (baslik payi) korunmali.

Calisma modeli 0..1 nominal ama **ustunu kirpmayan** float32. Bloom,
halation ve anamorfik cizgi bu payi okur: parlak kaynaklarin gercek
siddeti orada saklidir.

Bulgu: `tone.contrast` pozitif yonde tanh omuzunu tum degere
uyguluyordu. 1.5 ve 4.0 girdileri ayni cikiyor (~1.0), yani pay yok
oluyordu; kontrast eklenince parlak kaynaklarin halesi zayifliyordu.

Bu testler kullanici acisindan gozlemlenebilir sonucu olcer: kontrast
sonrasi parlak kaynaklar hala birbirinden ayirt edilebilir ve bloom
onlari halelendirebilir.
"""
from __future__ import annotations

import numpy as np
import pytest

from luma_atelier.imaging.effects.base import REGISTRY, RenderContext


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(full_width=5, full_height=1, scale=1.0, seed=1,
                         quality="final", purpose="preview")


#: 0..1 govde ve uzerinde pay
SAMPLE = np.array([[[0.2] * 3, [0.8] * 3, [1.0] * 3, [1.5] * 3, [4.0] * 3]],
                  np.float32)


class TestContrastKeepsHeadroom:
    @pytest.mark.parametrize("amount", [30.0, 60.0, 100.0])
    def test_bright_values_stay_distinct(self, ctx: RenderContext,
                                         amount: float) -> None:
        op = REGISTRY.require("tone.contrast")
        out = op.apply(SAMPLE, {"amount": amount, "pivot": 0.45}, ctx)
        values = [float(v) for v in out[0, :, 0]]
        assert values[4] > values[3] > values[2], (
            f"pay yok oldu: {values}"
        )
        assert values[4] > 1.2, "4.0'lik kaynak 1.0'a sikismamali"

    def test_in_range_look_is_unchanged(self, ctx: RenderContext) -> None:
        """Presetlerin gorunumu degismemeli: 0..1 govdesi aynen kalir."""
        op = REGISTRY.require("tone.contrast")
        out = op.apply(SAMPLE, {"amount": 50.0, "pivot": 0.45}, ctx)
        # Duzeltmeden onceki olculmus degerler
        assert float(out[0, 0, 0]) == pytest.approx(0.1364, abs=1e-4)
        assert float(out[0, 1, 0]) == pytest.approx(0.8458, abs=1e-4)

    def test_negative_contrast_also_keeps_order(self,
                                                ctx: RenderContext) -> None:
        op = REGISTRY.require("tone.contrast")
        out = op.apply(SAMPLE, {"amount": -60.0, "pivot": 0.45}, ctx)
        values = [float(v) for v in out[0, :, 0]]
        assert values[4] > values[3] > values[2]


class TestBloomStillSeesHeadroom:
    def test_contrast_then_bloom_keeps_glow(self) -> None:
        """Kontrast eklemek parlak kaynagin halesini yok etmemeli."""
        h, w = 80, 80
        img = np.full((h, w, 3), 0.15, np.float32)
        img[34:46, 34:46] = 3.0          # cok parlak kucuk kaynak

        ctx = RenderContext(full_width=w, full_height=h, scale=1.0, seed=1,
                            quality="final", purpose="preview")
        contrast = REGISTRY.require("tone.contrast")
        bloom = REGISTRY.require("light.bloom")

        raw_glow = bloom.apply(img, {"radius": 40.0, "intensity": 120.0,
                                     "threshold": 0.7}, ctx)
        boosted = contrast.apply(img, {"amount": 80.0, "pivot": 0.45}, ctx)
        glow_after = bloom.apply(boosted, {"radius": 40.0, "intensity": 120.0,
                                           "threshold": 0.7}, ctx)

        # Kaynagin disindaki hale enerjisi
        ring = (slice(10, 25), slice(10, 70))
        before = float((raw_glow[ring] - img[ring]).mean())
        after = float((glow_after[ring] - boosted[ring]).mean())
        assert before > 1e-4, "olcum anlamsiz: hale hic olusmamis"
        assert after > before * 0.5, (
            f"kontrast sonrasi hale cok zayifladi ({before:.4f} -> {after:.4f})"
        )

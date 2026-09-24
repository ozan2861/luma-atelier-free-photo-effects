"""Calismayan bir efekt sessiz kalmamali.

`Recipe.apply` tek bir katmanin hatasinda render'i cokertmez - bu
dogru davranis. Ama bulgu su: hata yalnizca gunluge yaziliyordu.
Denetim sirasinda bir yama vignette'i her render'da `TypeError` ile
dusurdu ve uygulama hicbir sey soylemeden calismaya devam etti; efekt
kullanici icin **sessizce yok** oldu.

Bu testler kullanici acisindan beklenen sonucu dogrular: atlanan
katman render sonucunda bildirilir, arayuz de onu gosterebilir.
"""
from __future__ import annotations

import numpy as np
import pytest

from luma_atelier.imaging.effects.base import REGISTRY, RenderContext
from luma_atelier.imaging.recipe import Layer, Recipe


@pytest.fixture
def image() -> np.ndarray:
    return np.full((40, 60, 3), 0.5, np.float32)


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(full_width=60, full_height=40, scale=1.0, seed=1,
                         quality="final", purpose="preview")


class TestSkippedLayersAreReported:
    def test_unknown_operation_is_reported(self, image: np.ndarray,
                                           ctx: RenderContext) -> None:
        recipe = Recipe(layers=(Layer(op_id="yok.boyle.bir.islem",
                                      instance_id="l1"),))
        failures: list[str] = []
        out = recipe.apply(image, ctx, failures=failures)

        assert failures == ["yok.boyle.bir.islem"]
        assert np.allclose(out, image), "bilinmeyen katman goruntuyu bozmamali"

    def test_raising_operation_is_reported(self, image: np.ndarray,
                                           ctx: RenderContext) -> None:
        op = REGISTRY.require("lens.vignette")

        def boom(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            raise TypeError("bilerek bozuldu")

        # Operation degismez bir dataclass; alan gecici olarak
        # degistirilir ve her durumda geri alinir.
        original = op.fn
        object.__setattr__(op, "fn", boom)
        try:
            recipe = Recipe(layers=(Layer(op_id="lens.vignette",
                                          instance_id="l1",
                                          params={"amount": -80.0}),))
            failures: list[str] = []
            out = recipe.apply(image, ctx, failures=failures)
        finally:
            object.__setattr__(op, "fn", original)

        assert failures, "dusen katman bildirilmeli"
        assert op.name in failures[0]
        assert np.allclose(out, image)

    def test_working_recipe_reports_nothing(self, image: np.ndarray,
                                            ctx: RenderContext) -> None:
        """Yanlis alarm olmamali."""
        recipe = Recipe(layers=(Layer(op_id="tone.exposure", instance_id="l1",
                                      params={"stops": 1.0}),))
        failures: list[str] = []
        out = recipe.apply(image, ctx, failures=failures)

        assert failures == []
        assert not np.allclose(out, image), "pozlama gercekten uygulanmali"

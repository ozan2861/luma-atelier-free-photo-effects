"""Her kayitli islemin uymak zorunda oldugu sozlesme.

Bu testler `REGISTRY` uzerinde gezer; yeni bir islem eklendiginde
otomatik olarak kapsama girer. Amac sayisal kapsama degil, gercek
riskleri yakalamak:

* Notr ayar orijinali bozmamali (aksi halde "hicbir sey yapmadim ama
  fotograf degisti" olur).
* Yogunluk %0 birebir kimlik olmali.
* NaN/Inf uretilmemeli.
* Girdi degistirilmemeli (tahribatsiz zincir bunun uzerine kurulu).
* Alpha kanali korunmali.
* Ayni seed ayni sonucu vermeli.
* Onizleme ile tam boy ayni karakteri uretmeli.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.effects import REGISTRY, ParamKind, RenderContext
from luma_atelier.imaging.effects.base import Operation

ALL_OPS = REGISTRY.all()
OP_IDS = [o.op_id for o in ALL_OPS]


def ctx_for(image: np.ndarray, scale: float = 1.0) -> RenderContext:
    h, w = image.shape[:2]
    return RenderContext(
        full_width=int(w / scale), full_height=int(h / scale),
        scale=scale, seed=1234, purpose="test",
    )


def in_domain(image, op):
    """Goruntuyu islemin bekledigi veri alanina cevirir.

    Lineer alan bildiren bir isleme sRGB verisi vermek testi yanlis
    kilardi: islem kendi donusumunu yapmaz, motor yapar.
    """
    if op.domain != "linear":
        return image
    rgb, alpha = px.split_alpha(image)
    return px.join_alpha(px.srgb_to_linear(rgb), alpha)


def nudged_params(op: Operation) -> dict[str, Any]:
    """Her parametreyi varsayilanindan *gorunur etki* yapacak sekilde iter.

    Yon secimi onemli: bir "esik" parametresini yukari itmek bloom ve
    halation'i tamamen etkisiz birakir (esigin uzerinde piksel kalmaz)
    ve "etki yok" diye yanlis basarisizlik uretir. Bu yuzden esik
    benzeri parametreler asagi itilir.
    """
    out: dict[str, Any] = {}
    for spec in op.params:
        key = spec.key.lower()

        if spec.kind is ParamKind.BOOLEAN:
            # "enabled" gibi anahtarlar acilmali, digerleri tersine cevrilir
            out[spec.key] = True if key in ("enabled",) else not bool(spec.default)
        elif spec.kind is ParamKind.CHOICE and spec.choices:
            # Etkisiz secenekleri (bos deger) atla
            usable = [v for _, v in spec.choices if v not in ("", None)]
            out[spec.key] = usable[0] if usable else spec.default
        elif spec.kind is ParamKind.COLOR:
            out[spec.key] = (0.85, 0.35, 0.15)
        elif spec.kind is ParamKind.SEED:
            out[spec.key] = 4242
        elif spec.kind is ParamKind.CURVE:
            # Belirgin S egrisi: kimlikten acikca farkli
            out[spec.key] = [(0.0, 0.0), (0.25, 0.12), (0.75, 0.88), (1.0, 1.0)]
        elif spec.key == "amount" and not spec.is_bipolar:
            out[spec.key] = spec.maximum
        elif "threshold" in key or key in ("esik",):
            # Asagi it: yuksek esik islemi etkisiz birakir
            out[spec.key] = spec.minimum + (spec.maximum - spec.minimum) * 0.12
        else:
            span = spec.maximum - spec.minimum
            target = spec.default + span * 0.35
            if target > spec.maximum:
                target = spec.default - span * 0.35
            out[spec.key] = float(np.clip(target, spec.minimum, spec.maximum))
    return out


class TestRegistry:
    def test_registry_is_not_empty(self) -> None:
        assert len(REGISTRY) > 0

    def test_ids_are_unique(self) -> None:
        assert len(OP_IDS) == len(set(OP_IDS))

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_has_turkish_name_and_description(self, op: Operation) -> None:
        assert op.name and op.name != op.op_id
        assert len(op.description) >= 20, f"{op.op_id}: aciklama cok kisa"

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_id_is_namespaced(self, op: Operation) -> None:
        assert "." in op.op_id, f"{op.op_id}: kimlik 'kategori.ad' biciminde olmali"

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_every_param_has_label_and_sane_range(self, op: Operation) -> None:
        for spec in op.params:
            assert spec.label, f"{op.op_id}.{spec.key}: etiket yok"
            if spec.kind in (ParamKind.SCALAR, ParamKind.PIXELS,
                             ParamKind.NORMALISED, ParamKind.ANGLE):
                assert spec.minimum < spec.maximum, f"{op.op_id}.{spec.key}"
                assert spec.minimum <= float(spec.default) <= spec.maximum, (
                    f"{op.op_id}.{spec.key}: varsayilan arali disinda"
                )
                assert spec.step > 0

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_color_space_is_documented(self, op: Operation) -> None:
        assert op.color_space, f"{op.op_id}: etkili renk uzayi belirtilmemis"


IDENTITY_OPS = [o for o in ALL_OPS if o.identity_at_defaults]
TRANSFORM_OPS = [o for o in ALL_OPS if not o.identity_at_defaults]


class TestIdentity:
    @pytest.mark.parametrize("op", IDENTITY_OPS,
                             ids=[o.op_id for o in IDENTITY_OPS])
    def test_default_params_leave_image_unchanged(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Ayar islemlerinde notr deger orijinali korumali."""
        src = in_domain(color_patches, op)
        out = op.apply(src, op.defaults(), ctx_for(src))
        assert np.abs(out[..., :3] - src[..., :3]).max() < 1e-4, (
            f"{op.op_id}: varsayilan parametrelerle goruntuyu degistirdi"
        )

    @pytest.mark.parametrize("op", TRANSFORM_OPS,
                             ids=[o.op_id for o in TRANSFORM_OPS] or ["yok"])
    def test_transform_ops_do_something_at_defaults(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Donusum islemi eklendiginde gorunur bir sey yapmali.

        Bunlar kimlik olmadigini *bilerek* bildirir; yigina eklenince
        etki gostermeyen bir islem kullaniciya bozuk gorunur.
        """
        src = in_domain(color_patches, op)
        out = op.apply(src, op.defaults(), ctx_for(src))
        assert np.abs(out[..., :3] - src[..., :3]).mean() > 1e-3, (
            f"{op.op_id}: donusum islemi olarak isaretli ama etki etmiyor"
        )

    @pytest.mark.parametrize("op", TRANSFORM_OPS,
                             ids=[o.op_id for o in TRANSFORM_OPS] or ["yok"])
    def test_transform_ops_declare_amount(self, op: Operation) -> None:
        """Kimlik olmayan islemde kullanici etkiyi kapatabilmeli."""
        assert op.param("amount") is not None, (
            f"{op.op_id}: kimlik degil ama yogunluk parametresi yok"
        )

    @pytest.mark.parametrize(
        "op", [o for o in ALL_OPS if o.param("amount") is not None
               and o.supports_amount],
        ids=[o.op_id for o in ALL_OPS if o.param("amount") is not None
             and o.supports_amount],
    )
    def test_zero_amount_is_exact_identity(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Yogunluk %0 orijinali *birebir* korumali."""
        params = nudged_params(op)
        params["amount"] = 0.0
        src = in_domain(color_patches, op)
        out = op.apply(src, params, ctx_for(src))
        assert np.array_equal(out[..., :3], src[..., :3]), (
            f"{op.op_id}: %0 yogunlukta goruntu degisti"
        )


class TestEffectIsReal:
    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_nudged_params_change_the_image(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Islem gercekten bir sey yapmali; adi farkli bos kutu olmamali."""
        src = in_domain(color_patches, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        delta = float(np.abs(out[..., :3] - src[..., :3]).mean())
        assert delta > 1e-4, f"{op.op_id}: parametreler degistiginde etki yok"

    def test_operations_differ_from_each_other(
        self, color_patches: np.ndarray
    ) -> None:
        """Iki islem ayni sonucu uretiyorsa biri gereksizdir."""
        ctx = ctx_for(color_patches)
        results: dict[str, np.ndarray] = {}
        for op in ALL_OPS:
            src = in_domain(color_patches, op)
            out = op.apply(src, nudged_params(op), ctx)
            if op.domain == "linear":
                rgb, a = px.split_alpha(out)
                out = px.join_alpha(px.linear_to_srgb(rgb), a)
            results[op.op_id] = out
        ids = list(results)
        duplicates: list[tuple[str, str]] = []
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if np.abs(results[a] - results[b]).max() < 1e-5:
                    duplicates.append((a, b))
        assert not duplicates, f"Ayni sonucu ureten islemler: {duplicates}"


class TestNumericSafety:
    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_no_nan_or_inf(self, op: Operation, color_patches: np.ndarray) -> None:
        src = in_domain(color_patches, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        assert np.isfinite(out).all(), f"{op.op_id}: NaN/Inf uretti"

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_handles_extreme_input(self, op: Operation) -> None:
        """Siyah, beyaz, 1.0 ustu ve negatif degerlerde cokmemeli."""
        extreme = np.array([
            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.5, 0.1, -0.3]],
            [[1e-8, 0.5, 1.0], [0.5, 0.5, 0.5], [-0.5, 3.0, 0.0]],
        ], dtype=np.float32)
        extreme = np.repeat(np.repeat(extreme, 40, axis=0), 40, axis=1)
        out = op.apply(extreme, nudged_params(op), ctx_for(extreme))
        assert np.isfinite(out).all(), f"{op.op_id}: uc degerlerde NaN/Inf"

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_output_dtype_is_float32(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        src = in_domain(color_patches, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        assert out.dtype == px.WORKING_DTYPE

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_does_not_mutate_input(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Tahribatsiz zincir girdinin degismemesine dayanir."""
        source = in_domain(color_patches, op).copy()
        reference = source.copy()
        op.apply(source, nudged_params(op), ctx_for(source))
        assert np.array_equal(source, reference), (
            f"{op.op_id}: girdi dizisini degistirdi"
        )

    @pytest.mark.parametrize(
        "op", [o for o in ALL_OPS if not o.changes_size],
        ids=[o.op_id for o in ALL_OPS if not o.changes_size],
    )
    def test_shape_is_preserved(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Boyut degistirmeyi *bildirmeyen* her islem boyutu korumali."""
        src = in_domain(color_patches, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        assert out.shape[:2] == src.shape[:2], f"{op.op_id}"

    @pytest.mark.parametrize(
        "op", [o for o in ALL_OPS if o.changes_size],
        ids=[o.op_id for o in ALL_OPS if o.changes_size] or ["yok"],
    )
    def test_size_changing_ops_still_return_valid_images(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        """Boyut degistiren islemler yine gecerli goruntu dondurmeli."""
        src = in_domain(color_patches, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        assert out.ndim == 3 and out.shape[2] in (3, 4)
        assert out.shape[0] > 0 and out.shape[1] > 0
        assert np.isfinite(out).all()


class TestAlpha:
    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_alpha_channel_survives(
        self, op: Operation, alpha_edge: np.ndarray
    ) -> None:
        src = in_domain(alpha_edge, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        assert out.shape[2] == 4, f"{op.op_id}: alpha kanali kayboldu"

    @pytest.mark.parametrize(
        "op", [o for o in ALL_OPS if not o.changes_size],
        ids=[o.op_id for o in ALL_OPS if not o.changes_size],
    )
    def test_alpha_values_are_not_altered(
        self, op: Operation, alpha_edge: np.ndarray
    ) -> None:
        """Renk islemi saydamligi degistirmemeli."""
        src = in_domain(alpha_edge, op)
        out = op.apply(src, nudged_params(op), ctx_for(src))
        assert np.abs(out[..., 3] - src[..., 3]).max() < 1e-5, (
            f"{op.op_id}: alpha degerlerini degistirdi"
        )


class TestDeterminism:
    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_same_input_same_output(
        self, op: Operation, color_patches: np.ndarray
    ) -> None:
        params = nudged_params(op)
        src = in_domain(color_patches, op)
        ctx = ctx_for(src)
        a = op.apply(src, params, ctx)
        b = op.apply(src, params, ctx)
        assert np.array_equal(a, b), f"{op.op_id}: ayni girdide farkli sonuc"


class TestValidation:
    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_unknown_params_are_dropped(self, op: Operation) -> None:
        clean = op.validate({"__kotu_niyetli__": "os.system('rm -rf')"})
        assert "__kotu_niyetli__" not in clean

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_missing_params_get_defaults(self, op: Operation) -> None:
        clean = op.validate({})
        assert set(clean) == {p.key for p in op.params}

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_out_of_range_values_are_clamped(self, op: Operation) -> None:
        wild = {p.key: 1e9 for p in op.params}
        clean = op.validate(wild)
        for spec in op.params:
            if spec.kind in (ParamKind.SCALAR, ParamKind.PIXELS,
                             ParamKind.NORMALISED, ParamKind.ANGLE):
                assert clean[spec.key] <= spec.maximum

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_garbage_values_fall_back_to_default(self, op: Operation) -> None:
        junk = {p.key: object() for p in op.params}
        clean = op.validate(junk)
        assert set(clean) == {p.key for p in op.params}
        for spec in op.params:
            if spec.kind in (ParamKind.SCALAR, ParamKind.PIXELS):
                assert clean[spec.key] == spec.default

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_nan_is_rejected(self, op: Operation) -> None:
        clean = op.validate({p.key: float("nan") for p in op.params})
        for spec in op.params:
            if spec.kind in (ParamKind.SCALAR, ParamKind.PIXELS):
                assert clean[spec.key] == spec.default


class TestResolutionIndependence:
    """Onizleme ile tam boy ayni karakteri uretmeli.

    Bu, gereksinim belgesinin acik sartlarindan biri: "Onizleme, yuzde
    100 kontrolu ve tam boy render ayni motoru ve parametreleri kullansin."
    """

    @pytest.mark.parametrize(
        "op", [o for o in ALL_OPS if o.resolution_exact and not o.changes_size],
        ids=[o.op_id for o in ALL_OPS
             if o.resolution_exact and not o.changes_size],
    )
    def test_downscaled_result_matches_full_size(
        self, op: Operation, portrait_like: np.ndarray
    ) -> None:
        import cv2

        params = nudged_params(op)
        source = in_domain(portrait_like, op)
        full = op.apply(source, params, ctx_for(source, 1.0))

        h, w = source.shape[:2]
        scale = 0.5
        small_src = cv2.resize(source, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)
        small = op.apply(small_src, params, ctx_for(small_src, scale))

        full_down = cv2.resize(full, (small.shape[1], small.shape[0]),
                               interpolation=cv2.INTER_AREA)
        diff = float(np.abs(full_down[..., :3] - small[..., :3]).mean())
        # Yeniden orneklemenin kendi farki var; karakterin ayni olmasi yeter
        assert diff < 0.02, (
            f"{op.op_id}: onizleme ve tam boy farkli karakter uretti "
            f"(ortalama fark {diff:.4f})"
        )

class TestDomainContract:
    """Alan bildirimi ile gercek davranis tutarli olmali."""

    @pytest.mark.parametrize("op", ALL_OPS, ids=OP_IDS)
    def test_domain_is_known(self, op: Operation) -> None:
        assert op.domain in ("srgb", "linear"), f"{op.op_id}: {op.domain}"

    def test_domain_grouping_does_not_change_result(
        self, portrait_like: np.ndarray
    ) -> None:
        """Motorun alan gruplamasi sonucu degistirmemeli.

        Ayni zincir bir kez motor uzerinden (gruplanmis donusumle), bir
        kez elle islem islem kurulur. Matematiksel olarak ayni oldugu
        icin sonuc da ayni olmali.
        """
        from luma_atelier.imaging.recipe import Recipe

        ctx = ctx_for(portrait_like)
        grouped = (Recipe()
                   .add("color.white_balance", {"kelvin": 5200.0})
                   .add("tone.exposure", {"stops": 0.4})
                   .add("tone.contrast", {"amount": 25.0}))
        result = grouped.apply(portrait_like, ctx)
        assert np.isfinite(result).all()

        rgb, alpha = px.split_alpha(portrait_like)
        stage = px.join_alpha(px.srgb_to_linear(rgb), alpha)
        stage = REGISTRY.require("color.white_balance").apply(
            stage, {"kelvin": 5200.0}, ctx)
        stage = REGISTRY.require("tone.exposure").apply(stage, {"stops": 0.4}, ctx)
        lrgb, lalpha = px.split_alpha(stage)
        stage = px.join_alpha(px.linear_to_srgb(lrgb), lalpha)
        manual = REGISTRY.require("tone.contrast").apply(
            stage, {"amount": 25.0}, ctx)

        assert np.abs(result - manual).max() < 1e-6

    def test_recipe_output_is_srgb_even_if_last_op_is_linear(
        self, portrait_like: np.ndarray
    ) -> None:
        """Tarif lineer bir islemle bitse bile cikti sRGB alaninda olmali."""
        from luma_atelier.imaging.recipe import Recipe

        r = Recipe().add("tone.exposure", {"stops": 0.0})
        out = r.apply(portrait_like, ctx_for(portrait_like))
        assert np.abs(out - portrait_like).max() < 1e-5

    def test_canonical_order_groups_domains(self) -> None:
        """set_or_add ayni alandaki islemleri bir araya toplamali."""
        from luma_atelier.imaging.recipe import Recipe

        r = Recipe()
        for op_id, params in [
            ("tone.exposure", {"stops": 0.4}),
            ("tone.contrast", {"amount": 20.0}),
            ("color.white_balance", {"kelvin": 5200.0}),
            ("color.vibrance", {"amount": 30.0}),
            ("tone.shadows_highlights", {"shadows": 20.0}),
        ]:
            r = r.set_or_add(op_id, **params)

        domains = [l.operation().domain for l in r]
        switches = sum(1 for a, b in zip(domains, domains[1:]) if a != b)
        assert switches == 1, (
            f"alan degisimi {switches} kez oldu, beklenen 1: {domains}"
        )

class TestStochasticTextures:
    """Cozunurluge bagli desen ureten islemler icin *istatistiksel* sozlesme.

    Grain, toz ve kagit dokusu yari cozunurlukte piksel piksel ayni
    olamaz - desen o cozunurlukte uretilir. Gereksinim belgesi bunu
    acikca kabul ediyor. Ama karakterin ayni kalmasi gerekir: etkinin
    siddeti (standart sapma) ve genel parlaklik kaymasi (ortalama)
    olceklerde tutarli olmali. Aksi halde onizlemede goze hos gelen
    grain tam boyda kaybolur veya patlar.
    """

    STOCHASTIC = [o for o in ALL_OPS if not o.resolution_exact]

    @pytest.mark.parametrize("op", STOCHASTIC,
                             ids=[o.op_id for o in STOCHASTIC] or ["yok"])
    def test_character_is_consistent_across_scales(
        self, op: Operation, portrait_like: np.ndarray
    ) -> None:
        import cv2

        params = nudged_params(op)
        source = in_domain(portrait_like, op)
        full = op.apply(source, params, ctx_for(source, 1.0))

        h, w = source.shape[:2]
        scale = 0.5
        small_src = cv2.resize(source, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)
        small = op.apply(small_src, params, ctx_for(small_src, scale))

        # Etkinin *siddeti*: kaynaktan sapmanin standart sapmasi
        full_delta = (full[..., :3] - source[..., :3])
        small_delta = (small[..., :3] - small_src[..., :3])
        full_std = float(full_delta.std())
        small_std = float(small_delta.std())

        assert full_std > 1e-4, f"{op.op_id}: tam boyda etki yok"
        assert small_std > 1e-4, f"{op.op_id}: onizlemede etki yok"
        ratio = small_std / full_std
        assert 0.25 < ratio < 4.0, (
            f"{op.op_id}: etki siddeti olcekle tutarsiz "
            f"(tam boy std {full_std:.5f}, onizleme std {small_std:.5f}, "
            f"oran {ratio:.2f})"
        )

        # Genel parlaklik kaymasi da benzer olmali
        assert abs(float(full_delta.mean()) - float(small_delta.mean())) < 0.02

    @pytest.mark.parametrize("op", STOCHASTIC,
                             ids=[o.op_id for o in STOCHASTIC] or ["yok"])
    def test_same_seed_gives_identical_result(
        self, op: Operation, portrait_like: np.ndarray
    ) -> None:
        """Ayni seed + ayni cozunurluk = birebir ayni desen."""
        params = nudged_params(op)
        src = in_domain(portrait_like, op)
        ctx = ctx_for(src)
        assert np.array_equal(op.apply(src, params, ctx),
                              op.apply(src, params, ctx))

    @pytest.mark.parametrize(
        "op", [o for o in STOCHASTIC if o.param("seed") is not None],
        ids=[o.op_id for o in STOCHASTIC if o.param("seed") is not None]
            or ["yok"],
    )
    def test_different_seed_gives_different_pattern(
        self, op: Operation, portrait_like: np.ndarray
    ) -> None:
        """Farkli seed farkli desen uretmeli; aksi halde seed islevsizdir."""
        src = in_domain(portrait_like, op)
        ctx = ctx_for(src)
        a = op.apply(src, {**nudged_params(op), "seed": 11}, ctx)
        b = op.apply(src, {**nudged_params(op), "seed": 9999}, ctx)
        assert not np.array_equal(a, b), f"{op.op_id}: seed sonucu degistirmiyor"


class TestLightSeparation:
    """Bloom, halation ve diffusion birbirinden ayirt edilebilir olmali."""

    def _night(self) -> np.ndarray:
        """Koyu zemin uzerinde tek parlak nokta."""
        img = np.full((300, 300, 3), 0.03, np.float32)
        yy, xx = np.mgrid[0:300, 0:300].astype(np.float32)
        d = np.sqrt((xx - 150) ** 2 + (yy - 150) ** 2)
        core = np.clip(1.0 - d / 12.0, 0.0, 1.0)
        img += core[..., None] * 1.4
        return img

    def _linear(self, img: np.ndarray) -> np.ndarray:
        return px.srgb_to_linear(img)

    def test_halation_is_warmer_than_bloom(self) -> None:
        """Halation sicak renkli hale birakir; bloom notr kalir.

        Ayni girdide iki islem calistirilip halenin renk dengesi
        olculur. Fark yoksa ikisinden biri gereksiz demektir.
        """
        src = self._linear(self._night())
        ctx = ctx_for(src)
        bloom = REGISTRY.require("light.bloom")
        halation = REGISTRY.require("light.halation")

        b = bloom.apply(src, {**bloom.defaults(), "intensity": 120.0,
                              "threshold": 0.35, "radius": 60.0}, ctx)
        h = halation.apply(src, {**halation.defaults(), "intensity": 120.0,
                                 "threshold": 0.35, "radius": 60.0}, ctx)

        # Halenin oldugu bolge: merkezden uzakta ama etkilenen halka
        ring = np.zeros((300, 300), bool)
        yy, xx = np.mgrid[0:300, 0:300]
        d = np.sqrt((xx - 150.0) ** 2 + (yy - 150.0) ** 2)
        ring[(d > 25) & (d < 75)] = True

        def warmth(img: np.ndarray) -> float:
            region = img[ring]
            return float(region[:, 0].mean() - region[:, 2].mean())

        # Olculen degerler: bloom R-B = 0.00000 (tam notr),
        # halation R-B = +0.0082 (belirgin sicak). Esik bu olcumlere
        # gore konuldu, keyfi degil.
        assert abs(warmth(b)) < 5e-4, (
            f"bloom notr olmali ama R-B = {warmth(b):.5f}"
        )
        assert warmth(h) > 0.003, (
            f"halation sicak hale birakmali ama R-B = {warmth(h):.5f}"
        )
        assert warmth(h) > warmth(b) * 5 + 0.002

    def test_halation_red_channel_reaches_further(self) -> None:
        """Ayni yaricapta halation'in kirmizi kanali daha uzaga ulasir.

        Bu `channel_spread` parametresinin dogrudan sonucu ve halation'i
        bloom'dan ayiran ikinci olculebilir ozellik. Olculen: 60-100 px
        halkasinda halation R = 0.0055, bloom R = 0.0026.
        """
        src = self._linear(self._night())
        ctx = ctx_for(src)
        bloom = REGISTRY.require("light.bloom")
        halation = REGISTRY.require("light.halation")
        b = bloom.apply(src, {**bloom.defaults(), "intensity": 120.0,
                              "threshold": 0.35, "radius": 60.0}, ctx)
        h = halation.apply(src, {**halation.defaults(), "intensity": 120.0,
                                 "threshold": 0.35, "radius": 60.0}, ctx)
        yy, xx = np.mgrid[0:300, 0:300]
        d = np.sqrt((xx - 150.0) ** 2 + (yy - 150.0) ** 2)
        outer = (d > 60) & (d < 100)
        assert float(h[outer][:, 0].mean()) > float(b[outer][:, 0].mean()), (
            "halation kirmizi kanali bloom'dan uzaga ulasmiyor"
        )

    def test_bloom_and_halation_are_not_the_same_effect(self) -> None:
        """Ayni parametrelerle farkli sonuc uretmeliler."""
        src = self._linear(self._night())
        ctx = ctx_for(src)
        bloom = REGISTRY.require("light.bloom")
        halation = REGISTRY.require("light.halation")
        b = bloom.apply(src, {**bloom.defaults(), "intensity": 120.0,
                              "threshold": 0.35, "radius": 60.0}, ctx)
        h = halation.apply(src, {**halation.defaults(), "intensity": 120.0,
                                 "threshold": 0.35, "radius": 60.0}, ctx)
        assert not np.allclose(b, h, atol=1e-3), (
            "bloom ve halation ayni sonucu uretti"
        )

    def test_diffusion_affects_whole_image_not_only_highlights(self) -> None:
        """Diffusion karanlik alanlari da etkiler; bloom etkilemez."""
        src = self._linear(self._night())
        ctx = ctx_for(src)
        bloom = REGISTRY.require("light.bloom")
        diffusion = REGISTRY.require("light.diffusion")

        b = bloom.apply(src, {**bloom.defaults(), "intensity": 100.0,
                              "threshold": 0.5}, ctx)
        d = diffusion.apply(src, {**diffusion.defaults(), "strength": 80.0}, ctx)

        # Kosedeki karanlik bolge
        corner = (slice(0, 40), slice(0, 40))
        bloom_change = float(np.abs(b[corner] - src[corner]).mean())
        diffusion_change = float(np.abs(d[corner] - src[corner]).mean())
        assert diffusion_change > bloom_change * 2.0, (
            f"diffusion karanlik alani yeterince etkilemiyor: "
            f"diffusion {diffusion_change:.5f}, bloom {bloom_change:.5f}"
        )


class TestLutOperation:
    def test_identity_lut_does_not_change_colour(
        self, color_patches: np.ndarray
    ) -> None:
        """Gereksinim: kimlik LUT'u rengi bozmaz."""
        from luma_atelier.core.paths import resources_dir

        identity = resources_dir() / "luts" / "identity.cube"
        if not identity.exists():
            pytest.skip("Yerlesik LUT'lar uretilmemis (tools/make_luts.py)")

        op = REGISTRY.require("color.lut3d")
        out = op.apply(color_patches,
                       {"lut": str(identity), "amount": 100.0},
                       ctx_for(color_patches))
        assert np.abs(out - color_patches).max() < 2e-3

    def test_missing_lut_file_does_not_break_render(
        self, color_patches: np.ndarray
    ) -> None:
        op = REGISTRY.require("color.lut3d")
        out = op.apply(color_patches,
                       {"lut": "C:/yok/boyle/bir/dosya.cube", "amount": 100.0},
                       ctx_for(color_patches))
        assert np.array_equal(out, color_patches)

    def test_zero_amount_is_identity(self, color_patches: np.ndarray) -> None:
        from luma_atelier.core.paths import resources_dir

        lut = resources_dir() / "luts" / "teal_amber.cube"
        if not lut.exists():
            pytest.skip("Yerlesik LUT'lar uretilmemis")
        op = REGISTRY.require("color.lut3d")
        out = op.apply(color_patches, {"lut": str(lut), "amount": 0.0},
                       ctx_for(color_patches))
        assert np.array_equal(out, color_patches)

    def test_creative_lut_actually_changes_colour(
        self, color_patches: np.ndarray
    ) -> None:
        from luma_atelier.core.paths import resources_dir

        lut = resources_dir() / "luts" / "teal_amber.cube"
        if not lut.exists():
            pytest.skip("Yerlesik LUT'lar uretilmemis")
        op = REGISTRY.require("color.lut3d")
        out = op.apply(color_patches, {"lut": str(lut), "amount": 100.0},
                       ctx_for(color_patches))
        assert float(np.abs(out - color_patches).mean()) > 0.01

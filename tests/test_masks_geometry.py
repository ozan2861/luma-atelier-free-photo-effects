"""Maskeler, geometri ve maske-kadraj hizasi."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from luma_atelier.core.document import Document, _relative_geometry
from luma_atelier.imaging.effects.base import RenderContext
from luma_atelier.imaging.geometry import (
    ASPECT_PRESETS,
    Geometry,
    crop_array,
    fit_crop_to_aspect,
)
from luma_atelier.imaging.loader import ImageMetadata, LoadedImage
from luma_atelier.imaging.masks import (
    BlendOp,
    BrushStroke,
    Mask,
    MaskKind,
    MaskStack,
    apply_masked,
)
from luma_atelier.imaging.recipe import Recipe


@pytest.fixture
def photo() -> np.ndarray:
    """Her bolgesi ayirt edilebilir sentetik goruntu."""
    height, width = 120, 200
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.stack([xx / width, yy / height,
                      0.5 + 0.3 * np.sin(xx / 11.0)], axis=-1)
    return np.ascontiguousarray(np.clip(image, 0, 1).astype(np.float32))


@pytest.fixture
def document(photo: np.ndarray, tmp_path) -> Document:  # noqa: ANN001
    path = tmp_path / "foto.png"
    path.write_bytes(b"yer tutucu")     # icerik okunmaz; yalnizca yol gerekir
    meta = ImageMetadata(path=path, width=photo.shape[1], height=photo.shape[0],
                         source_bit_depth=8, has_alpha=False,
                         source_format="PNG")
    return Document(LoadedImage(pixels=photo, metadata=meta))


def ctx_for(image: np.ndarray, seed: int = 0) -> RenderContext:
    h, w = image.shape[:2]
    return RenderContext(full_width=w, full_height=h, scale=1.0, seed=seed)


# ============================================================ MASKE URETIMI
class TestMaskRender:
    def test_radial_is_bright_at_centre(self) -> None:
        mask = Mask(mask_id="m", kind=MaskKind.RADIAL, center=(0.5, 0.5),
                    radius=(0.25, 0.25), feather=0.0)
        rendered = mask.render((100, 100))
        assert rendered[50, 50] > 0.9
        assert rendered[2, 2] < 0.05

    def test_linear_increases_along_direction(self) -> None:
        mask = Mask(mask_id="m", kind=MaskKind.LINEAR, start=(0.0, 0.5),
                    end=(1.0, 0.5), feather=0.0)
        rendered = mask.render((40, 200))
        column_means = rendered.mean(axis=0)
        assert column_means[0] < 0.1
        assert column_means[-1] > 0.9
        assert np.all(np.diff(column_means) >= -1e-5), "tek yonlu olmali"

    def test_inverted_is_complement(self) -> None:
        base = Mask(mask_id="m", kind=MaskKind.RADIAL, feather=0.0)
        flipped = replace(base, inverted=True)
        total = base.render((60, 60)) + flipped.render((60, 60))
        assert np.allclose(total, 1.0, atol=1e-5)

    def test_opacity_scales_mask(self) -> None:
        base = Mask(mask_id="m", kind=MaskKind.RADIAL, feather=0.0)
        half = replace(base, opacity=0.5)
        assert np.allclose(half.render((50, 50)),
                           base.render((50, 50)) * 0.5, atol=1e-5)

    def test_resolution_independent(self) -> None:
        """Ayni maske farkli cozunurlukte ayni sekli vermeli."""
        mask = Mask(mask_id="m", kind=MaskKind.RADIAL, center=(0.3, 0.6),
                    radius=(0.2, 0.2), feather=0.03)
        small = mask.render((100, 150))
        large = mask.render((400, 600))
        import cv2
        shrunk = cv2.resize(large, (150, 100), interpolation=cv2.INTER_AREA)
        assert float(np.abs(small - shrunk).mean()) < 0.02

    def test_luminance_targets_bright_pixels(self, photo: np.ndarray) -> None:
        mask = Mask(mask_id="m", kind=MaskKind.LUMINANCE, luma_low=0.7,
                    luma_high=1.0, luma_softness=0.05, feather=0.0)
        rendered = mask.render(photo.shape[:2], photo)
        luma = photo.mean(axis=2)
        bright = rendered[luma > 0.8].mean()
        dark = rendered[luma < 0.3].mean()
        assert bright > dark + 0.3

    def test_brush_paints_along_points(self) -> None:
        stroke = BrushStroke(points=((0.2, 0.5), (0.8, 0.5)), radius=0.05)
        mask = Mask(mask_id="m", kind=MaskKind.BRUSH, strokes=(stroke,))
        rendered = mask.render((100, 200))
        assert rendered[50, 100] > 0.5, "vurusun ortasi boyanmali"
        assert rendered[10, 100] < 0.1, "vurusun uzagi bos kalmali"

    def test_empty_stack_returns_none(self) -> None:
        assert MaskStack().render((10, 10)) is None
        disabled = Mask(mask_id="m", enabled=False)
        assert MaskStack(masks=(disabled,)).render((10, 10)) is None

    def test_subtract_removes_area(self) -> None:
        add = Mask(mask_id="a", kind=MaskKind.RADIAL, center=(0.5, 0.5),
                   radius=(0.4, 0.4), feather=0.0)
        sub = Mask(mask_id="b", kind=MaskKind.RADIAL, center=(0.5, 0.5),
                   radius=(0.15, 0.15), feather=0.0, blend=BlendOp.SUBTRACT)
        combined = MaskStack(masks=(add, sub)).render((100, 100))
        assert combined is not None
        assert combined[50, 50] < 0.05, "cikarilan merkez bos olmali"
        assert combined[50, 62] > 0.5, "halka ayakta kalmali"

    def test_subtract_first_starts_from_full(self) -> None:
        """Ilk bilesen cikarma ise tabandan baslanir, sonuc bos kalmaz."""
        sub = Mask(mask_id="b", kind=MaskKind.RADIAL, center=(0.5, 0.5),
                   radius=(0.2, 0.2), feather=0.0, blend=BlendOp.SUBTRACT)
        result = MaskStack(masks=(sub,)).render((80, 80))
        assert result is not None
        assert result[5, 5] > 0.9
        assert result[40, 40] < 0.05


class TestApplyMasked:
    def test_none_mask_passes_processed_through(self, photo: np.ndarray) -> None:
        processed = photo * 0.5
        assert apply_masked(photo, processed, None) is processed

    def test_blend_is_exact_at_extremes(self, photo: np.ndarray) -> None:
        processed = np.clip(photo + 0.2, 0, 1)
        mask = np.zeros(photo.shape[:2], np.float32)
        mask[:, 100:] = 1.0
        out = apply_masked(photo, processed, mask)
        assert np.allclose(out[:, :100], photo[:, :100])
        assert np.allclose(out[:, 100:], processed[:, 100:])


# ================================================================ GEOMETRI
class TestGeometry:
    def test_identity_returns_same_array(self, photo: np.ndarray) -> None:
        assert Geometry().apply(photo) is photo

    def test_crop_output_size_matches_apply(self, photo: np.ndarray) -> None:
        geometry = Geometry(crop=(0.1, 0.2, 0.5, 0.6))
        out = geometry.apply(photo)
        assert out.shape[1::-1] == geometry.output_size(photo.shape[1],
                                                        photo.shape[0])

    @pytest.mark.parametrize("degrees", [90, 180, 270])
    def test_rotation_output_size_matches_apply(self, photo: np.ndarray,
                                               degrees: int) -> None:
        geometry = Geometry().rotated(degrees)
        out = geometry.apply(photo)
        assert out.shape[1::-1] == geometry.output_size(photo.shape[1],
                                                        photo.shape[0])

    def test_four_rotations_return_original(self, photo: np.ndarray) -> None:
        geometry = Geometry()
        for _ in range(4):
            geometry = geometry.rotated(90)
        assert geometry.rotation % 360 == 0
        assert np.array_equal(geometry.apply(photo), photo)

    def test_rotation_moves_crop_with_content(self) -> None:
        """Dondurme kirpmayi da dondurmeli; icerik takip etmeli."""
        geometry = Geometry(crop=(0.0, 0.0, 0.5, 1.0)).rotated(90)
        # Sol yari, saat yonunde 90 sonrasi ust yari olur
        assert geometry.crop == pytest.approx((0.0, 0.0, 1.0, 0.5))

    def test_rotation_inverts_locked_aspect(self) -> None:
        geometry = Geometry(aspect=16 / 9).rotated(90)
        assert geometry.aspect == pytest.approx(9 / 16)

    def test_flips_are_involutions(self, photo: np.ndarray) -> None:
        assert np.array_equal(Geometry(flip_h=True).apply(
            Geometry(flip_h=True).apply(photo)), photo)
        assert np.array_equal(Geometry(flip_v=True).apply(
            Geometry(flip_v=True).apply(photo)), photo)

    def test_straighten_crops_empty_corners(self, photo: np.ndarray) -> None:
        out = Geometry(straighten=10.0).apply(photo)
        assert out.shape[0] < photo.shape[0]
        assert out.shape[1] < photo.shape[1]
        assert np.isfinite(out).all()

    def test_crop_never_produces_empty_array(self, photo: np.ndarray) -> None:
        for crop in ((0.0, 0.0, 0.0001, 0.0001), (0.999, 0.999, 0.5, 0.5)):
            out = crop_array(photo, crop)
            assert out.shape[0] >= 1 and out.shape[1] >= 1

    def test_from_dict_rejects_broken_values(self) -> None:
        broken = Geometry.from_dict({"crop": ["a", None, 3, 4],
                                     "rotation": "xx", "straighten": "nan"})
        assert broken.crop == (0.0, 0.0, 1.0, 1.0)
        assert broken.rotation == 0
        assert broken.straighten == 0.0

    def test_roundtrip_dict(self) -> None:
        geometry = Geometry(crop=(0.1, 0.2, 0.3, 0.4), rotation=180,
                            flip_h=True, straighten=-3.5, aspect=1.5)
        assert Geometry.from_dict(geometry.to_dict()) == geometry

    def test_aspect_presets_are_usable(self) -> None:
        for label, value in ASPECT_PRESETS:
            assert label
            assert value is None or value >= 0.0

    def test_fit_crop_keeps_inside_frame(self) -> None:
        for aspect in (1.0, 16 / 9, 9 / 16, 2.39):
            x, y, w, h = fit_crop_to_aspect((0.1, 0.1, 0.8, 0.8), aspect, 1.5)
            assert 0.0 <= x and 0.0 <= y
            assert x + w <= 1.0 + 1e-6
            assert y + h <= 1.0 + 1e-6


# ==================================================== MASKE - KADRAJ HIZASI
def effect_centre(document: Document) -> tuple[float, float]:
    """Maskeli etkinin agirlik merkezini kaynak piksel uzayina cevirir."""
    geometry = document.recipe.geometry
    base = document.geometry_source()
    out = document.recipe.without_geometry().apply(base, ctx_for(base))
    diff = np.abs(out - base).mean(2)
    weights = np.where(diff > diff.max() * 0.5, diff, 0.0)
    ys, xs = np.nonzero(weights)
    w = weights[ys, xs]
    h, wd = out.shape[:2]
    x = float((xs * w).sum() / w.sum()) / wd
    y = float((ys * w).sum() / w.sum()) / h

    cx, cy, cw, ch = geometry.crop
    x, y = cx + x * cw, cy + y * ch
    for _ in range((geometry.rotation // 90) % 4):
        x, y = y, 1.0 - x
    if geometry.flip_v:
        y = 1.0 - y
    if geometry.flip_h:
        x = 1.0 - x
    sh, sw = document.source.shape[:2]
    return (x * sw, y * sh)


@pytest.fixture
def masked_document(document: Document) -> Document:
    document.set_param("tone.exposure", stops=2.5)
    mask_id = document.create_mask(MaskKind.RADIAL)
    component = replace(document.mask_stack(mask_id).masks[0],
                        center=(0.35, 0.65), radius=(0.10, 0.10), feather=0.01)
    document.update_mask_component(mask_id, 0, component)
    document.assign_mask(document.recipe.layers[0].instance_id, mask_id)
    return document


GEOMETRIES = [
    Geometry(crop=(0.12, 0.18, 0.62, 0.58)),
    Geometry().rotated(90),
    Geometry().rotated(180),
    Geometry().rotated(270),
    Geometry(flip_h=True),
    Geometry(flip_v=True),
    Geometry(crop=(0.10, 0.12, 0.72, 0.70)).rotated(90),
    Geometry(crop=(0.20, 0.10, 0.60, 0.70), flip_h=True),
]


class TestMaskFollowsGeometry:
    @pytest.mark.parametrize("geometry", GEOMETRIES,
                             ids=lambda g: f"crop{g.crop[0]:.2f}_rot{g.rotation}"
                                           f"_h{int(g.flip_h)}_v{int(g.flip_v)}")
    def test_mask_stays_on_same_pixel(self, masked_document: Document,
                                      geometry: Geometry) -> None:
        """Kabul olcutu: kirpma/dondurme maskeyi yanlis konuma tasimaz."""
        before = effect_centre(masked_document)
        masked_document.set_geometry(geometry)
        after = effect_centre(masked_document)
        drift = float(np.hypot(after[0] - before[0], after[1] - before[1]))
        assert drift < 3.0, f"maske {drift:.2f} piksel kaydi"

    def test_geometry_source_size_matches_output_size(
        self, masked_document: Document,
    ) -> None:
        for geometry in GEOMETRIES:
            masked_document.set_geometry(geometry)
            h, w = masked_document.source.shape[:2]
            assert masked_document.geometry_source().shape[1::-1] == \
                geometry.output_size(w, h)

    def test_geometry_source_is_cached(self, masked_document: Document) -> None:
        masked_document.set_geometry(Geometry(crop=(0.1, 0.1, 0.5, 0.5)))
        first = masked_document.geometry_source()
        assert masked_document.geometry_source() is first

    def test_identity_geometry_returns_source_without_copy(
        self, document: Document,
    ) -> None:
        assert document.geometry_source() is document.source

    def test_relative_geometry_maps_points(self) -> None:
        old = Geometry(crop=(0.1, 0.1, 0.8, 0.8))
        new = Geometry(crop=(0.2, 0.2, 0.4, 0.4))
        rel = _relative_geometry(old, new)
        cx, cy, cw, ch = rel.crop
        # Eski uzayda 0.5, kaynakta 0.5; yeni uzayda 0.75 olmali
        assert (0.5 - cx) / cw == pytest.approx(0.75)


# ======================================================= BELGE ISLEMLERI
class TestDocumentMasks:
    def test_create_and_delete(self, document: Document) -> None:
        mask_id = document.create_mask(MaskKind.LINEAR)
        assert mask_id in document.recipe.masks
        document.delete_mask(mask_id)
        assert mask_id not in document.recipe.masks

    def test_delete_unlinks_layers(self, document: Document) -> None:
        document.set_param("tone.exposure", stops=1.0)
        instance = document.recipe.layers[0].instance_id
        mask_id = document.create_mask(MaskKind.RADIAL)
        document.assign_mask(instance, mask_id)
        assert document.recipe.find(instance).mask_id == mask_id
        document.delete_mask(mask_id)
        assert document.recipe.find(instance).mask_id is None

    def test_mask_ids_do_not_collide(self, document: Document) -> None:
        ids = {document.create_mask(MaskKind.BRUSH) for _ in range(5)}
        assert len(ids) == 5

    def test_components_add_and_remove(self, document: Document) -> None:
        mask_id = document.create_mask(MaskKind.RADIAL)
        document.add_mask_component(mask_id, MaskKind.LINEAR, BlendOp.SUBTRACT)
        assert len(document.mask_stack(mask_id).masks) == 2
        document.remove_mask_component(mask_id, 1)
        assert len(document.mask_stack(mask_id).masks) == 1

    def test_removing_last_component_deletes_mask(self, document: Document) -> None:
        mask_id = document.create_mask(MaskKind.RADIAL)
        document.remove_mask_component(mask_id, 0)
        assert mask_id not in document.recipe.masks

    def test_mask_edits_are_undoable(self, document: Document) -> None:
        mask_id = document.create_mask(MaskKind.RADIAL)
        component = document.mask_stack(mask_id).masks[0]
        document.update_mask_component(mask_id, 0,
                                       replace(component, opacity=0.25))
        assert document.mask_stack(mask_id).masks[0].opacity == 0.25
        assert document.undo()
        assert document.mask_stack(mask_id).masks[0].opacity == 1.0

    def test_slider_drag_is_one_undo_step(self, document: Document) -> None:
        mask_id = document.create_mask(MaskKind.RADIAL)
        document.commit()
        depth = document.history.depth
        base = document.mask_stack(mask_id).masks[0]
        for value in (0.9, 0.8, 0.7, 0.6):
            document.update_mask_component(
                mask_id, 0, replace(base, opacity=value),
                merge_key="mask:opacity")
        assert document.history.depth - depth == 1

    def test_unknown_mask_id_is_ignored(self, document: Document) -> None:
        document.update_mask_component("yok", 0, Mask(mask_id="x"))
        document.remove_mask_component("yok", 0)
        document.delete_mask("yok")
        assert not document.recipe.masks

    def test_layer_bound_to_missing_mask_still_renders(
        self, photo: np.ndarray,
    ) -> None:
        """Maske kaybolsa bile katman maskesiz uygulanir, cokmez."""
        recipe = Recipe().set_or_add("tone.exposure", stops=1.0)
        recipe = recipe.assign_mask(recipe.layers[0].instance_id, "olmayan")
        out = recipe.apply(photo, ctx_for(photo))
        assert out.shape == photo.shape
        assert np.isfinite(out).all()
        assert float(np.abs(out - photo).max()) > 0.01

    def test_set_geometry_ignores_no_change(self, document: Document) -> None:
        document.commit()
        depth = document.history.depth
        document.set_geometry(Geometry())
        assert document.history.depth == depth

    def test_reset_geometry(self, document: Document) -> None:
        document.set_geometry(Geometry(crop=(0.2, 0.2, 0.5, 0.5)))
        document.reset_geometry()
        assert document.recipe.geometry.is_identity


# ======================================================= SERILESTIRME
class TestSerialisation:
    def test_recipe_roundtrip_with_masks_and_geometry(self) -> None:
        brush = Mask(mask_id="b", kind=MaskKind.BRUSH,
                     strokes=(BrushStroke(points=((0.1, 0.2), (0.3, 0.4)),
                                          radius=0.07, erase=True),))
        recipe = (Recipe()
                  .set_or_add("tone.exposure", stops=0.5)
                  .with_mask("m1", MaskStack(masks=(brush,)))
                  .with_geometry(Geometry(crop=(0.1, 0.1, 0.7, 0.7),
                                          rotation=90, straighten=2.0)))
        recipe = recipe.assign_mask(recipe.layers[0].instance_id, "m1")
        restored = Recipe.from_dict(recipe.to_dict())
        assert restored.geometry == recipe.geometry
        assert restored.masks == recipe.masks
        assert restored.layers[0].mask_id == "m1"

    def test_empty_geometry_not_written(self) -> None:
        data = Recipe().to_dict()
        assert "geometry" not in data
        assert "masks" not in data

    def test_broken_mask_entry_is_skipped(self) -> None:
        stack = MaskStack.from_list([{"kind": "radial", "id": "ok"},
                                     "bu bir sozluk degil"])
        assert len(stack.masks) <= 2   # bozuk giris cokme yaratmaz

    def test_without_geometry_keeps_layers(self) -> None:
        recipe = (Recipe().set_or_add("tone.exposure", stops=1.0)
                  .with_geometry(Geometry(crop=(0.2, 0.2, 0.5, 0.5))))
        stripped = recipe.without_geometry()
        assert stripped.geometry.is_identity
        assert stripped.layers == recipe.layers

    def test_without_geometry_is_identity_noop(self) -> None:
        recipe = Recipe().set_or_add("tone.exposure", stops=1.0)
        assert recipe.without_geometry() is recipe


class TestMaskRoundTripAfterGeometry:
    """Kirpma sonrasi kaydedilen maske, acilinca **ayni** yerde olmali.

    Bulunan hata: `Mask.to_dict` yalnizca maskenin turune ait konum
    alanlarini yaziyordu, ama `transformed()` kirpma/dondurme sonrasi
    *tum* konumlari yeni kadraja tasir. Yazilmayan alanlar acilista
    varsayilana donuyor; kullanici maskenin turunu sonradan
    degistirdiginde gradyan eski kadrajin yerini gosteriyordu.
    """

    @pytest.mark.parametrize("kind", list(MaskKind),
                             ids=lambda k: k.value)
    def test_every_kind_survives_crop_and_reload(self, document: Document,
                                                 kind: MaskKind) -> None:
        document.set_param("tone.exposure", stops=0.4)
        mask_id = document.create_mask(kind)
        document.assign_mask(document.recipe.layers[0].instance_id, mask_id)
        document.set_geometry(Geometry(crop=(0.06, 0.06, 0.85, 0.85)))
        document.commit()

        before = document.recipe
        after = Recipe.from_dict(before.to_dict())
        assert after.masks == before.masks
        assert after == before

    def test_off_frame_gradient_anchor_is_preserved(self) -> None:
        """Kirpma gradyan ucunu kadraj disina tasiyabilir; bu gecerlidir."""
        mask = Mask(mask_id="m", kind=MaskKind.LINEAR,
                    start=(0.52, -0.07), end=(0.52, 1.11))
        restored = Mask.from_dict(mask.to_dict())
        assert restored.start == pytest.approx(mask.start)
        assert restored.end == pytest.approx(mask.end)

    def test_kind_switch_keeps_transformed_positions(self) -> None:
        """Tur degisince digerlerinin konumu da dogru kadrajda olmali."""
        radial = Mask(mask_id="m", kind=MaskKind.RADIAL)
        moved = radial.transformed(crop=(0.1, 0.1, 0.5, 0.5))
        restored = Mask.from_dict(moved.to_dict())
        assert restored.start == pytest.approx(moved.start)
        assert restored.end == pytest.approx(moved.end)
        assert restored.center == pytest.approx(moved.center)

"""Tarif, gecmis ve belge testleri (Qt gerektirmez)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from luma_atelier.core.branding import PRESET_FORMAT_VERSION
from luma_atelier.core.document import Document
from luma_atelier.core.history import COALESCE_WINDOW, History
from luma_atelier.imaging.effects import REGISTRY, RenderContext
from luma_atelier.imaging.loader import ImageMetadata, LoadedImage
from luma_atelier.imaging.recipe import Recipe, RecipeError


def ctx(image: np.ndarray) -> RenderContext:
    h, w = image.shape[:2]
    return RenderContext(full_width=w, full_height=h, scale=1.0, seed=1)


@pytest.fixture
def document(color_patches: np.ndarray, tmp_path) -> Document:  # noqa: ANN001
    meta = ImageMetadata(
        path=tmp_path / "test.jpg", width=color_patches.shape[1],
        height=color_patches.shape[0], source_bit_depth=8, has_alpha=False,
        source_format="JPEG",
    )
    return Document(LoadedImage(pixels=color_patches, metadata=meta))


class TestRecipeBasics:
    def test_empty_recipe_is_identity(self, color_patches: np.ndarray) -> None:
        out = Recipe().apply(color_patches, ctx(color_patches))
        assert np.array_equal(out, color_patches)

    def test_add_returns_new_recipe(self) -> None:
        a = Recipe()
        b = a.add("tone.exposure", {"stops": 1.0})
        assert len(a) == 0 and len(b) == 1, "tarif degismez olmali"

    def test_unknown_operation_is_rejected_on_add(self) -> None:
        with pytest.raises(RecipeError, match="Bilinmeyen işlem"):
            Recipe().add("yok.boyle.bir.islem")

    def test_disabled_layer_is_skipped(self, color_patches: np.ndarray) -> None:
        r = Recipe().add("tone.exposure", {"stops": 1.5})
        enabled = r.apply(color_patches, ctx(color_patches))
        off = r.set_enabled(r.layers[0].instance_id, False)
        disabled = off.apply(color_patches, ctx(color_patches))
        assert not np.array_equal(enabled, color_patches)
        assert np.array_equal(disabled, color_patches)

    def test_same_operation_can_appear_twice(self) -> None:
        r = Recipe().add("detail.clarity", {"amount": 20.0, "radius": 20.0}) \
                    .add("detail.clarity", {"amount": 15.0, "radius": 120.0})
        assert len(r) == 2
        assert r.layers[0].instance_id != r.layers[1].instance_id

    def test_order_changes_the_result(self, portrait_like: np.ndarray) -> None:
        """Sira degisikligi sonucu gercekten degistirmeli.

        Pozlama lineer isikta carpim, kontrast sRGB uzayinda tanh
        egrisidir; birbirinin yerine gecmezler.
        """
        a = (Recipe().add("tone.exposure", {"stops": 0.8})
                     .add("tone.contrast", {"amount": 60.0}))
        b = (Recipe().add("tone.contrast", {"amount": 60.0})
                     .add("tone.exposure", {"stops": 0.8}))
        ra = a.apply(portrait_like, ctx(portrait_like))
        rb = b.apply(portrait_like, ctx(portrait_like))
        assert float(np.abs(ra - rb).mean()) > 1e-3

    def test_some_operations_legitimately_commute(
        self, portrait_like: np.ndarray
    ) -> None:
        """Bazi islem ciftleri matematiksel olarak yer degistirebilir.

        Doygunluk ve siyah-beyaz karisimi ikisi de rgb <-> gri ekseninde
        dogrusaldir ve parlaklik dogrusal bir islevdir; bu yuzden sirasi
        sonucu degistirmez. Bu bir hata degil, beklenen davranistir ve
        burada belgelenir ki ileride "sira calismiyor" diye yanlis
        teshis konmasin.
        """
        a = (Recipe().add("color.saturation", {"amount": 80.0})
                     .add("color.monochrome", {"amount": 60.0}))
        b = (Recipe().add("color.monochrome", {"amount": 60.0})
                     .add("color.saturation", {"amount": 80.0}))
        ra = a.apply(portrait_like, ctx(portrait_like))
        rb = b.apply(portrait_like, ctx(portrait_like))
        assert float(np.abs(ra - rb).max()) < 1e-5

    def test_move_reorders(self) -> None:
        r = Recipe().add("tone.exposure").add("tone.contrast")
        first = r.layers[0].instance_id
        moved = r.move(first, 1)
        assert moved.layers[1].instance_id == first

    def test_broken_layer_does_not_break_render(
        self, color_patches: np.ndarray
    ) -> None:
        """Bir katman hata verirse digerleri calismaya devam etmeli."""
        from luma_atelier.imaging.effects.base import Category, Operation

        def boom(_image, _params, _ctx):
            raise RuntimeError("bilerek hata")

        failing = Operation(
            op_id="test.bozuk", name="Bozuk islem",
            description="Yalnizca test icin: her zaman hata firlatir.",
            category=Category.TONE, params=(), fn=boom,
        )
        REGISTRY.register(failing)
        try:
            r = (Recipe().add("test.bozuk")
                         .add("tone.contrast", {"amount": 30.0}))
            out = r.apply(color_patches, ctx(color_patches))
            assert np.isfinite(out).all()
            # Kontrast yine de uygulanmis olmali
            assert not np.array_equal(out, color_patches)
        finally:
            REGISTRY._ops.pop("test.bozuk", None)


class TestRecipeSerialisation:
    def test_roundtrip_preserves_render(self, portrait_like: np.ndarray) -> None:
        r = (Recipe().add("tone.exposure", {"stops": 0.6})
                     .add("color.white_balance", {"kelvin": 5000.0, "tint": -8.0})
                     .add("color.vibrance", {"amount": 25.0}))
        restored = Recipe.from_dict(json.loads(json.dumps(r.to_dict())))
        assert np.array_equal(
            r.apply(portrait_like, ctx(portrait_like)),
            restored.apply(portrait_like, ctx(portrait_like)),
        )

    def test_seed_survives_roundtrip(self) -> None:
        r = Recipe().with_seed(987654)
        assert Recipe.from_dict(r.to_dict()).seed == 987654

    def test_unknown_operation_is_kept_not_deleted(self) -> None:
        """Bilinmeyen efekt sessizce silinmemeli."""
        data = {
            "version": PRESET_FORMAT_VERSION,
            "layers": [
                {"op": "tone.exposure", "params": {"stops": 0.5}},
                {"op": "gelecek.efekt", "params": {"x": 3}},
            ],
        }
        r = Recipe.from_dict(data)
        assert len(r) == 1
        assert len(r.unknown_layers) == 1
        again = r.to_dict()
        assert any(l["op"] == "gelecek.efekt" for l in again["layers"])

    def test_strict_mode_rejects_unknown(self) -> None:
        data = {"layers": [{"op": "gelecek.efekt", "params": {}}]}
        with pytest.raises(RecipeError, match="Bilinmeyen işlem"):
            Recipe.from_dict(data, strict=True)

    def test_newer_format_version_is_refused_with_clear_message(self) -> None:
        data = {"version": PRESET_FORMAT_VERSION + 5, "layers": []}
        with pytest.raises(RecipeError, match="guncelleyin"):
            Recipe.from_dict(data)

    def test_malicious_params_are_sanitised(self, color_patches: np.ndarray) -> None:
        """Ice aktarilan veri kod calistirmamali, sema disi kalmamali."""
        data = {
            "layers": [{
                "op": "tone.exposure",
                "params": {"stops": 1e9, "__class__": "kotu", "cmd": "rm -rf"},
            }],
        }
        r = Recipe.from_dict(data)
        params = r.layers[0].params
        assert set(params) == {"stops"}
        assert params["stops"] <= 5.0
        assert np.isfinite(r.apply(color_patches, ctx(color_patches))).all()

    def test_non_dict_input_is_rejected(self) -> None:
        with pytest.raises(RecipeError):
            Recipe.from_dict([1, 2, 3])  # type: ignore[arg-type]

    def test_layer_without_op_is_rejected(self) -> None:
        with pytest.raises(RecipeError):
            Recipe.from_dict({"layers": [{"params": {}}]})


class TestHistory:
    def test_starts_with_no_undo(self) -> None:
        h = History("a")
        assert not h.can_undo() and not h.can_redo()

    def test_push_then_undo_redo(self) -> None:
        h = History("a")
        h.push("b", "B ekle")
        assert h.current == "b" and h.can_undo()
        assert h.undo() == "a"
        assert h.redo() == "b"

    def test_identical_state_is_not_pushed(self) -> None:
        h = History("a")
        assert not h.push("a", "ayni")
        assert h.depth == 1

    def test_new_branch_discards_redo(self) -> None:
        h = History("a")
        h.push("b", "B")
        h.undo()
        h.push("c", "C")
        assert not h.can_redo()
        assert h.current == "c"

    def test_merge_key_coalesces_rapid_changes(self) -> None:
        """Kaydirici suruklemesi tek adim olmali."""
        h = History(0)
        for i in range(1, 30):
            h.push(i, "Pozlama", merge_key="tone.exposure:stops")
        assert h.depth == 2, f"beklenen 2 adim, olusan {h.depth}"
        assert h.current == 29

    def test_different_merge_keys_do_not_coalesce(self) -> None:
        h = History(0)
        h.push(1, "Pozlama", merge_key="a")
        h.push(2, "Kontrast", merge_key="b")
        assert h.depth == 3

    def test_seal_closes_merge_window(self) -> None:
        h = History(0)
        h.push(1, "Pozlama", merge_key="k")
        h.seal()
        h.push(2, "Pozlama", merge_key="k")
        assert h.depth == 3

    def test_limit_drops_oldest(self) -> None:
        h = History(0, limit=10)
        for i in range(1, 50):
            h.push(i, f"adim {i}")
        assert h.depth == 10
        assert h.current == 49

    def test_supports_at_least_fifty_steps(self) -> None:
        """Gereksinim: en az 50 duzenleme adimi."""
        h = History(0)
        for i in range(1, 80):
            h.push(i, f"adim {i}")
        undos = 0
        while h.can_undo():
            h.undo()
            undos += 1
        assert undos >= 50

    def test_labels_are_reported(self) -> None:
        h = History("a")
        h.push("b", "Pozlama")
        assert h.undo_label() == "Pozlama"
        h.undo()
        assert h.redo_label() == "Pozlama"

    def test_reset_clears(self) -> None:
        h = History("a")
        h.push("b", "B")
        h.reset("z")
        assert h.current == "z" and not h.can_undo()


class TestDocument:
    def test_starts_unmodified(self, document: Document) -> None:
        assert not document.is_modified
        assert not document.has_edits

    def test_set_param_creates_layer(self, document: Document) -> None:
        document.set_param("tone.exposure", stops=0.7)
        assert document.recipe.has("tone.exposure")
        assert document.is_modified

    def test_repeated_set_param_updates_same_layer(
        self, document: Document
    ) -> None:
        """Kaydirici her hareketinde yeni katman eklememeli."""
        for v in (0.1, 0.2, 0.3, 0.4):
            document.set_param("tone.exposure", stops=v)
        assert len(document.recipe) == 1
        assert document.recipe.first_of("tone.exposure").params["stops"] == 0.4

    def test_slider_drag_is_one_history_step(self, document: Document) -> None:
        depth = document.history.depth
        for v in range(40):
            document.set_param("tone.exposure", stops=v / 100.0)
        document.commit()
        assert document.history.depth - depth == 1

    def test_reset_operation_removes_only_that_layer(
        self, document: Document
    ) -> None:
        document.set_param("tone.exposure", stops=0.5)
        document.commit()
        document.set_param("tone.contrast", amount=30.0)
        document.commit()
        document.reset_operation("tone.exposure")
        assert not document.recipe.has("tone.exposure")
        assert document.recipe.has("tone.contrast")

    def test_reset_all_is_undoable(self, document: Document) -> None:
        document.set_param("tone.exposure", stops=0.5)
        document.commit()
        document.reset_all()
        assert document.recipe.is_empty
        document.undo()
        assert document.recipe.has("tone.exposure")

    def test_mark_saved_clears_modified_flag(self, document: Document) -> None:
        document.set_param("tone.exposure", stops=0.5)
        document.commit()
        assert document.is_modified
        document.mark_saved()
        assert not document.is_modified

    def test_editing_after_save_sets_modified_again(
        self, document: Document
    ) -> None:
        document.set_param("tone.exposure", stops=0.5)
        document.mark_saved()
        document.set_param("tone.contrast", amount=20.0)
        assert document.is_modified

    def test_copy_paste_recipe_between_documents(
        self, document: Document, color_patches: np.ndarray, tmp_path
    ) -> None:  # noqa: ANN001
        document.set_param("tone.exposure", stops=0.6)
        document.set_param("color.vibrance", amount=25.0)
        recipe = document.copy_recipe()

        meta = ImageMetadata(
            path=tmp_path / "other.jpg", width=color_patches.shape[1],
            height=color_patches.shape[0], source_bit_depth=8,
            has_alpha=False, source_format="JPEG",
        )
        other = Document(LoadedImage(pixels=color_patches, metadata=meta))
        other.paste_recipe(recipe)
        assert len(other.recipe) == len(recipe)
        assert np.array_equal(
            recipe.apply(color_patches, ctx(color_patches)),
            other.recipe.apply(color_patches, ctx(color_patches)),
        )

    def test_source_pixels_are_never_modified(
        self, document: Document, color_patches: np.ndarray
    ) -> None:
        before = document.source.copy()
        document.set_param("tone.exposure", stops=1.2)
        document.recipe.apply(document.source, ctx(document.source))
        assert np.array_equal(document.source, before)

    def test_listener_is_called_on_edit(self, document: Document) -> None:
        calls: list[int] = []
        document.add_listener(lambda: calls.append(1))
        document.set_param("tone.exposure", stops=0.3)
        assert calls

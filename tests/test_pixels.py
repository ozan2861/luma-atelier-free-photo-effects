"""Renk uzayi ve piksel modeli testleri."""
from __future__ import annotations

import numpy as np
import pytest

from luma_atelier.imaging import pixels as px


class TestTransferFunctions:
    def test_srgb_roundtrip_is_lossless_within_float32(self) -> None:
        # Arrange - negatif ve 1.0 ustu degerler dahil genis aralik
        x = np.linspace(-0.3, 1.4, 200_000, dtype=np.float32).reshape(-1, 1)

        # Act
        back = px.linear_to_srgb(px.srgb_to_linear(x))

        # Assert
        assert np.abs(back - x).max() < 1e-5

    def test_srgb_to_linear_matches_published_midpoint(self) -> None:
        # IEC 61966-2-1: 0.5 sRGB -> 0.2140411 lineer
        got = float(px.srgb_to_linear(np.full((300, 300), 0.5, np.float32))[0, 0])
        assert got == pytest.approx(0.2140411, abs=1e-6)

    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_endpoints_are_fixed(self, value: float) -> None:
        arr = np.full((300, 300), value, np.float32)
        assert float(px.srgb_to_linear(arr)[0, 0]) == pytest.approx(value, abs=1e-6)
        assert float(px.linear_to_srgb(arr)[0, 0]) == pytest.approx(value, abs=1e-6)

    def test_negative_values_keep_sign(self) -> None:
        """Ara adimlarda olusan negatifler kirpilmaz, isaret korunur."""
        arr = np.full((300, 300), -0.5, np.float32)
        assert float(px.srgb_to_linear(arr)[0, 0]) < 0

    def test_highlight_headroom_is_preserved(self) -> None:
        """1.0 ustu parlak alan bilgisi donusumde kaybolmaz."""
        arr = np.full((300, 300), 1.8, np.float32)
        assert float(px.srgb_to_linear(arr)[0, 0]) > 1.0

    @pytest.mark.parametrize("shape", [(64, 64), (300, 300, 3), (300, 300, 4),
                                       (7,), (100_001, 1)])
    def test_shapes_are_handled(self, shape: tuple[int, ...]) -> None:
        """cv2 hizli yolu tek boyutlu diziyi NxN sanip cokuyordu."""
        arr = np.full(shape, 0.5, np.float32)
        out = px.srgb_to_linear(arr)
        assert out.shape == shape
        assert out.dtype == np.float32

    def test_no_nan_or_inf_on_extreme_input(self) -> None:
        arr = np.array([[-1e6, -1.0, 0.0, 1.0, 1e6]], dtype=np.float32).repeat(300, 0)
        assert np.isfinite(px.srgb_to_linear(arr)).all()
        assert np.isfinite(px.linear_to_srgb(arr)).all()


class TestEnsureWorking:
    def test_grayscale_expands_to_three_channels(self) -> None:
        out = px.ensure_working(np.zeros((8, 8), np.float32))
        assert out.shape == (8, 8, 3)

    def test_single_channel_expands(self) -> None:
        out = px.ensure_working(np.zeros((8, 8, 1), np.float32))
        assert out.shape == (8, 8, 3)

    def test_dtype_is_coerced_to_float32(self) -> None:
        out = px.ensure_working(np.zeros((8, 8, 3), np.float64))
        assert out.dtype == np.float32

    def test_rejects_unsupported_channel_count(self) -> None:
        with pytest.raises(ValueError, match="kanal"):
            px.ensure_working(np.zeros((8, 8, 5), np.float32))


class TestAlpha:
    def test_premultiply_roundtrip_restores_original(
        self, alpha_edge: np.ndarray
    ) -> None:
        back = px.unpremultiply(px.premultiply(alpha_edge))
        # Alpha=0 bolgelerinde RGB tanimsizdir; yalnizca gorunur kismi karsilastir
        visible = alpha_edge[..., 3] > 1e-3
        assert np.abs(back[visible][:, :3] - alpha_edge[visible][:, :3]).max() < 1e-5

    def test_unpremultiply_does_not_divide_by_zero(self) -> None:
        img = np.zeros((4, 4, 4), np.float32)
        out = px.unpremultiply(img)
        assert np.isfinite(out).all()

    def test_composite_over_uses_background_where_transparent(self) -> None:
        img = np.zeros((4, 4, 4), np.float32)
        img[..., :3] = 0.8
        img[..., 3] = 0.0
        out = px.composite_over(img, (1.0, 1.0, 1.0))
        assert np.allclose(out, 1.0)

    def test_composite_over_keeps_colour_where_opaque(self) -> None:
        img = np.zeros((4, 4, 4), np.float32)
        img[..., :3] = 0.8
        img[..., 3] = 1.0
        out = px.composite_over(img, (0.0, 0.0, 0.0))
        assert np.allclose(out, 0.8)

    def test_split_join_roundtrip(self, alpha_edge: np.ndarray) -> None:
        rgb, a = px.split_alpha(alpha_edge)
        assert np.array_equal(px.join_alpha(rgb, a), alpha_edge)


class TestBlend:
    def test_zero_amount_returns_base_unchanged(
        self, gradient_rgb: np.ndarray
    ) -> None:
        """Yogunluk %0 orijinali birebir korumali - kabul olcutu."""
        layer = gradient_rgb * 0.2
        out = px.blend(gradient_rgb, layer, 0.0)
        assert np.array_equal(out, gradient_rgb)

    def test_full_amount_returns_layer(self, gradient_rgb: np.ndarray) -> None:
        layer = gradient_rgb * 0.2
        assert np.array_equal(px.blend(gradient_rgb, layer, 1.0), layer)

    def test_half_amount_is_midpoint(self) -> None:
        base = np.zeros((4, 4, 3), np.float32)
        layer = np.ones((4, 4, 3), np.float32)
        assert np.allclose(px.blend(base, layer, 0.5), 0.5)

    def test_amount_is_clamped(self, gradient_rgb: np.ndarray) -> None:
        layer = gradient_rgb * 0.2
        assert np.array_equal(px.blend(gradient_rgb, layer, -5.0), gradient_rgb)
        assert np.array_equal(px.blend(gradient_rgb, layer, 5.0), layer)


class TestQuantisation:
    def test_uint16_roundtrip_preserves_all_levels(
        self, gray_ramp16: np.ndarray
    ) -> None:
        """16-bit hassasiyet float32 uzerinden gecerken kaybolmamali."""
        work = px.from_uint16(gray_ramp16)
        back = px.to_uint16(work)
        assert np.array_equal(back, gray_ramp16)

    def test_uint8_roundtrip_is_exact(self) -> None:
        src = np.arange(256, dtype=np.uint8).reshape(16, 16)
        src3 = np.dstack([src, src, src])
        assert np.array_equal(px.to_uint8(px.from_uint8(src3)), src3)

    def test_to_uint8_clips_out_of_range(self) -> None:
        arr = np.array([[-1.0, 0.0, 0.5, 1.0, 2.0]], np.float32)
        out = px.to_uint8(arr)
        assert out.min() == 0 and out.max() == 255


class TestLuminance:
    def test_neutral_grey_luminance_equals_grey_value(self) -> None:
        img = np.full((8, 8, 3), 0.42, np.float32)
        assert np.allclose(px.luminance(img), 0.42, atol=1e-6)

    def test_green_weighted_highest(self) -> None:
        r = px.luminance(np.array([[[1.0, 0.0, 0.0]]], np.float32))
        g = px.luminance(np.array([[[0.0, 1.0, 0.0]]], np.float32))
        b = px.luminance(np.array([[[0.0, 0.0, 1.0]]], np.float32))
        assert g > r > b

    def test_shape_drops_channel_axis(self, gradient_rgb: np.ndarray) -> None:
        assert px.luminance(gradient_rgb).shape == gradient_rgb.shape[:2]

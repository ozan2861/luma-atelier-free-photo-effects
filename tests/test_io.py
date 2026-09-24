"""Dosya okuma/yazma testleri: format, bit derinligi, EXIF, alpha, hata."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from luma_atelier.imaging import pixels as px
from luma_atelier.imaging.loader import (
    ImageLoadError,
    apply_orientation,
    load_image,
    probe_image,
)
from luma_atelier.imaging.saver import (
    ImageSaveError,
    OutputFormat,
    SaveOptions,
    save_image,
    unique_path,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestRoundTrip:
    @pytest.mark.parametrize(
        "fmt,lossless",
        [
            (OutputFormat.PNG, True),
            (OutputFormat.TIFF, True),
            (OutputFormat.WEBP, False),
            (OutputFormat.JPEG, False),
        ],
    )
    def test_colour_survives_write_then_read(
        self, tmp_path: Path, color_patches: np.ndarray,
        fmt: OutputFormat, lossless: bool,
    ) -> None:
        """Renk dogrulugu formatin dogasina uygun olculur.

        Kayipsiz formatlarda her piksel 8-bit yuvarlama icinde kalmali.
        Kayipli formatlarda sert renk siniri cevresindeki ringing
        kacinilmazdir; bu yuzden yama *merkezleri* ve genel istatistik
        olculur. Maksimum hatayla olcmek codec'in dogasini hata sayardi.
        """
        out = tmp_path / f"patches{fmt.extension}"
        save_image(color_patches, out, SaveOptions(fmt=fmt, quality=96))
        back = load_image(out)
        assert back.pixels.shape[:2] == color_patches.shape[:2]

        diff = np.abs(back.pixels[..., :3] - color_patches)
        if lossless:
            assert diff.max() < 1.0 / 255
            return

        # Her yamanin ic kismi (kenardan 24 px iceride) referansa sadik kalmali
        cell, rows, cols, inset = 120, 4, 6, 24
        for r in range(rows):
            for c in range(cols):
                y0, x0 = r * cell + inset, c * cell + inset
                y1, x1 = (r + 1) * cell - inset, (c + 1) * cell - inset
                patch_err = diff[y0:y1, x0:x1].mean()
                assert patch_err < 0.01, f"yama ({r},{c}) sapmasi {patch_err:.4f}"

        assert diff.mean() < 0.005
        assert float(np.percentile(diff, 99.0)) < 0.05

    def test_tiff_16bit_preserves_every_level(
        self, tmp_path: Path, gray_ramp16: np.ndarray
    ) -> None:
        """Dosya etiketi degil, piksel hassasiyeti test edilir."""
        work = px.from_uint16(gray_ramp16)
        out = tmp_path / "ramp.tif"
        result = save_image(
            work, out, SaveOptions(fmt=OutputFormat.TIFF, bit_depth=16)
        )
        assert result.bit_depth == 16

        back = load_image(out)
        assert back.metadata.source_bit_depth == 16
        recovered = px.to_uint16(back.pixels[..., 0])
        assert len(np.unique(recovered)) == 65536
        assert np.array_equal(recovered, gray_ramp16[..., 0])

    def test_8bit_tiff_would_lose_levels(
        self, tmp_path: Path, gray_ramp16: np.ndarray
    ) -> None:
        """Karsit kanit: 8-bit yazinca gercekten kayip olur."""
        work = px.from_uint16(gray_ramp16)
        out = tmp_path / "ramp8.tif"
        save_image(work, out, SaveOptions(fmt=OutputFormat.TIFF, bit_depth=8))
        back = load_image(out)
        assert len(np.unique(px.to_uint16(back.pixels[..., 0]))) <= 256


class TestAlphaHandling:
    def test_png_keeps_alpha_channel(
        self, tmp_path: Path, alpha_edge: np.ndarray
    ) -> None:
        out = tmp_path / "edge.png"
        result = save_image(alpha_edge, out, SaveOptions(fmt=OutputFormat.PNG))
        assert result.had_alpha
        back = load_image(out)
        assert back.has_alpha
        assert np.abs(back.pixels[..., 3] - alpha_edge[..., 3]).max() < 1.5 / 255

    def test_webp_keeps_alpha_channel(
        self, tmp_path: Path, alpha_edge: np.ndarray
    ) -> None:
        out = tmp_path / "edge.webp"
        save_image(alpha_edge, out,
                   SaveOptions(fmt=OutputFormat.WEBP, webp_lossless=True))
        assert load_image(out).has_alpha

    def test_jpeg_flattens_with_chosen_fill_colour(
        self, tmp_path: Path, alpha_edge: np.ndarray
    ) -> None:
        out = tmp_path / "edge.jpg"
        result = save_image(
            alpha_edge, out,
            SaveOptions(fmt=OutputFormat.JPEG, quality=98,
                        flatten_color=(0.0, 0.0, 1.0)),
        )
        assert not result.had_alpha
        back = load_image(out)
        assert not back.has_alpha
        # Kose tamamen saydamdi -> secilen mavi dolgu gorunmeli
        corner = back.pixels[2, 2]
        assert corner[2] > 0.8 and corner[0] < 0.2

    def test_transparent_edge_has_no_dark_halo(
        self, tmp_path: Path, alpha_edge: np.ndarray
    ) -> None:
        """Beyaz zemine yerlestirilen saydam kenar koyu hale birakmamali."""
        flat = px.composite_over(alpha_edge, (1.0, 1.0, 1.0))
        # Kenar bandindaki en koyu deger, nesnenin kendi renginden koyu olamaz
        a = alpha_edge[..., 3]
        edge_band = (a > 0.02) & (a < 0.98)
        assert edge_band.any()
        assert flat[edge_band].min() >= alpha_edge[..., :3].min() - 1e-5


class TestExifOrientation:
    def test_orientation_6_is_applied_to_pixels(self, rotated_jpeg: Path) -> None:
        """Dikey telefon fotografi yan yatmamali."""
        loaded = load_image(rotated_jpeg)
        assert loaded.metadata.exif_orientation == 6
        assert loaded.metadata.orientation_applied
        # Kaynak 200x100 yatay; orientation 6 uygulandiginda 100x200 dikey olur
        assert (loaded.width, loaded.height) == (100, 200)

    def test_orientation_can_be_skipped(self, rotated_jpeg: Path) -> None:
        loaded = load_image(rotated_jpeg, apply_exif_orientation=False)
        assert (loaded.width, loaded.height) == (200, 100)
        assert not loaded.metadata.orientation_applied

    def test_probe_reports_display_dimensions(self, rotated_jpeg: Path) -> None:
        meta = probe_image(rotated_jpeg)
        assert meta is not None
        assert (meta.width, meta.height) == (100, 200)

    @pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
    def test_every_orientation_preserves_pixel_count(self, orientation: int) -> None:
        arr = np.arange(2 * 3 * 3, dtype=np.float32).reshape(2, 3, 3)
        out = apply_orientation(arr, orientation)
        assert sorted(out.ravel().tolist()) == sorted(arr.ravel().tolist())

    def test_orientation_8_is_inverse_of_6(self) -> None:
        arr = np.arange(2 * 3 * 3, dtype=np.float32).reshape(2, 3, 3)
        assert np.array_equal(apply_orientation(apply_orientation(arr, 6), 8), arr)

    def test_unknown_orientation_leaves_image_alone(self) -> None:
        arr = np.zeros((2, 3, 3), np.float32)
        assert apply_orientation(arr, 99).shape == arr.shape


class TestIccProfile:
    def test_profile_is_written_and_read_back(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        from PIL import ImageCms

        blob = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        out = tmp_path / "with_icc.jpg"
        save_image(color_patches, out,
                   SaveOptions(fmt=OutputFormat.JPEG, quality=95, icc_profile=blob))
        back = load_image(out)
        assert back.metadata.icc_profile is not None
        assert not back.metadata.assumed_srgb

    def test_missing_profile_records_srgb_assumption(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        out = tmp_path / "no_icc.png"
        save_image(color_patches, out, SaveOptions(fmt=OutputFormat.PNG))
        assert load_image(out).metadata.assumed_srgb

    def test_strip_metadata_removes_profile(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        from PIL import ImageCms

        blob = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        out = tmp_path / "stripped.jpg"
        save_image(
            color_patches, out,
            SaveOptions(fmt=OutputFormat.JPEG, icc_profile=blob, strip_metadata=True),
        )
        assert load_image(out).metadata.icc_profile is None


class TestOriginalSafety:
    def test_reading_never_modifies_source(self, written_jpeg: Path) -> None:
        before = _sha256(written_jpeg)
        load_image(written_jpeg)
        load_image(written_jpeg)
        assert _sha256(written_jpeg) == before

    def test_save_does_not_overwrite_by_default(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        target = tmp_path / "out.png"
        first = save_image(color_patches, target, SaveOptions(fmt=OutputFormat.PNG))
        second = save_image(color_patches, target, SaveOptions(fmt=OutputFormat.PNG))
        assert first.path.name == "out.png"
        assert second.path.name == "out (2).png"
        assert second.renamed_from_conflict

    def test_overwrite_is_opt_in(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        target = tmp_path / "out.png"
        save_image(color_patches, target, SaveOptions(fmt=OutputFormat.PNG))
        again = save_image(color_patches, target,
                           SaveOptions(fmt=OutputFormat.PNG, overwrite=True))
        assert again.path == target
        assert len(list(tmp_path.glob("out*.png"))) == 1

    def test_unique_path_generates_sequence(self, tmp_path: Path) -> None:
        base = tmp_path / "a.jpg"
        base.write_bytes(b"x")
        p2, renamed = unique_path(base)
        assert renamed and p2.name == "a (2).jpg"
        p2.write_bytes(b"x")
        p3, _ = unique_path(base)
        assert p3.name == "a (3).jpg"


class TestFailureHandling:
    def test_missing_file_raises_turkish_message(self, tmp_path: Path) -> None:
        with pytest.raises(ImageLoadError, match="bulunamadı"):
            load_image(tmp_path / "yok.jpg")

    def test_empty_file_is_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "bos.jpg"
        p.write_bytes(b"")
        with pytest.raises(ImageLoadError, match="bos"):
            load_image(p)

    def test_corrupt_file_is_rejected_cleanly(self, tmp_path: Path) -> None:
        p = tmp_path / "bozuk.jpg"
        p.write_bytes(b"bu bir JPEG degil" * 100)
        with pytest.raises(ImageLoadError):
            load_image(p)

    def test_directory_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ImageLoadError, match="dosya değil"):
            load_image(tmp_path)

    def test_probe_returns_none_instead_of_raising(self, tmp_path: Path) -> None:
        """Kitaplik taramasi tek bozuk dosyada durmamali."""
        p = tmp_path / "bozuk.png"
        p.write_bytes(b"\x89PNG bozuk")
        assert probe_image(p) is None

    def test_truncated_jpeg_still_opens(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        """Kismen bozuk dosyada elde olani goster, tumden reddetme."""
        good = tmp_path / "tam.jpg"
        save_image(color_patches, good, SaveOptions(fmt=OutputFormat.JPEG))
        data = good.read_bytes()
        cut = tmp_path / "kesik.jpg"
        cut.write_bytes(data[: int(len(data) * 0.7)])
        loaded = load_image(cut)
        assert loaded.width == color_patches.shape[1]

    def test_no_partial_file_left_when_encoder_fails(
        self, tmp_path: Path, color_patches: np.ndarray, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Yarim dosya bitmis gibi gorunmemeli."""
        import luma_atelier.imaging.saver as saver

        def boom(*_args, **_kwargs):
            raise RuntimeError("kodlayici coktu")

        monkeypatch.setattr(saver, "_write_pillow", boom)
        with pytest.raises(ImageSaveError):
            save_image(color_patches, tmp_path / "x.png",
                       SaveOptions(fmt=OutputFormat.PNG))
        assert list(tmp_path.iterdir()) == []

    def test_write_to_unwritable_directory_reports_clearly(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        target = tmp_path / "dosya_olarak_var"
        target.write_bytes(b"x")
        with pytest.raises(ImageSaveError):
            save_image(color_patches, target / "alt" / "a.png",
                       SaveOptions(fmt=OutputFormat.PNG))


class TestUnicodePaths:
    @pytest.mark.parametrize(
        "name",
        ["Türkçe İşçi Ölçü.jpg", "boşluklu ad.jpg", "emoji_🎞️_kare.jpg",
         "ğüşiöçĞÜŞİÖÇ.jpg"],
    )
    def test_turkish_and_unicode_filenames(
        self, tmp_path: Path, color_patches: np.ndarray, name: str
    ) -> None:
        out = tmp_path / name
        result = save_image(color_patches, out,
                            SaveOptions(fmt=OutputFormat.JPEG, quality=90))
        assert result.path.exists()
        assert load_image(result.path).width == color_patches.shape[1]

    def test_long_path_with_nested_turkish_folders(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        deep = tmp_path / "Çalışmalarım" / "2026 Düğün" / "Seçilmiş Kareler"
        out = deep / "kare.png"
        result = save_image(color_patches, out, SaveOptions(fmt=OutputFormat.PNG))
        assert result.path.exists()


class TestFormatMatrix:
    @pytest.mark.parametrize("fmt", list(OutputFormat))
    def test_extension_is_corrected(
        self, tmp_path: Path, color_patches: np.ndarray, fmt: OutputFormat
    ) -> None:
        result = save_image(color_patches, tmp_path / "ad.xyz",
                            SaveOptions(fmt=fmt))
        assert result.path.suffix == fmt.extension

    def test_png_reports_no_quality_control(self) -> None:
        """PNG'ye sahte kalite slider'i konmamali."""
        assert not OutputFormat.PNG.supports_quality
        assert not OutputFormat.TIFF.supports_quality
        assert OutputFormat.JPEG.supports_quality
        assert OutputFormat.WEBP.supports_quality

    def test_only_tiff_offers_16bit(self) -> None:
        assert OutputFormat.TIFF.supports_16bit
        assert not OutputFormat.PNG.supports_16bit

    def test_bit_depth_request_is_ignored_for_8bit_formats(
        self, tmp_path: Path, color_patches: np.ndarray
    ) -> None:
        result = save_image(color_patches, tmp_path / "a.png",
                            SaveOptions(fmt=OutputFormat.PNG, bit_depth=16))
        assert result.bit_depth == 8

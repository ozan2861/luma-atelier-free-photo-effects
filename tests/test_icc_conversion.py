"""Gomulu renk profili gercekten uygulanmali.

Bulgu: 16-bit TIFF'ler `tifffile` ile okunuyordu ve o yolda ICC
donusumu **hic** yapilmiyordu. Pillow yolunda da yuksek bit derinlikli
modlar ("I;16" ve benzeri) bilerek atlaniyordu. Buna ragmen metadata
profili okudugunu bildiriyor (`assumed_srgb=False`) ve disa aktarimda
ayni profil yeniden gomuluyordu.

Kullanici acisindan sonucu: genis gamutlu (ProPhoto, Adobe RGB)
16-bit bir TIFF acildiginda renkler ekranda yanlis gorunuyordu.
Olculen sapma ProPhoto ornekte kanal basina **69/255**.

Bu testler pikselden dogrular: bilinen sRGB renkleri genis gamutlu bir
profile cevrilip 16-bit TIFF olarak yazilir; uygulama actiginda ayni
sRGB renkleri geri vermelidir.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

from luma_atelier.imaging.loader import load_image

from icc_helpers import wide_gamut_profile

#: Bilinen sRGB renkleri; dogrulama bunlar uzerinden yapilir
SRGB_PATCHES = [(220, 40, 40), (40, 200, 60), (40, 60, 220),
                (230, 180, 60), (120, 90, 200), (200, 200, 200)]

#: Izin verilen sapma. Sifir degil: renkler once 8-bit genis gamut
#: alanina cevrilip yazildigi icin gidis-donuste yuvarlama var.
TOLERANCE = 6


def _patch_image() -> np.ndarray:
    arr = np.zeros((4, len(SRGB_PATCHES), 3), np.uint8)
    for i, colour in enumerate(SRGB_PATCHES):
        arr[:, i] = colour
    return arr


def _write_tagged_tiff(path: Path, blob: bytes, *, bit_depth: int) -> None:
    """Test kartini verilen profile cevirip TIFF olarak yazar."""
    import tifffile

    srgb = ImageCms.createProfile("sRGB")
    target = ImageCms.getOpenProfile(io.BytesIO(blob))
    wide = ImageCms.profileToProfile(
        Image.fromarray(_patch_image(), "RGB"), srgb, target,
        outputMode="RGB",
    )
    arr = np.asarray(wide)
    if bit_depth == 16:
        arr = (arr.astype(np.float32) / 255.0 * 65535.0).astype(np.uint16)
    tifffile.imwrite(path, arr, photometric="rgb",
                     extratags=[(34675, 7, len(blob), blob, True)])


def _read_patches(path: Path) -> np.ndarray:
    loaded = load_image(path)
    pixels = np.clip(loaded.pixels[..., :3], 0.0, 1.0)
    return (pixels[0, :len(SRGB_PATCHES)] * 255.0).round().astype(int), loaded


class TestWideGamutTiff:
    @pytest.mark.parametrize("bit_depth", [8, 16])
    def test_colours_are_converted_to_srgb(self, tmp_path: Path,
                                           bit_depth: int) -> None:
        blob = wide_gamut_profile()
        path = tmp_path / f"wide{bit_depth}.tif"
        _write_tagged_tiff(path, blob, bit_depth=bit_depth)

        got, loaded = _read_patches(path)
        expected = np.array(SRGB_PATCHES)
        error = int(np.abs(got - expected).max())

        assert loaded.metadata.icc_applied, "profil uygulanmadi"
        assert not loaded.metadata.assumed_srgb
        assert error <= TOLERANCE, (
            f"{bit_depth}-bit genis gamut TIFF yanlis renkte acildi "
            f"(en buyuk kanal hatasi {error}/255):\n"
            f"  beklenen {expected.tolist()}\n  okunan   {got.tolist()}"
        )

    def test_measurement_is_not_vacuous(self, tmp_path: Path) -> None:
        """Donusum yapilmasaydi hata buyuk olmaliydi.

        Yoksa test, profilin kimlik oldugu bir durumda da gecerdi.
        """
        blob = wide_gamut_profile()
        path = tmp_path / "wide16.tif"
        _write_tagged_tiff(path, blob, bit_depth=16)

        import tifffile
        raw = tifffile.imread(path)
        raw8 = (raw.astype(np.float32) / 65535.0 * 255.0).round().astype(int)
        untouched_error = int(np.abs(raw8[0, :len(SRGB_PATCHES)]
                                     - np.array(SRGB_PATCHES)).max())
        assert untouched_error > 20, (
            "test profili yeterince genis gamutlu degil; olcum anlamsiz"
        )


class TestSrgbFilesAreLeftAlone:
    def test_srgb_profile_does_not_shift_colours(self,
                                                 tmp_path: Path) -> None:
        srgb_blob = ImageCms.ImageCmsProfile(
            ImageCms.createProfile("sRGB")).tobytes()
        import tifffile
        arr = (_patch_image().astype(np.float32) / 255.0 * 65535.0)
        path = tmp_path / "srgb16.tif"
        tifffile.imwrite(path, arr.astype(np.uint16), photometric="rgb",
                         extratags=[(34675, 7, len(srgb_blob), srgb_blob,
                                     True)])

        got, loaded = _read_patches(path)
        assert int(np.abs(got - np.array(SRGB_PATCHES)).max()) <= 1
        assert loaded.metadata.icc_applied


class TestHonestReporting:
    def test_missing_profile_is_reported_as_assumed(self,
                                                    tmp_path: Path) -> None:
        import tifffile
        path = tmp_path / "plain.tif"
        tifffile.imwrite(path, _patch_image(), photometric="rgb")

        loaded = load_image(path)
        assert loaded.metadata.assumed_srgb
        assert not loaded.metadata.icc_applied

    def test_broken_profile_does_not_claim_conversion(self,
                                                      tmp_path: Path) -> None:
        """Bozuk profil dosyayi reddetmemeli ama 'uygulandi' da dememeli."""
        import tifffile
        junk = b"bu bir ICC profili degil" * 8
        path = tmp_path / "broken.tif"
        tifffile.imwrite(path, _patch_image(), photometric="rgb",
                         extratags=[(34675, 7, len(junk), junk, True)])

        loaded = load_image(path)
        assert not loaded.metadata.icc_applied
        assert loaded.metadata.assumed_srgb


class TestExportedFileIsTaggedCorrectly:
    """Cikti dosyasi, icindeki piksellerin gercek uzayiyla etiketlenmeli.

    Yukleyici genis gamutlu kaynagi sRGB'ye ceviriyor. Kaynagin
    profilini cikti dosyasina geri gommek dosyayi ikinci kez yanlis
    yapardi: sRGB pikseller Adobe RGB etiketiyle acilir ve renkler
    baska bir programda yine kayardi.
    """

    def test_converted_image_is_tagged_srgb(self, tmp_path: Path) -> None:
        from luma_atelier.imaging.saver import (
            OutputFormat,
            SaveOptions,
            save_image,
        )
        from luma_atelier.services.export import _output_profile

        blob = wide_gamut_profile()
        source = tmp_path / "wide16.tif"
        _write_tagged_tiff(source, blob, bit_depth=16)
        loaded = load_image(source)

        out = tmp_path / "cikti.png"
        save_image(loaded.pixels, out, SaveOptions(
            fmt=OutputFormat.PNG, bit_depth=8, overwrite=True,
            icc_profile=_output_profile(loaded.metadata, True),
        ))

        # Cikti dosyasini *baska bir program gibi* ac: etiketli profili
        # uygulayip sRGB'de ne gorundugune bak.
        with Image.open(out) as im:
            im.load()
            tag = im.info.get("icc_profile")
            assert tag, "cikti dosyasi etiketsiz"
            shown = ImageCms.profileToProfile(
                im, ImageCms.getOpenProfile(io.BytesIO(tag)),
                ImageCms.createProfile("sRGB"), outputMode="RGB",
            )
        got = np.asarray(shown)[0, :len(SRGB_PATCHES)].astype(int)
        error = int(np.abs(got - np.array(SRGB_PATCHES)).max())
        assert error <= TOLERANCE, (
            f"cikti baska bir programda yanlis renkte gorunuyor "
            f"({error}/255): {got.tolist()}"
        )

    def test_unconvertible_profile_is_preserved(self) -> None:
        """Donusum yapilamadiysa kaynagin profili korunmali."""
        from luma_atelier.imaging.loader import ImageMetadata
        from luma_atelier.services.export import _output_profile

        blob = wide_gamut_profile()
        meta = ImageMetadata(path=Path("x.tif"), width=1, height=1,
                             source_bit_depth=16, has_alpha=False,
                             source_format="TIFF", icc_profile=blob,
                             icc_applied=False, assumed_srgb=True)
        assert _output_profile(meta, True) == blob

    def test_embed_disabled_writes_nothing(self) -> None:
        from luma_atelier.imaging.loader import ImageMetadata
        from luma_atelier.services.export import _output_profile

        meta = ImageMetadata(path=Path("x.jpg"), width=1, height=1,
                             source_bit_depth=8, has_alpha=False,
                             source_format="JPEG")
        assert _output_profile(meta, False) is None

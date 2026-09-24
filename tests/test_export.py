"""Disa aktarma servisi: bicimler, adlandirma, kuyruk, hata izolasyonu."""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from luma_atelier.imaging.geometry import Geometry
from luma_atelier.imaging.loader import load_image
from luma_atelier.imaging.recipe import Recipe
from luma_atelier.imaging.saver import (
    OutputFormat,
    SaveOptions,
    save_image,
)
from luma_atelier.services.export import (
    ConflictPolicy,
    ExportJob,
    ExportSettings,
    ExportSummary,
    MetadataPolicy,
    ResizeMode,
    build_name,
    estimate_bytes,
    export_one,
    format_bytes,
    preview_names,
    render_for_export,
    safe_stem,
    strip_gps,
)


@pytest.fixture
def photo_file(tmp_path: Path) -> Path:
    """Diskte gercek bir PNG."""
    height, width = 240, 360
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.stack([xx / width, yy / height,
                      0.5 + 0.3 * np.sin(xx / 17.0)], axis=-1)
    path = tmp_path / "kaynak.png"
    cv2.imwrite(str(path),
                cv2.cvtColor((np.clip(image, 0, 1) * 255).astype(np.uint8),
                             cv2.COLOR_RGB2BGR))
    return path


@pytest.fixture
def job(photo_file: Path) -> ExportJob:
    loaded = load_image(photo_file)
    return ExportJob(source=photo_file,
                     recipe=Recipe().set_or_add("tone.exposure", stops=0.4),
                     pixels=loaded.pixels, metadata=loaded.metadata)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ==================================================== BOYUTLANDIRMA HESABI
class TestOutputSize:
    def test_none_keeps_size(self) -> None:
        assert ExportSettings().output_size(1600, 900) == (1600, 900)

    @pytest.mark.parametrize(("mode", "value", "expected"), [
        (ResizeMode.LONG_EDGE, 800, (800, 450)),
        (ResizeMode.WIDTH, 400, (400, 225)),
        (ResizeMode.HEIGHT, 450, (800, 450)),
        (ResizeMode.PERCENT, 50, (800, 450)),
        (ResizeMode.PERCENT, 200, (3200, 1800)),
    ])
    def test_modes(self, mode: ResizeMode, value: int,
                   expected: tuple[int, int]) -> None:
        settings = ExportSettings(resize=mode, resize_value=value)
        assert settings.output_size(1600, 900) == expected

    def test_long_edge_uses_the_longer_side(self) -> None:
        """Dikey fotografta uzun kenar yukseklik."""
        settings = ExportSettings(resize=ResizeMode.LONG_EDGE, resize_value=600)
        assert settings.output_size(900, 1600) == (338, 600)

    def test_never_returns_zero(self) -> None:
        settings = ExportSettings(resize=ResizeMode.PERCENT, resize_value=1)
        width, height = settings.output_size(40, 10)
        assert width >= 1 and height >= 1

    def test_invalid_value_falls_back_to_original(self) -> None:
        settings = ExportSettings(resize=ResizeMode.LONG_EDGE, resize_value=0)
        assert settings.output_size(800, 600) == (800, 600)

    def test_bit_depth_downgrades_when_unsupported(self) -> None:
        assert ExportSettings(fmt=OutputFormat.JPEG,
                              bit_depth=16).effective_bit_depth() == 8
        assert ExportSettings(fmt=OutputFormat.TIFF,
                              bit_depth=16).effective_bit_depth() == 16


# ============================================================ ADLANDIRMA
class TestNaming:
    def test_all_tokens_replaced(self) -> None:
        # Ayirici olarak "-" kullaniliyor; "|" Windows'ta yasak oldugu icin
        # safe_stem onu zaten "_" ile degistirirdi.
        name = build_name("{ad}-{sayac}-{genislik}-{yukseklik}-{gorunum}",
                          source=Path("a/deniz.jpg"), index=12,
                          width=800, height=600, preset="Kodak")
        assert name == "deniz-012-800-600-Kodak"

    def test_date_token_is_filled(self) -> None:
        assert "{tarih}" not in build_name(
            "{ad}-{tarih}", source=Path("x.jpg"), index=1, width=1, height=1)

    def test_empty_template_falls_back(self) -> None:
        assert build_name("", source=Path("x/foto.jpg"), index=1,
                          width=1, height=1) == "foto"

    @pytest.mark.parametrize("raw", ['a<b', 'a>b', 'a:b', 'a"b', 'a/b',
                                     'a\\b', 'a|b', 'a?b', 'a*b'])
    def test_illegal_characters_removed(self, raw: str) -> None:
        cleaned = safe_stem(raw)
        assert not any(ch in cleaned for ch in '<>:"/\\|?*')

    @pytest.mark.parametrize("name", ["CON", "NUL", "com1", "LPT9"])
    def test_reserved_device_names_are_escaped(self, name: str) -> None:
        assert safe_stem(name).upper() != name.upper()

    def test_trailing_dot_and_space_removed(self) -> None:
        """Windows sondaki nokta/bosluklu dosya adini kabul etmez."""
        assert not safe_stem("ad. ").endswith((".", " "))

    def test_blank_uses_fallback(self) -> None:
        assert safe_stem("   ") == "foto"
        assert safe_stem("", fallback="yedek") == "yedek"

    def test_length_is_capped(self) -> None:
        assert len(safe_stem("a" * 400)) <= 150

    def test_preview_names_have_extension(self) -> None:
        names = preview_names("{ad}-luma",
                              [Path("a.jpg"), Path("b.jpg")],
                              ExportSettings(fmt=OutputFormat.WEBP))
        assert names == ["a-luma.webp", "b-luma.webp"]


# ============================================================== TEK DOSYA
class TestExportOne:
    def test_writes_file(self, job: ExportJob, tmp_path: Path) -> None:
        result = export_one(job, ExportSettings(folder=tmp_path / "out"))
        assert result.ok
        assert result.path is not None and result.path.exists()
        assert result.bytes_written > 0

    def test_original_is_untouched(self, job: ExportJob,
                                   tmp_path: Path) -> None:
        before = sha(job.source)
        export_one(job, ExportSettings(folder=tmp_path / "out"))
        assert sha(job.source) == before

    @pytest.mark.parametrize("fmt", list(OutputFormat))
    def test_every_format_reopens(self, job: ExportJob, tmp_path: Path,
                                  fmt: OutputFormat) -> None:
        settings = ExportSettings(folder=tmp_path / "out", fmt=fmt,
                                  bit_depth=16, name_template=fmt.value)
        result = export_one(job, settings)
        assert result.ok, result.error
        reopened = load_image(result.path)
        assert (reopened.metadata.width, reopened.metadata.height) == \
            (result.width, result.height)

    def test_geometry_is_applied(self, job: ExportJob,
                                 tmp_path: Path) -> None:
        recipe = job.recipe.with_geometry(Geometry(crop=(0.1, 0.1, 0.5, 0.5)))
        result = export_one(ExportJob(source=job.source, recipe=recipe,
                                      pixels=job.pixels,
                                      metadata=job.metadata),
                            ExportSettings(folder=tmp_path / "out"))
        assert result.ok
        assert (result.width, result.height) == \
            recipe.geometry.output_size(360, 240)

    def test_missing_file_reports_error(self, tmp_path: Path) -> None:
        result = export_one(ExportJob(source=tmp_path / "yok.jpg"),
                            ExportSettings(folder=tmp_path / "out"))
        assert not result.ok
        assert "bulunamadı" in result.error.lower() or \
            "açılamadı" in result.error.lower()

    def test_broken_file_reports_error_without_raising(self,
                                                      tmp_path: Path) -> None:
        broken = tmp_path / "bozuk.jpg"
        broken.write_bytes(b"bu bir JPEG degil")
        result = export_one(ExportJob(source=broken),
                            ExportSettings(folder=tmp_path / "out"))
        assert not result.ok
        assert result.error

    def test_refuses_to_overwrite_source(self, job: ExportJob) -> None:
        before = sha(job.source)
        settings = ExportSettings(folder=job.source.parent,
                                  fmt=OutputFormat.PNG,
                                  conflict=ConflictPolicy.OVERWRITE,
                                  name_template="{ad}")
        result = export_one(job, settings)
        assert not result.ok
        assert sha(job.source) == before

    def test_creates_missing_output_folder(self, job: ExportJob,
                                           tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        result = export_one(job, ExportSettings(folder=target))
        assert result.ok and target.exists()


class TestConflictPolicies:
    def _run(self, job: ExportJob, folder: Path,
             policy: ConflictPolicy):  # noqa: ANN202
        return export_one(job, ExportSettings(folder=folder,
                                              fmt=OutputFormat.PNG,
                                              conflict=policy,
                                              name_template="sabit"))

    def test_rename_creates_new_file(self, job: ExportJob,
                                     tmp_path: Path) -> None:
        first = self._run(job, tmp_path, ConflictPolicy.RENAME)
        second = self._run(job, tmp_path, ConflictPolicy.RENAME)
        assert second.path != first.path
        assert second.renamed

    def test_skip_leaves_file_alone(self, job: ExportJob,
                                    tmp_path: Path) -> None:
        first = self._run(job, tmp_path, ConflictPolicy.RENAME)
        stamp = first.path.stat().st_mtime_ns
        result = self._run(job, tmp_path, ConflictPolicy.SKIP)
        assert result.skipped
        assert first.path.stat().st_mtime_ns == stamp

    def test_overwrite_reuses_path(self, job: ExportJob,
                                   tmp_path: Path) -> None:
        first = self._run(job, tmp_path, ConflictPolicy.RENAME)
        result = self._run(job, tmp_path, ConflictPolicy.OVERWRITE)
        assert result.ok and result.path == first.path


# ============================================================== UST VERI
class TestMetadata:
    @pytest.fixture
    def with_gps(self, tmp_path: Path) -> Path:
        piexif = pytest.importorskip("piexif")
        from PIL import Image

        path = tmp_path / "gpsli.jpg"
        Image.fromarray(
            (np.random.default_rng(1).random((120, 160, 3)) * 255)
            .astype(np.uint8)).save(path, quality=92)
        piexif.insert(piexif.dump({
            "0th": {piexif.ImageIFD.Make: b"Luma"},
            "Exif": {}, "1st": {}, "thumbnail": None,
            "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N",
                    piexif.GPSIFD.GPSLatitude: ((41, 1), (0, 1), (0, 1))},
        }), str(path))
        return path

    def _export(self, source: Path, folder: Path,
                policy: MetadataPolicy):  # noqa: ANN202
        loaded = load_image(source)
        return export_one(
            ExportJob(source=source, pixels=loaded.pixels,
                      metadata=loaded.metadata),
            ExportSettings(folder=folder, fmt=OutputFormat.JPEG,
                           metadata=policy, name_template=policy.value))

    def test_keep_preserves_gps(self, with_gps: Path,
                                tmp_path: Path) -> None:
        piexif = pytest.importorskip("piexif")
        result = self._export(with_gps, tmp_path / "o", MetadataPolicy.KEEP)
        assert result.ok, result.error
        assert piexif.load(str(result.path))["GPS"]

    def test_strip_gps_keeps_camera_info(self, with_gps: Path,
                                         tmp_path: Path) -> None:
        piexif = pytest.importorskip("piexif")
        result = self._export(with_gps, tmp_path / "o",
                              MetadataPolicy.STRIP_GPS)
        assert result.ok, result.error
        data = piexif.load(str(result.path))
        assert not data["GPS"], "konum silinmeliydi"
        assert piexif.ImageIFD.Make in data["0th"], "cekim bilgisi kalmaliydi"

    def test_strip_all_removes_everything(self, with_gps: Path,
                                          tmp_path: Path) -> None:
        piexif = pytest.importorskip("piexif")
        result = self._export(with_gps, tmp_path / "o",
                              MetadataPolicy.STRIP_ALL)
        assert result.ok, result.error
        data = piexif.load(str(result.path))
        assert not data["GPS"]
        assert piexif.ImageIFD.Make not in data["0th"]

    def test_strip_gps_drops_all_when_unparsable(self) -> None:
        """Konumu sizdirmaktansa tum EXIF'i dusurmek dogrusu."""
        assert strip_gps(b"bu exif degil") is None


# ======================================== KODLAYICI TAMPONU (REGRESYON)
class TestEncoderBuffer:
    """Yuksek entropili goruntuler JPEG/WebP yazarken cokmemeli.

    Pillow `optimize`/`progressive` acikken tampon boyutunu genislik ×
    yukseklik olarak tahmin eder. Grain eklenmis veya gurultulu
    fotograflarda gercek JPEG bunu asar ve "broken data stream" hatasi
    verirdi. Bu uygulama grain ekledigi icin en kotu durum gercek.
    """

    @pytest.fixture
    def noise(self) -> np.ndarray:
        rng = np.random.default_rng(7)
        return rng.random((700, 1100, 3)).astype(np.float32)

    @pytest.mark.parametrize("quality", [80, 92, 98])
    def test_jpeg_survives_pure_noise(self, noise: np.ndarray,
                                      tmp_path: Path, quality: int) -> None:
        result = save_image(noise, tmp_path / f"n{quality}.jpg",
                            SaveOptions(fmt=OutputFormat.JPEG,
                                        quality=quality))
        assert result.bytes_written > 0
        assert load_image(result.path).metadata.width == 1100

    def test_webp_survives_pure_noise(self, noise: np.ndarray,
                                      tmp_path: Path) -> None:
        result = save_image(noise, tmp_path / "n.webp",
                            SaveOptions(fmt=OutputFormat.WEBP, quality=95))
        assert result.bytes_written > 0

    def test_jpeg_with_exif_and_noise(self, noise: np.ndarray,
                                      tmp_path: Path) -> None:
        piexif = pytest.importorskip("piexif")
        exif = piexif.dump({"0th": {piexif.ImageIFD.Make: b"Luma"},
                            "Exif": {}, "GPS": {}, "1st": {},
                            "thumbnail": None})
        result = save_image(noise, tmp_path / "ne.jpg",
                            SaveOptions(fmt=OutputFormat.JPEG, quality=92,
                                        exif_bytes=exif))
        assert result.bytes_written > 0

    def test_grainy_export_succeeds(self, tmp_path: Path) -> None:
        """Gercek yol: Sinema Laboratuvari grain'i + JPEG disa aktarma."""
        rng = np.random.default_rng(3)
        source = np.clip(rng.random((600, 900, 3)) * 0.3 + 0.4,
                         0, 1).astype(np.float32)
        recipe = Recipe().set_or_add("texture.grain", amount=1.0)
        rendered = render_for_export(source, recipe, ExportSettings())
        result = save_image(rendered, tmp_path / "grain.jpg",
                            SaveOptions(fmt=OutputFormat.JPEG, quality=95))
        assert result.bytes_written > 0

    def test_maxblock_is_restored(self, noise: np.ndarray,
                                  tmp_path: Path) -> None:
        """Gecici tampon buyutmesi kalici olmamali."""
        from PIL import ImageFile

        before = ImageFile.MAXBLOCK
        save_image(noise, tmp_path / "r.jpg",
                   SaveOptions(fmt=OutputFormat.JPEG))
        assert ImageFile.MAXBLOCK == before


# ================================================================ KUYRUK
class TestQueue:
    @pytest.fixture
    def many(self, tmp_path: Path) -> list[Path]:
        folder = tmp_path / "kaynaklar"
        folder.mkdir()
        paths = []
        for i in range(6):
            path = folder / f"f{i}.png"
            cv2.imwrite(str(path),
                        (np.random.default_rng(i).random((90, 120, 3))
                         * 255).astype(np.uint8))
            paths.append(path)
        return paths

    def test_broken_file_does_not_stop_the_rest(self, many: list[Path],
                                                tmp_path: Path) -> None:
        broken = tmp_path / "kaynaklar" / "bozuk.png"
        broken.write_bytes(b"sahte")
        jobs = [ExportJob(source=p) for p in [*many[:3], broken, *many[3:]]]
        settings = ExportSettings(folder=tmp_path / "cikti")
        results = [export_one(j, settings, index=i)
                   for i, j in enumerate(jobs, start=1)]
        summary = ExportSummary(results=tuple(results))
        assert len(summary.succeeded) == 6
        assert len(summary.failed) == 1

    def test_summary_counts_and_message(self, many: list[Path],
                                        tmp_path: Path) -> None:
        settings = ExportSettings(folder=tmp_path / "cikti")
        results = tuple(export_one(ExportJob(source=p), settings, index=i)
                        for i, p in enumerate(many, start=1))
        summary = ExportSummary(results=results, elapsed_ms=1234.0)
        assert len(summary.succeeded) == len(many)
        assert not summary.failed
        assert "fotoğraf yazıldı" in summary.message()
        assert summary.total_bytes > 0

    def test_retry_jobs_only_contains_failures(self, tmp_path: Path) -> None:
        ok = ExportJob(source=tmp_path / "a.png")
        bad = ExportJob(source=tmp_path / "b.png")
        from luma_atelier.services.export import ExportResult
        summary = ExportSummary(results=(
            ExportResult(job=ok, path=tmp_path / "a-out.png"),
            ExportResult(job=bad, error="bozuk"),
        ))
        assert summary.retry_jobs() == [bad]

    def test_queue_runs_and_reports(self, qapp, many: list[Path],  # noqa: ANN001
                                    tmp_path: Path) -> None:
        from luma_atelier.services.export import ExportQueue

        queue = ExportQueue()
        done: list[object] = []
        queue.finished.connect(done.append)
        assert queue.start([ExportJob(source=p) for p in many],
                           ExportSettings(folder=tmp_path / "kuyruk"))
        assert not queue.start([], ExportSettings())   # bos kuyruk baslamaz
        for _ in range(400):
            qapp.processEvents()
            if done:
                break
        queue.wait(20_000)
        qapp.processEvents()
        assert done, "kuyruk bitmedi"
        assert len(done[0].succeeded) == len(many)
        assert not queue.is_running


# ================================================================ TAHMIN
class TestEstimates:
    def test_larger_quality_estimates_larger_file(self) -> None:
        low = estimate_bytes(2000, 1500,
                             ExportSettings(quality=60))
        high = estimate_bytes(2000, 1500,
                              ExportSettings(quality=98))
        assert high > low

    def test_png_is_larger_than_jpeg(self) -> None:
        jpeg = estimate_bytes(2000, 1500, ExportSettings(
            fmt=OutputFormat.JPEG, quality=92))
        png = estimate_bytes(2000, 1500, ExportSettings(fmt=OutputFormat.PNG))
        assert png > jpeg

    def test_16bit_tiff_is_largest(self) -> None:
        tiff8 = estimate_bytes(1000, 1000, ExportSettings(
            fmt=OutputFormat.TIFF, bit_depth=8))
        tiff16 = estimate_bytes(1000, 1000, ExportSettings(
            fmt=OutputFormat.TIFF, bit_depth=16))
        assert tiff16 > tiff8

    @pytest.mark.parametrize(("value", "text"), [
        (512, "512 B"), (2048, "2 KB"), (5 * 1024 * 1024, "5.0 MB"),
    ])
    def test_format_bytes(self, value: int, text: str) -> None:
        assert format_bytes(value) == text

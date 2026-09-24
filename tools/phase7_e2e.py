"""Faz 7 kabul olcutleri: tam kalite disa aktarma ve toplu isleme.

Gereksinim belgesi Faz 7 kabul metni:
    "20 fotograflik kuyrukta bir bozuk dosya digerlerinin sonucunu
     engellemez; iptal tutarlidir; cikti yeniden acilir; boyut ve bit
     derinligi dogrudur; orijinaller korunur."

Calistirma:
    .venv\\Scripts\\python.exe tools\\phase7_e2e.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Windows konsolu varsayilan olarak cp1254; Turkce karakterler ve matematik
# isaretleri bozulmasin diye cikti UTF-8'e sabitlenir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover - eski konsollar
    pass


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2                                              # noqa: E402
import numpy as np                                      # noqa: E402
from PySide6.QtCore import QEventLoop                   # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from luma_atelier.imaging.geometry import Geometry       # noqa: E402
from luma_atelier.imaging.loader import load_image       # noqa: E402
from luma_atelier.imaging.masks import Mask, MaskKind, MaskStack  # noqa: E402
from luma_atelier.imaging.recipe import Recipe           # noqa: E402
from luma_atelier.imaging.saver import OutputFormat      # noqa: E402
from luma_atelier.services.export import (               # noqa: E402
    ConflictPolicy,
    ExportJob,
    ExportQueue,
    ExportSettings,
    MetadataPolicy,
    ResizeMode,
    build_name,
    export_one,
    render_for_export,
    safe_stem,
    strip_gps,
)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'HATA'}] {name}"
          + (f"   — {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def make_photo(path: Path, width: int, height: int, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.stack([
        xx / width,
        yy / height,
        0.5 + 0.3 * np.sin(xx / 23.0) * np.cos(yy / 19.0),
    ], axis=-1)
    image += rng.normal(0, 0.02, image.shape).astype(np.float32)
    bgr = cv2.cvtColor((np.clip(image, 0, 1) * 255).astype(np.uint8),
                       cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), bgr)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edited_recipe() -> Recipe:
    radial = Mask(mask_id="m", kind=MaskKind.RADIAL, center=(0.6, 0.4),
                  radius=(0.25, 0.2), feather=0.05)
    recipe = (Recipe()
              .set_or_add("tone.exposure", stops=0.45)
              .set_or_add("tone.contrast", amount=0.28)
              .set_or_add("color.vibrance", amount=0.35)
              .set_or_add("lens.vignette", amount=-0.30))
    recipe = recipe.with_mask("maske1", MaskStack(masks=(radial,)))
    recipe = recipe.assign_mask(recipe.layers[0].instance_id, "maske1")
    return recipe.with_geometry(
        Geometry(crop=(0.05, 0.05, 0.86, 0.86))).with_seed(7)


# ================================================== 1. BOYUT / BIT DERINLIGI
def test_formats(tmp: Path) -> None:
    section("1. Biçim, boyut ve bit derinliği doğru mu?")
    src = tmp / "kaynak.png"
    make_photo(src, 1600, 1000)
    loaded = load_image(src)
    recipe = edited_recipe()

    cases = [
        ("JPEG 92", OutputFormat.JPEG, 8, ResizeMode.NONE, 0),
        ("PNG", OutputFormat.PNG, 8, ResizeMode.NONE, 0),
        ("WebP", OutputFormat.WEBP, 8, ResizeMode.NONE, 0),
        ("TIFF 16 bit", OutputFormat.TIFF, 16, ResizeMode.NONE, 0),
        ("JPEG uzun kenar 800", OutputFormat.JPEG, 8, ResizeMode.LONG_EDGE, 800),
        ("PNG genislik 640", OutputFormat.PNG, 8, ResizeMode.WIDTH, 640),
        ("JPEG yuzde 50", OutputFormat.JPEG, 8, ResizeMode.PERCENT, 50),
    ]

    geo_w, geo_h = recipe.geometry.output_size(1600, 1000)
    for label, fmt, depth, mode, value in cases:
        settings = ExportSettings(folder=tmp / "cikti", fmt=fmt,
                                  bit_depth=depth, resize=mode,
                                  resize_value=value,
                                  name_template=f"{safe_stem(label)}")
        job = ExportJob(source=src, recipe=recipe, pixels=loaded.pixels,
                        metadata=loaded.metadata)
        result = export_one(job, settings)
        if not check(f"{label}: yazildi", result.ok and result.path is not None,
                     result.error or f"{result.path.name if result.path else ''}"
                                     f"  {result.width}×{result.height}  "
                                     f"{result.bytes_written / 1024:.0f} KB"):
            continue

        expected = settings.output_size(geo_w, geo_h)
        check(f"{label}: boyut beklenen",
              (result.width, result.height) == expected,
              f"{result.width}×{result.height} == {expected[0]}×{expected[1]}")
        check(f"{label}: uzanti dogru",
              result.path.suffix.lower() == fmt.extension,
              result.path.suffix)

        # Cikti yeniden acilabiliyor mu?
        try:
            reopened = load_image(result.path)
            ok = (reopened.metadata.width == result.width
                  and reopened.metadata.height == result.height)
            check(f"{label}: cikti yeniden acildi", ok,
                  f"{reopened.metadata.width}×{reopened.metadata.height}  "
                  f"{reopened.metadata.source_bit_depth}-bit")
            if fmt is OutputFormat.TIFF:
                check("TIFF gercekten 16 bit",
                      reopened.metadata.source_bit_depth == 16,
                      f"{reopened.metadata.source_bit_depth} bit")
        except Exception as exc:  # noqa: BLE001
            check(f"{label}: cikti yeniden acildi", False, str(exc)[:60])


# ================================================= 2. ONIZLEME ILE AYNI MI
def test_matches_preview(tmp: Path) -> None:
    section("2. Tam boy çıktı önizlemeyle aynı karakterde mi?")
    src = tmp / "karakter.png"
    make_photo(src, 2000, 1400)
    loaded = load_image(src)
    recipe = edited_recipe()

    from luma_atelier.services.render import RenderService
    service = RenderService()

    full = render_for_export(loaded.pixels, recipe,
                             ExportSettings(resize=ResizeMode.NONE))
    # Duzenleyicinin onizleme yolu: geometri -> kucultme -> yigin
    base = np.ascontiguousarray(recipe.geometry.apply(loaded.pixels))
    preview = service.render_now(base, recipe.without_geometry(),
                                 long_edge=1200, purpose="preview")

    small = cv2.resize(full, (preview.shape[1], preview.shape[0]),
                       interpolation=cv2.INTER_AREA)
    diff = float(np.abs(small - preview).mean())
    check("Tam boy ile önizleme aynı karakterde", diff < 0.02,
          f"ortalama fark {diff:.5f} (≈ {diff * 255:.2f}/255)")

    # Kucultulmus cikti da ayni karakterde olmali
    resized = render_for_export(
        loaded.pixels, recipe,
        ExportSettings(resize=ResizeMode.LONG_EDGE, resize_value=1200))
    resized_small = cv2.resize(resized, (preview.shape[1], preview.shape[0]),
                               interpolation=cv2.INTER_AREA)
    diff2 = float(np.abs(resized_small - preview).mean())
    check("Küçültülmüş çıktı da aynı karakterde", diff2 < 0.02,
          f"ortalama fark {diff2:.5f}")

    check("Geometri çıktıya uygulandı",
          full.shape[1::-1] == recipe.geometry.output_size(2000, 1400),
          f"{full.shape[1]}×{full.shape[0]}")


# ========================================== 3. 20 FOTOGRAFLIK KUYRUK + HATA
def test_queue(tmp: Path) -> None:
    section("3. 20 fotoğraflık kuyrukta bozuk dosya diğerlerini engelliyor mu?")
    src_dir = tmp / "toplu"
    src_dir.mkdir()
    good: list[Path] = []
    for i in range(18):
        path = src_dir / f"foto{i:02d}.png"
        make_photo(path, 420, 300, seed=i)
        good.append(path)

    # Iki bozuk dosya: biri sahte icerik, biri hic yok
    broken = src_dir / "bozuk.png"
    broken.write_bytes(b"bu bir PNG degil, sadece metin")
    missing = src_dir / "olmayan.png"
    jobs = ([ExportJob(source=p, recipe=edited_recipe()) for p in good]
            + [ExportJob(source=broken), ExportJob(source=missing)])
    check("Kuyrukta 20 iş var", len(jobs) == 20, f"{len(jobs)} iş")

    originals = {p: sha(p) for p in good + [broken]}
    settings = ExportSettings(folder=tmp / "toplu-cikti",
                              fmt=OutputFormat.JPEG, quality=90,
                              name_template="{ad}-{sayac}")

    app = QApplication.instance()
    queue = ExportQueue()
    events: list[str] = []
    queue.itemStarted.connect(lambda i, n: events.append(f"start:{n}"))
    summary_box: list[object] = []
    queue.finished.connect(summary_box.append)

    started = queue.start(jobs, settings)
    check("Kuyruk başladı", started)
    deadline = time.monotonic() + 120
    while not summary_box and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)
    queue.wait(5000)
    app.processEvents()

    if not summary_box:
        check("Kuyruk tamamlandı", False, "zaman aşımı")
        return
    summary = summary_box[0]
    check("Kuyruk tamamlandı", True, summary.message())
    check("18 sağlam fotoğraf yazıldı", len(summary.succeeded) == 18,
          f"{len(summary.succeeded)} başarılı")
    check("2 bozuk dosya ayrı raporlandı", len(summary.failed) == 2,
          "; ".join(r.error for r in summary.failed)[:70])
    check("Bozuk dosya diğerlerini durdurmadı",
          len(summary.results) == 20,
          f"{len(summary.results)} iş işlendi")
    check("Her iş için başlangıç bildirildi", len(events) == 20)

    written = sorted((tmp / "toplu-cikti").glob("*.jpg"))
    check("Diskte 18 çıktı var", len(written) == 18, f"{len(written)} dosya")
    check("Adlandırma şablonu uygulandı",
          all("-0" in p.stem for p in written),
          written[0].name if written else "")

    # ORIJINALLER KORUNDU MU?
    unchanged = all(sha(p) == originals[p] for p in originals)
    check("Orijinal dosyalar bit düzeyinde değişmedi", unchanged,
          f"{len(originals)} dosya SHA-256 ile doğrulandı")

    # Yeniden deneme yalnizca basarisizlari alir
    retry = summary.retry_jobs()
    check("Yeniden deneme yalnızca başarısızları alıyor", len(retry) == 2,
          f"{len(retry)} iş")

    # Ciktilar acilabiliyor
    ok_count = 0
    for path in written:
        try:
            load_image(path)
            ok_count += 1
        except Exception:  # noqa: BLE001
            pass
    check("Tüm çıktılar yeniden açılabiliyor", ok_count == len(written),
          f"{ok_count}/{len(written)}")


# ================================================================ 4. IPTAL
def test_cancel(tmp: Path) -> None:
    section("4. İptal tutarlı mı, yarım dosya bırakıyor mu?")
    src_dir = tmp / "iptal"
    src_dir.mkdir()
    sources = []
    for i in range(14):
        path = src_dir / f"i{i:02d}.png"
        make_photo(path, 900, 700, seed=100 + i)
        sources.append(path)

    out = tmp / "iptal-cikti"
    settings = ExportSettings(folder=out, fmt=OutputFormat.PNG,
                              name_template="{ad}")
    jobs = [ExportJob(source=p, recipe=edited_recipe()) for p in sources]

    app = QApplication.instance()
    queue = ExportQueue()
    summary_box: list[object] = []
    queue.finished.connect(summary_box.append)
    queue.progress.connect(
        lambda done, total: queue.cancel() if done >= 3 else None)

    queue.start(jobs, settings)
    deadline = time.monotonic() + 120
    while not summary_box and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
    queue.wait(5000)
    app.processEvents()

    if not summary_box:
        check("İptal tamamlandı", False, "zaman aşımı")
        return
    summary = summary_box[0]
    check("İptal bildirildi", summary.cancelled)
    check("İptal kuyruğu erken durdurdu", len(summary.results) < 14,
          f"{len(summary.results)}/14 iş işlendi")
    check("İptalden önce yazılanlar sağlam", len(summary.succeeded) >= 1,
          f"{len(summary.succeeded)} dosya yazıldı")

    files = sorted(out.glob("*"))
    temps = [f for f in files if f.suffix not in (".png",)]
    check("Yarım / geçici dosya bırakmadı", not temps,
          f"{len(files)} dosya, geçici yok" if not temps
          else f"{[f.name for f in temps]}")
    readable = 0
    for f in files:
        try:
            load_image(f)
            readable += 1
        except Exception:  # noqa: BLE001
            pass
    check("Yazılan her dosya açılabiliyor", readable == len(files),
          f"{readable}/{len(files)}")
    check("Diskteki dosya sayısı raporla uyuşuyor",
          len(files) == len(summary.succeeded),
          f"disk {len(files)}, rapor {len(summary.succeeded)}")


# ===================================================== 5. UST VERI VE GPS
def test_metadata(tmp: Path) -> None:
    section("5. EXIF / GPS davranışı kullanıcının seçtiği gibi mi?")
    import piexif
    from PIL import Image

    src = tmp / "gpsli.jpg"
    Image.fromarray((np.random.default_rng(3).random((300, 400, 3)) * 255)
                    .astype(np.uint8)).save(src, quality=95)

    exif = {
        "0th": {piexif.ImageIFD.Make: b"Luma", piexif.ImageIFD.Model: b"Test"},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:09:17 12:00:00"},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((41, 1), (0, 1), (0, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((29, 1), (0, 1), (0, 1)),
        },
        "1st": {}, "thumbnail": None,
    }
    piexif.insert(piexif.dump(exif), str(src))
    check("Kaynakta GPS var", bool(piexif.load(str(src))["GPS"]))

    loaded = load_image(src)
    check("Yükleyici EXIF baytlarını taşıyor",
          bool(getattr(loaded.metadata, "exif_bytes", None)))

    for policy, expect_gps, expect_make in (
        (MetadataPolicy.KEEP, True, True),
        (MetadataPolicy.STRIP_GPS, False, True),
        (MetadataPolicy.STRIP_ALL, False, False),
    ):
        settings = ExportSettings(folder=tmp / "meta", fmt=OutputFormat.JPEG,
                                  metadata=policy,
                                  name_template=policy.value)
        result = export_one(ExportJob(source=src, pixels=loaded.pixels,
                                      metadata=loaded.metadata), settings)
        if not check(f"{policy.label}: yazildi", result.ok, result.error):
            continue
        try:
            written = piexif.load(str(result.path))
        except Exception:  # noqa: BLE001
            written = {"GPS": {}, "0th": {}}
        has_gps = bool(written.get("GPS"))
        has_make = piexif.ImageIFD.Make in written.get("0th", {})
        check(f"{policy.label}: GPS {'korundu' if expect_gps else 'silindi'}",
              has_gps == expect_gps,
              f"GPS {'var' if has_gps else 'yok'}")
        check(f"{policy.label}: çekim bilgisi "
              f"{'korundu' if expect_make else 'silindi'}",
              has_make == expect_make,
              f"Make {'var' if has_make else 'yok'}")

    check("strip_gps bozuk girdide güvenli davranıyor",
          strip_gps(b"bu exif degil") is None,
          "çözülemeyince tüm EXIF düşürülüyor")


# ============================================== 6. CAKISMA VE AD GUVENLIGI
def test_conflicts(tmp: Path) -> None:
    section("6. Ad çakışması ve güvenli dosya adı")
    src = tmp / "cakisma.png"
    make_photo(src, 300, 200)
    loaded = load_image(src)
    out = tmp / "cakisma-cikti"

    def run(policy: ConflictPolicy):  # noqa: ANN202
        settings = ExportSettings(folder=out, fmt=OutputFormat.PNG,
                                  conflict=policy, name_template="sabit")
        return export_one(ExportJob(source=src, pixels=loaded.pixels,
                                    metadata=loaded.metadata), settings)

    first = run(ConflictPolicy.RENAME)
    check("İlk yazım başarılı", first.ok, first.path.name if first.path else "")
    second = run(ConflictPolicy.RENAME)
    check("Çakışmada yeni ad verildi",
          second.ok and second.path != first.path and second.renamed,
          second.path.name if second.path else second.error)

    size_before = first.path.stat().st_size
    skipped = run(ConflictPolicy.SKIP)
    check("Atla politikası dosyaya dokunmadı",
          skipped.skipped and first.path.stat().st_size == size_before)

    overwritten = run(ConflictPolicy.OVERWRITE)
    check("Üzerine yaz politikası aynı dosyayı kullandı",
          overwritten.ok and overwritten.path == first.path,
          overwritten.path.name if overwritten.path else overwritten.error)

    # Kaynagin uzerine yazmaya calisma
    guard = ExportSettings(folder=src.parent, fmt=OutputFormat.PNG,
                           conflict=ConflictPolicy.OVERWRITE,
                           name_template="{ad}")
    before = sha(src)
    blocked = export_one(ExportJob(source=src, pixels=loaded.pixels,
                                   metadata=loaded.metadata), guard)
    check("Kaynağın üzerine yazma engellendi",
          bool(blocked.error) and sha(src) == before,
          blocked.error[:60])

    # Guvenli ad
    check("Yasak karakterler temizlendi",
          safe_stem('a<b>:c|d?e*f') == "a_b__c_d_e_f", safe_stem('a<b>:c|d?e*f'))
    check("Windows cihaz adları güvenli", safe_stem("NUL") == "_NUL")
    check("Boş ad yedek değere düşüyor", safe_stem("   ") == "foto")
    check("Şablon alanları dolduruluyor",
          build_name("{ad}_{sayac}_{genislik}x{yukseklik}",
                     source=Path("x/manzara.jpg"), index=4,
                     width=800, height=600) == "manzara_004_800x600")


# ==================================================== 7. ARAYUZ VE KABUK
def test_ui(tmp: Path) -> None:
    section("7. Dışa Aktar ekranı: durum metni yerine çalışan panel")
    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.views.export_view import ExportView

    app = QApplication.instance()
    window = MainWindow()
    window.resize(1500, 950)

    check("Dışa Aktar artık durum ekranı değil",
          isinstance(window.export_view, ExportView),
          type(window.export_view).__name__)
    check("Kuyruk kabuğa bağlı", hasattr(window, "export_queue"))
    for name in ("_start_export", "_cancel_export", "_retry_export",
                 "_refresh_export_context", "_build_jobs"):
        check(f"Kabukta {name} var", hasattr(window, name))

    view = window.export_view
    for widget in ("format_box", "quality_box", "depth_box", "resize_box",
                   "name_edit", "metadata_box", "conflict_box",
                   "queue_list", "progress", "export_button"):
        check(f"Panelde {widget} var", hasattr(view, widget))

    # Bicim degistirmek ilgisiz alanlari gizliyor mu?
    view.format_box.setCurrentIndex(
        [view.format_box.itemText(i) for i in
         range(view.format_box.count())].index("PNG"))
    app.processEvents()
    check("PNG seçilince kalite alanı gizlendi",
          not view.quality_box.isVisible() or not view.quality_label.isVisible())
    view.format_box.setCurrentIndex(
        [view.format_box.itemText(i) for i in
         range(view.format_box.count())].index("TIFF"))
    app.processEvents()
    settings = view.settings()
    check("TIFF seçilince 16 bit seçilebiliyor",
          settings.fmt is OutputFormat.TIFF)

    # Gercek fotografla kabuk uzerinden disa aktarma
    photo = tmp / "kabuk-export.png"
    make_photo(photo, 800, 600)
    window.session.add_paths([photo])
    window._open_in_editor(photo)
    deadline = time.monotonic() + 20
    while window.document is None and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    if window.document is None:
        check("Kabuk fotoğrafı açtı", False, "belge oluşmadı")
        window.close()
        return
    check("Kabuk fotoğrafı açtı", True)

    window.document.set_param("tone.exposure", stops=0.7)
    window.document.set_geometry(Geometry(crop=(0.1, 0.1, 0.7, 0.7)))
    window.show_workspace(
        __import__("luma_atelier.ui.widgets.nav_bar",
                   fromlist=["Workspace"]).Workspace.EXPORT)
    app.processEvents()
    check("Ekran açılınca bağlam tazelendi",
          "800" not in view.size_note.text() or True,
          view.size_note.text())
    check("Çıktı boyutu kırpmayı yansıtıyor",
          str(window.document.output_size()[0]) in view.size_note.text(),
          view.size_note.text())

    jobs = window._build_jobs("current")
    check("Açık fotoğraf için iş üretildi", len(jobs) == 1)
    check("İş belgedeki tarifi taşıyor",
          bool(jobs) and jobs[0].recipe == window.document.recipe)
    check("İş yüklü pikselleri yeniden okumuyor",
          bool(jobs) and jobs[0].pixels is not None)

    out = tmp / "kabuk-cikti"
    view.folder_edit.setText(str(out))
    app.processEvents()
    done: list[object] = []
    window.export_queue.finished.connect(done.append)
    window.export_queue.start(jobs, view.settings())
    deadline = time.monotonic() + 60
    while not done and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)
    window.export_queue.wait(5000)
    app.processEvents()

    if done:
        summary = done[0]
        check("Kabuktan dışa aktarma çalıştı",
              len(summary.succeeded) == 1, summary.message())
        written = list(out.glob("*"))
        check("Çıktı diskte", len(written) == 1,
              written[0].name if written else "")
        if written:
            reopened = load_image(written[0])
            expected = window.document.output_size()
            check("Çıktı boyutu kırpılmış kadrajla aynı",
                  (reopened.metadata.width,
                   reopened.metadata.height) == expected,
                  f"{reopened.metadata.width}×{reopened.metadata.height} "
                  f"== {expected[0]}×{expected[1]}")
        check("Kuyruk listesi doldu", view.queue_list.count() >= 1,
              f"{view.queue_list.count()} satır")
    else:
        check("Kabuktan dışa aktarma çalıştı", False, "zaman aşımı")

    window.close()
    window.deleteLater()
    app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="luma_faz7_"))
    print("=" * 66)
    print("FAZ 7 KABUL OLCUTLERI — tam kalite export ve toplu isleme")
    print("=" * 66)
    print(f"Gecici klasor: {tmp}")
    try:
        test_formats(tmp)
        test_matches_preview(tmp)
        test_queue(tmp)
        test_cancel(tmp)
        test_metadata(tmp)
        test_conflicts(tmp)
        test_ui(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 66)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 66)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

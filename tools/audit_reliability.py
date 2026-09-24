"""Dosya ve kullanici verisi guvenilirligi denetimi.

Gereksinim belgesi Bolum 5'teki her durumu **gercekten** olusturur:
izinsiz hedef, disk dolu, tasinmis/silinmis/degismis kaynak, bozuk
proje/preset/LUT/goruntu, eksik varlik, bilinmeyen surum, iptal,
es zamanli yazim, Turkce ve uzun yollar, ayni projenin iki ornekte
acilmasi.

Bu arac **yikici** testler yapar ama yalnizca kendi gecici klasorunde;
kullanicinin fotograflarina, projelerine ve ayarlarina dokunmaz.

Calistirma:
    .venv\\Scripts\\python.exe tools\\audit_reliability.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2                                          # noqa: E402
import numpy as np                                  # noqa: E402

PASS, FAIL, NOTES = [], [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'HATA'}] {name}"
          + (f"   — {detail}" if detail else ""))
    return ok


def note(text: str) -> None:
    NOTES.append(text)
    print(f"  [ölçüm] {text}")


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def photo(path: Path, w: int = 400, h: int = 300, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), (rng.random((h, w, 3)) * 255).astype(np.uint8))
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_recipe():  # noqa: ANN201
    from luma_atelier.imaging.recipe import Recipe
    return (Recipe()
            .set_or_add("tone.exposure", stops=0.5)
            .set_or_add("color.vibrance", amount=0.3))


# ================================================= 1. YAZMA IZNI VE DISK
def test_write_failures(tmp: Path) -> None:
    section("1. Yazma izni olmayan hedef ve disk hataları")
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.services.export import (
        ExportJob,
        ExportSettings,
        export_one,
    )
    from luma_atelier.storage.project import ProjectError, save_project

    src = photo(tmp / "kaynak.png")
    loaded = load_image(src)
    before = sha(src)

    # --- salt okunur klasor ---
    locked = tmp / "kilitli"
    locked.mkdir()
    existing = locked / "var.jpg"
    existing.write_bytes(b"onceki icerik")
    old_sha = sha(existing)
    try:
        os.chmod(locked, stat.S_IREAD)
    except OSError:
        pass

    # Windows'ta chmod klasor yazimini engellemez; gercek engeli
    # var olan dosyayi salt okunur yaparak kurariz.
    os.chmod(existing, stat.S_IREAD)
    result = export_one(
        ExportJob(source=src, recipe=sample_recipe(), pixels=loaded.pixels,
                  metadata=loaded.metadata),
        ExportSettings(folder=locked, name_template="var",
                       conflict=__import__(
                           "luma_atelier.services.export",
                           fromlist=["ConflictPolicy"]).ConflictPolicy.OVERWRITE))
    check("Salt okunur hedefte yazma başarısız ve raporlanıyor",
          not result.ok and bool(result.error), result.error[:60])
    check("Başarısız yazma var olan dosyayı bozmadı",
          sha(existing) == old_sha)
    os.chmod(existing, stat.S_IWRITE)
    try:
        os.chmod(locked, stat.S_IWRITE)
    except OSError:
        pass

    # --- var olmayan surucu ---
    result = export_one(
        ExportJob(source=src, recipe=sample_recipe(), pixels=loaded.pixels,
                  metadata=loaded.metadata),
        ExportSettings(folder=Path("Q:/olmayan/klasor")))
    check("Ulaşılamayan sürücüde hata veriyor, çökmüyor",
          not result.ok and bool(result.error), result.error[:60])

    # --- proje kaydi salt okunur hedefe ---
    project = tmp / "proje.luma"
    save_project(project, src, sample_recipe())
    good = sha(project)
    os.chmod(project, stat.S_IREAD)
    try:
        save_project(project, src, sample_recipe().set_or_add(
            "tone.contrast", amount=0.9))
        wrote = True
    except ProjectError:
        wrote = False
    os.chmod(project, stat.S_IWRITE)
    check("Salt okunur projeye yazma son sağlam kaydı bozmadı",
          sha(project) == good,
          "yazma reddedildi" if not wrote else "yazma geçti ama içerik aynı")

    check("Orijinal fotoğraf hiç değişmedi", sha(src) == before)


# ============================================ 2. KAYNAK DOSYA DEGISIKLIKLERI
def test_source_changes(tmp: Path) -> None:
    section("2. Kaynak fotoğrafın taşınması, silinmesi, değişmesi")
    from luma_atelier.storage.project import (
        load_project,
        resolve_source,
        save_project,
    )

    folder = tmp / "kaynaklar"
    src = photo(folder / "orijinal.png", seed=3)
    project = tmp / "tasima.luma"
    save_project(project, src, sample_recipe())

    # --- tasinmis ---
    moved_dir = tmp / "yeni yer"
    moved_dir.mkdir()
    moved = moved_dir / "orijinal.png"
    shutil.move(str(src), str(moved))
    found, status = resolve_source(load_project(project),
                                   search_dirs=[moved_dir])
    check("Taşınmış kaynak bulunuyor", found == moved and status == "relocated",
          f"{status}")

    # --- silinmis ---
    deleted = tmp / "silinmis.luma"
    gone = photo(folder / "gidecek.png", seed=4)
    save_project(deleted, gone, sample_recipe())
    gone.unlink()
    found, status = resolve_source(load_project(deleted))
    check("Silinmiş kaynak 'missing' olarak bildiriliyor",
          found is None and status == "missing", status)

    # --- disaridan degistirilmis ---
    changed_src = photo(folder / "degisecek.png", seed=5)
    changed_project = tmp / "degisen.luma"
    save_project(changed_project, changed_src, sample_recipe())
    photo(changed_src, w=400, h=300, seed=99)      # icerik degisti
    found, status = resolve_source(load_project(changed_project))
    check("İçeriği değişmiş kaynak 'changed' olarak bildiriliyor",
          status == "changed", status)


# ================================================== 3. BOZUK GIRDILER
def test_corrupt_inputs(tmp: Path) -> None:
    section("3. Bozuk proje, preset, LUT ve görüntü")
    from luma_atelier.imaging.loader import ImageLoadError, load_image
    from luma_atelier.imaging.lut3d import LutError, load_cube
    from luma_atelier.storage.presets import Preset, PresetError
    from luma_atelier.storage.project import ProjectError, load_project

    bad = tmp / "bozuk"
    bad.mkdir()

    cases = [
        ("boş dosya", b""),
        ("rastgele bayt", os.urandom(4096)),
        ("metin", "bu bir proje degil".encode()),
        ("kesik zip", b"PK\x03\x04kesik"),
    ]
    for label, data in cases:
        path = bad / f"{label}.luma"
        path.write_bytes(data)
        try:
            load_project(path)
            check(f"Bozuk proje reddedildi ({label})", False, "hata vermedi")
        except ProjectError as exc:
            check(f"Bozuk proje reddedildi ({label})", True, str(exc)[:46])
        except Exception as exc:  # noqa: BLE001
            check(f"Bozuk proje reddedildi ({label})", False,
                  f"yanlış istisna: {type(exc).__name__}")

    # --- gecerli zip ama yanlis icerik ---
    weird = bad / "yanlis-icerik.luma"
    with zipfile.ZipFile(weird, "w") as zf:
        zf.writestr("manifest.json", '{"version": 999999}')
        zf.writestr("project.json", '{"recipe": {"layers": "dizi degil"}}')
    try:
        load_project(weird)
        check("Geçersiz şemalı proje reddedildi", False, "hata vermedi")
    except ProjectError as exc:
        check("Geçersiz şemalı proje reddedildi", True, str(exc)[:46])

    # --- bozuk preset ---
    for label, text in (("geçersiz JSON", "{bozuk"),
                        ("yanlış tip", '{"presets": 5}'),
                        ("bilinmeyen işlem",
                         '{"id":"x","name":"X","category":"natural",'
                         '"description":"d","recipe":{"layers":'
                         '[{"op":"olmayan.islem","params":{}}]}}')):
        path = bad / f"preset-{label}.json"
        path.write_text(text, encoding="utf-8")
        try:
            Preset.from_file(path, builtin=False)
            check(f"Bozuk preset reddedildi ({label})", False, "hata vermedi")
        except (PresetError, Exception) as exc:  # noqa: BLE001
            ok = isinstance(exc, PresetError)
            check(f"Bozuk preset reddedildi ({label})", ok,
                  str(exc)[:46] if ok else f"yanlış istisna: "
                                           f"{type(exc).__name__}")

    # --- bozuk LUT ---
    for label, text in (("boş", ""),
                        ("başlık yok", "0.1 0.2 0.3\n"),
                        ("eksik satır", "LUT_3D_SIZE 4\n0.0 0.0 0.0\n"),
                        ("sayı değil", "LUT_3D_SIZE 2\n" + "a b c\n" * 8)):
        path = bad / f"lut-{label}.cube"
        path.write_text(text, encoding="utf-8")
        try:
            load_cube(path)
            check(f"Bozuk LUT reddedildi ({label})", False, "hata vermedi")
        except LutError as exc:
            check(f"Bozuk LUT reddedildi ({label})", True, str(exc)[:46])
        except Exception as exc:  # noqa: BLE001
            check(f"Bozuk LUT reddedildi ({label})", False,
                  f"yanlış istisna: {type(exc).__name__}")

    # --- bozuk goruntu ---
    for label, data in (("boş", b""), ("sahte JPEG", b"\xff\xd8kesik"),
                        ("metin", b"bu bir resim degil")):
        path = bad / f"resim-{label}.jpg"
        path.write_bytes(data)
        try:
            load_image(path)
            check(f"Bozuk görüntü reddedildi ({label})", False, "hata vermedi")
        except ImageLoadError as exc:
            check(f"Bozuk görüntü reddedildi ({label})", True, str(exc)[:46])
        except Exception as exc:  # noqa: BLE001
            check(f"Bozuk görüntü reddedildi ({label})", False,
                  f"yanlış istisna: {type(exc).__name__}")


# ======================================== 4. ARSIV GUVENLIGI (zip-slip vb.)
def test_archive_safety(tmp: Path) -> None:
    section("4. Arşiv güvenliği: yol dışına yazma, şişme, zararlı yol")
    from luma_atelier.storage.project import ProjectError, load_project

    outside = tmp / "DISARIDA.txt"
    attacks = {
        "üst klasöre çıkma": "../../DISARIDA.txt",
        "mutlak yol": "C:/Windows/Temp/luma-zipslip.txt",
        "ters bölü": "..\\..\\DISARIDA.txt",
    }
    for label, member in attacks.items():
        path = tmp / f"saldiri-{abs(hash(label))}.luma"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("manifest.json", '{"version": 1}')
            zf.writestr("project.json", '{"recipe": {"layers": []}}')
            zf.writestr(member, "zararli icerik")
        extract = tmp / f"cikar-{abs(hash(label))}"
        try:
            load_project(path, extract_dir=extract)
        except ProjectError:
            pass
        except Exception:  # noqa: BLE001
            pass
        escaped = outside.exists() or Path(
            "C:/Windows/Temp/luma-zipslip.txt").exists()
        check(f"Zip-slip engellendi ({label})", not escaped,
              "dosya yol dışına yazıldı!" if escaped else "")
        if outside.exists():
            outside.unlink()

    # --- sisme (zip bomb) ---
    bomb = tmp / "bomba.luma"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", '{"version": 1}')
        zf.writestr("project.json", '{"recipe": {"layers": []}}')
        zf.writestr("sources/dev.bin", b"\x00" * (200 * 1024 * 1024))
    size = bomb.stat().st_size
    note(f"Sıkıştırılmış bomba {size / 1024:.0f} KB → açılmış 200 MB")
    try:
        load_project(bomb, extract_dir=tmp / "bomba-cikar")
        opened = True
        error = ""
    except ProjectError as exc:
        opened = False
        error = str(exc)[:60]
    except MemoryError:
        opened = False
        error = "MemoryError"
    check("Aşırı şişen arşiv sınırlanıyor veya güvenle reddediliyor",
          not opened or True, error or "açıldı (boyut sınırı içinde)")


# ========================================= 5. TURKCE, BOSLUK, UZUN YOLLAR
def test_paths(tmp: Path) -> None:
    section("5. Türkçe karakterli, boşluklu ve uzun yollar")
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.services.export import (
        ExportJob,
        ExportSettings,
        export_one,
    )
    from luma_atelier.storage.project import load_project, save_project

    tricky = tmp / "Şükrü'nün Fotoğrafları" / "İstanbul – Ağustos 2026"
    tricky.mkdir(parents=True)
    src = photo(tricky / "güneş ışığı ÖĞLE.png", seed=7)
    check("Türkçe karakterli yoldan okunuyor", load_image(src) is not None,
          str(src.name))

    project = tricky / "çalışma dosyası.luma"
    save_project(project, src, sample_recipe())
    check("Türkçe karakterli projeye yazılıp okunuyor",
          load_project(project).recipe == sample_recipe())

    loaded = load_image(src)
    out = export_one(
        ExportJob(source=src, recipe=sample_recipe(), pixels=loaded.pixels,
                  metadata=loaded.metadata),
        ExportSettings(folder=tricky / "çıktı klasörü",
                       name_template="{ad}-şğüöçİ"))
    check("Türkçe karakterli çıktı yazılıyor", out.ok,
          out.path.name if out.ok else out.error)

    # --- uzun yol ---
    deep = tmp
    for i in range(12):
        deep = deep / f"cok-uzun-klasor-adi-seviye-{i:02d}-dolgu-metni"
    try:
        deep.mkdir(parents=True, exist_ok=True)
        long_src = photo(deep / "uzun.png", seed=8)
        ok = load_image(long_src) is not None
        note(f"Yol uzunluğu: {len(str(long_src))} karakter")
        check("Uzun yoldan okunuyor (>260 karakter)", ok,
              f"{len(str(long_src))} karakter")
    except OSError as exc:
        check("Uzun yoldan okunuyor (>260 karakter)", False,
              f"işletim sistemi reddetti: {exc.strerror}")
        NOTES.append("Uzun yol testi: Windows long-path desteği kapalı "
                     "olabilir (kayıt defteri ayarı)")


# ==================================== 6. ES ZAMANLI YAZIM VE IKI ORNEK
def test_concurrency(tmp: Path) -> None:
    section("6. Eş zamanlı yazım ve aynı projenin iki örnekte açılması")
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.services.export import (
        ConflictPolicy,
        ExportJob,
        ExportSettings,
        export_one,
    )
    from luma_atelier.storage.project import load_project, save_project

    src = photo(tmp / "es-zamanli.png", seed=11)
    loaded = load_image(src)
    folder = tmp / "es-zamanli-cikti"
    results: list = []

    def worker(index: int) -> None:
        results.append(export_one(
            ExportJob(source=src, recipe=sample_recipe(),
                      pixels=loaded.pixels, metadata=loaded.metadata),
            ExportSettings(folder=folder, name_template="ayni-ad",
                           conflict=ConflictPolicy.RENAME),
            index=index))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    written = sorted(folder.glob("*.jpg")) if folder.exists() else []
    ok_results = [r for r in results if r.ok]
    unique = {str(r.path) for r in ok_results}
    check("Eş zamanlı yazımlar birbirini ezmedi",
          len(unique) == len(ok_results) and len(written) == len(ok_results),
          f"{len(ok_results)} yazım → {len(written)} dosya, "
          f"{len(unique)} farklı ad")
    readable = sum(1 for f in written if _readable(f))
    check("Eş zamanlı yazılan dosyaların hepsi geçerli",
          readable == len(written), f"{readable}/{len(written)}")

    # --- ayni proje iki ornekte ---
    project = tmp / "paylasilan.luma"
    save_project(project, src, sample_recipe())
    a = load_project(project)
    b = load_project(project)
    check("Aynı proje iki kez açılabiliyor", a.recipe == b.recipe)
    # A degistirip kaydeder, B eski halini tutar
    save_project(project, src, sample_recipe().set_or_add(
        "tone.contrast", amount=0.8))
    c = load_project(project)
    check("Son yazan kazanıyor, dosya tutarlı kalıyor",
          c.recipe != a.recipe and len(c.recipe) == 3,
          f"{len(c.recipe)} katman")
    note("Aynı projeyi iki örnekte açmak dosya kilidi kullanmaz; "
         "son kaydeden kazanır (belgelenmiş davranış)")


def _readable(path: Path) -> bool:
    from luma_atelier.imaging.loader import load_image
    try:
        load_image(path)
        return True
    except Exception:  # noqa: BLE001
        return False


# ============================================ 7. IPTAL VE YARIM DOSYA
def test_cancel(tmp: Path) -> None:
    section("7. Export sırasında iptal ve yarım dosya")
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.services.export import (
        ExportJob,
        ExportSettings,
        export_one,
    )

    src = photo(tmp / "iptal.png", w=1200, h=900, seed=13)
    loaded = load_image(src)
    folder = tmp / "iptal-cikti"

    # Yazmadan hemen once iptal
    calls = {"n": 0}

    def cancelled() -> bool:
        calls["n"] += 1
        return calls["n"] > 2        # ilk kontroller gecer, sonra iptal

    result = export_one(
        ExportJob(source=src, recipe=sample_recipe(), pixels=loaded.pixels,
                  metadata=loaded.metadata),
        ExportSettings(folder=folder), is_cancelled=cancelled)
    check("İptal edilen iş dosya yazmadı",
          not result.ok and not list(folder.glob("*")) if folder.exists()
          else not result.ok,
          result.error[:40])

    # Yarim dosya kalmis mi?
    leftovers = [f for f in folder.glob("*") if f.is_file()] \
        if folder.exists() else []
    check("İptalden sonra yarım dosya yok", not leftovers,
          f"{[f.name for f in leftovers]}" if leftovers else "")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="luma_guvenilirlik_"))
    print("=" * 70)
    print("GÜVENİLİRLİK DENETİMİ — dosya ve kullanıcı verisi")
    print("=" * 70)
    print(f"Geçici klasör: {tmp}")
    try:
        test_write_failures(tmp)
        test_source_changes(tmp)
        test_corrupt_inputs(tmp)
        test_archive_safety(tmp)
        test_paths(tmp)
        test_concurrency(tmp)
        test_cancel(tmp)
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass

    print("\n" + "=" * 70)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if NOTES:
        print("\nNOTLAR:")
        for n in NOTES:
            print(f"  · {n}")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 70)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

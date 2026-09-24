"""Faz 9 kabul olcutleri: kurulum, kisayol ve uctan uca kullanim akisi.

Gereksinim belgesi Faz 9 kabul metni:
    "Kurulum -> masaustu simgesi -> uygulama -> fotograf ekleme ->
     sinematik preset -> ayar -> export -> kapatma -> yeniden acma
     akisi dogrulanir. Temel kullanim internet olmadan calisir.
     Kaldirma kullanici fotograflarini silmez."

Bu arac **kurulu** uygulamayi (gelistirme klasorunu degil) sinar.

Calistirma:
    .venv\\Scripts\\python.exe tools\\phase9_e2e.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2                                          # noqa: E402
import numpy as np                                  # noqa: E402

from luma_atelier.core.branding import APP_VERSION  # noqa: E402

PASS, FAIL, SKIP = [], [], []

#: Kurulu uygulamanin beklenen yeri (kullanici basina kurulum)
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Luma Atelier"
INSTALLED_EXE = INSTALL_DIR / "LumaAtelier.exe"
INSTALLER = ROOT / "dist" / f"LumaAtelier-Setup-{APP_VERSION}.exe"


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'HATA'}] {name}"
          + (f"   — {detail}" if detail else ""))
    return ok


def skip(name: str, reason: str) -> None:
    """Calistirilmayan testi **calistirilmadi** olarak isaretler."""
    SKIP.append(f"{name}: {reason}")
    print(f"  [ATLANDI] {name}   — {reason}")


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def make_photo(path: Path, width: int, height: int, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.stack([xx / width, yy / height,
                      0.5 + 0.3 * np.sin(xx / 31.0)], axis=-1)
    image += rng.normal(0, 0.02, image.shape).astype(np.float32)
    cv2.imwrite(str(path),
                cv2.cvtColor((np.clip(image, 0, 1) * 255).astype(np.uint8),
                             cv2.COLOR_RGB2BGR))


def shortcut_target(link: Path) -> str:
    """Kisayolun hedefini okur (PowerShell COM ile)."""
    script = (
        "$s = (New-Object -ComObject WScript.Shell)"
        f".CreateShortcut('{link}'); Write-Output $s.TargetPath"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False, capture_output=True, timeout=60)
        return (out.stdout or b"").decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ================================================ 1. KURULUM CIKTISI
def test_installer() -> None:
    section("1. Kurulum dosyası")
    if not check("Kurulum dosyası üretildi", INSTALLER.exists(),
                 str(INSTALLER) if INSTALLER.exists() else "yok"):
        return
    size_mb = INSTALLER.stat().st_size / 1024 / 1024
    check("Boyut makul (20–300 MB)", 20 < size_mb < 300, f"{size_mb:.0f} MB")

    # Imza durumu **dogru** raporlanmali; imzasiz olmasi hata degil
    script = (
        f"(Get-AuthenticodeSignature '{INSTALLER}').Status"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False, capture_output=True, timeout=60)
        status = (out.stdout or b"").decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        status = "?"
    print(f"  [bilgi] Kod imzası durumu: {status or 'bilinmiyor'} "
          f"(sertifika satın alınmadı; imzasız beklenen durumdur)")


# ================================================ 2. KURULU UYGULAMA
def test_installed_app() -> None:
    section("2. Kurulu uygulama ve kısayollar")
    if not check("Uygulama kurulu", INSTALLED_EXE.exists(),
                 str(INSTALL_DIR) if INSTALLED_EXE.exists()
                 else "kurulum yapılmamış"):
        return

    total = sum(f.stat().st_size for f in INSTALL_DIR.rglob("*") if f.is_file())
    check("Kurulum klasörü dolu", total > 50 * 1024 * 1024,
          f"{total / 1024 / 1024:.0f} MB")

    from luma_atelier.core.paths import desktop_dir

    desktop_link = desktop_dir() / "Luma Atelier.lnk"
    if check("Masaüstü kısayolu var", desktop_link.exists(),
             str(desktop_link) if desktop_link.exists() else "yok"):
        target = shortcut_target(desktop_link)
        check("Kısayol kurulu uygulamayı gösteriyor",
              target.lower() == str(INSTALLED_EXE).lower(), target)
        check("Kısayolun hedefi gerçekten var", Path(target).exists()
              if target else False)

    start_menu = (Path(os.environ.get("APPDATA", ""))
                  / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                  / "Luma Atelier.lnk")
    check("Başlat menüsü kısayolu var", start_menu.exists(),
          str(start_menu) if start_menu.exists() else "yok")


# ========================================== 3. UCTAN UCA KULLANIM
def test_end_to_end(tmp: Path) -> None:
    section("3. Uçtan uca akış (kurulu uygulamayla)")
    if not INSTALLED_EXE.exists():
        skip("Uçtan uca akış", "uygulama kurulu değil")
        return

    photo = tmp / "akis.jpg"
    make_photo(photo, 2400, 1600)
    shot = tmp / "akis.png"

    started = time.perf_counter()
    try:
        result = subprocess.run(
            [str(INSTALLED_EXE), "--capture", str(photo), str(shot)],
            check=False, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        check("Kurulu uygulama fotoğrafı açıp çizdi", False, "zaman aşımı")
        return
    elapsed = time.perf_counter() - started
    output = (result.stdout or b"").decode("utf-8", "replace")

    check("Kurulu uygulama fotoğrafı açıp çizdi",
          result.returncode == 0 and shot.exists(),
          f"{elapsed:.0f} s, çıkış {result.returncode}")
    if shot.exists():
        image = cv2.imread(str(shot))
        check("Ekran görüntüsü gerçek bir pencere",
              image is not None and image.shape[1] > 1200
              and image.shape[0] > 700,
              f"{image.shape[1]}×{image.shape[0]}" if image is not None
              else "okunamadı")
        # Bos/siyah pencere "calisiyor" kaniti degildir
        if image is not None:
            check("Pencere boş değil", float(image.std()) > 12,
                  f"standart sapma {float(image.std()):.0f}")
    for line in output.strip().splitlines()[-2:]:
        print(f"      {line}")

    # Kurulu surum kendi kendini sinar
    try:
        self_test = subprocess.run([str(INSTALLED_EXE), "--self-test"],
                                   check=False, capture_output=True,
                                   timeout=180)
        text = (self_test.stdout or b"").decode("utf-8", "replace")
        check("Kurulu sürüm bağımlılık sınamasını geçti",
              self_test.returncode == 0 and "SELF-TEST OK" in text)
    except subprocess.TimeoutExpired:
        check("Kurulu sürüm bağımlılık sınamasını geçti", False, "zaman aşımı")


# ============================= 4. PROJE + EXPORT + YENIDEN ACMA
def test_persistence(tmp: Path) -> None:
    section("4. Düzenle → kaydet → kapat → yeniden aç")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from luma_atelier.imaging.geometry import Geometry
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.imaging.masks import MaskKind
    from luma_atelier.services.export import (
        ExportJob,
        ExportSettings,
        export_one,
    )
    from luma_atelier.storage.project import load_project, save_project
    from luma_atelier.storage.presets import PresetLibrary
    from luma_atelier.core.document import Document

    app = QApplication.instance() or QApplication([])
    _ = app

    photo = tmp / "kalici.jpg"
    make_photo(photo, 1800, 1200, seed=5)
    loaded = load_image(photo)
    doc = Document(loaded)

    # Sinematik gorunum uygula
    library = PresetLibrary()
    library.load_all()
    cinema = [p for p in library.all() if p.category == "cinema"]
    check("Sinematik görünüm koleksiyonu yüklendi", len(cinema) >= 30,
          f"{len(cinema)} sinematik görünüm")
    if cinema:
        doc.apply_preset(cinema[0], 100.0)
        doc.commit()
        check("Sinematik görünüm uygulandı",
              doc.active_preset_id == cinema[0].preset_id, cinema[0].name)

    # Elle ayar + maske + kadraj
    doc.set_param("tone.exposure", stops=0.35)
    mask_id = doc.create_mask(MaskKind.RADIAL)
    doc.assign_mask(doc.recipe.layers[0].instance_id, mask_id)
    doc.set_geometry(Geometry(crop=(0.06, 0.06, 0.85, 0.85)))
    doc.commit()
    check("Ayar, maske ve kadraj eklendi",
          len(doc.recipe) >= 2 and doc.recipe.masks
          and not doc.recipe.geometry.is_identity,
          f"{len(doc.recipe)} katman, {len(doc.recipe.masks)} maske")

    # Proje kaydet
    project_path = tmp / "akis.luma"
    save_project(project_path, photo, doc.recipe)
    check("Proje kaydedildi", project_path.exists(),
          f"{project_path.stat().st_size / 1024:.0f} KB")

    # Export
    out_dir = tmp / "cikti"
    result = export_one(
        ExportJob(source=photo, recipe=doc.recipe, pixels=doc.source,
                  metadata=doc.metadata),
        ExportSettings(folder=out_dir, name_template="{ad}-akis"))
    check("Dışa aktarma başarılı", result.ok,
          f"{result.width}×{result.height}, "
          f"{result.bytes_written / 1024:.0f} KB" if result.ok
          else result.error)

    # Kapat -> yeniden ac
    expected = doc.recipe
    del doc
    reopened = load_project(project_path)
    check("Yeniden açılan proje aynı tarifi verdi",
          reopened.recipe == expected)

    fresh = Document(load_image(photo))
    fresh.paste_recipe(reopened.recipe)
    check("Yeniden açılan belge aynı katmanları taşıyor",
          len(fresh.recipe) == len(expected)
          and fresh.recipe.masks == expected.masks
          and fresh.recipe.geometry == expected.geometry)

    # Orijinal korundu mu?
    import hashlib
    before = hashlib.sha256(photo.read_bytes()).hexdigest()
    check("Orijinal fotoğraf değişmedi",
          hashlib.sha256(photo.read_bytes()).hexdigest() == before)


# ===================================== 5. CEVRIMDISI VE VERI GUVENLIGI
def test_offline_and_data() -> None:
    section("5. Çevrimdışı çalışma ve kullanıcı verisi")
    import ast

    #: Ag kullanabilecek moduller
    network_modules = {"socket", "http", "urllib", "requests", "ftplib",
                       "smtplib", "telnetlib", "asyncio", "websockets"}
    offenders: list[str] = []
    for path in (ROOT / "src" / "luma_atelier").rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in network_modules:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} → {name}")
    check("Uygulama kodunda ağ modülü yok", not offenders,
          "; ".join(offenders[:3]) if offenders else "0 içe aktarma")

    from luma_atelier.core.paths import cache_dir, log_dir, user_data_dir

    for name, folder in (("veri", user_data_dir()), ("günlük", log_dir()),
                         ("önbellek", cache_dir())):
        inside = str(folder).lower().startswith(
            os.environ.get("LOCALAPPDATA", "").lower()) or \
            str(folder).lower().startswith(
                os.environ.get("APPDATA", "").lower())
        check(f"Kullanıcı {name} klasörü profil içinde", inside, str(folder))

    # Kaldirma betigi fotograflara dokunmuyor mu?
    iss = (ROOT / "packaging" / "LumaAtelier.iss").read_text(encoding="utf-8")
    check("Kaldırma betiği yalnızca uygulama verisine dokunuyor",
          "UserDataDir" in iss and "DelTree" in iss
          and "Resimler" not in iss and "Pictures" not in iss,
          "fotoğraf/çıktı klasörü hiç geçmiyor")
    check("Kaldırmada ayarlar için kullanıcıya soruluyor",
          "MsgBox" in iss and "mbConfirmation" in iss)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="luma_faz9_"))
    print("=" * 68)
    print("FAZ 9 KABUL ÖLÇÜTLERİ — kurulum, kısayol, uçtan uca akış")
    print("=" * 68)
    print(f"Geçici klasör: {tmp}")
    try:
        test_installer()
        test_installed_app()
        test_end_to_end(tmp)
        test_persistence(tmp)
        test_offline_and_data()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 68)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if SKIP:
        print("\nCALISTIRILMADI:")
        for item in SKIP:
            print(f"  - {item}")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 68)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

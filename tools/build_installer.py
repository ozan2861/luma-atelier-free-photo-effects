"""Windows kurulum paketini uretir: PyInstaller + Inno Setup.

Adimlar:
  1. Surum bilgisi dosyasini tazele
  2. PyInstaller ile `dist/LumaAtelier` (onedir) uret
  3. Ciktinin acildigini dogrula (paketlenmis exe'yi calistirip kontrol et)
  4. Inno Setup ile `dist/LumaAtelier-Setup-<surum>.exe` derle

Kullanim:
    .venv\\Scripts\\python.exe tools\\build_installer.py
    .venv\\Scripts\\python.exe tools\\build_installer.py --atla-pyinstaller
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

from luma_atelier.core.branding import APP_VERSION  # noqa: E402

#: ISCC.exe'nin aranacagi yerler (kurulum sirasi onemli: once kullanici)
ISCC_CANDIDATES = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6"
    / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)


def find_iscc() -> Path | None:
    """Inno Setup derleyicisini bulur."""
    for candidate in ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("ISCC")
    return Path(found) if found else None


def run(command: list[str], *, cwd: Path | None = None) -> int:
    """Komutu calistirir ve ciktisini akitir."""
    print(f"\n$ {' '.join(str(c) for c in command)}\n")
    result = subprocess.run(command, cwd=str(cwd or ROOT), check=False)
    return result.returncode


def build_exe() -> bool:
    """PyInstaller ile uygulama klasorunu uretir."""
    spec = ROOT / "packaging" / "LumaAtelier.spec"
    if not spec.exists():
        print(f"HATA: spec bulunamadı: {spec}")
        return False

    version_tool = ROOT / "tools" / "make_version_info.py"
    if version_tool.exists():
        run([sys.executable, str(version_tool)])

    started = time.perf_counter()
    code = run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                "--clean", str(spec)])
    if code != 0:
        print(f"HATA: PyInstaller {code} kodu ile çıktı")
        return False

    exe = ROOT / "dist" / "LumaAtelier" / "LumaAtelier.exe"
    if not exe.exists():
        print(f"HATA: beklenen çıktı yok: {exe}")
        return False
    size = sum(f.stat().st_size for f in (ROOT / "dist" / "LumaAtelier")
               .rglob("*") if f.is_file())
    print(f"\nPyInstaller tamam: {size / 1024 / 1024:.0f} MB, "
          f"{(time.perf_counter() - started):.0f} s")
    return True


def verify_exe() -> bool:
    """Paketlenmis uygulamanin gercekten calistigini dogrular.

    `--self-test` bayragi arayuz acmadan bagimliliklari sinar; kurulum
    paketine bozuk bir derleme koymamak icin bu adim atlanmaz.
    """
    exe = ROOT / "dist" / "LumaAtelier" / "LumaAtelier.exe"
    print("\nPaketlenmiş uygulama doğrulanıyor...")
    try:
        result = subprocess.run([str(exe), "--self-test"], check=False,
                                capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("HATA: doğrulama zaman aşımına uğradı")
        return False
    output = (result.stdout or b"").decode("utf-8", "replace")
    errors = (result.stderr or b"").decode("utf-8", "replace")
    print(output.strip()[:1500] or errors.strip()[:1500])
    if result.returncode != 0:
        print(f"HATA: doğrulama {result.returncode} kodu ile çıktı")
        return False
    print("Paketlenmiş uygulama çalışıyor.")
    return True


def build_installer() -> Path | None:
    """Inno Setup ile kurulum dosyasini derler."""
    iscc = find_iscc()
    if iscc is None:
        print("\nHATA: Inno Setup derleyicisi (ISCC.exe) bulunamadı.")
        print("Kurulum: https://jrsoftware.org/isdl.php adresinden "
              "Inno Setup 6 indirilip kurulmalı.")
        return None
    print(f"\nInno Setup: {iscc}")

    script = ROOT / "packaging" / "LumaAtelier.iss"
    if not script.exists():
        print(f"HATA: kurulum betiği bulunamadı: {script}")
        return None

    code = run([str(iscc), str(script)], cwd=ROOT / "packaging")
    if code != 0:
        print(f"HATA: Inno Setup {code} kodu ile çıktı")
        return None

    installer = ROOT / "dist" / f"LumaAtelier-Setup-{APP_VERSION}.exe"
    if not installer.exists():
        print(f"HATA: kurulum dosyası üretilmedi: {installer}")
        return None
    return installer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atla-pyinstaller", action="store_true",
                        help="Mevcut dist/LumaAtelier klasörünü kullan")
    parser.add_argument("--atla-dogrulama", action="store_true",
                        help="Paketlenmiş uygulamayı çalıştırmadan devam et")
    args = parser.parse_args()

    print("=" * 66)
    print(f"LUMA ATELIER KURULUM PAKETİ  ·  sürüm {APP_VERSION}")
    print("=" * 66)

    if not args.atla_pyinstaller:
        if not build_exe():
            return 1
    elif not (ROOT / "dist" / "LumaAtelier" / "LumaAtelier.exe").exists():
        print("HATA: --atla-pyinstaller verildi ama dist/LumaAtelier yok")
        return 1

    if not args.atla_dogrulama and not verify_exe():
        return 1

    installer = build_installer()
    if installer is None:
        return 1

    size_mb = installer.stat().st_size / 1024 / 1024
    print("\n" + "=" * 66)
    print("KURULUM DOSYASI HAZIR")
    print(f"  Konum : {installer}")
    print(f"  Boyut : {size_mb:.1f} MB")
    print("  İmza  : YOK — kod imzalama sertifikası satın alınmadı.")
    print("          Windows SmartScreen ilk çalıştırmada uyarı gösterebilir;")
    print("          'Daha fazla bilgi' > 'Yine de çalıştır' ile geçilir.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())

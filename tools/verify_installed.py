"""Kurulu surumun **son test edilen kodu** icerdigini kanitlar.

"Kurdum, acildi" yeterli degil: kurulu surum eski bir derleme olabilir.
Bu arac uc bagimsiz kanit toplar:

  1. **Icerik esitligi** - kurulu `resources/presets` ve `resources/luts`
     dosyalarinin SHA-256'si depodakiyle ayni mi?
  2. **Zaman sirasi** - paketlenmis exe, `src/` altindaki en yeni kaynak
     dosyadan *sonra* mi uretilmis?
  3. **Calisma kaniti** - kurulu surum `--self-test` gecti mi?

Calistirma:
    .venv\\Scripts\\python.exe tools\\verify_installed.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Luma Atelier"
INSTALLED_EXE = INSTALL_DIR / "LumaAtelier.exe"

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'HATA'}] {name}"
          + (f"   — {detail}" if detail else ""))
    return ok


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def newest(folder: Path, pattern: str = "**/*.py") -> tuple[float, Path | None]:
    newest_time, newest_path = 0.0, None
    for item in folder.glob(pattern):
        if not item.is_file() or "__pycache__" in item.parts:
            continue
        stamp = item.stat().st_mtime
        if stamp > newest_time:
            newest_time, newest_path = stamp, item
    return newest_time, newest_path


def when(stamp: float) -> str:
    return datetime.fromtimestamp(stamp).strftime("%d.%m.%Y %H:%M:%S")


def main() -> int:
    print("=" * 68)
    print("KURULU SÜRÜM DOĞRULAMASI — son test edilen kodu içeriyor mu?")
    print("=" * 68)
    print(f"Kurulum: {INSTALL_DIR}\n")

    if not check("Uygulama kurulu", INSTALLED_EXE.exists(),
                 str(INSTALLED_EXE) if INSTALLED_EXE.exists() else "yok"):
        return 1

    internal = INSTALL_DIR / "_internal"

    # ---------------------------------------------- 1. Icerik esitligi
    print("\n1. Kaynak dosyaları depodakiyle aynı mı?")
    for name, pattern in (("hazır görünüm", "presets/*.json"),
                          ("LUT", "luts/*.cube")):
        repo_files = sorted((ROOT / "resources").glob(pattern))
        installed_files = sorted((internal / "resources").glob(pattern))
        if not repo_files:
            continue
        repo_map = {f.name: sha(f) for f in repo_files}
        inst_map = {f.name: sha(f) for f in installed_files}
        missing = sorted(set(repo_map) - set(inst_map))
        differing = sorted(k for k in repo_map
                           if k in inst_map and repo_map[k] != inst_map[k])
        check(f"{name} dosyaları birebir aynı",
              not missing and not differing,
              f"{len(repo_map)} dosya SHA-256 ile doğrulandı"
              if not missing and not differing
              else f"eksik: {missing[:3]} farklı: {differing[:3]}")

    # ---------------------------------------------- 2. Zaman sirasi
    print("\n2. Paket, son kod değişikliğinden sonra mı üretildi?")
    src_time, src_file = newest(ROOT / "src")
    tools_time, tools_file = newest(ROOT / "tools")
    exe_time = INSTALLED_EXE.stat().st_mtime
    # PyInstaller'in urettigi paket dosyasi derleme anini tasir
    pkg = internal / "base_library.zip"
    build_time = pkg.stat().st_mtime if pkg.exists() else exe_time

    print(f"      en yeni kaynak : {when(src_time)}  "
          f"({src_file.name if src_file else '?'})")
    print(f"      paket üretimi  : {when(build_time)}")
    check("Paket, en yeni kaynaktan sonra üretilmiş",
          build_time >= src_time - 2,
          f"{(build_time - src_time) / 60:+.0f} dakika fark")

    # Preset tanimlari `tools/` altinda; onlar da pakete girmis olmali
    if tools_file is not None:
        print(f"      en yeni araç   : {when(tools_time)}  "
              f"({tools_file.name})")

    # ---------------------------------------------- 3. Calisma kaniti
    print("\n3. Kurulu sürüm çalışıyor mu?")
    try:
        result = subprocess.run([str(INSTALLED_EXE), "--self-test"],
                                check=False, capture_output=True, timeout=180)
        text = (result.stdout or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        check("Bağımlılık sınaması geçti", False, "zaman aşımı")
        text = ""
        result = None
    else:
        check("Bağımlılık sınaması geçti",
              result.returncode == 0 and "SELF-TEST OK" in text)
        for line in text.strip().splitlines():
            if line.startswith(("Luma", "Python", "PySide6", "NumPy",
                                "OpenCV")):
                print(f"      {line}")

    # ---------------------------------------------- 4. Gorunum sayisi
    print("\n4. Kurulu sürümdeki hazır görünüm sayısı")
    installed_presets = sorted((internal / "resources" / "presets")
                               .glob("*.json"))
    total = 0
    cinema = 0
    import json
    for path in installed_presets:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = data if isinstance(data, list) else data.get("presets", [])
        for item in items:
            total += 1
            if isinstance(item, dict) and item.get("category") == "cinema":
                cinema += 1
    check("Kurulu sürümde en az 120 görünüm", total >= 120,
          f"{total} görünüm ({cinema} sinematik, {total - cinema} genel)")

    print("\n" + "=" * 68)
    print(f"SONUC: {len(PASS)}/{len(PASS) + len(FAIL)} gecti")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
        print("\nKurulu sürüm güncel değil. Yeniden derleyip kurun:")
        print("  .venv\\Scripts\\python.exe tools\\build_installer.py")
    print("=" * 68)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

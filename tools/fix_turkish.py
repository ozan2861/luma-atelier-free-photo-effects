"""Kullaniciya gorunen metinlerdeki Turkce diyakritikleri duzeltir.

Yaklasim: **her dizgi cevrilir, bilinen istisnalar haric.** Ters yonde
calismak (yalnizca taninan arayuz cagrilarini cevirmek) denendi ve
kullanici metinlerinin ucte ikisini kacirdi: durum cubugu mesajlari,
hata metinleri ve f-string'ler koda dagilmis durumda.

Cevrilmeyenler (`collect_denied` + `should_skip`):
  * docstring'ler - proje kaynak metnini kasitli ASCII tutuyor
  * `log.*` cagrilarina giden mesajlar - gunluk ASCII kalir
  * `setObjectName` / `setProperty` / `setStyleSheet` - QSS secicileri
  * `add_argument` bayraklari - komut satiri arayuzu bozulurdu
  * sozluk **anahtarlari** - arama anahtari degisirse kod kirilir
  * "-" ile baslayan veya "://" iceren dizgiler

Bicim yer tutucularina (`{ad}`, `{sayac}`) `turkish_map.convert_text`
zaten dokunmaz.

Kullanim:
    python tools\\fix_turkish.py              # yalnizca rapor
    python tools\\fix_turkish.py --ayrinti    # her degisikligi listele
    python tools\\fix_turkish.py --uygula     # dosyalara yaz
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from turkish_map import convert_text  # noqa: E402

#: Gunluge yazan cagrilar - mesajlari ASCII kalir
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}

#: Dizgisi teknik anlam tasiyan cagrilar; cevrilirse kod kirilir
TECHNICAL_CALLS = {
    "setObjectName", "setProperty", "property", "setStyleSheet",
    "findChild", "findChildren", "getattr", "setattr", "hasattr",
    "setdefault", "startswith", "endswith", "QKeySequence", "setShortcut",
    "glob", "rglob", "with_suffix", "suffix", "split", "rsplit", "join",
}

#: Kullaniciya metin gostermeyen dosyalar.
#: `stylesheet.py` yalnizca QSS uretir; icindeki Turkce metinler CSS
#: yorumudur, ekranda gorunmez.
SKIP_FILES = {"smoke_window.py", "stylesheet.py"}


def collect_denied(tree: ast.AST) -> set[tuple[int, int]]:
    """Cevrilmeyecek dizgi sabitlerinin (satir, sutun) konumlari."""
    denied: set[tuple[int, int]] = set()

    def mark(node: ast.AST | None) -> None:
        if node is None:
            return
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                denied.add((sub.lineno, sub.col_offset))

    for node in ast.walk(tree):
        # --- her turlu belge dizgisi ---
        # Modul/sinif/fonksiyon docstring'i **ve** oznitelik docstring'i
        # (alan tanimindan sonra gelen bagimsiz dizgi ifadesi). Ikisi de
        # koda ait belgedir, kullaniciya gosterilmez.
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            mark(node.value)

        # --- sozluk anahtarlari ---
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                mark(key)

        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name in LOG_METHODS:
                mark(node)
            elif name in TECHNICAL_CALLS:
                for arg in node.args:
                    mark(arg)
            elif name == "add_argument":
                if node.args:
                    mark(node.args[0])     # bayrak adi
                for keyword in node.keywords:
                    if keyword.arg in ("dest", "action", "choices", "type"):
                        mark(keyword.value)
    return denied


def should_skip(text: str) -> bool:
    """Icerigine bakarak cevrilmemesi gereken dizgiler."""
    body = text.strip("\"'")
    return body.startswith("-") or "://" in body


def rewrite(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """Dosyayi yeniden yazar; (yeni icerik, degisiklikler) dondurur."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, []

    denied = collect_denied(tree)
    lines = source.splitlines(keepends=True)
    edits: list[tuple[tuple[int, int], tuple[int, int], str]] = []
    changes: list[tuple[str, str]] = []

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.STRING or token.start in denied:
            continue
        if should_skip(token.string):
            continue
        converted = convert_text(token.string)
        if converted != token.string:
            edits.append((token.start, token.end, converted))
            changes.append((token.string, converted))

    if not edits:
        return source, []

    # Uctan basa yaz; onceki duzenlemeler konumlari kaydirmasin
    for (srow, scol), (erow, ecol), text in reversed(edits):
        if srow == erow:
            line = lines[srow - 1]
            lines[srow - 1] = line[:scol] + text + line[ecol:]
        else:
            first = lines[srow - 1][:scol]
            last = lines[erow - 1][ecol:]
            lines[srow - 1:erow] = [first + text + last]

    return "".join(lines), changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uygula", action="store_true",
                        help="Degisiklikleri dosyalara yaz")
    parser.add_argument("--ayrinti", action="store_true",
                        help="Her degisikligi listele")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    src = ROOT / "src" / "luma_atelier"
    total_files = total_changes = 0
    for path in sorted(src.rglob("*.py")):
        if path.name in SKIP_FILES:
            continue
        new_source, changes = rewrite(path)
        if not changes:
            continue
        total_files += 1
        total_changes += len(changes)
        print(f"{path.relative_to(ROOT)}: {len(changes)} metin")
        if args.ayrinti:
            for before, after in changes:
                print(f"    {before.strip()[:70]}")
                print(f"  → {after.strip()[:70]}")
        if args.uygula:
            path.write_text(new_source, encoding="utf-8")

    print(f"\n{total_changes} metin, {total_files} dosyada"
          + ("  (yazildi)" if args.uygula else "  (yalnizca rapor)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

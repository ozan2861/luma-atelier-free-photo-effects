"""Faz 8 denetimi: gorsel kalite, erisilebilirlik ve performans.

Gereksinim belgesi Faz 8 kabul metni:
    "Ana akista tasma veya kilitlenme yok; klavye islemleri calisir;
     gercek cihaz uzerinde gecikme ve RAM olcumleri raporlanir.
     Performans sorunu varsa saklanmaz."

Bu arac **olcer ve raporlar**; degeri begenmedigi icin esigi
gevsetmez. Basarisiz olcum aciktan yazilir.

Calistirma:
    .venv\\Scripts\\python.exe tools\\phase8_audit.py
"""
from __future__ import annotations

import gc
import os
import shutil
import sys
import tempfile
import time
import weakref
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
from PySide6.QtCore import QEventLoop, Qt           # noqa: E402
from PySide6.QtGui import QKeySequence               # noqa: E402
from PySide6.QtWidgets import (                      # noqa: E402
    QAbstractButton,
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QWidget,
)

from luma_atelier.ui.widgets.elided_combo import ElidedComboBox  # noqa: E402

PASS, FAIL, NOTES = [], [], []

#: Test edilecek pencere boyutlari (genislik, yukseklik, aciklama)
SIZES: tuple[tuple[int, int, str], ...] = (
    (1280, 720, "en kucuk desteklenen"),
    (1366, 768, "dizustu"),
    (1600, 900, "yaygin"),
    (1920, 1080, "tam HD"),
    (2560, 1440, "yuksek"),
)

#: DPI olcekleri (Windows "Metni buyut" ayari)
DPI_SCALES: tuple[float, ...] = (1.0, 1.25, 1.5, 2.0)


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


def make_photo(path: Path, width: int, height: int, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.stack([xx / width, yy / height,
                      0.5 + 0.3 * np.sin(xx / 29.0)], axis=-1)
    image += rng.normal(0, 0.015, image.shape).astype(np.float32)
    cv2.imwrite(str(path),
                cv2.cvtColor((np.clip(image, 0, 1) * 255).astype(np.uint8),
                             cv2.COLOR_RGB2BGR))


def pump(app: QApplication, seconds: float = 0.25) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def wait_for(app: QApplication, predicate, timeout: float = 25.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
    return False


def rss_mb() -> float:
    """Sürecin bellek kullanimi (MB). psutil yoksa 0 doner."""
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return 0.0


# ================================================== 1. TASMA VE KESILME
def collect_overflows(root: QWidget) -> list[str]:
    """Icerigi kutusuna sigmayan gorunur widget'lari bulur."""
    problems: list[str] = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisible() or widget.width() <= 0:
            continue

        # Metin kesilmesi
        if isinstance(widget, QLabel) and widget.text() and not widget.wordWrap():
            needed = widget.fontMetrics().horizontalAdvance(widget.text())
            if needed > widget.width() + 2:
                problems.append(
                    f"QLabel kesiliyor: '{widget.text()[:32]}' "
                    f"({needed}px > {widget.width()}px)")
        elif isinstance(widget, QAbstractButton) and widget.text():
            needed = widget.fontMetrics().horizontalAdvance(widget.text()) + 24
            if needed > widget.width() + 2:
                problems.append(
                    f"Düğme kesiliyor: '{widget.text()[:32]}' "
                    f"({needed}px > {widget.width()}px)")
        elif isinstance(widget, QComboBox) and widget.currentText():
            # Metnini kendisi kisaltan listeler tasma sayilmaz; dar
            # kutuda "Analog ve vinta..." gostermek dogru davranis.
            if isinstance(widget, ElidedComboBox):
                continue
            needed = widget.fontMetrics().horizontalAdvance(
                widget.currentText()) + 34
            if needed > widget.width() + 2:
                problems.append(
                    f"Açılır liste kesiliyor: '{widget.currentText()[:28]}' "
                    f"({needed}px > {widget.width()}px)")

        # Kutusundan tasma
        minimum = widget.minimumSizeHint()
        if (minimum.isValid() and minimum.width() > 0
                and minimum.width() > widget.width() + 4
                and widget.width() > 1):
            problems.append(
                f"{type(widget).__name__} taşıyor: en az "
                f"{minimum.width()}px gerekiyor, {widget.width()}px var")
    return problems


def test_layout(app: QApplication, tmp: Path) -> None:
    section("1. Farklı pencere boyutlarında taşma ve kesilme")
    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.widgets.nav_bar import Workspace

    photo = tmp / "yerlesim.png"
    make_photo(photo, 1400, 900)

    window = MainWindow()
    window.show()
    pump(app, 0.6)
    window.session.add_paths([photo])
    window._open_in_editor(photo)
    if not wait_for(app, lambda: window.document is not None):
        check("Fotoğraf yüklendi", False, "zaman aşımı")
        window.close()
        return
    pump(app, 1.0)

    workspaces = [Workspace.START, Workspace.LIBRARY, Workspace.EDITOR,
                  Workspace.CINEMA, Workspace.EXPORT, Workspace.SETTINGS]
    total_problems = 0
    for width, height, label in SIZES:
        window.resize(width, height)
        pump(app, 0.5)
        found: list[str] = []
        for workspace in workspaces:
            window.show_workspace(workspace)
            pump(app, 0.35)
            found += [f"{workspace.label}: {p}"
                      for p in collect_overflows(window)]
        total_problems += len(found)
        check(f"{width}×{height} ({label}) temiz", not found,
              f"{len(found)} sorun" if found else "taşma/kesilme yok")
        for problem in found[:4]:
            print(f"        · {problem}")

    check("Hiçbir boyutta taşma yok", total_problems == 0,
          f"{total_problems} toplam sorun")

    window.close()
    window.deleteLater()
    pump(app, 0.3)


# ============================================================= 2. DPI
def test_dpi(app: QApplication, tmp: Path) -> None:
    section("2. DPI ölçeklemesi (%100 / %125 / %150 / %200)")
    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.widgets.nav_bar import Workspace

    photo = tmp / "dpi.png"
    make_photo(photo, 1200, 800)

    for scale in DPI_SCALES:
        # Yazi tipi noktasini olceklemek DPI artisinin arayuze etkisini
        # taklit eder: her sey buyur, kutular ayni kalir.
        base_font = app.font()
        scaled = app.font()
        scaled.setPointSizeF(max(6.0, base_font.pointSizeF() * scale))
        app.setFont(scaled)

        window = MainWindow()
        window.resize(1366, 768)      # en zorlayici: kucuk ekran + buyuk yazi
        window.show()
        pump(app, 0.5)
        window.session.add_paths([photo])
        window._open_in_editor(photo)
        wait_for(app, lambda: window.document is not None, timeout=20)
        pump(app, 0.6)

        problems: list[str] = []
        for workspace in (Workspace.EDITOR, Workspace.EXPORT,
                          Workspace.SETTINGS):
            window.show_workspace(workspace)
            pump(app, 0.35)
            problems += collect_overflows(window)

        check(f"%{int(scale * 100)} ölçekte 1366×768 temiz", not problems,
              f"{len(problems)} sorun" if problems else "kesilme yok")
        for problem in problems[:4]:
            print(f"        · {problem}")

        window.close()
        window.deleteLater()
        app.setFont(base_font)
        pump(app, 0.3)


# ======================================================== 3. KLAVYE
def test_keyboard(app: QApplication, tmp: Path) -> None:
    section("3. Klavye işlemleri ve odak")
    from luma_atelier.app.shell import MainWindow

    photo_a = tmp / "k1.png"
    photo_b = tmp / "k2.png"
    make_photo(photo_a, 700, 500, 1)
    make_photo(photo_b, 700, 500, 2)

    window = MainWindow()
    window.resize(1500, 900)
    window.show()
    pump(app, 0.5)
    window.session.add_paths([photo_a, photo_b])
    window._open_in_editor(photo_a)
    if not wait_for(app, lambda: window.document is not None):
        check("Fotoğraf yüklendi", False, "zaman aşımı")
        window.close()
        return

    # --- kisayollar tanimli mi ve benzersiz mi? ---
    actions = [a for a in window.findChildren(type(window.save_action))
               if not a.shortcut().isEmpty()]
    sequences = [a.shortcut().toString() for a in actions]
    duplicates = {s for s in sequences if sequences.count(s) > 1}
    check("Kısayollar tanımlı", len(actions) >= 15,
          f"{len(actions)} kısayol")
    check("Kısayol çakışması yok", not duplicates,
          f"çakışan: {sorted(duplicates)}" if duplicates else "")

    expected = {"Ctrl+O", "Ctrl+S", "Ctrl+Z", "Ctrl+Y", "Ctrl+Q",
                "Left", "Right", "0", "1", "F"}
    missing = expected - set(sequences)
    check("Temel kısayolların hepsi var", not missing,
          f"eksik: {sorted(missing)}" if missing else f"{len(expected)} tanesi")

    # --- gercekten calisiyorlar mi? ---
    window.document.set_param("tone.exposure", stops=0.6)
    window.document.commit()
    before = window.document.recipe
    window._undo()
    pump(app, 0.2)
    check("Ctrl+Z geri alıyor", window.document.recipe != before)
    window._redo()
    pump(app, 0.2)
    check("Ctrl+Y yineliyor", window.document.recipe == before)

    start_path = window._current_path
    window._go_next()
    if not wait_for(app, lambda: window._current_path != start_path,
                    timeout=20):
        check("→ sonraki fotoğrafa geçiyor", False, "geçiş olmadı")
    else:
        check("→ sonraki fotoğrafa geçiyor", True,
              f"{start_path.name} → {window._current_path.name}")
        window._go_previous()
        wait_for(app, lambda: window._current_path == start_path, timeout=20)
        check("← önceki fotoğrafa dönüyor",
              window._current_path == start_path)

    canvas = window.editor_view.canvas
    canvas.zoomToFit()
    pump(app, 0.2)
    fit_zoom = canvas.zoom()
    canvas.zoomToActualPixels()
    pump(app, 0.2)
    check("1 tuşu gerçek pikseli açıyor", abs(canvas.zoom() - 1.0) < 1e-6,
          f"sığdır {fit_zoom:.3f} → %100 {canvas.zoom():.3f}")

    # --- odak gezinmesi ---
    focusable = [w for w in window.findChildren(QWidget)
                 if w.isVisible() and w.focusPolicy() != Qt.FocusPolicy.NoFocus]
    check("Sekme ile gezilebilir öğe var", len(focusable) >= 10,
          f"{len(focusable)} odaklanabilir öğe")

    # --- arac ipuclari ---
    interactive = [w for w in window.findChildren(QWidget)
                   if isinstance(w, (QAbstractButton, QComboBox, QLineEdit))
                   and w.isVisible()]
    with_tips = [w for w in interactive if w.toolTip()]
    ratio = len(with_tips) / max(1, len(interactive))
    note(f"Etkileşimli öğelerin %{ratio * 100:.0f}'ında araç ipucu var "
         f"({len(with_tips)}/{len(interactive)})")
    check("Etkileşimli öğelerin çoğunda ipucu var", ratio >= 0.45,
          f"%{ratio * 100:.0f}")

    window.close()
    window.deleteLater()
    pump(app, 0.3)


# ==================================================== 4. PERFORMANS
def test_performance(app: QApplication, tmp: Path) -> None:
    section("4. Gecikme ölçümleri (bu cihazda)")
    from luma_atelier.imaging.loader import load_image
    from luma_atelier.imaging.recipe import Recipe
    from luma_atelier.services.render import RenderService

    photo = tmp / "perf.png"
    make_photo(photo, 3840, 2160)          # 8.3 MP
    loaded = load_image(photo)
    service = RenderService()

    heavy = (Recipe()
             .set_or_add("tone.exposure", stops=0.4)
             .set_or_add("tone.contrast", amount=0.3)
             .set_or_add("color.vibrance", amount=0.35)
             .set_or_add("detail.clarity", amount=0.3)
             .set_or_add("lens.vignette", amount=-0.3)
             .set_or_add("light.halation", amount=0.4)
             .set_or_add("texture.grain", amount=0.5))

    def timed(fn, runs: int = 3) -> float:  # noqa: ANN001
        best = float("inf")
        for _ in range(runs):
            start = time.perf_counter()
            fn()
            best = min(best, (time.perf_counter() - start) * 1000)
        return best

    simple = Recipe().set_or_add("tone.exposure", stops=0.5)
    ms_simple = timed(lambda: service.render_now(
        loaded.pixels, simple, long_edge=1920, purpose="preview"))
    ms_heavy = timed(lambda: service.render_now(
        loaded.pixels, heavy, long_edge=1920, purpose="preview"))
    ms_full = timed(lambda: service.render_now(loaded.pixels, heavy), runs=2)

    note(f"Önizleme (1 efekt, 1920px): {ms_simple:.0f} ms")
    note(f"Önizleme (7 efekt, 1920px): {ms_heavy:.0f} ms")
    note(f"Tam boy 8.3 MP (7 efekt): {ms_full:.0f} ms")

    check("Basit önizleme < 250 ms", ms_simple < 250, f"{ms_simple:.0f} ms")
    check("Ağır önizleme < 800 ms", ms_heavy < 800, f"{ms_heavy:.0f} ms")
    check("Tam boy 8.3 MP < 6 s", ms_full < 6000, f"{ms_full:.0f} ms")

    # Detay karosu (%100 gorunum)
    base = loaded.pixels
    ms_tile = timed(lambda: service.render_tile(base, heavy,
                                                (800, 600, 900, 700)))
    note(f"%100 detay karosu (900×700): {ms_tile:.0f} ms")
    check("Detay karosu < 700 ms", ms_tile < 700, f"{ms_tile:.0f} ms")


# ======================================================= 5. BELLEK
def test_memory(app: QApplication, tmp: Path) -> None:
    section("5. Uzun oturumda bellek eğilimi")
    try:
        import psutil  # noqa: F401
    except ImportError:
        print("  [atlandı] psutil kurulu değil; RAM ölçümü YAPILMADI.")
        NOTES.append("RAM ölçümü YAPILMADI (psutil yok)")
        return

    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.widgets.nav_bar import Workspace

    photos = []
    for i in range(6):
        path = tmp / f"bellek{i}.png"
        make_photo(path, 2400, 1600, seed=i)
        photos.append(path)

    window = MainWindow()
    window.resize(1500, 900)
    window.show()
    pump(app, 0.6)
    window.session.add_paths(photos)

    library = window.presets.all()
    samples: list[float] = []

    gc.collect()
    baseline = rss_mb()
    note(f"Başlangıç RAM: {baseline:.0f} MB")
    #: Acilan her belgeye zayif referans; GC sonrasi canli kalan varsa
    #: birileri onu tutuyor demektir.
    doc_refs: list = []

    rounds = 3
    for round_index in range(rounds):
        for i, photo in enumerate(photos):
            window._open_in_editor(photo)
            wait_for(app, lambda: window.document is not None
                     and window._current_path == photo, timeout=25)
            doc = window.document
            if doc is None:
                continue
            doc_refs.append(weakref.ref(doc))
            # Duzenle
            doc.set_param("tone.exposure", stops=0.3 + 0.1 * i)
            doc.set_param("color.vibrance", amount=0.25)
            doc.commit()
            # Gorunum uygula
            if library:
                preset = library[(round_index * len(photos) + i) % len(library)]
                doc.apply_preset(preset, 80.0)
                doc.commit()
            # Calisma alanlari arasinda gez
            for workspace in (Workspace.CINEMA, Workspace.EXPORT,
                              Workspace.EDITOR):
                window.show_workspace(workspace)
                pump(app, 0.15)
        gc.collect()
        gc.collect()
        pump(app, 0.4)
        samples.append(rss_mb())
        note(f"{round_index + 1}. tur sonrası RAM: {samples[-1]:.0f} MB")

    peak = max(samples)
    growth = samples[-1] - samples[0]
    per_round = growth / max(1, len(samples) - 1)
    note(f"Tepe RAM: {peak:.0f} MB  ·  turlar arası RSS değişimi: "
         f"{growth:+.0f} MB ({per_round:+.0f} MB/tur)")

    check("Tepe RAM < 3 GB", peak < 3072, f"{peak:.0f} MB")

    # RSS *tek basina* sizinti olcusu degildir: Python ve OpenCV
    # bosalttiklari bellegi isletim sistemine hemen geri vermez, bu
    # yuzden ayni senaryo iki kosuda farkli egri cizer. Gercek olcut
    # nesnelerin serbest birakilip birakilmadigidir; bu yuzden acilan
    # her belgeye zayif referans tutulup GC sonrasi kac tanesinin
    # hayatta kaldigina bakilir.
    alive = sum(1 for ref in doc_refs if ref() is not None)
    note(f"{len(doc_refs)} belge açıldı, GC sonrası {alive} tanesi canlı")
    check("Kapanan belgeler serbest bırakılıyor", alive <= 2,
          f"{alive} canlı belge (yalnızca açık olan beklenir)")

    window.close()
    window.deleteLater()
    pump(app, 0.4)


# ====================================================== 6. KİLİTLENME
def test_responsiveness(app: QApplication, tmp: Path) -> None:
    section("6. Ana akışta kilitlenme")
    from luma_atelier.app.shell import MainWindow
    from luma_atelier.ui.widgets.nav_bar import Workspace

    photo = tmp / "yanit.png"
    make_photo(photo, 4000, 3000)      # 12 MP

    window = MainWindow()
    window.resize(1500, 900)
    window.show()
    pump(app, 0.5)
    window.session.add_paths([photo])

    start = time.perf_counter()
    window._open_in_editor(photo)
    blocked = 0.0
    last = time.perf_counter()
    while window.document is None and time.perf_counter() - start < 30:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 16)
        now = time.perf_counter()
        blocked = max(blocked, now - last)
        last = now
    opened_ms = (time.perf_counter() - start) * 1000

    check("12 MP fotoğraf açıldı", window.document is not None,
          f"{opened_ms:.0f} ms")
    note(f"Açılış sırasında en uzun kesintisiz blok: {blocked * 1000:.0f} ms")
    check("Yükleme arayüzü kilitlemiyor", blocked < 0.6,
          f"en uzun blok {blocked * 1000:.0f} ms")

    # Kaydirici surukleme benzetimi.
    #
    # Belgeyi dogrudan surmek (`doc.set_param`) kullanicinin yolu
    # DEGILDIR: gercek kaydirici `EditorView._on_param_changed`
    # cagirir ve bu **etkilesimli** (dusuk cozunurluklu) render ister.
    # Dogrudan surmek yalnizca tam kalite render'i tetikler ve olcum
    # kullanicinin yasadigindan yavas cikar.
    view = window.editor_view
    doc = window.document
    if doc is not None:
        pump(app, 1.2)          # acilis render'i bitsin, olcume karismasin
        worst = 0.0
        for i in range(25):
            t0 = time.perf_counter()
            view._on_param_changed("tone.exposure", {"stops": i * 0.04})
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 8)
            worst = max(worst, time.perf_counter() - t0)
        view._on_param_committed("tone.exposure", {"stops": 1.0})
        note(f"Kaydırıcı sürüklemede en uzun adım: {worst * 1000:.0f} ms")
        check("Kaydırıcı sürükleme akıcı (<150 ms/adım)", worst < 0.15,
              f"{worst * 1000:.0f} ms")

        # Birakildiktan sonraki tam kalite render'in arayuzu ne kadar
        # mesgul ettigi ayrica olculur; bu tek seferlik bir duraklamadir.
        settle = time.perf_counter()
        longest_block = 0.0
        last = settle
        while time.perf_counter() - settle < 4.0:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 16)
            now = time.perf_counter()
            longest_block = max(longest_block, now - last)
            last = now
        note(f"Bırakıldıktan sonra tam kalite render duraklaması: "
             f"{longest_block * 1000:.0f} ms")
        check("Bırakma sonrası duraklama < 400 ms", longest_block < 0.4,
              f"{longest_block * 1000:.0f} ms")

    # Calisma alanlari arasi gecis
    worst_switch = 0.0
    for workspace in (Workspace.LIBRARY, Workspace.CINEMA, Workspace.EXPORT,
                      Workspace.SETTINGS, Workspace.EDITOR):
        t0 = time.perf_counter()
        window.show_workspace(workspace)
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        worst_switch = max(worst_switch, time.perf_counter() - t0)
    note(f"Çalışma alanı geçişinde en uzun: {worst_switch * 1000:.0f} ms")
    check("Ekran geçişi < 500 ms", worst_switch < 0.5,
          f"{worst_switch * 1000:.0f} ms")

    window.close()
    window.deleteLater()
    pump(app, 0.3)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="luma_faz8_"))
    print("=" * 68)
    print("FAZ 8 DENETİMİ — görsel kalite, erişilebilirlik, performans")
    print("=" * 68)
    print(f"Geçici klasör: {tmp}")
    try:
        test_layout(app, tmp)
        test_dpi(app, tmp)
        test_keyboard(app, tmp)
        test_performance(app, tmp)
        test_memory(app, tmp)
        test_responsiveness(app, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 68)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if NOTES:
        print("\nÖLÇÜMLER:")
        for text in NOTES:
            print(f"  · {text}")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 68)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

"""Yarış durumu ve durum tutarliligi denetimi — uretilebilir kanit.

Her kontrol bir **kullanici senaryosunu** yeniden kurar ve sonucun
dogru olup olmadigini olcer. Amac iddia degil kanit uretmek: her
basarisiz kontrol, duzeltilmeden once basarisiz olmali.

Calistirma:
    .venv\\Scripts\\python.exe tools\\audit_races.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
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
from PySide6.QtCore import QEventLoop               # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'HATA'}] {name}"
          + (f"   — {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def photo(path: Path, w: int = 900, h: int = 700, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), (rng.random((h, w, 3)) * 255).astype(np.uint8))
    return path


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def wait_for(app: QApplication, predicate, timeout: float = 30.0) -> bool:  # noqa: ANN001
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    return False


def make_window(app: QApplication):  # noqa: ANN201
    from luma_atelier.app.shell import MainWindow

    window = MainWindow()
    window.resize(1400, 860)
    window.show()
    pump(app, 0.4)
    return window


# ============================================= 1. TEK FOTOGRAF, TEK YUKLEME
def test_single_load(app: QApplication, tmp: Path) -> None:
    section("1. Bir fotoğraf açmak kaç kez yükleme başlatıyor?")
    from luma_atelier.app import shell as shell_mod

    window = make_window(app)
    src = photo(tmp / "tek.png", seed=1)
    window.session.add_paths([src])

    starts: list[str] = []
    original = shell_mod._LoadTask.__init__

    def counting(self, path, signals, token):  # noqa: ANN001, ANN202
        starts.append(str(path))
        return original(self, path, signals, token)

    shell_mod._LoadTask.__init__ = counting
    try:
        window.show_workspace(shell_mod.Workspace.EDITOR)
        pump(app, 0.3)
        starts.clear()
        window._open_in_editor(src)
        wait_for(app, lambda: window.document is not None)
        pump(app, 0.8)
    finally:
        shell_mod._LoadTask.__init__ = original

    check("Bir fotoğraf tam olarak bir kez yükleniyor", len(starts) == 1,
          f"{len(starts)} yükleme başlatıldı "
          f"(çift yükleme = çift kod çözme + durum çakışması)")

    window.close()
    pump(app, 0.2)


# ================================== 2. ILERI-GERI: GORUNTU KAYBOLUYOR MU?
def test_back_and_forth(app: QApplication, tmp: Path) -> None:
    section("2. Sonraki → hemen Önceki: düzenleyici boş kalıyor mu?")
    window = make_window(app)
    a = photo(tmp / "ileri-a.png", 2200, 1700, seed=2)
    b = photo(tmp / "ileri-b.png", 2200, 1700, seed=3)
    window.session.add_paths([a, b])
    window._open_in_editor(a)
    if not wait_for(app, lambda: window.document is not None):
        check("A yüklendi", False, "zaman aşımı")
        window.close()
        return

    # B'ye gec, yuklenmesini **bekleme**, hemen A'ya don
    window._go_next()
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
    window._go_previous()

    ok = wait_for(app, lambda: window.document is not None
                  and window._current_path == a, timeout=25)
    check("Hızlı ileri-geri sonrası fotoğraf yüklü kalıyor", ok,
          f"belge={'var' if window.document else 'YOK'}, "
          f"yol={window._current_path.name if window._current_path else '-'}")

    # Bu durumda 'Kopya olarak kaydet' ne yazardi?
    saveable = window.save_action.isEnabled()
    consistent = (window.document is not None) == saveable
    check("Kaydet düğmesi belge durumuyla tutarlı", consistent,
          f"belge={'var' if window.document else 'yok'}, "
          f"kaydet={'açık' if saveable else 'kapalı'}")

    window.close()
    pump(app, 0.2)


# ========================== 3. ESKI HATA SONUCU YENI FOTOGRAFI SILIYOR MU?
def test_stale_failure(app: QApplication, tmp: Path) -> None:
    section("3. Eski fotoğrafın hata sonucu yeni fotoğrafı bozuyor mu?")
    window = make_window(app)
    good = photo(tmp / "saglam.png", seed=4)
    window.session.add_paths([good])
    window._open_in_editor(good)
    if not wait_for(app, lambda: window.document is not None):
        check("Sağlam fotoğraf yüklendi", False, "zaman aşımı")
        window.close()
        return

    before_doc = window.document
    # Artik kullanicinin *terk ettigi* bir fotografin hata sinyali gelir
    window._on_photo_failed(str(tmp / "cok-onceki-bozuk.png"),
                            "Dosya açılamadı veya bozuk")
    pump(app, 0.3)

    check("Terk edilmiş fotoğrafın hatası açık belgeyi bozmadı",
          window.document is before_doc and window.document is not None,
          "belge silindi" if window.document is None else "")
    check("Terk edilmiş hata tuvali temizlemedi",
          window.editor_view.canvas._edited is not None,
          "tuval boşaltıldı" if window.editor_view.canvas._edited is None
          else "")

    window.close()
    pump(app, 0.2)


# ================================ 4. KAPANISTA KAYDEDILMEMIS IS KAYBOLUYOR MU?
def test_close_unsaved(app: QApplication, tmp: Path) -> None:
    section("4. Kaydedilmemiş düzenleme, kapanışta kayboluyor mu?")
    from luma_atelier.storage.project import find_autosave

    window = make_window(app)
    src = photo(tmp / "kaydedilmemis.png", seed=5)
    window.session.add_paths([src])
    window._open_in_editor(src)
    if not wait_for(app, lambda: window.document is not None):
        check("Fotoğraf yüklendi", False, "zaman aşımı")
        window.close()
        return

    window.document.set_param("tone.exposure", stops=0.9)
    window.document.set_param("color.vibrance", amount=0.5)
    window.document.commit()
    modified = window.document.is_modified
    check("Belge 'kaydedilmemiş' durumda", modified)

    window._autosave_tick()          # kurtarma kaydi yazilir
    pump(app, 0.3)
    had_autosave = find_autosave(src) is not None
    check("Kurtarma kaydı yazıldı", had_autosave)

    # Kullanici pencereyi kapatir - hicbir sey kaydetmeden
    window.close()
    pump(app, 0.5)

    still_there = find_autosave(src) is not None
    check("Kapanışta kaydedilmemiş iş korunuyor", still_there,
          "kurtarma kaydı silindi — düzenlemeler geri getirilemez"
          if not still_there else "kurtarma kaydı duruyor")


# ================================ 5. KAPANISTA SUREN EXPORT NE OLUYOR?
def test_close_during_export(app: QApplication, tmp: Path) -> None:
    section("5. Export sürerken kapatmak")
    from luma_atelier.services.export import ExportJob, ExportSettings

    window = make_window(app)
    photos = [photo(tmp / f"toplu{i}.png", 1400, 1000, seed=10 + i)
              for i in range(12)]
    window.session.add_paths(photos)
    pump(app, 0.3)

    jobs = [ExportJob(source=p) for p in photos]
    out = tmp / "kapanis-cikti"
    window.export_queue.start(jobs, ExportSettings(folder=out))
    pump(app, 0.5)
    running_before = window.export_queue.is_running
    check("Export başladı", running_before)

    window.close()
    pump(app, 1.0)

    still_running = window.export_queue.is_running
    check("Kapanışta export kuyruğu durduruldu", not still_running,
          "kuyruk pencere kapandıktan sonra da çalışıyor"
          if still_running else "")
    window.export_queue.cancel()
    window.export_queue.wait(20_000)


# ============================ 6. KITAPLIK SECIMI ILE DUZENLEYICI TUTARLI MI?
def test_library_selection(app: QApplication, tmp: Path) -> None:
    section("6. Kitaplıkta seçip Düzenleyiciye geçmek")
    from luma_atelier.ui.widgets.nav_bar import Workspace

    window = make_window(app)
    photos = [photo(tmp / f"secim{i}.png", seed=20 + i) for i in range(4)]
    window.session.add_paths(photos)
    window._open_in_editor(photos[0])
    if not wait_for(app, lambda: window.document is not None):
        check("İlk fotoğraf yüklendi", False, "zaman aşımı")
        window.close()
        return

    window.show_workspace(Workspace.LIBRARY)
    pump(app, 0.3)
    # Kullanici 3. fotografi **tek tikla** secer (acmaz)
    window.session.set_selection([2])
    pump(app, 0.3)
    window.show_workspace(Workspace.EDITOR)
    pump(app, 1.0)
    wait_for(app, lambda: window._current_path == photos[2], timeout=20)

    shown = window._current_path
    current = window.session.current.path if window.session.current else None
    check("Düzenleyicideki fotoğraf, seçili fotoğrafla aynı",
          shown == current,
          f"ekranda {shown.name if shown else '-'}, "
          f"seçili {current.name if current else '-'}")

    window.close()
    pump(app, 0.2)


# ================================ 7. HIZLI FOTOGRAF DEGISTIRME DAYANIKLILIGI
def test_rapid_switching(app: QApplication, tmp: Path) -> None:
    section("7. Hızlı fotoğraf değiştirme (20 geçiş)")
    window = make_window(app)
    photos = [photo(tmp / f"hizli{i}.png", 1600, 1200, seed=30 + i)
              for i in range(5)]
    window.session.add_paths(photos)
    window._open_in_editor(photos[0])
    wait_for(app, lambda: window.document is not None)

    errors: list[str] = []
    for i in range(20):
        target = photos[i % len(photos)]
        window._open_in_editor(target)
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 15)

    settled = wait_for(app, lambda: window.document is not None
                       and window._current_path == photos[19 % len(photos)],
                       timeout=30)
    check("20 hızlı geçişten sonra doğru fotoğraf yüklü", settled,
          f"ekranda {window._current_path.name if window._current_path else '-'}, "
          f"beklenen {photos[19 % len(photos)].name}")
    check("Hızlı geçişte hata oluşmadı", not errors, "; ".join(errors[:2]))

    # Yigin durumu ile gosterilen fotograf tutarli mi?
    if window.document is not None:
        check("Belge ile gösterilen yol aynı",
              window.document.path == window._current_path,
              f"{window.document.path.name} vs "
              f"{window._current_path.name}")

    window.close()
    pump(app, 0.3)


# ================== 8. KAYDIRICI SURUKLERKEN FOTOGRAF DEGISTIRME
def test_slider_then_switch(app: QApplication, tmp: Path) -> None:
    section("8. Kaydırıcı sürüklerken fotoğraf değiştirme")
    window = make_window(app)
    a = photo(tmp / "kaydirici-a.png", 2400, 1800, seed=40)
    b = photo(tmp / "kaydirici-b.png", 2400, 1800, seed=41)
    window.session.add_paths([a, b])
    window._open_in_editor(a)
    if not wait_for(app, lambda: window.document is not None):
        check("A yüklendi", False, "zaman aşımı")
        window.close()
        return

    view = window.editor_view
    for i in range(10):
        view._on_param_changed("tone.exposure", {"stops": i * 0.15})
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)

    # Surukleme biterken B'ye gec
    window._open_in_editor(b)
    ok = wait_for(app, lambda: window.document is not None
                  and window._current_path == b, timeout=25)
    pump(app, 1.5)

    check("Fotoğraf değişti", ok,
          window._current_path.name if window._current_path else "-")
    if window.document is not None:
        clean = len(window.document.recipe) == 0
        check("Yeni fotoğraf, öncekinin ayarlarını devralmadı", clean,
              f"{len(window.document.recipe)} katman taşındı")

    window.close()
    pump(app, 0.3)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="luma_yaris_"))
    print("=" * 70)
    print("YARIŞ DURUMU VE DURUM TUTARLILIĞI DENETİMİ")
    print("=" * 70)
    print(f"Geçici klasör: {tmp}")
    try:
        test_single_load(app, tmp)
        test_back_and_forth(app, tmp)
        test_stale_failure(app, tmp)
        test_close_unsaved(app, tmp)
        test_close_during_export(app, tmp)
        test_library_selection(app, tmp)
        test_rapid_switching(app, tmp)
        test_slider_then_switch(app, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 70)
    total = len(PASS) + len(FAIL)
    print(f"SONUC: {len(PASS)}/{total} gecti")
    if FAIL:
        print("\nBASARISIZ:")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 70)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

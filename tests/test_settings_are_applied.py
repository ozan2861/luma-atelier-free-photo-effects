"""Ayarlar ekranindaki her kutu gercekten bir sey yapmali.

Bulgu: uc ayar toplaniyor, kaydediliyor ve arayuzde isaretli
gorunuyordu ama **hicbir yerde okunmuyordu**:

* "Pencere boyutunu ve konumunu hatırla" (`remember_window`)
* "Çok sayıda fotoğraf dışa aktarılırken onay iste"
  (`confirm_large_export`)
* "Klavye kısayollarını ipuçlarında göster" (`keyboard_hints`)

Etkisiz kontrol, gereksinim belgesindeki "yer tutucu ekran, etkisiz
kontrol" maddesine giriyor. Bu testler her birinin gozlemlenebilir bir
sonucu oldugunu dogrular.
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from luma_atelier.core.settings import Settings  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path, monkeypatch):  # noqa: ANN201
    """Kullanici verisine dokunmayan bir ana pencere."""
    monkeypatch.setenv("LUMA_DATA_HOME", str(tmp_path / "veri"))
    from luma_atelier.app.shell import MainWindow

    win = MainWindow()
    yield win
    win.deleteLater()


class TestWindowGeometryIsRemembered:
    def test_geometry_is_written_on_close(self, window) -> None:  # noqa: ANN001
        window.settings = replace(window.settings, remember_window=True,
                                  window_geometry="")
        window.resize(1180, 760)
        window._remember_geometry()

        assert window.settings.window_geometry, "geometri kaydedilmedi"

    def test_nothing_is_written_when_disabled(self, window) -> None:  # noqa: ANN001
        window.settings = replace(window.settings, remember_window=False,
                                  window_geometry="")
        window.resize(1024, 700)
        window._remember_geometry()

        assert window.settings.window_geometry == ""

    def test_saved_geometry_is_restored(self, window, monkeypatch) -> None:  # noqa: ANN001
        """Kullanici acisindan sonuc: pencere ayni boyutta acilmali.

        Genislik burada dogrulanmiyor: bassiz ("offscreen") Qt
        platformunda `restoreGeometry` genisligi sanal ekrana
        kirpiyor - bu Qt'nin davranisi, uygulamanin degil. Yukseklik
        birebir geri gelmeli ve sonuc varsayilan boyut **olmamali**.
        """
        from luma_atelier.ui.theme.tokens import METRICS

        window.resize(1180, 764)
        window.settings = replace(window.settings, remember_window=True)
        window._remember_geometry()
        assert window.settings.window_geometry

        window.resize(900, 600)
        monkeypatch.setattr(window, "_is_on_a_screen", lambda: True)
        window._restore_geometry()
        window.show()
        QApplication.processEvents()

        assert window.height() == 764
        assert (window.width(), window.height()) != (
            METRICS.window_default_width, METRICS.window_default_height
        )

    def test_offscreen_geometry_falls_back_to_default(self, window,  # noqa: ANN001
                                                      monkeypatch) -> None:  # noqa: ANN001
        """Ekran yerlesimi degistiyse pencere kaybolmamali."""
        window.resize(1100, 700)
        window.move(-9000, -9000)
        window.settings = replace(window.settings, remember_window=True)
        window._remember_geometry()

        monkeypatch.setattr(window, "_is_on_a_screen", lambda: False)
        window._restore_geometry()
        assert window.x() > -1000 and window.y() > -1000


class TestKeyboardHints:
    def test_shortcut_is_shown_in_tooltip(self, window) -> None:  # noqa: ANN001
        window._apply_keyboard_hints(True)
        tips = [a.toolTip() for a in window.findChildren(QAction)
                if not a.shortcut().isEmpty()]
        assert tips, "kisayollu eylem bulunamadi"
        assert any("(" in t and ")" in t for t in tips), tips

    def test_shortcut_is_removed_when_disabled(self, window) -> None:  # noqa: ANN001
        window._apply_keyboard_hints(True)
        with_hint = {a.text(): a.toolTip() for a in window.findChildren(QAction)}
        window._apply_keyboard_hints(False)
        for act in window.findChildren(QAction):
            if act.shortcut().isEmpty():
                continue
            plain = str(act.property("_plain_tooltip"))
            assert act.toolTip() == plain
            # Ipucu gercekten degismis olmali; yoksa test bos gecerdi
            assert with_hint[act.text()] != plain

    def test_toggling_does_not_corrupt_the_text(self, window) -> None:  # noqa: ANN001
        window._apply_keyboard_hints(False)
        before = {a.text(): a.toolTip() for a in window.findChildren(QAction)}
        for _ in range(3):
            window._apply_keyboard_hints(True)
            window._apply_keyboard_hints(False)
        after = {a.text(): a.toolTip() for a in window.findChildren(QAction)}
        assert before == after


class TestLargeExportConfirmation:
    def _jobs(self, count: int, tmp_path: Path) -> list:
        from luma_atelier.services.export import ExportJob

        jobs = []
        for i in range(count):
            src = tmp_path / f"f{i}.jpg"
            src.write_bytes(b"x")
            jobs.append(ExportJob(source=src))
        return jobs

    def test_no_dialog_when_the_setting_is_off(self, window, tmp_path: Path,  # noqa: ANN001
                                               monkeypatch) -> None:  # noqa: ANN001
        from PySide6.QtWidgets import QMessageBox

        asked: list[str] = []
        monkeypatch.setattr(
            "luma_atelier.app.shell.QMessageBox.question",
            lambda *a, **k: (asked.append("soruldu"),
                             QMessageBox.StandardButton.Yes)[1])

        window.settings = replace(window.settings,
                                  confirm_large_export=False)
        settings = window.export_view.settings()
        settings = replace(settings, folder=str(tmp_path / "cikti"))
        (tmp_path / "cikti").mkdir()

        assert window._confirm_export(self._jobs(40, tmp_path), settings)
        assert not asked, "ayar kapaliyken onay sorulmamali"

    def test_dialog_appears_when_the_setting_is_on(self, window,  # noqa: ANN001
                                                   tmp_path: Path,
                                                   monkeypatch) -> None:  # noqa: ANN001
        from PySide6.QtWidgets import QMessageBox

        asked: list[str] = []
        monkeypatch.setattr(
            "luma_atelier.app.shell.QMessageBox.question",
            lambda *a, **k: (asked.append("soruldu"),
                             QMessageBox.StandardButton.Yes)[1])

        window.settings = replace(window.settings, confirm_large_export=True)
        settings = window.export_view.settings()
        out = tmp_path / "cikti2"
        out.mkdir()
        settings = replace(settings, folder=str(out))

        assert window._confirm_export(self._jobs(40, tmp_path), settings)
        assert asked, "ayar acikken onay sorulmali"


class TestSettingsDefaultsAreCoherent:
    def test_every_boolean_setting_has_a_reader(self) -> None:
        """Yeni bir ayar eklenirken okunmadan kalmasin.

        Bu kontrol, ayar adinin kaynak agacinda Settings tanimi ve
        Ayarlar ekrani disinda en az bir yerde gectigini arar.
        """
        import re

        root = Path(__file__).resolve().parents[1] / "src" / "luma_atelier"
        skip = {"settings.py", "settings_view.py"}
        haystack = "\n".join(
            f.read_text(encoding="utf-8")
            for f in root.rglob("*.py") if f.name not in skip
        )
        unread = [
            name for name, value in vars(Settings()).items()
            if isinstance(value, bool)
            and not re.search(rf"\b{re.escape(name)}\b", haystack)
        ]
        assert not unread, f"hicbir yerde okunmayan ayar: {unread}"

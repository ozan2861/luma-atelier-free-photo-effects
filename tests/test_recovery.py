"""Otomatik kurtarmanin ne zaman teklif edildigi.

Kurtarma **cokme sonrasi** icindir. Uygulamanin ayni oturumda kendi
yazdigi kaydi kullaniciya "kurtarma" diye sunmasi yanlistir: hicbir sey
kaybolmamistir ve modal soru kullanicinin akisini boler.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from luma_atelier.imaging.recipe import Recipe
from luma_atelier.storage.project import (
    autosave_path,
    clear_autosave,
    find_autosave,
    load_project,
    write_autosave,
)


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    path = tmp_path / "kaynak.png"
    cv2.imwrite(str(path),
                (np.random.default_rng(1).random((120, 160, 3)) * 255)
                .astype(np.uint8))
    return path


class TestAutosaveFile:
    def test_written_to_separate_file(self, photo: Path) -> None:
        recipe = Recipe().set_or_add("tone.exposure", stops=0.7)
        written = write_autosave(photo, recipe)
        assert written is not None
        assert written != photo
        assert ".autosave" in written.name

    def test_name_is_stable_for_the_same_source(self, photo: Path) -> None:
        assert autosave_path(photo) == autosave_path(photo)

    def test_found_and_cleared(self, photo: Path) -> None:
        write_autosave(photo, Recipe().set_or_add("tone.exposure", stops=0.3))
        assert find_autosave(photo) is not None
        clear_autosave(photo)
        assert find_autosave(photo) is None

    def test_content_round_trips(self, photo: Path) -> None:
        recipe = (Recipe()
                  .set_or_add("tone.exposure", stops=0.8)
                  .set_or_add("color.vibrance", amount=0.4))
        written = write_autosave(photo, recipe)
        assert written is not None
        assert load_project(written).recipe == recipe

    def test_clear_is_safe_when_missing(self, photo: Path) -> None:
        clear_autosave(photo)       # yoksa da hata vermemeli
        clear_autosave(photo)


class TestRecoveryOffer:
    """Kabuk davranisi: kurtarma yalnizca *onceki* oturum icin sorulur."""

    @pytest.fixture
    def window(self, qapp):  # noqa: ANN001, ANN201
        from luma_atelier.app.shell import MainWindow

        win = MainWindow()
        yield win
        win.close()
        win.deleteLater()
        qapp.processEvents()

    def test_own_autosave_is_not_offered(self, window, photo: Path,  # noqa: ANN001
                                         monkeypatch) -> None:  # noqa: ANN001
        """Ayni oturumda yazilan kayit icin soru sorulmaz."""
        asked: list[str] = []
        monkeypatch.setattr(
            "luma_atelier.app.shell.QMessageBox.question",
            lambda *a, **k: asked.append("soruldu"))

        write_autosave(photo, Recipe().set_or_add("tone.exposure", stops=0.5))
        window._session_autosaves.add(photo)

        class _Doc:
            path = photo
            has_edits = False
            is_modified = False

        window.document = _Doc()
        window._offer_recovery()
        assert not asked, "kendi yazdigi kayit icin sorulmamali"
        clear_autosave(photo)

    def test_previous_session_autosave_is_offered(self, window, photo: Path,  # noqa: ANN001
                                                  monkeypatch) -> None:  # noqa: ANN001
        """Onceki oturumdan kalan kayit icin sorulur."""
        from PySide6.QtWidgets import QMessageBox

        asked: list[str] = []
        monkeypatch.setattr(
            "luma_atelier.app.shell.QMessageBox.question",
            lambda *a, **k: (asked.append("soruldu"),
                             QMessageBox.StandardButton.No)[1])

        write_autosave(photo, Recipe().set_or_add("tone.exposure", stops=0.5))

        class _Doc:
            path = photo
            has_edits = False
            is_modified = False

        window.document = _Doc()
        window._session_autosaves.clear()       # baska oturumdan gelmis gibi
        window._offer_recovery()
        assert asked, "onceki oturumun kaydi icin sorulmali"

    def test_clean_close_clears_session_autosaves(self, window,  # noqa: ANN001
                                                  photo: Path) -> None:
        """Temiz kapanista kurtarilacak bir sey yoktur."""
        write_autosave(photo, Recipe().set_or_add("tone.exposure", stops=0.5))
        window._session_autosaves.add(photo)
        window._clear_session_autosaves()
        assert find_autosave(photo) is None
        assert not window._session_autosaves

    def test_edited_document_is_never_overwritten_by_recovery(
        self, window, photo: Path, monkeypatch,  # noqa: ANN001
    ) -> None:
        """Kullanici zaten duzenlemisse kurtarma sorulmaz."""
        asked: list[str] = []
        monkeypatch.setattr(
            "luma_atelier.app.shell.QMessageBox.question",
            lambda *a, **k: asked.append("soruldu"))
        write_autosave(photo, Recipe().set_or_add("tone.exposure", stops=0.5))

        class _Doc:
            path = photo
            has_edits = True        # kullanici bir sey yapmis
            is_modified = False     # kaydedilmemis degisiklik yok

        window.document = _Doc()
        window._session_autosaves.clear()
        window._offer_recovery()
        assert not asked, "duzenlenmis belgede kurtarma sorulmamali"
        clear_autosave(photo)

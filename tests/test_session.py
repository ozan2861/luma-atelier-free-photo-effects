"""Oturum/kitaplik modeli testleri (Qt gerektirmez)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from luma_atelier.core.session import Session, SortKey
from luma_atelier.imaging.saver import OutputFormat, SaveOptions, save_image


@pytest.fixture
def photo_dir(tmp_path: Path, color_patches: np.ndarray) -> Path:
    """Icinde dort fotograf, bir bozuk ve bir metin dosyasi olan klasor."""
    root = tmp_path / "kitaplik"
    (root / "alt klasor").mkdir(parents=True)
    for name in ("bravo.jpg", "alfa.png", "charlie.webp"):
        save_image(color_patches, root / name,
                   SaveOptions(fmt=OutputFormat[name.split(".")[1].upper()
                                                if name.endswith("png") else
                                                ("JPEG" if name.endswith("jpg")
                                                 else "WEBP")]))
    save_image(color_patches, root / "alt klasor" / "delta.jpg",
               SaveOptions(fmt=OutputFormat.JPEG))
    (root / "bozuk.jpg").write_bytes(b"gecerli degil" * 40)
    (root / "notlar.txt").write_text("fotograf degil", encoding="utf-8")
    return root


class TestImport:
    def test_adds_supported_files_only(self, photo_dir: Path) -> None:
        s = Session()
        report = s.add_paths([photo_dir])
        assert len(report.added) == 3           # alt klasor taranmadi
        assert len(report.unsupported) == 0     # .txt glob'da elenir
        assert len(report.failed) == 1          # bozuk.jpg
        assert len(s) == 3

    def test_recursive_includes_subfolders(self, photo_dir: Path) -> None:
        s = Session()
        report = s.add_paths([photo_dir], recursive=True)
        assert len(report.added) == 4
        assert any(e.name == "delta.jpg" for e in report.added)

    def test_subfolders_excluded_by_default(self, photo_dir: Path) -> None:
        """Alt klasor taramasi acik bir secenek olmali, varsayilan degil."""
        s = Session()
        s.add_paths([photo_dir])
        assert not any(e.name == "delta.jpg" for e in s)

    def test_explicit_unsupported_file_is_reported(self, photo_dir: Path) -> None:
        s = Session()
        report = s.add_paths([photo_dir / "notlar.txt"])
        assert len(report.unsupported) == 1
        assert not report.added

    def test_broken_file_does_not_stop_the_rest(self, photo_dir: Path) -> None:
        """Bir bozuk dosya tum ice aktarmayi cokertmemeli."""
        s = Session()
        files = sorted(p for p in photo_dir.iterdir() if p.is_file())
        report = s.add_paths(files)
        assert len(report.added) == 3
        assert len(report.failed) == 1
        assert report.failed[0][0].name == "bozuk.jpg"
        assert len(report.unsupported) == 1   # notlar.txt

    def test_duplicates_are_skipped(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        report = s.add_paths([photo_dir])
        assert report.skipped_duplicates == 3
        assert not report.added
        assert len(s) == 3

    def test_summary_is_turkish_and_informative(self, photo_dir: Path) -> None:
        s = Session()
        report = s.add_paths(sorted(p for p in photo_dir.iterdir() if p.is_file()))
        text = report.summary()
        assert "eklendi" in text
        assert "okunamadı" in text

    def test_metadata_is_probed(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        entry = next(iter(s))
        assert entry.metadata is not None
        assert entry.metadata.width == 720
        assert entry.dimensions_label == "720 × 480"
        assert entry.size_bytes > 0


class TestNavigation:
    def test_first_import_selects_first_photo(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        assert s.current_index == 0
        assert s.current is not None

    def test_next_and_previous(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        assert s.can_go_next()
        assert not s.can_go_previous()
        assert s.next_photo()
        assert s.current_index == 1
        assert s.previous_photo()
        assert s.current_index == 0

    def test_navigation_does_not_wrap(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        for _ in range(10):
            s.next_photo()
        assert s.current_index == len(s) - 1
        assert not s.can_go_next()
        assert not s.next_photo()

    def test_empty_session_has_no_current(self) -> None:
        s = Session()
        assert s.current is None
        assert s.current_index == -1
        assert not s.next_photo()


class TestSorting:
    def test_sorts_by_name(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.set_sort(SortKey.NAME)
        assert [e.name for e in s] == ["alfa.png", "bravo.jpg", "charlie.webp"]

    def test_descending_reverses(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.set_sort(SortKey.NAME, descending=True)
        assert [e.name for e in s][0] == "charlie.webp"

    def test_current_photo_survives_resort(self, photo_dir: Path) -> None:
        """Siralama degisince kullanicinin bakitigi fotograf kaybolmamali."""
        s = Session()
        s.add_paths([photo_dir])
        s.set_sort(SortKey.NAME)
        s.set_current(2)
        watching = s.current.path
        s.set_sort(SortKey.NAME, descending=True)
        assert s.current is not None
        assert s.current.path == watching

    def test_sort_by_size(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.set_sort(SortKey.SIZE)
        sizes = [e.size_bytes for e in s]
        assert sizes == sorted(sizes)


class TestFilters:
    def test_search_filters_by_name(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.set_search("alfa")
        assert [e.name for e in s.visible] == ["alfa.png"]
        assert len(s) == 3  # filtre kitapligi kucultmez

    def test_search_is_case_insensitive(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.set_search("ALFA")
        assert len(s.visible) == 1

    def test_search_matches_folder_name(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir], recursive=True)
        s.set_search("alt klasor")
        assert [e.name for e in s.visible] == ["delta.jpg"]

    def test_favourites_filter(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.toggle_favourite(1)
        s.set_favourites_only(True)
        assert len(s.visible) == 1
        assert s.visible[0].favourite

    def test_toggle_favourite_is_reversible(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        assert s.toggle_favourite(0) is True
        assert s.toggle_favourite(0) is False


class TestMissingFiles:
    def test_detects_removed_file(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        target = s.entries[0].path
        target.unlink()
        changed = s.refresh_missing()
        assert len(changed) == 1
        assert changed[0].missing

    def test_relocate_updates_path(self, photo_dir: Path, tmp_path: Path,
                                   color_patches: np.ndarray) -> None:
        s = Session()
        s.add_paths([photo_dir])
        old = s.entries[0].path
        new = tmp_path / "tasindi" / old.name
        save_image(color_patches, new, SaveOptions(fmt=OutputFormat.PNG))
        assert s.relocate(old, new)
        assert s.index_of(new) >= 0
        assert s.index_of(old) < 0

    def test_relocate_rejects_nonexistent_target(self, photo_dir: Path,
                                                 tmp_path: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        assert not s.relocate(s.entries[0].path, tmp_path / "yok.jpg")


class TestRemoval:
    def test_remove_does_not_delete_from_disk(self, photo_dir: Path) -> None:
        """Kitapliktan cikarmak kullanicinin fotografini silmemeli."""
        s = Session()
        s.add_paths([photo_dir])
        path = s.entries[0].path
        assert s.remove([0]) == 1
        assert path.exists()
        assert len(s) == 2

    def test_clear_empties_session(self, photo_dir: Path) -> None:
        s = Session()
        s.add_paths([photo_dir])
        s.clear()
        assert len(s) == 0
        assert s.current is None


class TestListeners:
    def test_listener_is_notified_on_change(self, photo_dir: Path) -> None:
        s = Session()
        calls: list[int] = []
        s.add_listener(lambda: calls.append(1))
        s.add_paths([photo_dir])
        assert calls

    def test_import_notifies_exactly_once(self, photo_dir: Path) -> None:
        """Tek ice aktarma kitapligi iki kez yeniden kurmamali."""
        s = Session()
        calls: list[int] = []
        s.add_listener(lambda: calls.append(1))
        s.add_paths([photo_dir])
        assert len(calls) == 1

    def test_failing_listener_does_not_break_others(self, photo_dir: Path) -> None:
        s = Session()
        seen: list[str] = []

        def bad() -> None:
            raise RuntimeError("bilerek hata")

        s.add_listener(bad)
        s.add_listener(lambda: seen.append("ok"))
        s.add_paths([photo_dir])
        assert seen, "hatali dinleyici digerini engellemis"

"""Kurulum betigi, uygulamanin gercekte kullandigi yollarla tutarli olmali.

Bulgu: kaldirici `%LOCALAPPDATA%\\Luma Atelier` (boslukla) klasorunu
siliyordu. Uygulama ise ayarlarini `%APPDATA%\\LumaAtelier`, onbellegini
`%LOCALAPPDATA%\\LumaAtelier\\cache` altina yaziyor. O klasor hic
olusmadigi icin kullanicinin "uygulama verileri de silinsin" secimi
**hicbir sey yapmiyordu** - kaldirmadan sonra ayarlar ve ozel presetler
sessizce yerinde kaliyordu.

Bu kontrol iki tarafin ayni yolu kullandigini dogrular; ileride
`paths.py` degisirse kurulum betigi sessizce eskimez.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from luma_atelier.core.branding import PROJECT_EXTENSION

ISS = Path(__file__).resolve().parents[1] / "packaging" / "LumaAtelier.iss"


@pytest.fixture(scope="module")
def script() -> str:
    return ISS.read_text(encoding="utf-8")


class TestUninstallTargetsRealFolders:
    def test_settings_folder_matches_paths_module(self, script: str,
                                                  monkeypatch) -> None:  # noqa: ANN001
        from luma_atelier.core import paths

        monkeypatch.delenv("LUMA_DATA_HOME", raising=False)
        leaf = paths.APP_SLUG
        assert re.search(rf"\{{userappdata\}}\\{re.escape(leaf)}'", script), (
            f"kaldirici {leaf} klasorunu hedeflemiyor"
        )

    def test_cache_folder_matches_paths_module(self, script: str,
                                               monkeypatch) -> None:  # noqa: ANN001
        from luma_atelier.core import paths

        monkeypatch.delenv("LUMA_DATA_HOME", raising=False)
        # cache_dir() -> ...\LumaAtelier\cache; kaldirici ust klasoru siler
        root = paths.APP_SLUG
        assert re.search(rf"\{{localappdata\}}\\{re.escape(root)}'", script)

    def test_no_other_data_folder_is_targeted(self, script: str) -> None:
        """Kod yalnizca gercekten var olan iki klasoru genisletmeli.

        Aciklama satirlari disarida: eski (yanlis) yol orada **ornek**
        olarak geciyor.
        """
        from luma_atelier.core import paths

        expanded = re.findall(r"ExpandConstant\('([^']+)'\)", script)
        assert expanded, "ExpandConstant cagrisi yok"
        allowed = {
            "{userappdata}\\" + paths.APP_SLUG,
            "{localappdata}\\" + paths.APP_SLUG,
        }
        assert set(expanded) == allowed, (
            f"beklenmeyen klasor hedefi: {sorted(set(expanded) - allowed)}"
        )


class TestUpgradeAndUninstallSafety:
    def test_old_internal_folder_is_cleared_on_upgrade(self,
                                                       script: str) -> None:
        """Eski surumun kutuphaneleri yerinde kalmamali."""
        assert "[InstallDelete]" in script
        assert re.search(r"Name:\s*\"\{app\}\\_internal\"", script)

    def test_user_folders_are_not_in_installdelete(self, script: str) -> None:
        """Kurulum, kullanici verisini silme listesine koymamali."""
        block = script.split("[InstallDelete]", 1)[1].split("[", 1)[0]
        assert "userappdata" not in block
        assert "localappdata" not in block
        assert "userpictures" not in block.lower()

    def test_output_folder_is_never_deleted(self, script: str) -> None:
        """Disa aktarma klasoru hicbir kosulda silinmemeli."""
        assert "DelTree" in script
        deleted = re.findall(r"DelTree\((\w+)\(\)", script)
        assert set(deleted) <= {"SettingsDir", "CacheDir"}, deleted


class TestProjectAssociation:
    def test_extension_matches_the_application(self, script: str) -> None:
        assert f'#define ProjectExt   "{PROJECT_EXTENSION}"' in script.replace(
            "ProjectExt     ", "ProjectExt   ")

    def test_open_command_passes_the_file(self, script: str) -> None:
        assert '""%1""' in script, "iliskilendirme dosya yolunu gecirmiyor"

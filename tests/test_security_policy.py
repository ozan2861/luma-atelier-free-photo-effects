from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.security_audit import (
    audit_network_imports,
    audit_personal_paths,
    audit_repository,
    audit_secrets,
)


ROOT = Path(__file__).resolve().parents[1]


def test_test_suite_redirects_application_data_outside_user_profile() -> None:
    data_home = os.environ.get("LUMA_DATA_HOME")

    assert data_home, "Tests must never write to the real application-data folder"
    resolved = Path(data_home).resolve()
    for variable in ("APPDATA", "LOCALAPPDATA"):
        profile_root = os.environ.get(variable)
        if profile_root:
            real_data_root = (Path(profile_root) / "LumaAtelier").resolve()
            assert not resolved.is_relative_to(real_data_root)


def test_secret_audit_reports_without_echoing_the_secret(tmp_path: Path) -> None:
    secret = "ghp_" + "A" * 36
    (tmp_path / "config.py").write_text(
        "ACCESS_" + f'TOKEN = "{secret}"\n', encoding="utf-8"
    )

    findings = audit_secrets(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "secret"
    assert findings[0].path == Path("config.py")
    assert secret not in repr(findings)


def test_network_audit_rejects_client_imports_in_application_code(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "luma_atelier"
    source.mkdir(parents=True)
    (source / "remote.py").write_text("import requests\n", encoding="utf-8")

    findings = audit_network_imports(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "network-import"
    assert findings[0].path == Path("src/luma_atelier/remote.py")


def test_personal_path_audit_allows_placeholder_but_rejects_real_user(
    tmp_path: Path,
) -> None:
    (tmp_path / "unsafe.md").write_text(
        "C:" + "\\Users\\Alice\\Pictures\\photo.jpg\n", encoding="utf-8"
    )
    (tmp_path / "safe.md").write_text(
        "C:" + "\\Users\\<kullanici>\\Pictures\\photo.jpg\n", encoding="utf-8"
    )

    findings = audit_personal_paths(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "personal-path"
    assert findings[0].path == Path("unsafe.md")


def test_repository_has_no_secret_network_or_personal_path_findings() -> None:
    assert audit_repository(ROOT) == []


@pytest.mark.parametrize(
    "relative_path",
    [
        ".coverage",
        "coverage.xml",
        "htmlcov/index.html",
        ".ruff_cache/state.json",
        ".mypy_cache/state.json",
        ".idea/workspace.xml",
        ".vscode/settings.json",
        "local.log",
    ],
)
def test_local_development_artifacts_are_ignored_by_git(
    relative_path: str,
) -> None:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT}",
            "check-ignore",
            "--quiet",
            relative_path,
        ],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, f"Git must ignore {relative_path}"

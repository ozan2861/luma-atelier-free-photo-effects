from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from luma_atelier.storage.project import (
    PROJECT_NAME,
    ProjectError,
    load_project,
    project_preview,
)


def _project_json(*, padding_bytes: int = 0) -> str:
    return json.dumps({
        "version": 1,
        "source": {"path": "photo.jpg"},
        "recipe": {},
        "padding": "A" * padding_bytes,
    })


def test_project_rejects_oversized_decompressed_json(tmp_path: Path) -> None:
    archive = tmp_path / "oversized.luma"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(PROJECT_NAME, _project_json(padding_bytes=8 * 1024 * 1024))

    with pytest.raises(ProjectError, match="proje verisi.*buyuk"):
        load_project(archive)


def test_project_preview_refuses_oversized_member(tmp_path: Path) -> None:
    archive = tmp_path / "preview-bomb.luma"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("preview.jpg", b"0" * (32 * 1024 * 1024 + 1))

    assert project_preview(archive) is None


def test_project_rejects_archives_with_excessive_member_count(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "too-many-members.luma"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        bundle.writestr(PROJECT_NAME, _project_json())
        for index in range(256):
            bundle.writestr(f"unused/{index}.txt", b"")

    with pytest.raises(ProjectError, match="cok fazla dosya"):
        load_project(archive)


@pytest.mark.parametrize("payload", [b"[]", b"\xff\xfe\xfd"])
def test_project_wraps_malformed_structural_data(
    tmp_path: Path,
    payload: bytes,
) -> None:
    archive = tmp_path / "malformed.luma"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        bundle.writestr(PROJECT_NAME, payload)

    with pytest.raises(ProjectError, match="proje verisi"):
        load_project(archive)

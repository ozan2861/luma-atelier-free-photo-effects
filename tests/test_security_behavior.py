from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from luma_atelier.app.shell import MainWindow
from luma_atelier.services.render import RenderService


def test_photo_loaded_callback_rejects_non_array_payload() -> None:
    path = Path("photo.png")
    window = SimpleNamespace(
        _load_token=7,
        session=SimpleNamespace(current=SimpleNamespace(path=path)),
    )

    with pytest.raises(TypeError, match="pixels"):
        MainWindow._on_photo_loaded(window, 7, str(path), object(), object())


def test_export_finished_callback_rejects_invalid_summary() -> None:
    with pytest.raises(TypeError, match="ExportSummary"):
        MainWindow._on_export_finished(object(), object())


def test_settings_callback_rejects_invalid_settings() -> None:
    with pytest.raises(TypeError, match="Settings"):
        MainWindow._apply_settings(object(), object())


def test_render_callback_rejects_invalid_result(qapp) -> None:  # noqa: ANN001
    service = RenderService()
    try:
        with pytest.raises(TypeError, match="RenderResult"):
            service._on_done(object())
    finally:
        service.shutdown()

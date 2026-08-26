# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

import prodockit.environment as environment
from prodockit.environment import BuildEnvironmentError, check_pdf_environment, requirement_floors


def _project(tmp_path: Path, requirements: str) -> Path:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Test"\n', encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")
    return config


def test_requirement_floors_are_read_relative_to_the_selected_config(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "# build tools\nzensical>=0.0.57  # tested floor\nprodockit[index]>=0.47.0\n",
    )

    assert [(floor.package, floor.version) for floor in requirement_floors(config)] == [
        ("zensical", "0.0.57"),
        ("prodockit", "0.47.0"),
    ]


def test_old_active_zensical_is_rejected_before_the_pdf_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, "zensical>=0.0.57\n")
    monkeypatch.setattr(environment, "_zensical_cli", lambda: "/project/.venv/bin/zensical")
    monkeypatch.setattr(environment, "_installed_zensical_version", lambda _command: "0.0.53")

    with pytest.raises(BuildEnvironmentError) as caught:
        check_pdf_environment(config)

    message = str(caught.value)
    assert "zensical 0.0.53 is active" in message
    assert "requires zensical>=0.0.57" in message
    assert "Active Python:" in message
    assert "-m pip install -r" in message


def test_matching_or_newer_active_zensical_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, "zensical>=0.0.57\n")
    monkeypatch.setattr(environment, "_zensical_cli", lambda: "/project/.venv/bin/zensical")
    monkeypatch.setattr(environment, "_installed_zensical_version", lambda _command: "0.0.58")

    check_pdf_environment(config)


def test_project_without_a_runtime_floor_keeps_existing_pdf_behaviour(tmp_path: Path) -> None:
    config = _project(tmp_path, "beautifulsoup4\n")

    check_pdf_environment(config)

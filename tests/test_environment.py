# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest
from click.testing import CliRunner

import prodockit.environment as environment
from prodockit.environment import BuildEnvironmentError, check_pdf_environment, requirement_floors


@pytest.mark.parametrize(
    "arguments",
    [
        ["diag"],
        ["diag", "--json"],
        ["adopt", "--dry-run"],
        ["adopt", "--apply"],
        ["adopt", "--configure"],
        ["template-sync"],
        ["template-sync", "--apply"],
    ],
)
def test_commands_reject_parent_environment_before_work(tmp_path, monkeypatch, arguments):
    from prodockit.cli import main

    project = tmp_path / "project"
    project.mkdir()
    (project / ".venv").mkdir()
    config = _project(project, "prodockit>=0.61.0\n")
    monkeypatch.chdir(project)
    monkeypatch.setattr(environment.sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(environment.sys, "base_prefix", str(tmp_path / "base"))
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / ".venv"))
    before = config.read_bytes()

    result = CliRunner().invoke(main, arguments)

    assert result.exit_code != 0, result.output
    assert "Active Python is not the project's .venv" in result.output
    assert "activate" in result.output.lower()
    if arguments[0] == "diag":
        assert "project environment: .venv" in result.output
        assert "WeasyPrint" not in result.output
        assert "Adopt has" not in result.output
    else:
        assert str(project / ".venv") in result.output
    assert config.read_bytes() == before
    assert not (project / ".prodockit-components.toml").exists()


def test_adopt_warns_about_parent_environment_before_project_venv_exists(tmp_path, monkeypatch):
    from prodockit.cli import main

    project = tmp_path / "project"
    project.mkdir()
    config = _project(project, "prodockit>=0.61.0\n")
    monkeypatch.chdir(project)
    monkeypatch.setattr(environment.sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(environment.sys, "base_prefix", str(tmp_path / "base"))
    before = config.read_bytes()

    result = CliRunner().invoke(main, ["adopt", "--dry-run"])

    assert "WARNING: No project-local .venv" in result.output
    assert "No project-local .venv is set up" in result.output
    assert str(tmp_path / ".venv") in result.output
    assert config.read_bytes() == before
    assert not (project / ".prodockit-components.toml").exists()


def test_project_environment_accepts_matching_prefix_and_no_local_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(environment.sys, "prefix", str(tmp_path / ".venv"))
    assert environment.project_environment_problem(tmp_path) is None
    (tmp_path / ".venv").mkdir()
    assert environment.project_environment_problem(tmp_path) is None


def test_project_environment_activation_command_matches_the_platform(monkeypatch):
    monkeypatch.setattr(environment.os, "name", "nt")
    assert environment.project_environment_activation_command() == r".\.venv\Scripts\Activate.ps1"
    monkeypatch.setattr(environment.os, "name", "posix")
    assert environment.project_environment_activation_command() == "source .venv/bin/activate"


def test_adopt_without_venv_warns_and_allows_preview(tmp_path, monkeypatch):
    import prodockit.cli as cli

    _project(tmp_path, "prodockit>=0.61.0\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(environment.sys, "prefix", environment.sys.base_prefix)
    monkeypatch.setattr(cli, "assess_adoption", lambda *args, **kwargs: [])
    result = CliRunner().invoke(cli.main, ["adopt", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "WARNING: No virtual environment is active" in result.output
    assert "running Python installation" in result.output


def test_pins_warns_about_other_environment_without_installing(tmp_path, monkeypatch):
    from prodockit.cli import main

    _project(tmp_path, "prodockit>=0.61.0\n")
    (tmp_path / ".venv").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(environment.sys, "prefix", str(tmp_path / "other"))
    result = CliRunner().invoke(main, ["pins", "--check", "--offline"])
    assert "WARNING: Active Python is not the project's .venv" in result.output
    assert "it changes declarations, not installed packages" in result.output
    assert "tested with installed prodockit" in result.output


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
    monkeypatch.setattr(environment, "_installed_zensical_version", lambda: "0.0.53")

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
    monkeypatch.setattr(environment, "_installed_zensical_version", lambda: "0.0.58")

    check_pdf_environment(config)


def test_project_without_a_runtime_floor_keeps_existing_pdf_behaviour(tmp_path: Path) -> None:
    config = _project(tmp_path, "beautifulsoup4\n")

    check_pdf_environment(config)

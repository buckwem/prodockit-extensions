# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.pdf import python_requirements as requirements


def _project(tmp_path: Path, source: str = requirements.STANDARD_REQUIREMENTS) -> Path:
    (tmp_path / "zensical.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / requirements.REQUIREMENTS_NAME).write_text(source, encoding="utf-8")
    return tmp_path


def test_cold_prepare_installs_once_then_warm_prepare_never_invokes_pip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    installed: dict[str, str] | None = None
    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(requirements, "_installed_versions", lambda _items: installed)
    monkeypatch.setattr(
        requirements,
        "_fresh_versions",
        lambda _items: {"weasyprint": "69.0"},
    )
    monkeypatch.setattr(requirements, "_probe", lambda _items: None)

    def run(command, **_kwargs):
        nonlocal installed
        commands.append(command)
        installed = {"weasyprint": "69.0"}

    monkeypatch.setattr(requirements, "run_install_command", run)

    cold = requirements.prepare_pdf_python_requirements(project / "zensical.toml")
    warm = requirements.prepare_pdf_python_requirements(project / "zensical.toml")

    assert cold.cached is False
    assert warm.cached is True
    assert len(commands) == 1
    assert commands[0][-2:] == ("-r", str(project / requirements.REQUIREMENTS_NAME))
    assert requirements.cache_manifest_path(project).is_file()


def test_existing_satisfactory_install_is_recorded_without_running_pip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(
        requirements,
        "_installed_versions",
        lambda _items: {"weasyprint": "70.0"},
    )
    monkeypatch.setattr(requirements, "_probe", lambda _items: None)
    monkeypatch.setattr(
        requirements,
        "run_install_command",
        lambda *_args, **_kwargs: pytest.fail("pip must not run"),
    )

    result = requirements.prepare_pdf_python_requirements(project / "zensical.toml")

    assert result.cached is False
    assert result.versions == {"weasyprint": "70.0"}


def test_failed_install_leaves_no_manifest_and_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    installed: dict[str, str] | None = None
    attempts = 0
    monkeypatch.setattr(requirements, "_installed_versions", lambda _items: installed)
    monkeypatch.setattr(
        requirements, "_fresh_versions", lambda _items: {"weasyprint": "69.0"}
    )
    monkeypatch.setattr(requirements, "_probe", lambda _items: None)

    def run(*_args, **_kwargs) -> None:
        nonlocal attempts, installed
        attempts += 1
        if attempts == 1:
            raise requirements.ToolchainError("package index unavailable")
        installed = {"weasyprint": "69.0"}

    monkeypatch.setattr(requirements, "run_install_command", run)

    with pytest.raises(
        requirements.PdfPythonRequirementsError, match="package index unavailable"
    ):
        requirements.prepare_pdf_python_requirements(project / "zensical.toml")
    assert not requirements.cache_manifest_path(project).exists()

    result = requirements.prepare_pdf_python_requirements(project / "zensical.toml")

    assert attempts == 2
    assert result.cached is False
    assert requirements.cache_manifest_path(project).is_file()


def test_index_adds_pymupdf_only_when_the_index_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    captured = []
    monkeypatch.setattr(requirements, "_installed_versions", lambda _items: None)
    monkeypatch.setattr(
        requirements,
        "_fresh_versions",
        lambda items: {requirement.name.lower(): "69.0" for requirement in items},
    )
    monkeypatch.setattr(requirements, "_probe", lambda items: captured.extend(items))
    monkeypatch.setattr(requirements, "run_install_command", lambda *_args, **_kwargs: None)

    requirements.prepare_pdf_python_requirements(
        project / "zensical.toml", include_index=True
    )

    assert {item.name.lower() for item in captured} == {"weasyprint", "pymupdf"}


def test_windows_never_installs_python_weasyprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(requirements.sys, "platform", "win32")
    monkeypatch.setattr(
        requirements,
        "run_install_command",
        lambda *_args, **_kwargs: pytest.fail("there are no Python packages to install"),
    )
    monkeypatch.setattr(requirements, "_probe", lambda _items: None)

    result = requirements.prepare_pdf_python_requirements(project / "zensical.toml")

    assert result.versions == {}


def test_automatic_requirements_reject_arbitrary_packages(tmp_path: Path) -> None:
    project = _project(tmp_path, "requests>=2\n")

    with pytest.raises(requirements.PdfPythonRequirementsError, match="only PDF runtime"):
        requirements.prepare_pdf_python_requirements(project / "zensical.toml")


def test_prepare_refuses_to_install_outside_an_existing_project_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    (project / ".venv").mkdir()
    monkeypatch.setattr(
        requirements,
        "run_install_command",
        lambda *_args, **_kwargs: pytest.fail("pip must not run in the wrong environment"),
    )

    with pytest.raises(
        requirements.PdfPythonRequirementsError,
        match=r"Active Python is not the project's \.venv",
    ):
        requirements.prepare_pdf_python_requirements(project / "zensical.toml")


def test_changed_environment_identity_invalidates_the_warm_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(
        requirements,
        "_installed_versions",
        lambda _items: {"weasyprint": "69.0"},
    )
    monkeypatch.setattr(requirements, "_probe", lambda _items: None)

    first = requirements.prepare_pdf_python_requirements(project / "zensical.toml")
    monkeypatch.setattr(
        requirements,
        "_environment_identity",
        lambda: {"executable": "/different/project/.venv/bin/python"},
    )
    second = requirements.prepare_pdf_python_requirements(project / "zensical.toml")

    assert first.cached is False
    assert second.cached is False


def test_established_state_distinguishes_a_removed_package_from_a_clean_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    installed: dict[str, str] | None = {"weasyprint": "69.0"}
    monkeypatch.setattr(requirements, "_installed_versions", lambda _items: installed)
    monkeypatch.setattr(requirements, "_probe", lambda _items: None)

    requirements.prepare_pdf_python_requirements(project / "zensical.toml")
    installed = None

    assert requirements.pdf_python_requirements_established(project / "zensical.toml")
    assert not requirements.pdf_python_requirements_prepared(project / "zensical.toml")

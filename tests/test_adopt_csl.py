# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Adopt owns the known citation-style prerequisite without guessing custom ones."""

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit import diagnostics
from prodockit.adopt import AdoptOptions, apply_step, assess
from prodockit.pins import TESTED_VERSIONS


@pytest.fixture(autouse=True)
def _supported_toolchain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "prodockit.toolchain.installed_python_version", lambda: TESTED_VERSIONS["python"]
    )
    monkeypatch.setattr(
        "prodockit.toolchain.installed_distribution_version",
        lambda package: TESTED_VERSIONS[package],
    )
    monkeypatch.setattr(
        "prodockit.toolchain._fresh_distribution_versions",
        lambda packages: {package: TESTED_VERSIONS[package] for package in packages},
    )
    monkeypatch.setattr(
        "prodockit.toolchain.installed_pandoc_version", lambda: TESTED_VERSIONS["pandoc"]
    )
    monkeypatch.setattr("prodockit.adopt._interpreter_problem", lambda _root: None)


def _project(tmp_path: Path, style: str) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Existing document\n", encoding="utf-8")
    (tmp_path / "zensical.toml").write_text(
        "[project]\n"
        'site_name = "Existing document"\n\n'
        '[project.markdown_extensions."prodockit.bibliography"]\n'
        f'csl_style = "{style}"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_assessment_offers_the_supported_missing_csl_style(tmp_path: Path) -> None:
    project = _project(tmp_path, "harvard-cite-them-right.csl")

    activity = next(step for step in assess(project, AdoptOptions()) if step.id == "csl")

    assert activity.status == "missing"
    assert "harvard-cite-them-right.csl" in activity.detail
    assert "zotero.org/styles/harvard-cite-them-right" in activity.detail
    assert activity.files == (project / "harvard-cite-them-right.csl",)


def test_assessment_preserves_an_existing_csl_style(tmp_path: Path) -> None:
    project = _project(tmp_path, "styles/house.csl")
    style = project / "styles" / "house.csl"
    style.parent.mkdir()
    style.write_text("author supplied", encoding="utf-8")

    activity = next(step for step in assess(project, AdoptOptions()) if step.id == "csl")

    assert activity.status == "ok"
    assert "preserve" in activity.detail
    assert style.read_text(encoding="utf-8") == "author supplied"


def test_assessment_blocks_an_unknown_missing_csl_style_with_manual_guidance(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, "styles/house.csl")

    activity = next(step for step in assess(project, AdoptOptions()) if step.id == "csl")

    assert activity.status == "wrong"
    assert "trusted source" in activity.detail
    assert "download the intended CSL file" in activity.detail


def test_apply_csl_uses_the_configured_safe_path(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, "styles/harvard-cite-them-right.csl")
    observed = []

    def install(path: Path, *, offline: bool = False) -> Path:
        observed.append((path, offline))
        path.parent.mkdir(parents=True)
        path.write_text("installed", encoding="utf-8")
        return path

    monkeypatch.setattr("prodockit.adopt.install_csl", install)

    written = apply_step(project, AdoptOptions(), "csl", offline=True)

    expected = project / "styles" / "harvard-cite-them-right.csl"
    assert written == [expected]
    assert observed == [(expected, True)]


def test_diagnostics_names_the_missing_style_as_adopt_work(tmp_path: Path) -> None:
    project = _project(tmp_path, "harvard-cite-them-right.csl")

    check = diagnostics._adopt_readiness_checks(project, online=False)[0]

    assert check.status == "warn"
    assert "Citation style" in " ".join(check.details)
    assert "csl" in check.data["pending"]

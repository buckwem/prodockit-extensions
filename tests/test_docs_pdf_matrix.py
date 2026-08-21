# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Coverage contract for documentation's single-page PDF build matrix."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / ".github" / "docs-single-page-pdfs.toml"


def _nav_paths(items: list[Any]) -> list[str]:
    paths: list[str] = []
    for item in items:
        value = next(iter(item.values()))
        if isinstance(value, list):
            paths.extend(_nav_paths(value))
        else:
            paths.append(value)
    return paths


def _matrix() -> tuple[dict[str, list[str]], dict[str, str]]:
    data = read_config(MATRIX.read_text(encoding="utf-8"))
    assert data["version"] == 1
    return data["build"], data["covered"]


def _build_paths(groups: dict[str, list[str]]) -> list[str]:
    return [path for paths in groups.values() for path in paths]


def test_every_nav_page_has_an_explicit_single_page_pdf_decision() -> None:
    config = read_config((ROOT / "zensical.toml").read_text(encoding="utf-8"))
    nav = set(_nav_paths(config["project"]["nav"]))
    groups, covered = _matrix()
    builds = _build_paths(groups)

    assert len(builds) == len(set(builds)), "a representative is built more than once"
    assert set(builds).isdisjoint(covered), "a page is both built and marked covered"
    assert set(builds) | set(covered) == nav


def test_every_coverage_representative_is_really_built() -> None:
    groups, covered = _matrix()
    builds = set(_build_paths(groups))

    assert all(representative == "complete" or representative in builds for representative in covered.values())
    assert {path for path, representative in covered.items() if representative == "complete"} == {
        "index.md"
    }


def test_all_nine_authoring_extensions_use_the_single_page_path() -> None:
    groups, _ = _matrix()

    assert groups["authoring_extensions"] == [
        "extensions/headings.md",
        "extensions/refs.md",
        "extensions/citations.md",
        "extensions/glossary.md",
        "extensions/tables.md",
        "extensions/tree.md",
        "extensions/steps.md",
        "extensions/bibliography.md",
        "extensions/index-terms.md",
    ]


def test_each_audience_overview_uses_the_single_page_path() -> None:
    groups, _ = _matrix()

    assert groups["overviews"] == [
        "introduction.md",
        "authoring.md",
        "publishing.md",
        "project-maintenance.md",
        "devcons/devcons.md",
        "about/index.md",
    ]


def test_matrix_build_targets_exist() -> None:
    groups, _ = _matrix()

    missing = [path for path in _build_paths(groups) if not (ROOT / "docs" / path).is_file()]
    assert not missing


def test_documentation_workflow_consumes_the_reviewed_matrix() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")

    assert '.github/docs-single-page-pdfs.toml' in workflow
    assert 'subprocess.run(["prodockit", "pdf", "-m", path], check=True)' in workflow
    assert "prodockit pdf -m" not in workflow, "a hand-maintained build bypasses the matrix"

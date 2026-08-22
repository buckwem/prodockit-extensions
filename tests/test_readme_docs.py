# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The repository and PyPI landing page reflects the current public package."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_preserves_the_managed_badge_block() -> None:
    assert "<!-- repo-badges:start" in README
    assert "<!-- repo-badges:end -->" in README


def test_readme_routes_each_audience_to_the_right_guide() -> None:
    for target in (
        "https://buckwem.github.io/prodockit-userguide/",
        "https://github.com/buckwem/prodockit-template",
        "https://prodockit.org/getting-started/",
        "https://prodockit.org/authoring/",
        "https://prodockit.org/publishing/",
        "https://prodockit.org/about/support/",
        "CONTRIBUTING.md",
    ):
        assert target in README


def test_readme_describes_the_current_foundation_and_test_depth() -> None:
    for phrase in (
        "PyMdown Blocks",
        "prodockit.steps",
        "prodockit.tree",
        "Alpha",
        "Ubuntu",
        "Windows",
        "macOS",
        "Surrey GitLab",
        "GitHub.com",
        "full test suite",
    ):
        assert phrase in README

    assert "github.com has been run" not in README
    assert "not completed a clean run" not in README


def test_readme_distinguishes_python_and_external_pdf_requirements() -> None:
    for phrase in (
        "pip install prodockit",
        "pip install weasyprint",
        "Pandoc",
        "Pango",
        "prodockit[index]",
        "prodockit[testing]",
    ):
        assert phrase in README

    assert "weasyprint` - external binaries" not in README
    assert "No Python required" not in README


def test_readme_inventories_every_public_command_and_alias() -> None:
    for command in (
        "prodockit bootstrap",
        "prodockit init-tools",
        "prodockit init-mathjax",
        "prodockit pdf",
        "prodockit source-bundle",
        "prodockit sync-repo",
        "prodockit pins",
        "prodockit template-sync",
        "`pdk`",
        "`boot`",
        "`source`",
    ):
        assert command in README

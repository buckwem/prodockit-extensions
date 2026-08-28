# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The GitHub-facing contributor guide matches the maintained workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_contributing_links_to_the_detailed_site_guides() -> None:
    for target in (
        "docs/devcons/development.md",
        "docs/project-maintenance.md",
        "docs/devcons/releasing.md",
    ):
        assert target in GUIDE


def test_contributing_setup_is_copyable_and_names_external_pdf_tools() -> None:
    for phrase in (
        'python -m venv .venv',
        'python -m pip install -e ".[dev]"',
        "Pandoc",
        "WeasyPrint",
        "brew install pango",
        "export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib",
        "cannot load library 'libgobject-2.0-0'",
    ):
        assert phrase in GUIDE


def test_contributing_lists_the_complete_source_gates() -> None:
    for command in (
        "ruff check .",
        "mypy src",
        "prodockit pins --check --offline",
        "pytest",
        "zensical build --clean --strict",
        "git diff --check",
    ):
        assert command in GUIDE


def test_contributing_lists_the_pdf_and_built_output_gates_in_order() -> None:
    section = GUIDE.index("## Verify documentation and PDF changes")
    site = GUIDE.index("zensical build --clean --strict", section)
    pdf = GUIDE.index("prodockit pdf", site)
    built = GUIDE.index("python -m pytest tests/test_built_docs.py -m built -v", pdf)

    assert section < site < pdf < built

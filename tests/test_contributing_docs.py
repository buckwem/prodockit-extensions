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
        '"$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv',
        "py -3.14 -m venv .venv",
        "python3.14 -m venv .venv",
        'python -m pip install -e ".[dev]"',
        "Pandoc",
        "WeasyPrint",
        "brew install pango",
        'export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib',
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


def test_contributing_has_one_complete_ordered_setup_tab_per_platform() -> None:
    headings = (
        '=== ":material-apple: macOS"',
        '=== ":fontawesome-brands-windows: Windows PowerShell"',
        '=== ":material-linux: Linux (Ubuntu)"',
    )
    starts = [GUIDE.index(heading) for heading in headings]
    ends = [*starts[1:], GUIDE.index("Activate the environment before running commands")]

    for start, end in zip(starts, ends, strict=True):
        tab = GUIDE[start:end]
        clone = tab.index("git clone ")
        enter = min(
            position
            for command in ("cd prodockit-extensions", "Set-Location prodockit-extensions")
            if (position := tab.find(command)) >= 0
        )
        create = tab.index(" -m venv .venv")
        activate = (
            tab.index("Activate.ps1")
            if "PowerShell" in tab
            else tab.index("source .venv/bin/activate")
        )
        install = tab.index('python -m pip install -e ".[dev]"')
        assert clone < enter < create < activate < install

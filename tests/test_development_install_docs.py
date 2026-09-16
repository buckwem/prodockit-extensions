# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Development installs stay complete, linked, and confined to contributor guidance."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_INSTALL = "python -m pip install -r requirements-test.txt"
PLATFORMS = (
    '=== ":material-apple: macOS"',
    '=== ":fontawesome-brands-windows: Windows PowerShell"',
    '=== ":material-linux: Linux (Ubuntu)"',
)


def test_rendered_development_guide_has_three_complete_platform_tabs() -> None:
    guide = (ROOT / "docs/devcons/development.md").read_text(encoding="utf-8")

    for platform in PLATFORMS:
        assert platform in guide
    assert guide.count(TEST_INSTALL) == 3
    assert '"$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv' in guide
    assert "py -3.14 -m venv .venv" in guide
    assert "python3.14 -m venv .venv" in guide


def test_release_guide_links_directly_to_development_environment_setup() -> None:
    guide = (ROOT / "docs/devcons/releasing.md").read_text(encoding="utf-8")

    assert "[development environment](development.md#create-a-development-environment)" in guide


def test_dev_requirements_install_is_confined_to_contributor_setup_pages() -> None:
    allowed = {Path("CONTRIBUTING.md"), Path("docs/devcons/development.md")}
    found = {
        path.relative_to(ROOT)
        for path in (ROOT / "docs").rglob("*.md")
        if TEST_INSTALL in path.read_text(encoding="utf-8")
    }
    if TEST_INSTALL in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"):
        found.add(Path("CONTRIBUTING.md"))

    assert found == allowed


def test_requirements_entry_points_delegate_to_project_metadata() -> None:
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    testing = (ROOT / "requirements-test.txt").read_text(encoding="utf-8").splitlines()

    assert "." in runtime
    assert "-e .[dev]" in testing

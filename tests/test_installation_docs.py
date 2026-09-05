# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The requirements documentation against what the project actually declares.

The requirements table is read by people setting a machine up and edited
by nobody, which is the shape of documentation that goes quietly wrong.
It had `Markdown (>= 3.4)` long after the real floor moved to 3.10.3,
and omitted `pymdown-extensions` entirely - a dependency whose class
shapes `prodockit.pdf` matches on (prodockit-extensions#372).

Neither would break a build. Both would send a reader to install the
wrong thing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLATION = REPO / "docs" / "installation.md"
REQUIREMENTS = REPO / "docs" / "requirements-dependencies.md"
PYPROJECT = REPO / "pyproject.toml"
ADOPTION = REPO / "docs" / "adopt.md"
BOOTSTRAP_GUIDE = REPO / "docs" / "devcons" / "bootstrap.md"
POWERSHELL_POLICY = "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned"

if sys.version_info >= (3, 11):  # pragma: no cover - version-gated import
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def _declared() -> dict[str, str]:
    """Every runtime dependency and its floor, from `pyproject.toml`."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    wanted = list(project["dependencies"])
    # The index extra is documented in the same table, marked as optional.
    wanted += project.get("optional-dependencies", {}).get("index", [])

    floors: dict[str, str] = {}
    for spec in wanted:
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*>=\s*([0-9][\w.]*)", spec)
        if match:
            floors[match.group(1).lower()] = match.group(2)
    return floors


def test_every_declared_dependency_is_documented() -> None:
    """A dependency absent from the table is one a reader never installs
    deliberately - it arrives silently with `pip`, and its version is
    then nobody's decision."""
    page = REQUIREMENTS.read_text(encoding="utf-8").lower()

    missing = [name for name in _declared() if name not in page]

    assert not missing, f"not mentioned in requirements-dependencies.md: {missing}"


def test_the_documented_floors_match_the_declared_ones() -> None:
    """The failure this exists for: the page said `Markdown (>= 3.4)`
    while `pyproject.toml` said 3.10.3.

    Read as "the page names this floor somewhere for this package"
    rather than by parsing the table's shape, so the table can be
    rewritten freely - it is the *number* that must not drift.
    """
    page = REQUIREMENTS.read_text(encoding="utf-8").lower()
    wrong = []
    for name, floor in _declared().items():
        # The line that mentions the package must carry its floor.
        lines = [line for line in page.splitlines() if name in line]
        if not any(floor in line for line in lines):
            wrong.append(f"{name}: pyproject says >= {floor}, page does not")

    assert not wrong, "\n".join(wrong)


def test_pandoc_and_weasyprint_are_not_filed_as_the_same_kind_of_thing() -> None:
    """One is a `pip install` away and the other is not.

    Both used to be labelled "(external binary)". A reader who treats
    them alike goes looking for a pandoc package that does not exist, or
    misses a weasyprint one that does.
    """
    page = REQUIREMENTS.read_text(encoding="utf-8")

    assert "A Python package, but not a dependency of prodockit" in page
    assert "Genuinely not a Python package" in page


def test_the_versions_bootstrap_enforces_are_the_ones_documented() -> None:
    """`prodockit bootstrap` refuses a pandoc below `PANDOC_MIN_MAJOR`
    and installs `PANDOC_VERSION`; it wants Node `NODE_MAJOR`. A reader
    following this page should end up with a machine bootstrap agrees
    with, rather than one it then argues about.
    """
    from prodockit.bootstrap.stages import NODE_MAJOR, PANDOC_MIN_MAJOR, PANDOC_VERSION

    page = REQUIREMENTS.read_text(encoding="utf-8")

    assert f">= {PANDOC_MIN_MAJOR}" in page, "the pandoc floor is not stated"
    assert PANDOC_VERSION in page, "the pinned pandoc release is not stated"
    assert f"Node >= {NODE_MAJOR}" in page, "the Node major version is not stated"


def test_every_documented_powershell_activation_sets_the_execution_policy() -> None:
    """Keep every copyable PowerShell activation sequence usable on clean Windows."""
    paths = [REPO / "CONTRIBUTING.md", *(REPO / "docs").rglob("*.md")]
    paths.append(REPO / "tests" / "adopt_install" / "README.md")
    checked = 0

    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if r".\.venv\Scripts\Activate.ps1" not in line:
                continue
            checked += 1
            assert index and lines[index - 1].strip() == POWERSHELL_POLICY, (
                f"{path.relative_to(REPO)}:{index + 1} activates PowerShell without first "
                "setting the CurrentUser execution policy"
            )

    assert checked > 1, "the documentation activation audit did not find every usage"


def test_installation_preparation_is_shared_by_later_routes() -> None:
    preparation_page = INSTALLATION.read_text(encoding="utf-8")
    preparation = preparation_page[
        preparation_page.index("## Prepare Python and its environment") :
        preparation_page.index("## From PyPI")
    ]

    for command in (
        "brew install python@3.14",
        '"$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv',
        "py -3.14 --version",
        "py -3.14 -m venv .venv",
        "sudo apt install python3.14 python3.14-venv python3-pip",
        "python3.14 -m venv .venv",
        "python --version",
    ):
        assert command in preparation

    assert preparation.count("//// step | ") == 4
    assert preparation.count('=== ":material-apple: macOS"') == 4
    assert preparation.count('=== ":fontawesome-brands-windows: Windows"') == 4
    assert preparation.count('=== ":material-linux: Linux (Ubuntu)"') == 4

    routes = (
        ADOPTION,
        BOOTSTRAP_GUIDE,
        REPO / "docs" / "prodockit-template.md",
        REPO / "docs" / "getting-started.md",
    )
    for route in routes:
        page = route.read_text(encoding="utf-8")
        assert "installation.md#installation-preparation" in page
        assert "brew install python@3.14" not in page
        assert "py -3.14 -m venv .venv" not in page
        assert "python3.14 -m venv .venv" not in page


def test_adoption_continues_after_shared_preparation() -> None:
    page = ADOPTION.read_text(encoding="utf-8")

    assert "python -m pip install --upgrade prodockit" in page

    assert "MkDocs" not in page

    review = page[page.index("## Review the existing project") : page.index("## Choose optional")]
    assert review.count("//// step | ") == 2

    resume = page[page.index("## Run it again safely") :]
    assert '=== ":material-apple: macOS"' in resume
    assert '=== ":fontawesome-brands-windows: Windows"' in resume
    assert '=== ":material-linux: Linux (Ubuntu)"' in resume
    assert "python --version\nprodockit adopt --apply" in resume


def test_prodockit_is_not_presented_as_supporting_mkdocs() -> None:
    """MkDocs may only be named for compatibility or configuration filenames."""
    paths = [
        REPO / "README.md",
        *(REPO / "docs").rglob("*.md"),
        *(REPO / "src" / "prodockit").rglob("*.py"),
    ]
    unsupported_phrases = (
        "zensical or mkdocs",
        "mkdocs document",
        "mkdocs project",
    )
    violations: list[str] = []

    for path in paths:
        contents = path.read_text(encoding="utf-8").lower()
        for phrase in unsupported_phrases:
            if phrase in contents:
                violations.append(f"{path.relative_to(REPO)}: {phrase}")

    assert not violations, "MkDocs is not a supported Prodockit generator:\n" + "\n".join(
        violations
    )


def test_bootstrap_continues_after_shared_preparation() -> None:
    page = BOOTSTRAP_GUIDE.read_text(encoding="utf-8")

    installation = page[
        page.index("## Install with bootstrap") : page.index("## What it covers")
    ]
    assert "installation.md#installation-preparation" in installation
    assert installation.count("//// step | ") == 5
    assert "//// step | Install Prodockit into the active environment" in installation
    confirm = installation[installation.index("//// step | Confirm") :]
    assert '!!! warning "Complete the manual step before confirming"' in confirm
    assert "Type `yes` only after checking that the action succeeded" in " ".join(confirm.split())
    assert "python3.14 -m venv" not in installation
    assert "py -3.14 -m venv" not in installation

    for legacy_tab in ('=== "macOS"', '=== "Windows"', '=== "Ubuntu"'):
        assert legacy_tab not in page

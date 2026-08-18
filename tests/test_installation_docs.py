# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""`docs/installation.md` against what the project actually declares.

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
PYPROJECT = REPO / "pyproject.toml"

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
    page = INSTALLATION.read_text(encoding="utf-8").lower()

    missing = [name for name in _declared() if name not in page]

    assert not missing, f"not mentioned in installation.md: {missing}"


def test_the_documented_floors_match_the_declared_ones() -> None:
    """The failure this exists for: the page said `Markdown (>= 3.4)`
    while `pyproject.toml` said 3.10.3.

    Read as "the page names this floor somewhere for this package"
    rather than by parsing the table's shape, so the table can be
    rewritten freely - it is the *number* that must not drift.
    """
    page = INSTALLATION.read_text(encoding="utf-8").lower()
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
    page = INSTALLATION.read_text(encoding="utf-8")

    assert "A Python package, but not a dependency of prodockit" in page
    assert "Genuinely not a Python package" in page


def test_the_versions_bootstrap_enforces_are_the_ones_documented() -> None:
    """`prodockit bootstrap` refuses a pandoc below `PANDOC_MIN_MAJOR`
    and installs `PANDOC_VERSION`; it wants Node `NODE_MAJOR`. A reader
    following this page should end up with a machine bootstrap agrees
    with, rather than one it then argues about.
    """
    from prodockit.bootstrap.stages import NODE_MAJOR, PANDOC_MIN_MAJOR, PANDOC_VERSION

    page = INSTALLATION.read_text(encoding="utf-8")

    assert f">= {PANDOC_MIN_MAJOR}" in page, "the pandoc floor is not stated"
    assert PANDOC_VERSION in page, "the pinned pandoc release is not stated"
    assert f"Node >= {NODE_MAJOR}" in page, "the Node major version is not stated"

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Check that the active build environment satisfies a project's floors.

``prodockit pins --check`` compares declarations committed to the project.
This module deliberately does something different: it compares the tools
which are about to run with the requirements beside the selected project
configuration. Keeping the two checks separate makes pins deterministic in
CI while preventing a local PDF build from silently using an older venv.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from prodockit import __version__
from prodockit._zensical import _installed_zensical_version
from prodockit.pdf.site import _zensical_cli
from prodockit.template_sync import prodockit_upgrade_required


class BuildEnvironmentError(RuntimeError):
    """The active Python environment cannot satisfy the project build."""


@dataclass(frozen=True)
class RequirementFloor:
    package: str
    version: str
    path: Path


_FLOOR = re.compile(
    r"^\s*(?P<name>zensical|prodockit)(?:\[[\w.,\s-]*\])?\s*>=\s*"
    r"(?P<version>[0-9][\w.+!-]*)\s*$",
    re.IGNORECASE,
)


def _requirements_file(root: Path) -> Path | None:
    """Return the conventional requirements file used by this project."""
    for relative in ("requirements.txt", "requirements/docs.txt", "docs/requirements.txt"):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def requirement_floors(config_file: str | Path) -> list[RequirementFloor]:
    """Read relevant compatibility floors beside ``config_file``.

    Other requirement operators remain the responsibility of the package
    installer. Prodockit's templates and adoption workflow deliberately use
    ``>=`` floors for these two runtime tools, which is the mismatch this
    preflight is intended to make explicit.
    """
    config = Path(config_file).expanduser().resolve()
    requirements = _requirements_file(config.parent)
    if requirements is None:
        return []

    floors: list[RequirementFloor] = []
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        match = _FLOOR.fullmatch(line)
        if match:
            floors.append(
                RequirementFloor(
                    package=match.group("name").lower(),
                    version=match.group("version"),
                    path=requirements,
                )
            )
    return floors


def check_pdf_environment(config_file: str | Path) -> None:
    """Stop a PDF build whose active tools are below declared floors."""
    floors = requirement_floors(config_file)
    if not floors:
        return

    installed = {
        "prodockit": __version__,
        # Ask the same executable the public renderer will run, rather than
        # importing Zensical or accepting an unrelated command from PATH.
        "zensical": _installed_zensical_version(_zensical_cli()),
    }
    failures = [
        floor
        for floor in floors
        if installed[floor.package] == "unknown"
        or prodockit_upgrade_required(installed[floor.package], floor.version)
    ]
    if not failures:
        return

    requirements = failures[0].path
    details = "; ".join(
        f"{floor.package} {installed[floor.package]} is active, but "
        f"{requirements.name} requires {floor.package}>={floor.version}"
        for floor in failures
    )
    python = Path(sys.executable)
    raise BuildEnvironmentError(
        f"{details}. Active Python: {python}. Activate this project's virtual "
        f"environment and run `{python} -m pip install -r {requirements}`, then "
        "run `prodockit pdf` again."
    )

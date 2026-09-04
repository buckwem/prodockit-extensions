# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Environment prerequisites which precede a template-sync mutation.

The incoming template decides the Prodockit release.  This module deliberately
does not ask PyPI for its newest release: the package supplies code and managed
assets used by the update, so newest and compatible are different questions.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from prodockit.pins import discover
from prodockit.renderer_resilience import RetryReporter
from prodockit.template_sync import TemplateSyncError, prodockit_requirement
from prodockit.toolchain import (
    ToolchainError,
    pip_install_specifier_command,
    run_install_command,
)


@dataclass(frozen=True)
class ProdockitPrerequisite:
    """The exact package handoff required by the incoming template."""

    installed: str
    target: str
    extras: str
    command: tuple[str, ...]
    offline: bool = False

    @property
    def needs_work(self) -> bool:
        return self.installed != self.target

    @property
    def action(self) -> str:
        if not self.needs_work:
            return "check"
        try:
            installed = Version(self.installed)
            target = Version(self.target)
        except InvalidVersion:
            return "align"
        return "upgrade" if installed < target else "downgrade"

    @property
    def specifier(self) -> str:
        return f"prodockit{self.extras}=={self.target}"


def installed_prodockit_version() -> str:
    """Read distribution metadata without relying on already-imported code."""

    try:
        return importlib.metadata.version("prodockit")
    except importlib.metadata.PackageNotFoundError as error:
        raise TemplateSyncError(
            "the active interpreter has no installed Prodockit distribution; "
            "activate the project environment and rerun template-sync"
        ) from error


def template_prodockit_version(template: Path) -> tuple[str, str]:
    """Return the template's exact paired release and required extras.

    ``pins.discover`` reads all template declarations and applies the same
    highest-version rule already used when syncing an older, internally
    inconsistent template.  The requirements declaration supplies extras,
    which must survive an upgrade or downgrade.
    """

    state = discover(str(template), ("prodockit",))["prodockit"]
    if state.current is None:
        raise TemplateSyncError(
            "the incoming template does not declare a Prodockit version, so its "
            "compatible runtime cannot be determined; nothing has been changed"
        )
    requirements = template / "requirements.txt"
    requirement = (
        prodockit_requirement(requirements.read_text(encoding="utf-8"))
        if requirements.is_file()
        else None
    )
    extras = ""
    if requirement and "[" in requirement.specifier:
        extras = "[" + requirement.specifier.split("[", 1)[1].split("]", 1)[0] + "]"
    return state.current, extras


def plan_prodockit(
    template: Path,
    *,
    installed: str | None = None,
    offline: bool = False,
) -> ProdockitPrerequisite:
    target, extras = template_prodockit_version(template)
    current = installed if installed is not None else installed_prodockit_version()
    specifier = f"prodockit{extras}=={target}"
    return ProdockitPrerequisite(
        current,
        target,
        extras,
        pip_install_specifier_command((specifier,), offline=offline),
        offline,
    )


def install_prodockit(
    plan: ProdockitPrerequisite,
    *,
    root: Path,
    reporter: RetryReporter | None = None,
) -> None:
    """Install a planned exact release; verification belongs to fresh code."""

    if not plan.needs_work:
        return
    try:
        run_install_command(
            plan.command,
            root=root,
            reporter=reporter,
            offline=plan.offline,
        )
    except ToolchainError as error:
        raise TemplateSyncError(str(error)) from error

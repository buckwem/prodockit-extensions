# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Automate a full prodockit install on a new machine - `prodockit bootstrap`.

The User Guide's install instructions are long, sequential, and easy to
get half-right in ways that only surface much later (a missing Pango that
looks fine until the first `prodockit pdf`, a Node without npm that fails
in an apparently unrelated step). This turns that sequence into eighteen
stages that can each be *checked*, and reapplied individually when a
check fails (prodockit-extensions#217).

**bootstrap cannot be the first thing you run.** It is a prodockit
subcommand, so Python and `pip install prodockit` necessarily come first -
the automation starts after that, which is also where the per-platform
manual clicks stop.

Phase 1 is check-and-plan only: `prodockit bootstrap --check` reports
every stage's state, and `--dry-run` prints the exact commands a real run
would use. Nothing here installs anything yet.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from prodockit.bootstrap.config import (
    PROMPTS,
    BootstrapConfig,
    BootstrapConfigError,
    config_path,
    default_for,
    load,
    missing_keys,
    question_for,
    save,
)
from prodockit.bootstrap.model import (
    HOSTS,
    INSTALL_TIMEOUT_SECONDS,
    MACOS,
    SURREY_GITLAB,
    UBUNTU,
    WINDOWS,
    CheckResult,
    CommandResult,
    Context,
    Host,
    Plan,
    Runner,
    Stage,
    Status,
    SubprocessRunner,
    authenticate_sudo,
    connection_problem,
    host_problem,
    needs_sudo,
    normalise_host,
    resolve_host,
)
from prodockit.bootstrap.stages import STAGES

__all__ = [
    "HOSTS",
    "INSTALL_TIMEOUT_SECONDS",
    "PROMPTS",
    "STAGES",
    "SURREY_GITLAB",
    "ApplyResult",
    "BootstrapConfig",
    "BootstrapConfigError",
    "CheckResult",
    "CommandResult",
    "Context",
    "Host",
    "Plan",
    "Runner",
    "Stage",
    "StageReport",
    "Status",
    "SubprocessRunner",
    "UnsupportedHostError",
    "apply_stage",
    "authenticate_sudo",
    "build_context",
    "check_all",
    "config_path",
    "connection_problem",
    "current_platform",
    "default_for",
    "host_problem",
    "load",
    "missing_keys",
    "needs_sudo",
    "normalise_host",
    "plan_all",
    "question_for",
    "resolve_host",
    "save",
]


class UnsupportedHostError(Exception):
    """Raised for a host that is declared but not yet implemented."""


def current_platform() -> str:
    """Which install recipe applies to the machine this is running on.

    Raises for anything else rather than guessing: a wrong package
    manager is a worse outcome than a clear "not supported".
    """
    # Read into a plain `str` deliberately: mypy narrows `sys.platform` to
    # whichever platform it is checking *on*, which makes the other two
    # branches unreachable and (with warn_unreachable) an error. The
    # branches are all genuinely reachable at runtime.
    name: str = sys.platform
    if name == "darwin":
        return MACOS
    if name.startswith("linux"):
        return UBUNTU
    if name.startswith("win"):
        return WINDOWS
    raise UnsupportedHostError(f"no install recipe for platform {name!r}")


def build_context(
    config: BootstrapConfig,
    *,
    runner: Runner | None = None,
    platform: str | None = None,
    home: Path | None = None,
    exists: Callable[[Path], bool] | None = None,
) -> Context:
    """Assembles what the stages need, resolving the configured host.

    Every dependency is overridable so a test can describe a machine it
    isn't running on.
    """
    # The same question the configure prompt asks, from the same place -
    # so a host the prompt accepted cannot be one the run refuses (#255).
    if (problem := host_problem(config.host)) is not None:
        raise UnsupportedHostError(problem)
    host = resolve_host(config.host)
    assert host is not None  # host_problem returned None, so it resolves
    return Context(
        config=config,
        host=host,
        platform=platform or current_platform(),
        runner=runner or SubprocessRunner(),
        home=home or Path.home(),
        exists=exists or Path.exists,
    )


@dataclass(frozen=True)
class ApplyResult:
    """What applying one stage did, and whether it worked.

    `verified` is the check re-run *afterwards*, and is the only claim
    worth making: a command exiting zero says the installer ran, not that
    the thing it installed now works. Every stage this project has got
    wrong in the past exited zero while producing something broken.
    """

    stage: Stage
    ran: list[list[str]] = field(default_factory=list)
    failed: CommandResult | None = None
    verified: CheckResult | None = None

    @property
    def ok(self) -> bool:
        return self.failed is None and self.verified is not None and not self.verified.needs_work


def apply_stage(context: Context, stage: Stage) -> ApplyResult:
    """Runs a stage's plan, then re-checks it.

    Stops at the first command that fails rather than pressing on: the
    later commands in a plan generally depend on the earlier ones (a
    `npm ci` into a directory the clone was supposed to create), and
    running them anyway turns one clear failure into several confusing
    ones.

    A stage whose plan is purely instructions - the two browser steps -
    runs its verification command only, which is exactly the point: the
    human does the work, bootstrap decides whether it took.
    """
    plan = stage.plan(context)
    result = ApplyResult(stage=stage)
    for command in plan.commands:
        # An install is allowed to be slow in a way a check is not: a
        # 100 MB download and an `apt install` behind it are ordinary
        # here, and killing them at the check's limit reported a failure
        # over an install that then succeeded (#243).
        outcome = context.runner.run(
            command,
            cwd=plan.cwd,
            timeout=INSTALL_TIMEOUT_SECONDS,
            # Applying is never captured. An installer's own output is
            # the only sign a run is alive: `apt update`, a 100 MB
            # download and `apt install` behind it are minutes of
            # silence otherwise, and a silent terminal is
            # indistinguishable from a hung one - readers interrupted
            # installs that were working (prodockit-extensions#244).
            #
            # It also covers what `needs_terminal` was added for: a
            # command that has to ask something (#246) now always has
            # the terminal, rather than only when a plan remembered to
            # say so.
            #
            # Checks stay captured - they read what a command printed,
            # and there are dozens of them per run.
            capture=False,
        )
        result.ran.append(list(command))
        if not outcome.ok:
            return ApplyResult(stage=stage, ran=result.ran, failed=outcome)
    return ApplyResult(stage=stage, ran=result.ran, verified=stage.check(context))


@dataclass(frozen=True)
class StageReport:
    """One stage's state, and what would fix it."""

    stage: Stage
    result: CheckResult
    plan: Plan | None = None

    @property
    def needs_work(self) -> bool:
        return self.result.needs_work


def check_all(context: Context, stages: tuple[Stage, ...] = STAGES) -> list[StageReport]:
    """Runs every stage's `check` and reports. Changes nothing."""
    return [StageReport(stage=stage, result=stage.check(context)) for stage in stages]


def plan_all(context: Context, stages: tuple[Stage, ...] = STAGES) -> list[StageReport]:
    """Checks every stage, and works out a plan for those that need one.

    A stage that is already `OK` gets no plan - the point of a rerun is to
    repair what is broken, not to reinstall what works.

    Nor does an `UNKNOWN` one. A plan built from unanswered configuration
    is worse than no plan: it renders as `git clone ... /Users/you/project`
    and `create a blank project named '' in the group ''`, which reads as
    an instruction rather than as the missing answer it actually is.
    """
    reports = []
    for stage in stages:
        result = stage.check(context)
        plannable = result.needs_work and result.status is not Status.UNKNOWN
        plan = stage.plan(context) if plannable else None
        reports.append(StageReport(stage=stage, result=result, plan=plan))
    return reports

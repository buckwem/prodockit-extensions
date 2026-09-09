# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Native PDF dependencies, separate from the active Python/Pandoc pins."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from prodockit import adopt_package_manager
from prodockit.adopt_node import run_commands
from prodockit.bootstrap import UnsupportedHostError, current_platform
from prodockit.bootstrap.config import BootstrapConfig
from prodockit.bootstrap.model import (
    GITHUB_COM,
    MACOS,
    WINDOWS,
    Context,
    SubprocessRunner,
    refresh_windows_path,
)
from prodockit.bootstrap.stages import (
    _MACOS_DYLD_MARKER,
    _homebrew_library_path,
    _macos_loader_line,
    _plan_pandoc,
)
from prodockit.renderer_resilience import RetryReporter
from prodockit.toolchain import ToolchainError


@dataclass(frozen=True)
class NativePlan:
    commands: tuple[tuple[str, ...], ...] = ()
    detail: str = "PDF libraries and fonts are available"
    blocked: str = ""
    environment_repair: bool = False

    @property
    def needs_work(self) -> bool:
        return bool(self.commands or self.blocked or self.environment_repair)


def _context() -> Context:
    return Context(
        BootstrapConfig(),
        GITHUB_COM,
        current_platform(),
        SubprocessRunner(),
        Path.home(),
        guided=True,
    )


def _environment(context: Context) -> dict[str, str]:
    env = dict(os.environ)
    if context.platform == MACOS:
        library = _homebrew_library_path(context)
        existing = env.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(os.pathsep)
        env["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(
            dict.fromkeys([library, *filter(None, existing)])
        )
    return env


def _probe(context: Context, *, render: bool = False) -> str:
    code = (
        "import importlib.util, sys; "
        "missing = importlib.util.find_spec('weasyprint') is None; "
        "print('PDK_PYTHON_PACKAGE_PENDING' if missing else ''); "
        "sys.exit(0) if missing else None; import weasyprint"
    )
    if render:
        code += (
            "; data=weasyprint.HTML(string='<p>PDF runtime test</p>').write_pdf(); "
            "assert data.startswith(b'%PDF')"
        )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=_environment(context),
            check=False,
        )
        if result.returncode:
            if "ModuleNotFoundError:" in result.stderr:
                return "WeasyPrint Python package is pending"
            detail = next(
                (line for line in reversed(result.stderr.splitlines()) if line.strip()),
                "no error detail",
            )
            return f"WeasyPrint library/PDF health check failed: {detail[-400:]}"
        if "PDK_PYTHON_PACKAGE_PENDING" in result.stdout:
            return "WeasyPrint Python package is pending"
        for family in ("Inter", "JetBrains Mono"):
            match = subprocess.run(
                ["fc-match", "-f", "%{family}", family],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=_environment(context),
                check=False,
            )
            if match.returncode or family.casefold().replace(
                " ", ""
            ) not in match.stdout.casefold().replace(" ", ""):
                matched = match.stdout.strip() or "nothing"
                return f"PDF font {family} is unavailable (matched {matched})"
    except (OSError, subprocess.SubprocessError) as error:
        return f"PDF library or font health could not be verified: {error}"
    return ""


def _loader_missing(context: Context) -> bool:
    if context.platform != MACOS:
        return False
    activate = Path(sys.prefix) / "bin" / "activate"
    if not activate.is_file():
        return False
    return _macos_loader_line(context) not in activate.read_text(encoding="utf-8")


def plan(*, offline: bool = False) -> NativePlan:
    try:
        context = _context()
    except UnsupportedHostError as error:
        return NativePlan(blocked=str(error))
    problem = _probe(context)
    if problem == "WeasyPrint Python package is pending":
        return NativePlan(
            environment_repair=True,
            detail="verify native dependencies after installing WeasyPrint",
        )
    if not problem and not _loader_missing(context):
        return NativePlan()
    if not problem:
        return NativePlan(
            environment_repair=True,
            detail="save the Homebrew library path in the active environment",
        )
    if offline:
        return NativePlan(blocked=f"{problem}; native installation requires an online run")
    manager = adopt_package_manager.plan(context.platform, offline=offline)
    if manager.blocked:
        return NativePlan(blocked=f"{problem}; {manager.blocked}")
    commands = _plan_pandoc(context, native_only=True).commands
    return NativePlan(
        manager.commands + tuple(tuple(command) for command in commands),
        problem + "; install or repair PDF libraries and fonts",
    )


def _refresh(context: Context) -> None:
    if context.platform == WINDOWS:
        refresh_windows_path()
    elif context.platform == MACOS:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = _environment(context)[
            "DYLD_FALLBACK_LIBRARY_PATH"
        ]


def _persist_loader(context: Context) -> None:
    if context.platform != MACOS:
        return
    activate = Path(sys.prefix) / "bin" / "activate"
    if not activate.is_file():
        return
    from prodockit.adopt import _atomic_write

    source = activate.read_text(encoding="utf-8")
    line = _macos_loader_line(context)
    if line in source:
        return
    lines = source.splitlines()
    kept = []
    index = 0
    while index < len(lines):
        if lines[index] == _MACOS_DYLD_MARKER:
            index += 1
            if index < len(lines) and lines[index].startswith("export DYLD_FALLBACK_LIBRARY_PATH="):
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    _atomic_write(
        activate,
        ("\n".join(kept).rstrip() + "\n\n" + _MACOS_DYLD_MARKER + "\n" + line + "\n").encode(),
    )


def apply(root: Path, *, offline: bool = False, reporter: RetryReporter | None = None) -> None:
    context = _context()
    _refresh(context)
    pending = plan(offline=offline)
    if pending.blocked:
        raise ToolchainError(pending.blocked)
    commands = pending.commands
    run_commands(
        root,
        commands,
        offline=offline,
        reporter=reporter,
        refresh=lambda: _refresh(context),
        label="PDF runtime",
    )
    _persist_loader(context)
    if commands and shutil.which("fc-cache"):
        run_commands(
            root,
            (("fc-cache", "-f"),),
            offline=offline,
            reporter=reporter,
            refresh=lambda: _refresh(context),
            label="font cache",
        )
    problem = _probe(context, render=True)
    if problem:
        raise ToolchainError(
            "PDF runtime verification failed: "
            + problem
            + ". Rerun Adopt to repair; the activity is not complete."
        )

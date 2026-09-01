# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Durable recovery state for the ``prodockit bootstrap`` command."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prodockit.bootstrap.model import UBUNTU, WINDOWS, CommandResult

REPORT_SCHEMA = 1


@dataclass(frozen=True)
class RecoveryAdvice:
    """A diagnosed failure category and safe next actions."""

    category: str
    steps: tuple[str, ...]


def recovery_advice(
    stage_id: str,
    platform: str,
    command: Sequence[str],
    outcome: CommandResult,
) -> RecoveryAdvice:
    """Turn common installer failures into conservative recovery actions."""
    executable = Path(command[0]).name.lower() if command else "command"
    if executable in {"sudo", "sudo.exe"}:
        executable = next(
            (
                Path(argument).name.lower()
                for argument in command[1:]
                if not argument.startswith("-")
            ),
            executable,
        )
    output = f"{outcome.stdout}\n{outcome.stderr}".lower()

    if "did not finish within" in output:
        return RecoveryAdvice(
            "command-timeout",
            (
                "The command exceeded prodockit bootstrap's 30-minute safety limit. Check that "
                "no installer or package-manager process is still running before retrying.",
                "Do not start a second installer over a running one. Once the first has "
                "finished or stopped, resume prodockit bootstrap; the stage will be checked before "
                "anything is repeated.",
            ),
        )

    missing = outcome.returncode == 127 or any(
        marker in output for marker in ("not found", "not recognized")
    )
    if missing:
        if executable in {"winget", "winget.exe"}:
            return RecoveryAdvice(
                "package-manager-missing",
                (
                    "Open Microsoft Store and install or repair App Installer, "
                    "which provides winget.",
                    "Close and reopen the terminal, run `winget --version`, then "
                    "resume prodockit bootstrap.",
                ),
            )
        if executable == "brew":
            return RecoveryAdvice(
                "package-manager-missing",
                (
                    "Confirm Homebrew is installed and `brew --version` works in this terminal.",
                    "If Homebrew is installed elsewhere, reopen the terminal after "
                    "adding its shell environment, then resume prodockit bootstrap.",
                ),
            )
        name = command[0] if command else "the command"
        return RecoveryAdvice(
            "command-missing",
            (
                f"Confirm `{name}` is installed and visible on PATH in this terminal.",
                "If it was just installed, close and reopen the terminal before "
                "resuming prodockit bootstrap.",
            ),
        )

    winget_source_error = executable in {"winget", "winget.exe"} and any(
        marker in output
        for marker in (
            "source data",
            "failed when opening source",
            "failed when searching source",
            "0x8a15000f",
            "0x80072ee7",
        )
    )
    if winget_source_error:
        return RecoveryAdvice(
            "winget-source",
            (
                "Run `winget source update` and retry.",
                "If that reports a damaged source, run `winget source reset "
                "--force`, then `winget source update` before resuming prodockit bootstrap.",
            ),
        )

    if any(
        marker in output
        for marker in (
            "server returned 408",
            "server returned 429",
            "server returned 500",
            "server returned 502",
            "server returned 503",
            "server returned 504",
            "http status code 408",
            "request timeout",
            "service unavailable",
            "too many requests",
            "temporarily unavailable",
        )
    ):
        return RecoveryAdvice(
            "service-temporarily-unavailable",
            (
                "The remote package or extension service is temporarily unavailable; "
                "no local repair is needed.",
                "Wait briefly and resume prodockit bootstrap; completed work will be skipped and "
                "the failed download will be retried.",
            ),
        )

    if any(
        marker in output
        for marker in (
            "timed out",
            "could not resolve",
            "temporary failure in name resolution",
            "connection refused",
            "connection reset",
            "econnreset",
            "etimedout",
            "operation timed out",
            "tls handshake timeout",
            "unexpected eof",
            "remote end closed connection",
            "network is unreachable",
            "certificate verify failed",
            "ssl certificate problem",
        )
    ):
        return RecoveryAdvice(
            "network",
            (
                "Check the VM's network, DNS, proxy and system clock, then retry "
                "the failed command.",
                "Resume prodockit bootstrap after the command can reach its package "
                "or repository service.",
            ),
        )

    if any(
        marker in output
        for marker in (
            "permission denied",
            "access is denied",
            "requires elevation",
            "eacces",
        )
    ):
        return RecoveryAdvice(
            "permissions",
            (
                "Check the failed path and package-manager permissions; do not "
                "change ownership recursively.",
                "Use an elevated terminal only if the failed installer explicitly "
                "requires it, then resume prodockit bootstrap.",
            ),
        )

    if any(marker in output for marker in ("no space left", "disk full", "enospc")):
        return RecoveryAdvice(
            "disk-space",
            (
                "Free disk space in the VM and its temporary-file location.",
                "Resume prodockit bootstrap; completed stages will be checked rather "
                "than installed again.",
            ),
        )

    if any(
        marker in output
        for marker in (
            "could not get lock",
            "unable to acquire the dpkg frontend lock",
            "another installation is in progress",
        )
    ):
        return RecoveryAdvice(
            "installer-busy",
            (
                "Let the other installer or operating-system update finish; do "
                "not delete package-manager lock files.",
                "Resume prodockit bootstrap when no other installation is running.",
            ),
        )

    package_manager = executable in {
        "apt",
        "apt-get",
        "brew",
        "winget",
        "winget.exe",
    }
    if package_manager and platform == WINDOWS and stage_id in {"git", "vscode", "node"}:
        product = {
            "git": "Git for Windows",
            "vscode": "Visual Studio Code",
            "node": "the current Node.js LTS",
        }[stage_id]
        verification = {
            "git": "`git --version`",
            "vscode": "`code --version`",
            "node": "both `node --version` and `npm --version`",
        }[stage_id]
        return RecoveryAdvice(
            "alternative-installer",
            (
                f"If winget continues to fail, use the vendor's official installer "
                f"for {product}; keep its option to add the command to PATH enabled.",
                f"Close and reopen the terminal, confirm {verification}, then resume "
                "prodockit bootstrap so the installed version and remaining "
                "configuration are checked.",
            ),
        )

    if package_manager and platform != WINDOWS and stage_id == "vscode":
        return RecoveryAdvice(
            "alternative-installer",
            (
                "If the package manager remains unavailable, install Visual Studio "
                "Code with the vendor's official desktop installer.",
                "Enable VS Code's `code` shell command, reopen the terminal, run "
                "`code --version`, then resume prodockit bootstrap.",
            ),
        )

    if executable == "brew" and stage_id == "git":
        return RecoveryAdvice(
            "alternative-installer",
            (
                "If Homebrew remains unavailable, run `xcode-select --install` and "
                "complete Apple's Command Line Tools installer.",
                "Open a new terminal, run `git --version`, then resume prodockit bootstrap so "
                "Git configuration is completed.",
            ),
        )

    if stage_id == "clone":
        return RecoveryAdvice(
            "partial-clone",
            (
                "Inspect the destination directory: a failed clone may have left "
                "a partial checkout.",
                "If it contains work, preserve it. Otherwise move the partial "
                "directory aside, then resume prodockit bootstrap.",
            ),
        )
    if stage_id == "project-env":
        return RecoveryAdvice(
            "partial-environment",
            (
                "The project environment may be partially populated; resume once "
                "to let prodockit bootstrap recheck it.",
                "If the same dependency failure repeats, move the project's "
                "`.venv` aside and resume to rebuild it cleanly.",
            ),
        )
    if (
        stage_id == "node"
        and platform == UBUNTU
        and any("nodesource-setup.sh" in argument for argument in command)
    ):
        return RecoveryAdvice(
            "node-repository",
            (
                "The NodeSource repository setup failed before Node was installed; "
                "review its output and confirm the VM's Ubuntu release is supported.",
                "If NodeSource remains unavailable, install the current Node.js LTS "
                "with its official Linux instructions, confirm both `node --version` "
                "and `npm --version`, then resume prodockit bootstrap.",
            ),
        )
    if stage_id == "node":
        return RecoveryAdvice(
            "node-toolchain",
            (
                "Run `node --version` and `npm --version` to distinguish a runtime "
                "failure from a project-toolchain failure.",
                "Run `npm cache verify`; if it succeeds, resume prodockit bootstrap so `npm ci` "
                "can rebuild the project toolchains.",
            ),
        )
    if stage_id == "pandoc" and platform == UBUNTU:
        return RecoveryAdvice(
            "linux-pdf-toolchain",
            (
                "Check whether the pinned Pandoc package downloaded to "
                "`/tmp/pandoc.deb` and whether its architecture matches `dpkg "
                "--print-architecture`.",
                "Resume prodockit bootstrap after the download or apt problem is corrected; "
                "it will recheck Pandoc before installing the remaining PDF libraries.",
            ),
        )
    if stage_id == "pandoc" and platform == WINDOWS:
        return RecoveryAdvice(
            "windows-pdf-toolchain",
            (
                "Run `winget list --id JohnMacFarlane.Pandoc --exact` and `pandoc "
                "--version` to check whether Pandoc installed despite the error.",
                "Check that MSYS2 opens before resuming; prodockit bootstrap will recheck "
                "Pandoc and the PDF libraries separately.",
            ),
        )

    return RecoveryAdvice(
        "unclassified",
        (
            "Review the command output above and correct the reported condition.",
            "Resume prodockit bootstrap; completed stages will be checked and skipped.",
        ),
    )


def bootstrap_report_path(config_path: Path) -> Path:
    """Put recovery state beside, but distinctly from, prodockit bootstrap's config."""
    return config_path.with_name(f"{config_path.stem}.last-run.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BootstrapRunJournal:
    """An atomically replaced account of the latest apply run.

    A damaged or half-written recovery file is worse than no recovery file,
    so every update is written, flushed and replaced as one filesystem
    operation. Journal failure never stops installation; ``error`` lets the
    command warn that this secondary safety net is unavailable.
    """

    def __init__(
        self,
        path: Path,
        *,
        version: str,
        config_path: Path,
        resume: Sequence[str],
        stages: Sequence[dict[str, Any]],
    ) -> None:
        self.path = path
        self.error: str | None = None
        started = _now()
        self.data: dict[str, Any] = {
            "schema": REPORT_SCHEMA,
            "prodockit_version": version,
            "status": "running",
            "started_at": started,
            "updated_at": started,
            "config_file": str(config_path),
            "resume": list(resume),
            "current_stage": None,
            "failure": None,
            "stages": [dict(stage) for stage in stages],
        }
        self._write()

    def stage(
        self,
        stage_id: str,
        status: str,
        *,
        detail: str = "",
        action: str = "",
    ) -> None:
        """Record the latest known state of one stage and the active stage."""
        if self.error is not None:
            return
        for stage in self.data["stages"]:
            if stage["id"] == stage_id:
                stage["status"] = status
                stage["detail"] = detail
                if action:
                    stage["action"] = action
                break
        if status == "running":
            self.data["current_stage"] = stage_id
        elif (
            status in {"completed", "satisfied", "skipped"}
            and self.data["current_stage"] == stage_id
        ):
            self.data["current_stage"] = None
        self.data["updated_at"] = _now()
        self._write()

    def settle(self) -> str:
        """Finish normally, distinguishing a complete run from pending work."""
        pending = {"planned", "running", "skipped", "waiting", "unknown"}
        statuses = {stage["status"] for stage in self.data["stages"]}
        status = "incomplete" if statuses & pending else "completed"
        self.finish(status)
        return status

    def finish(
        self,
        status: str,
        *,
        failure: dict[str, Any] | None = None,
    ) -> None:
        """Close the run, retaining the failed/waiting stage when useful."""
        if self.error is not None:
            return
        self.data["status"] = status
        self.data["failure"] = failure
        if status == "completed":
            self.data["current_stage"] = None
        self.data["updated_at"] = _now()
        self._write()

    def _write(self) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            self.error = f"could not update {self.path}: {error}"
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)


__all__ = [
    "BootstrapRunJournal",
    "RecoveryAdvice",
    "bootstrap_report_path",
    "recovery_advice",
]

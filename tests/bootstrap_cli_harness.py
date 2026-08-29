# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Hermetic command harness for the ``prodockit bootstrap`` command.

The stage-model tests have their own broad fake-machine helpers.  This
smaller harness is deliberately about the command boundary: Click parsing,
mode routing, configuration errors, exit codes and interactive input.  It
patches the one context-construction seam and records the runner it supplied,
so command tests never inherit tools, files, hosts or network access from the
developer machine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from prodockit.bootstrap import CommandResult, build_context
from prodockit.bootstrap.model import MACOS
from prodockit.cli import main


class CliFakeRunner:
    """A minimal command-table runner used only by the CLI harness."""

    def __init__(self, responses: dict[str, CommandResult] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []
        self.cwds: list[str | None] = []
        self.timeouts: list[float | None] = []
        self.captures: list[bool] = []

    def run(
        self,
        command: Sequence[str],
        cwd: str | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> CommandResult:
        self.calls.append(list(command))
        self.cwds.append(cwd)
        self.timeouts.append(timeout)
        self.captures.append(capture)
        joined = " ".join(command)
        if joined in self.responses:
            return self.responses[joined]
        fragments = [key for key in self.responses if key in joined]
        if fragments:
            return self.responses[max(fragments, key=len)]
        if command and command[0] in self.responses:
            return self.responses[command[0]]
        return CommandResult(returncode=127, stderr="not found")


def _looks_like_vscode_app(path: Path) -> bool:
    text = str(path)
    return "Visual Studio Code" in text or text.endswith(("/usr/share/code", "/snap/code"))


def unreachable(_url: str, timeout: float = 20.0):
    """A fetch seam that proves command tests cannot reach a live host."""
    del timeout
    return None


class BootstrapCliHarness:
    """Invoke ``prodockit bootstrap`` against a deterministic fake machine."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.last_runner: CliFakeRunner | None = None

    def invoke(
        self,
        *args: str,
        responses: dict[str, CommandResult] | None = None,
        input: str | None = None,
        platform: str = MACOS,
        fetch: Callable[..., Any] | None = None,
        config_path: Path | None = None,
        patch_context: bool = True,
    ) -> Result:
        """Run the command, optionally leaving real context validation intact.

        ``patch_context=False`` is for host/platform error-path tests.  It
        still uses Click's isolated runner, but deliberately does not replace
        ``build_bootstrap_context`` so those validation failures can occur.
        """
        if patch_context:
            runner = CliFakeRunner(
                {
                    "sys.base_prefix": CommandResult(0, "True"),
                    "import ensurepip, venv": CommandResult(0),
                }
                | (responses or {})
            )
            self.last_runner = runner
            self.monkeypatch.setattr(
                "prodockit.cli.build_bootstrap_context",
                lambda config, *, guided=False: build_context(
                    config,
                    runner=runner,
                    exists=lambda path: False if _looks_like_vscode_app(path) else path.exists(),
                    platform=platform,
                    home=self.tmp_path,
                    fetch=fetch or unreachable,
                    guided=guided,
                ),
            )

        path = config_path or self.tmp_path / "b.toml"
        return CliRunner().invoke(
            main,
            ["bootstrap", "--config", str(path), *args],
            input=input,
        )

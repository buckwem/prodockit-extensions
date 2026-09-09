# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Provision Mermaid's browser explicitly, never through an npm postinstall."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from prodockit.adopt_node import run_commands
from prodockit.bootstrap import UnsupportedHostError, current_platform
from prodockit.bootstrap.model import UBUNTU
from prodockit.bootstrap.stages import _apt
from prodockit.init_tools import TEMPLATE_DIR
from prodockit.renderer_health import find_browser
from prodockit.renderer_resilience import RetryReporter
from prodockit.toolchain import ToolchainError, run_install_command


@dataclass(frozen=True)
class BrowserPlan:
    commands: tuple[tuple[str, ...], ...] = ()
    detail: str = "reuse an available browser; verify by rendering a diagram"
    blocked: str = ""


def _system_browser() -> str | None:
    browser = find_browser()
    if browser and (Path(browser).is_file() or shutil.which(browser)):
        return browser
    return None


def _cached_browser(root: Path) -> str | None:
    root = root.resolve()
    package = root / "tools/mermaid/node_modules/puppeteer"
    node = shutil.which("node")
    if not node or not package.is_dir():
        return None
    try:
        result = subprocess.run(
            [
                node,
                "-e",
                # Puppeteer 25 returns a Promise; older releases returned a
                # string. Await either form before validating the file path.
                "Promise.resolve(require(process.argv[1]).executablePath())"
                ".then(path => process.stdout.write(path))"
                ".catch(error => { console.error(error); process.exitCode = 1; })",
                str(package),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            cwd=root / "tools/mermaid",
        )
        value = result.stdout.strip()
        return value if result.returncode == 0 and value and Path(value).is_file() else None
    except (OSError, subprocess.SubprocessError):
        return None


def plan(root: Path, *, offline: bool = False) -> BrowserPlan:
    if os.environ.get("PUPPETEER_EXECUTABLE_PATH") and not _system_browser():
        return BrowserPlan(
            blocked="PUPPETEER_EXECUTABLE_PATH points to a missing browser; "
            "correct or unset that override before retrying"
        )
    if _system_browser():
        return BrowserPlan()
    try:
        platform = current_platform()
    except UnsupportedHostError as error:
        return BrowserPlan(blocked=str(error))
    # Ubuntu's package manager chooses the host architecture. In particular,
    # never rely on a Puppeteer Chrome download on an ARM64 Ubuntu host.
    if platform == UBUNTU:
        if offline:
            return BrowserPlan(
                blocked="Chromium is required for Mermaid on Ubuntu; "
                "installing it requires an online run"
            )
        if not shutil.which("apt"):
            return BrowserPlan(blocked="Automatic Chromium installation requires Ubuntu with apt")
        return BrowserPlan(
            (tuple(_apt("install", "-y", "chromium-browser")),),
            "install Ubuntu's architecture-matched Chromium before npm",
        )
    if _cached_browser(root):
        return BrowserPlan()
    return BrowserPlan(
        detail="install the browser selected by the release's Puppeteer package after npm; "
        "offline runs require an existing browser cache"
    )


def prepare(
    root: Path, *, offline: bool = False, reporter: RetryReporter | None = None
) -> dict[str, str]:
    pending = plan(root, offline=offline)
    if pending.blocked:
        raise ToolchainError(pending.blocked)
    if pending.commands:
        run_commands(root, pending.commands, offline=offline, reporter=reporter, label="Chromium")
        if not _system_browser():
            raise ToolchainError(
                "Chromium installation finished but its executable was not found; "
                "rerun Adopt to repair"
            )
    environment = dict(os.environ)
    environment["PUPPETEER_SKIP_DOWNLOAD"] = "true"
    if browser := _system_browser():
        environment["PUPPETEER_EXECUTABLE_PATH"] = browser
    return environment


def complete(root: Path, *, offline: bool = False, reporter: RetryReporter | None = None) -> None:
    root = root.resolve()
    if _system_browser():
        return
    if current_platform() == UBUNTU:
        raise ToolchainError(
            "Ubuntu Chromium is unavailable; the architecture-matched browser "
            "must be installed before Mermaid"
        )
    if _cached_browser(root):
        return
    if offline:
        raise ToolchainError(
            "Mermaid's browser is not cached. Rerun Adopt online to install it; "
            "npm packages alone are insufficient"
        )
    # Invoke only the already installed CLI: npm exec could fetch a different
    # package when a partial install left the intended one unavailable.
    lock = json.loads((TEMPLATE_DIR / "mermaid/package-lock.json").read_text(encoding="utf-8"))
    binary = lock["packages"]["node_modules/puppeteer"]["bin"]["puppeteer"]
    cli = root / "tools/mermaid/node_modules/puppeteer" / binary
    node = shutil.which("node")
    if not node or not cli.is_file():
        raise ToolchainError(
            "The locked Puppeteer installation is incomplete; rerun Adopt to reinstall the renderer"
        )
    try:
        run_install_command(
            [node, str(cli), "browsers", "install"], root=root / "tools/mermaid", reporter=reporter
        )
    except subprocess.TimeoutExpired as error:
        raise ToolchainError(
            "Browser download timed out. Check that the installer and its child processes "
            "have stopped before rerunning Adopt; no automatic retry was started."
        ) from error
    if not _cached_browser(root):
        raise ToolchainError(
            "Browser installer completed without a usable cached executable; rerun Adopt to repair"
        )

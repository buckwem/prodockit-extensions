# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Small, non-destructive health probes for optional renderer commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RendererProbe:
    """The result of asking one renderer command to identify itself."""

    path: Path
    version: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def find_browser() -> str | None:
    """Find a browser Puppeteer can use without downloading another copy."""
    if configured := os.environ.get("PUPPETEER_EXECUTABLE_PATH"):
        return configured
    for name in (
        "google-chrome-stable",
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
        "msedge",
    ):
        if found := shutil.which(name):
            return found
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.extend(
            (
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            )
        )
    elif os.name == "nt":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if base := os.environ.get(variable):
                root = Path(base)
                candidates.extend(
                    (
                        root / "Google" / "Chrome" / "Application" / "chrome.exe",
                        root / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    )
                )
    return next((str(path) for path in candidates if path.is_file()), None)


def _renderer_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if "PUPPETEER_EXECUTABLE_PATH" not in environment and (browser := find_browser()):
        environment["PUPPETEER_EXECUTABLE_PATH"] = browser
    return environment


def _command(
    path: Path, *arguments: str, platform: str | None = None
) -> list[str]:
    platform = os.name if platform is None else platform
    if platform == "nt" and not path.suffix:
        for suffix in (".cmd", ".exe", ".bat", ".com"):
            sibling = Path(f"{path}{suffix}")
            if sibling.is_file():
                return _command(sibling, *arguments, platform=platform)
    command = [str(path), *arguments]
    if platform == "nt" and path.suffix.casefold() in {".bat", ".cmd"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", *command]
    return command


def _output(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )


def probe_mermaid(path: str | Path, *, timeout: float = 30.0) -> RendererProbe:
    """Render a minimal diagram, exercising Mermaid and its browser."""
    executable = Path(path)
    environment = _renderer_environment()
    try:
        version_result = subprocess.run(
            _command(executable, "--version"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return RendererProbe(executable, error=str(error))
    version = _output(version_result)
    if version_result.returncode:
        return RendererProbe(
            executable,
            error=version or f"version probe exited with status {version_result.returncode}",
        )
    try:
        with tempfile.TemporaryDirectory(prefix="prodockit-mermaid-") as temporary:
            directory = Path(temporary)
            source = directory / "health.mmd"
            rendered = directory / "health.svg"
            source.write_text("graph LR\n  A --> B\n", encoding="utf-8")
            render_result = subprocess.run(
                _command(executable, "-i", str(source), "-o", str(rendered)),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                env=environment,
            )
            render_output = _output(render_result)
            if render_result.returncode:
                return RendererProbe(
                    executable,
                    version=version or None,
                    error=render_output
                    or f"render probe exited with status {render_result.returncode}",
                )
            if not rendered.is_file() or "<svg" not in rendered.read_text(
                encoding="utf-8", errors="replace"
            ):
                return RendererProbe(
                    executable,
                    version=version or None,
                    error="render probe did not produce an SVG",
                )
    except (OSError, subprocess.SubprocessError) as error:
        return RendererProbe(executable, version=version or None, error=str(error))
    return RendererProbe(executable, version=version or None)


def probe_mathjax(
    node_path: str | Path,
    script_path: str | Path,
    *,
    timeout: float = 15.0,
) -> RendererProbe:
    """Convert a minimal expression with the project's MathJax script."""
    node = Path(node_path)
    script = Path(script_path)
    try:
        completed = subprocess.run(
            [str(node), str(script), "inline"],
            input="x",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return RendererProbe(script, error=str(error))
    output = _output(completed)
    if completed.returncode:
        return RendererProbe(
            script,
            error=output or f"render probe exited with status {completed.returncode}",
        )
    if "<svg" not in completed.stdout:
        return RendererProbe(script, error="render probe did not produce an SVG")
    return RendererProbe(script)

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Small, non-destructive health probes for optional renderer commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RendererProbe:
    """The result of asking one renderer command to identify itself."""

    path: Path
    version: str | None = None
    error: str | None = None
    attempts: int = 1
    transient_failures: tuple[str, ...] = ()

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


def _output(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )


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

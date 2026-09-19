# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Small, non-destructive health probes for optional renderer commands."""

from __future__ import annotations

import subprocess
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

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Small, non-destructive health probes for optional renderer commands."""

from __future__ import annotations

import os
import subprocess
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


def probe_mermaid(path: str | Path, *, timeout: float = 10.0) -> RendererProbe:
    """Run the Mermaid CLI's read-only version command."""
    executable = Path(path)
    command = [str(executable), "--version"]
    if os.name == "nt" and executable.suffix.casefold() in {".bat", ".cmd"}:
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", *command]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return RendererProbe(executable, error=str(error))
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if completed.returncode:
        return RendererProbe(
            executable,
            error=output or f"exited with status {completed.returncode}",
        )
    return RendererProbe(executable, version=output or None)

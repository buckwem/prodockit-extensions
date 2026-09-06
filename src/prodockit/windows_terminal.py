"""Recover installer environment changes without modifying the parent shell."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import click


def restart_banner(project: Path, *, blocked: bool = False) -> None:
    lines = [
        "=" * 60,
        "RESTART YOUR TERMINAL — WINDOWS SETTINGS HAVE CHANGED",
        "=" * 60,
        "Fully close Windows Terminal or VS Code, then reopen it.",
        "Open PowerShell in your project directory:",
        str(project),
        r".\.venv\Scripts\Activate.ps1",
        "pdk diag",
    ]
    if blocked:
        lines.append("Template Sync cannot continue in this terminal.")
    lines.append("=" * 60)
    click.echo(click.style("\n".join(lines), fg=(230, 159, 0), bold=True))


def prepare_template_environment(project: Path) -> None:
    """Refresh this process, keeping the running environment first on PATH."""
    # Avoid mypy discarding the Windows branch when checking on Linux/macOS.
    running_on: str = sys.platform
    if running_on != "win32":
        return
    from prodockit.bootstrap.model import refresh_windows_path

    before = (os.environ.get("PATH"), os.environ.get("WEASYPRINT_DLL_DIRECTORIES"))
    missing = {name for name in ("git", "pandoc", "node", "npm") if not shutil.which(name)}
    refresh_windows_path()
    refreshed = (os.environ.get("PATH"), os.environ.get("WEASYPRINT_DLL_DIRECTORIES"))
    scripts = str(Path(sys.prefix) / "Scripts")
    parts = os.environ.get("PATH", "").split(";")
    os.environ["PATH"] = ";".join(
        [scripts, *(part for part in parts if part and part.casefold() != scripts.casefold())]
    )
    unresolved = sorted(name for name in missing if not shutil.which(name))
    if "git" in unresolved or (before != refreshed and unresolved):
        restart_banner(project, blocked=True)
        raise click.ClickException(
            "Commands still unavailable: "
            + ", ".join(unresolved)
            + ". If a fresh terminal has the same problem, run pdk diag to check installation."
        )
    if before != refreshed:
        click.echo(
            "Windows settings refreshed for Template Sync; the active terminal is unchanged."
        )

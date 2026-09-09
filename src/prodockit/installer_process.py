# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded installer execution with progress and process-tree cleanup."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path


class InstallerCleanupError(subprocess.SubprocessError):
    """An installer cannot safely be followed by another invocation."""


def _descendants_remain(pid: int, *, launched_at: float = 0) -> bool:
    if not _windows():
        try:
            os.killpg(pid, 0)
            return True
        except ProcessLookupError:
            return False
    # A child retains its parent PID even after its parent exits. Do not
    # interpret an unavailable process inventory as proof of completion.
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$ErrorActionPreference = 'Stop'; "
                f"$children = @(Get-CimInstance Win32_Process -ErrorAction Stop | "
                f"Where-Object {{ $_.ParentProcessId -eq {pid} }} | "
                "ForEach-Object { if (-not $_.CreationDate) { throw 'Missing creation time' }; "
                "([DateTimeOffset]$_.CreationDate).ToUnixTimeMilliseconds() }); "
                "ConvertTo-Json -InputObject $children -Compress",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        creation_times = json.loads(result.stdout)
        if (
            result.returncode
            or not isinstance(creation_times, list)
            or any(type(value) is not int for value in creation_times)
        ):
            raise ValueError("unverified process inventory")
        # ParentProcessId can refer to an earlier process which had this PID.
        # Such stale children predate our launch and are not ours to stop.
        return any(value >= int(launched_at * 1000) for value in creation_times)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        raise InstallerCleanupError(
            "Installer process cleanup could not be verified; no automatic retry. "
            "Check for running installers before continuing."
        ) from error


def _windows() -> bool:
    return os.name == "nt"


def _wait_for_children(pid: int, *, grace: float, launched_at: float = 0) -> bool:
    """Allow normal child teardown; never start another installer while waiting."""
    deadline = time.monotonic() + max(0, grace)
    while _descendants_remain(pid, launched_at=launched_at):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.25, remaining))
    return True


def _stop(process: subprocess.Popen[bytes]) -> bool:
    """Stop the owned group/tree, without assuming detached services are owned."""
    try:
        if _windows():
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if result.returncode:
                process.kill()
                process.wait(timeout=10)
                return False
        else:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=3)
            # The leader can exit while a descendant ignores SIGTERM.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def run_installer(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
    progress_interval: float = 15,
    show_progress: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Capture output in files so inherited pipes cannot hang a finished process.

    Timeout/interruption stops the owned process group (POSIX) or tree
    (Windows). Timeouts remain non-retriable: detached/elevated processes may
    be outside that ownership boundary and must not race another installer.
    """
    if timeout <= 0 or progress_interval <= 0:
        raise ValueError("installer timeout and progress interval must be positive")
    label = Path(command[0]).name
    started = time.monotonic()
    if show_progress:
        print(f"  Installing with {label}...", file=sys.stderr, flush=True)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        launched_at = time.time()
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=not _windows(),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
            if _windows()
            else 0,
        )
        try:
            while True:
                elapsed = time.monotonic() - started
                remaining = timeout - elapsed
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(list(command), timeout)
                try:
                    process.wait(timeout=min(progress_interval, remaining))
                    break
                except subprocess.TimeoutExpired:
                    if show_progress:
                        print(
                            f"  Working: {label} ({time.monotonic() - started:.0f}s)",
                            file=sys.stderr,
                            flush=True,
                        )
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            stopped = _stop(process)
            detail = (
                "owned installer processes stopped"
                if stopped
                else "process cleanup could not be verified"
            )
            print(
                f"  WARNING: {detail}; no automatic retry. "
                "Check for detached installers before rerunning.",
                file=sys.stderr,
                flush=True,
            )
            raise
        if not _wait_for_children(
            process.pid,
            grace=min(5.0, max(0, timeout - (time.monotonic() - started))),
            launched_at=launched_at,
        ):
            _stop(process)
            raise InstallerCleanupError(
                f"Installer {label} exited while child processes remained active "
                "after waiting for shutdown; "
                "cleanup was requested, but no automatic retry is safe. "
                "Check for detached installers before rerunning."
            )
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(
            list(command),
            process.returncode,
            stdout.read().decode("utf-8", errors="replace"),
            stderr.read().decode("utf-8", errors="replace"),
        )

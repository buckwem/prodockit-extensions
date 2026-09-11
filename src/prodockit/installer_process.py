# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded installer execution with progress and process-tree cleanup."""

from __future__ import annotations

import json
import os
import re
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
            # The wrapper may have been stopped before creating its group.
            if process.poll() is None:
                process.kill()
        process.wait(timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _progress_label(command: Sequence[str]) -> str:
    """Describe package work without exposing command paths or index credentials."""
    executable = command[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    executable = executable.removesuffix(".exe").removesuffix(".cmd")
    if executable == "sudo":
        arguments = list(command[1:])
        while arguments and arguments[0] in {"-n", "-E"}:
            arguments.pop(0)
        if arguments:
            return _progress_label(arguments)
    if list(command[1:4]) == ["-m", "pip", "install"]:
        packages = [
            item
            for item in command[4:]
            if re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?"
                r"(?:==|>=|<=|~=|>|<)[A-Za-z0-9.*+_-]+",
                item,
            )
        ]
        if packages:
            return "Installing project packages: " + ", ".join(packages)
        return "Installing project packages in the active environment"
    if executable == "fc-cache":
        return "Refreshing the font list so PDF tools can find installed fonts"
    if executable == "brew":
        names = {
            "pango": "PDF text-layout libraries",
            "fontconfig": "font detection tools",
            "font-inter": "Inter font",
            "font-jetbrains-mono": "JetBrains Mono font",
            "pandoc": "Pandoc document converter",
            "node": "Node.js and npm",
            "python@3.14": "Python 3.14",
        }
        packages = [names[item] for item in command[1:] if item in names]
        return "Installing or updating " + (", ".join(packages) or "required system software")
    if executable in {"bash", "sh", "powershell", "pwsh"}:
        # Bootstrap's Homebrew wrapper checks ownership before upgrading.
        # Recognise its package check, but never print the shell script.
        if executable in {"bash", "sh"} and len(command) == 3 and command[1] == "-c":
            package = re.search(r"brew list --(?:formula|cask) ([a-z0-9@.-]+)", command[2])
            if package:
                return _progress_label(["brew", "install", package.group(1)])
        return "Preparing required system software and environment settings"
    if executable == "npm":
        return "Installing project diagram or maths dependencies"
    if executable == "node" and "browsers" in command and "install" in command:
        return "Preparing the browser used to render diagrams"
    if executable in {"curl", "wget"}:
        return "Downloading required software"
    if executable in {"apt", "apt-get", "dpkg", "winget", "pacman", "installer"}:
        return "Installing or updating required system software"
    return "Preparing required project tools"


# Python 3.10 has no Popen(process_group=...). Start a minimal interpreter
# which sets its own group and then replaces itself, retaining the PID and
# terminal session. Avoid preexec_fn: it can deadlock a threaded caller.
_POSIX_GROUP_EXEC = """
import os
import signal
import sys
os.setpgid(0, 0)
for name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
    if hasattr(signal, name):
        signal.signal(getattr(signal, name), signal.SIG_DFL)
try:
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
except OSError as error:
    print(str(error), file=sys.stderr)
    sys.exit(127 if isinstance(error, FileNotFoundError) else 126)
"""


def _group_command(command: Sequence[str]) -> list[str]:
    if _windows():
        return list(command)
    return [sys.executable, "-I", "-S", "-c", _POSIX_GROUP_EXEC, *command]


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

    The POSIX child keeps the caller's terminal session for sudo credentials,
    but owns a separate process group. Timeout/interruption stops that group or tree
    (Windows). Timeouts remain non-retriable: detached/elevated processes may
    be outside that ownership boundary and must not race another installer.
    """
    if timeout <= 0 or progress_interval <= 0:
        raise ValueError("installer timeout and progress interval must be positive")
    label = Path(command[0]).name
    progress_label = _progress_label(command)
    started = time.monotonic()
    if show_progress:
        print(f"  {progress_label}...", file=sys.stderr, flush=True)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        launched_at = time.time()
        process = subprocess.Popen(
            _group_command(command),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
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
                            f"  Working: {progress_label} ({time.monotonic() - started:.0f}s)",
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

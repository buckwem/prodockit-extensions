# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Install non-provider prerequisites for the macOS live-provider candidates."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from live_provider_resilience import (
    failure_with_history,
    safe_failure_detail,
    transient_external_failure,
)
from live_provider_state import write_private_json

RETRY_DELAYS = (5.0, 15.0)
COMMAND_TIMEOUT = 20 * 60
COMMANDS = (
    ("brew", "install", "pandoc", "pango"),
    (
        "brew",
        "install",
        "--cask",
        "visual-studio-code",
        "font-inter",
        "font-jetbrains-mono",
    ),
    ("code", "--install-extension", "ms-python.python"),
    ("code", "--install-extension", "zensical.zensical-studio"),
    ("code", "--install-extension", "tamasfe.even-better-toml"),
    ("code", "--install-extension", "ltex-plus.vscode-ltex-plus"),
)


class PrerequisiteError(RuntimeError):
    """A non-provider prerequisite could not be installed safely."""


def _detail(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )


def install_prerequisites(
    report: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
    commands: Sequence[Sequence[str]] = COMMANDS,
) -> dict[str, Any]:
    """Run completed idempotent installs with bounded transient retries."""

    records: list[dict[str, Any]] = []
    try:
        for command in commands:
            failures: list[str] = []
            for attempt in range(1, len(RETRY_DELAYS) + 2):
                try:
                    completed = runner(
                        list(command),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=COMMAND_TIMEOUT,
                        check=False,
                    )
                except subprocess.TimeoutExpired as error:
                    # The timeout may leave installer descendants alive.  As in
                    # the production renderer policy, never race them with an
                    # automatic second installer.
                    raise PrerequisiteError(
                        f"{' '.join(command)} exceeded {COMMAND_TIMEOUT} seconds; "
                        "the timed-out installer was not retried"
                    ) from error
                detail = _detail(completed)
                if completed.returncode == 0:
                    records.append(
                        {
                            "command": list(command),
                            "attempts": attempt,
                            "transient_failures": failures,
                            "status": "passed",
                        }
                    )
                    break
                if attempt > len(RETRY_DELAYS) or not transient_external_failure(detail):
                    final = safe_failure_detail(detail, limit=2000)
                    raise PrerequisiteError(
                        failure_with_history(
                            f"{' '.join(command)} failed: {final}",
                            failures,
                        )
                    )
                failures.append(safe_failure_detail(detail))
                delay = RETRY_DELAYS[attempt - 1]
                print(
                    f"Transient prerequisite failure on attempt {attempt}/3; "
                    f"retrying {' '.join(command)} in {delay:g}s.",
                    file=sys.stderr,
                    flush=True,
                )
                sleeper(delay)
        result = {"passed": True, "operations": records}
    except PrerequisiteError as error:
        result = {
            "passed": False,
            "operations": records,
            "error": str(error)[-2000:],
        }
        write_private_json(report, result)
        raise
    write_private_json(report, result)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--report", type=Path, required=True)
    result.add_argument(
        "--pdf-only",
        action="store_true",
        help="install only Pandoc and Pango on a runner that already has editor tooling",
    )
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    try:
        install_prerequisites(
            args.report.resolve(), commands=COMMANDS[:1] if args.pdf_only else COMMANDS
        )
    except (OSError, PrerequisiteError) as error:
        print(f"live-provider prerequisites failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

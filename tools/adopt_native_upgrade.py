# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Upgrade a genuinely old adopted project with a candidate wheel.

This is the slow release-candidate companion to ``adopt_acceptance.py``.  It
downloads a published older Prodockit, uses that installed command to adopt a
real Zensical project with Mermaid and maths selected, then installs the
candidate wheel over the same environment and project.  The candidate must
refresh its managed files, build successfully, and be idempotent.

The test deliberately stays within Adopt's project boundary.  Git, SSH,
editors, and operating-system packages belong to Bootstrap's native gates.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import time
import venv
from dataclasses import asdict
from pathlib import Path
from typing import Any

import adopt_acceptance as acceptance

OLD_PRODOCKIT_VERSION = "0.47.0"


def installed_versions(python: Path, cwd: Path) -> dict[str, str]:
    """Return the installed versions which define the adoption boundary."""

    source = (
        "import json; from importlib.metadata import version; "
        "print(json.dumps({name: version(name) for name in "
        "('prodockit', 'zensical', 'Markdown', 'pymdown-extensions')}))"
    )
    value = json.loads(acceptance.run([str(python), "-c", source], cwd=cwd).stdout)
    if not isinstance(value, dict) or not all(
        isinstance(name, str) and isinstance(version, str)
        for name, version in value.items()
    ):
        raise acceptance.AcceptanceError("installed version inventory was not a string mapping")
    return value


def install_old_release(python: Path, root: Path, version: str) -> None:
    """Install the published release which creates the starting project."""

    acceptance.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade-strategy",
            "eager",
            f"prodockit=={version}",
        ],
        cwd=root,
    )


def install_upgrade(python: Path, wheel: Path) -> None:
    """Upgrade the environment eagerly, with the candidate as its root."""

    acceptance.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--upgrade-strategy",
            "eager",
            "--force-reinstall",
            str(wheel),
        ],
        cwd=wheel.parent,
    )
    location = acceptance.run(
        [
            str(python),
            "-c",
            "import pathlib, prodockit; print(pathlib.Path(prodockit.__file__).resolve())",
        ],
        cwd=wheel.parent,
    ).stdout.strip()
    if str(wheel.parent.parent.resolve()) in location:
        raise acceptance.AcceptanceError(
            f"candidate imported from the checkout instead of the wheel: {location}"
        )
    print(f"Installed candidate: {location}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Upgrade an older fully adopted Zensical project with a candidate wheel."
    )
    result.add_argument("--wheel", type=Path, required=True, help="Wheel file or directory")
    result.add_argument(
        "--old-version",
        default=OLD_PRODOCKIT_VERSION,
        help=(
            "Published Prodockit release used for the starting project "
            f"(default: {OLD_PRODOCKIT_VERSION})"
        ),
    )
    architecture = result.add_mutually_exclusive_group()
    architecture.add_argument("--require-x64", action="store_true")
    architecture.add_argument("--require-arm64", action="store_true")
    result.add_argument("--report", type=Path, help="Write a JSON result report")
    return result


def main(arguments: list[str] | None = None) -> int:
    started = time.perf_counter()
    args = parser().parse_args(arguments)
    wheel = acceptance.resolve_wheel(args.wheel)
    if args.require_x64:
        machine = acceptance.assert_x64()
    elif args.require_arm64:
        machine = acceptance.assert_arm64()
    else:
        machine = platform.machine()

    temporary_path = Path(tempfile.mkdtemp(prefix="prodockit-adopt-upgrade-"))
    try:
        environment = temporary_path / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = acceptance.venv_python(environment)
        install_old_release(python, temporary_path, args.old_version)
        old_versions = installed_versions(python, temporary_path)
        if old_versions["prodockit"] != args.old_version:
            raise acceptance.AcceptanceError(
                f"expected old Prodockit {args.old_version}, found {old_versions['prodockit']}"
            )

        project = temporary_path / "old-adopted-site"
        project.mkdir()
        acceptance.fixture(project, "zensical.toml", mermaid=True, maths=True)
        old_output = acceptance.adopt(
            python,
            project,
            mermaid=True,
            maths=True,
            apply=True,
        )
        if "Nothing has been committed or pushed" not in old_output:
            raise acceptance.AcceptanceError("old release did not complete project adoption")
        acceptance.build(
            python,
            project,
            acceptance.find_config(project),
            fixture_content=True,
        )
        old_source = acceptance.snapshot(project)

        install_upgrade(python, wheel)
        candidate_versions = installed_versions(python, temporary_path)
        if candidate_versions["prodockit"] == old_versions["prodockit"]:
            raise acceptance.AcceptanceError("candidate did not upgrade the installed Prodockit")

        result = acceptance.exercise(
            python,
            project,
            name="old-adopted-site",
            mermaid=True,
            maths=True,
            fixture_content=True,
        )
        expected = {
            "requirements.txt",
            "docs/stylesheets/pdk.css",
        }
        missing = expected - set(result.changed_files)
        if missing:
            raise acceptance.AcceptanceError(
                "candidate did not refresh managed adoption files: " + ", ".join(sorted(missing))
            )
        if acceptance.snapshot(project) == old_source:
            raise acceptance.AcceptanceError("candidate left the old adopted project unchanged")

        report: dict[str, Any] = {
            "wheel": str(wheel),
            "platform": platform.platform(),
            "architecture": machine,
            "old_versions": old_versions,
            "candidate_versions": candidate_versions,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "result": asdict(result),
        }
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Report: {args.report.resolve()}")
        print(
            "PASS: upgraded a fully adopted project from "
            f"Prodockit {old_versions['prodockit']} to {candidate_versions['prodockit']}"
        )
    except Exception:
        print(f"Work directory preserved for diagnosis: {temporary_path}", file=sys.stderr)
        raise
    else:
        shutil.rmtree(temporary_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (acceptance.AcceptanceError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise bootstrap repository and upgrade routes from an installed wheel.

The routes run serially in one native runner.  Creating and installing
the wheel is the expensive part; sharing that environment keeps the matrix to
five jobs while retaining complete operating-system and processor coverage.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path
from typing import Any

SCENARIOS = (
    ("surrey-new", "surrey", "new", False),
    ("surrey-existing", "surrey", "existing", False),
    ("surrey-existing-old-software", "surrey", "existing", True),
    ("github-new-old-software", "github", "new", True),
    ("github-existing", "github", "existing", False),
)


class AcceptanceError(RuntimeError):
    """The installed wheel or one bootstrap route failed acceptance."""


def resolve_wheel(value: Path) -> Path:
    if value.is_file() and value.suffix == ".whl":
        return value.resolve()
    wheels = sorted(value.glob("prodockit-*.whl")) if value.is_dir() else []
    if len(wheels) != 1:
        raise AcceptanceError(f"expected one prodockit wheel in {value}; found {len(wheels)}")
    return wheels[0].resolve()


def environment_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def require_architecture(*, x64: bool, arm64: bool) -> str:
    machine = platform.machine().lower()
    if x64 and machine not in {"amd64", "x86_64"}:
        raise AcceptanceError(f"expected x64, found {machine}")
    if arm64 and machine not in {"arm64", "aarch64"}:
        raise AcceptanceError(f"expected ARM64, found {machine}")
    return machine


def run(command: list[str], *, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise AcceptanceError(
            f"command failed ({' '.join(command)}):\n{result.stdout}\n{result.stderr}"
        )
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--wheel", type=Path, required=True)
    architecture = result.add_mutually_exclusive_group()
    architecture.add_argument("--require-x64", action="store_true")
    architecture.add_argument("--require-arm64", action="store_true")
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--keep-on-failure", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    wheel = resolve_wheel(args.wheel)
    machine = require_architecture(x64=args.require_x64, arm64=args.require_arm64)
    root = Path(tempfile.mkdtemp(prefix="prodockit-bootstrap-"))
    failed = True
    started = time.perf_counter()
    reports: list[dict[str, Any]] = []
    try:
        environment = root / ".venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment_python(environment)
        run([str(python), "-m", "pip", "install", str(wheel)], cwd=root)
        driver = Path(__file__).with_name("_bootstrap_acceptance_driver.py").resolve()
        for name, host, route, old_software in SCENARIOS:
            scenario_root = root / name
            scenario_report = root / f"{name}.json"
            completed = run(
                [
                    str(python),
                    str(driver),
                    "--root",
                    str(scenario_root),
                    "--host",
                    host,
                    "--route",
                    route,
                    *(["--old-software"] if old_software else []),
                    "--report",
                    str(scenario_report),
                ],
                cwd=scenario_root.parent,
            )
            report = json.loads(scenario_report.read_text(encoding="utf-8"))
            report["output"] = completed.stdout.strip()
            reports.append(report)
            print(f"{name}: passed in {report['duration_seconds']}s")
        failed = False
    finally:
        summary = {
            "passed": not failed,
            "machine": machine,
            "python": platform.python_version(),
            "wheel": wheel.name,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "scenarios": reports,
            "temporary_root": str(root) if failed else None,
        }
        args.report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if not (failed and args.keep_on_failure):
            shutil.rmtree(root, ignore_errors=True)
    print(json.dumps(summary))


if __name__ == "__main__":
    try:
        main()
    except AcceptanceError as error:
        print(f"acceptance failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error

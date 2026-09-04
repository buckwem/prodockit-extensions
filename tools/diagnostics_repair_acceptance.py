# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Run the complete diagnostic repair flow from an installed wheel."""

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


class AcceptanceError(RuntimeError):
    """The installed wheel or its complete repair scenario failed."""


def resolve_wheel(value: Path) -> Path:
    if value.is_file() and value.suffix == ".whl":
        return value.resolve()
    wheels = sorted(value.glob("prodockit-*.whl")) if value.is_dir() else []
    if len(wheels) != 1:
        raise AcceptanceError(f"expected one prodockit wheel in {value}; found {len(wheels)}")
    return wheels[0].resolve()


def environment_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def environment_scripts(environment: Path) -> Path:
    return environment / ("Scripts" if os.name == "nt" else "bin")


def require_architecture(*, x64: bool, arm64: bool) -> str:
    machine = platform.machine().lower()
    if x64 and machine not in {"amd64", "x86_64"}:
        raise AcceptanceError(f"expected x64, found {machine}")
    if arm64 and machine not in {"arm64", "aarch64"}:
        raise AcceptanceError(f"expected ARM64, found {machine}")
    return machine


def run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    configured = dict(os.environ if environment is None else environment)
    configured.pop("PYTHONPATH", None)
    configured["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=configured,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode:
        detail = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise AcceptanceError(f"command failed ({' '.join(command)}):\n{detail}")
    return completed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Test every safe pdk diag repair from an installed candidate wheel."
    )
    result.add_argument("--wheel", type=Path, required=True)
    architecture = result.add_mutually_exclusive_group()
    architecture.add_argument("--require-x64", action="store_true")
    architecture.add_argument("--require-arm64", action="store_true")
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--keep-on-failure", action="store_true")
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    wheel = resolve_wheel(args.wheel)
    machine = require_architecture(x64=args.require_x64, arm64=args.require_arm64)
    report_path = args.report.resolve()
    root = Path(tempfile.mkdtemp(prefix="prodockit-diagnostics-repair-"))
    started = time.perf_counter()
    failed = True
    summary: dict[str, Any] = {}
    try:
        environment = root / ".venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment_python(environment)
        run([str(python), "-m", "pip", "install", str(wheel)], cwd=root)
        prefix_result = run(
            [str(python), "-c", "import sys; print(sys.prefix)"],
            cwd=root,
        )
        running_environment = Path(prefix_result.stdout.strip())
        if not running_environment.is_absolute():
            raise AcceptanceError(
                f"wheel interpreter reported a non-absolute prefix: {running_environment}"
            )

        child_environment = dict(os.environ)
        child_environment["VIRTUAL_ENV"] = str(running_environment)
        child_environment["PATH"] = os.pathsep.join(
            (
                str(environment_scripts(running_environment)),
                child_environment.get("PATH", ""),
            )
        )
        child_environment["PUPPETEER_SKIP_DOWNLOAD"] = "true"
        driver = Path(__file__).with_name("_diagnostics_repair_acceptance_driver.py").resolve()
        driver_report = root / "driver-report.json"
        completed = run(
            [
                str(python),
                str(driver),
                "--root",
                str(root / "project with spaces"),
                "--report",
                str(driver_report),
            ],
            cwd=root,
            environment=child_environment,
        )
        scenario = json.loads(driver_report.read_text(encoding="utf-8"))
        summary = {
            "passed": True,
            "platform": platform.platform(),
            "machine": machine,
            "python": platform.python_version(),
            "wheel": wheel.name,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "scenario": scenario,
            "output": completed.stdout.strip(),
            "temporary_root": None,
        }
        failed = False
        return 0
    except (AcceptanceError, OSError, ValueError, json.JSONDecodeError) as error:
        summary = {
            "passed": False,
            "platform": platform.platform(),
            "machine": machine,
            "python": platform.python_version(),
            "wheel": wheel.name,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": str(error),
            "temporary_root": str(root),
        }
        print(f"acceptance failed: {error}", file=sys.stderr)
        return 1
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if not (failed and args.keep_on_failure):
            shutil.rmtree(root, ignore_errors=True)
        print(json.dumps(summary))


if __name__ == "__main__":
    raise SystemExit(main())

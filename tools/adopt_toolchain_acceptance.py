# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Run one genuine Adopt upgrade or downgrade from an installed wheel."""

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

# Real published wheels immediately below the supported combination. They are
# installed intact for the upgrade scenario; no metadata or package files are
# altered by the harness.
PREVIOUS_PYTHON_VERSIONS = {
    "zensical": "0.0.58",
    "weasyprint": "68.1",
    "markdown": "3.10.2",
    "pymdown-extensions": "11.0.1",
}

# All managed Python pins are currently the newest published releases, so no
# genuine newer Python distribution exists. Pandoc publishes both adjacent
# releases on every target platform, giving the downgrade scenario one real
# newer executable to install and replace without simulation.
PANDOC_FIXTURE_VERSIONS = {
    "upgrade": "3.10",
    "downgrade": "3.10.2",
}


class AcceptanceError(RuntimeError):
    """The installed wheel did not align the complete supported toolchain."""


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


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _excerpt(path: Path, *, limit: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def run_logged(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    environment: dict[str, str],
    timeout: int,
) -> None:
    """Use regular files so inherited Windows handles cannot hold a pipe open."""

    configured = dict(environment)
    configured.pop("PYTHONPATH", None)
    configured.update(
        {
            "PYTHONUTF8": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_RETRIES": "5",
            "PIP_TIMEOUT": "30",
            "PIP_PREFER_BINARY": "1",
        }
    )
    try:
        with (
            stdout_path.open("w", encoding="utf-8", errors="replace") as stdout,
            stderr_path.open("w", encoding="utf-8", errors="replace") as stderr,
        ):
            result = subprocess.run(
                command,
                cwd=cwd,
                env=configured,
                stdout=stdout,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
    except subprocess.TimeoutExpired as error:
        raise AcceptanceError(
            f"command timed out after {timeout} seconds: {' '.join(command)}\n"
            f"{_excerpt(stdout_path)}\n{_excerpt(stderr_path)}"
        ) from error
    if result.returncode:
        raise AcceptanceError(
            f"command failed ({' '.join(command)}):\n"
            f"{_excerpt(stdout_path)}\n{_excerpt(stderr_path)}"
        )


def _supported_versions(
    python: Path,
    *,
    root: Path,
    environment: dict[str, str],
) -> dict[str, str]:
    stdout = root / "supported-versions.stdout.log"
    stderr = root / "supported-versions.stderr.log"
    run_logged(
        [
            str(python),
            "-c",
            (
                "import json; from prodockit.pins import TESTED_VERSIONS; "
                "print(json.dumps(TESTED_VERSIONS))"
            ),
        ],
        cwd=root,
        environment=environment,
        stdout_path=stdout,
        stderr_path=stderr,
        timeout=30,
    )
    try:
        value = json.loads(stdout.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceError("could not read the candidate supported-version manifest") from error
    if not isinstance(value, dict) or not all(
        isinstance(package, str) and isinstance(version, str)
        for package, version in value.items()
    ):
        raise AcceptanceError("candidate supported versions are not a string mapping")
    return value


def install_real_fixture(
    python: Path,
    *,
    root: Path,
    environment: dict[str, str],
    scenario: str,
    supported: dict[str, str],
) -> dict[str, str]:
    """Install only unmodified, published package and Pandoc artifacts."""

    python_versions = {
        package: (
            PREVIOUS_PYTHON_VERSIONS[package]
            if scenario == "upgrade"
            else supported[package]
        )
        for package in PREVIOUS_PYTHON_VERSIONS
    }
    run_logged(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--only-binary=:all:",
            "--no-deps",
            "--retries",
            "5",
            "--timeout",
            "30",
            "--prefer-binary",
            *(f"{package}=={version}" for package, version in python_versions.items()),
        ],
        cwd=root,
        environment=environment,
        stdout_path=root / "fixture-python.stdout.log",
        stderr_path=root / "fixture-python.stderr.log",
        timeout=900,
    )
    pandoc = PANDOC_FIXTURE_VERSIONS[scenario]
    run_logged(
        [
            str(python),
            "-m",
            "prodockit.toolchain",
            "install-pandoc",
            "--version",
            pandoc,
        ],
        cwd=root,
        environment=environment,
        stdout_path=root / "fixture-pandoc.stdout.log",
        stderr_path=root / "fixture-pandoc.stderr.log",
        timeout=900,
    )
    return {**python_versions, "pandoc": pandoc}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Test Adopt toolchain alignment from an installed candidate wheel."
    )
    result.add_argument("--wheel", type=Path, required=True)
    result.add_argument("--scenario", choices=("upgrade", "downgrade"), required=True)
    architecture = result.add_mutually_exclusive_group()
    architecture.add_argument("--require-x64", action="store_true")
    architecture.add_argument("--require-arm64", action="store_true")
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--driver-timeout-seconds", type=positive_integer, default=1500)
    result.add_argument("--keep-on-failure", action="store_true")
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    wheel = resolve_wheel(args.wheel)
    machine = require_architecture(x64=args.require_x64, arm64=args.require_arm64)
    report_path = args.report.resolve()
    root = Path(tempfile.mkdtemp(prefix=f"prodockit-adopt-{args.scenario}-"))
    stdout_path = root / "driver.stdout.log"
    stderr_path = root / "driver.stderr.log"
    started = time.perf_counter()
    failed = True
    summary: dict[str, Any]
    try:
        environment = root / ".venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment_python(environment)
        child_environment = dict(os.environ)
        child_environment["VIRTUAL_ENV"] = str(environment)
        child_environment["PATH"] = os.pathsep.join(
            (str(environment_scripts(environment)), child_environment.get("PATH", ""))
        )
        child_environment.setdefault(
            "PDK_NATIVE_DOWNLOAD_CACHE", str(Path.cwd() / ".cache" / "native-downloads")
        )
        install_stdout = root / "install.stdout.log"
        install_stderr = root / "install.stderr.log"
        run_logged(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--retries",
                "5",
                "--timeout",
                "30",
                "--prefer-binary",
                str(wheel),
            ],
            cwd=root,
            environment=child_environment,
            stdout_path=install_stdout,
            stderr_path=install_stderr,
            timeout=900,
        )
        supported = _supported_versions(
            python,
            root=root,
            environment=child_environment,
        )
        fixture_versions = install_real_fixture(
            python,
            root=root,
            environment=child_environment,
            scenario=args.scenario,
            supported=supported,
        )
        fixture_manifest = root / "fixture-versions.json"
        fixture_manifest.write_text(
            json.dumps(fixture_versions, indent=2) + "\n",
            encoding="utf-8",
        )
        driver = Path(__file__).with_name("_adopt_toolchain_acceptance_driver.py").resolve()
        driver_report = root / "driver-report.json"
        run_logged(
            [
                str(python),
                str(driver),
                "--scenario",
                args.scenario,
                "--root",
                str(root / "project with spaces"),
                "--report",
                str(driver_report),
                "--fixture-versions",
                str(fixture_manifest),
            ],
            cwd=root,
            environment=child_environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=args.driver_timeout_seconds,
        )
        scenario = json.loads(driver_report.read_text(encoding="utf-8"))
        summary = {
            "passed": True,
            "scenario": args.scenario,
            "platform": platform.platform(),
            "machine": machine,
            "python": platform.python_version(),
            "wheel": wheel.name,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "result": scenario,
            "output": _excerpt(stdout_path).strip(),
            "temporary_root": None,
        }
        failed = False
        return 0
    except (AcceptanceError, OSError, ValueError, json.JSONDecodeError) as error:
        summary = {
            "passed": False,
            "scenario": args.scenario,
            "platform": platform.platform(),
            "machine": machine,
            "python": platform.python_version(),
            "wheel": wheel.name,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": str(error),
            "stdout": _excerpt(stdout_path),
            "stderr": _excerpt(stderr_path),
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

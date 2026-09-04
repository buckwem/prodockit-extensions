# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Align genuine published package and Pandoc installations."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import prodockit
from prodockit import diagnostics
from prodockit.pins import DEFAULT_PACKAGES, TESTED_VERSIONS, discover
from prodockit.toolchain import (
    PYTHON_PACKAGES,
    TOOLCHAIN_MANIFEST,
    installed_pandoc_version,
)


class AcceptanceError(RuntimeError):
    """The installed wheel did not align or verify the fixture."""


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _distribution_fingerprint(package: str) -> dict[str, str | int]:
    """Hash installed package code while excluding all metadata."""

    distribution = importlib.metadata.distribution(package)
    digest = hashlib.sha256()
    count = 0
    for entry in sorted(distribution.files or (), key=str):
        if any(part.endswith(".dist-info") for part in entry.parts):
            continue
        path = Path(distribution.locate_file(entry))
        if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        digest.update(str(entry).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        count += 1
    if count == 0:
        raise AcceptanceError(f"published {package} distribution installed no code files")
    return {"files": count, "sha256": digest.hexdigest()}


def _pandoc_fingerprint() -> dict[str, str]:
    executable = shutil.which("pandoc")
    version = installed_pandoc_version()
    if executable is None or version is None:
        raise AcceptanceError("a working published Pandoc executable is not installed")
    return {
        "version": version,
        "sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
    }


def _install_cached_pandoc(project: Path, version: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "prodockit.toolchain",
            "install-pandoc",
            "--version",
            version,
            "--offline",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if result.returncode:
        raise AcceptanceError(
            f"could not reinstall genuine cached Pandoc {version}:\n{_output(result)}"
        )


def _run_cli(
    project: Path,
    arguments: list[str],
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "prodockit", *arguments],
        cwd=project,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def write_fixture(project: Path) -> None:
    project.mkdir(parents=True)
    _write(
        project / "zensical.toml",
        """\
[project]
site_name = "Adopt toolchain acceptance"
docs_dir = "docs"
nav = [{ Home = "index.md" }]
""",
    )
    _write(project / "docs" / "index.md", "# Existing project\n")
    _write(
        project / "requirements.txt",
        "sphinx==8.0\nprodockit[index]>=0.1  # preserve extras and operator\n",
    )


def _versions() -> dict[str, str | None]:
    script = """\
import importlib.metadata
import json
import sys

versions = {}
for name in sys.argv[1:]:
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        versions[name] = None
print(json.dumps(versions))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, *PYTHON_PACKAGES],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise AcceptanceError(f"could not inspect installed versions: {result.stderr}")
    value = json.loads(result.stdout)
    return {package: value.get(package) for package in PYTHON_PACKAGES}


def exercise(
    project: Path,
    scenario: str,
    fixture_versions: dict[str, str],
) -> dict[str, Any]:
    started = time.perf_counter()
    installed = Path(prodockit.__file__).resolve()
    try:
        installed.relative_to(Path(sys.prefix).resolve())
    except ValueError as error:
        raise AcceptanceError(f"Prodockit was not imported from the wheel: {installed}") from error
    expected_python = TESTED_VERSIONS["python"]
    active_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if active_python != expected_python:
        raise AcceptanceError(f"fixture needs Python {expected_python}, found {active_python}")

    before_versions = _versions()
    expected_before = {
        package: fixture_versions.get(package, TESTED_VERSIONS[package])
        for package in PYTHON_PACKAGES
    }
    version_mismatches = {
        package: (before_versions[package], expected)
        for package, expected in expected_before.items()
        if before_versions[package] != expected
    }
    if version_mismatches:
        raise AcceptanceError(
            f"published Python fixture installation failed: {version_mismatches}"
        )
    before_code = {
        package: _distribution_fingerprint(package)
        for package in PYTHON_PACKAGES
        if package != "prodockit"
    }
    before_pandoc = _pandoc_fingerprint()
    if before_pandoc["version"] != fixture_versions["pandoc"]:
        raise AcceptanceError(
            f"published Pandoc fixture installation failed: {before_pandoc['version']}"
        )
    before = {**before_versions, "pandoc": before_pandoc["version"]}
    write_fixture(project)
    os.chdir(project)
    dry_run = _run_cli(
        project,
        ["adopt", "--dry-run", "--no-mermaid", "--no-maths"],
    )
    dry_output = _output(dry_run)
    if dry_run.returncode:
        raise AcceptanceError(f"Adopt dry-run failed:\n{dry_output}")
    if scenario not in dry_output:
        raise AcceptanceError(f"dry-run did not identify the {scenario} actions:\n{dry_output}")
    if "Command:" not in dry_output or "File:" not in dry_output:
        raise AcceptanceError("dry-run omitted the commands or affected files")

    applied = _run_cli(
        project,
        ["adopt", "--apply", "--no-mermaid", "--no-maths"],
        input_text="y\ny\n",
    )
    if applied.returncode:
        raise AcceptanceError(f"Adopt apply failed:\n{_output(applied)}")

    versions = _versions()
    mismatches = {
        package: (versions[package], TESTED_VERSIONS[package])
        for package in PYTHON_PACKAGES
        if versions[package] != TESTED_VERSIONS[package]
    }
    if mismatches:
        raise AcceptanceError(f"Python package verification failed: {mismatches}")
    after_code = {
        package: _distribution_fingerprint(package)
        for package in PYTHON_PACKAGES
        if package != "prodockit"
    }
    expected_code_changes = {
        package
        for package, version in fixture_versions.items()
        if package in PYTHON_PACKAGES and version != TESTED_VERSIONS[package]
    }
    unchanged_code = {
        package
        for package in expected_code_changes
        if before_code[package] == after_code[package]
    }
    if unchanged_code:
        raise AcceptanceError(
            "package versions changed without changing their installed code: "
            + ", ".join(sorted(unchanged_code))
        )
    after_pandoc = _pandoc_fingerprint()
    if after_pandoc["version"] != TESTED_VERSIONS["pandoc"]:
        raise AcceptanceError(
            f"Pandoc verification failed: expected {TESTED_VERSIONS['pandoc']}, "
            f"found {after_pandoc['version']}"
        )
    if before_pandoc["sha256"] == after_pandoc["sha256"]:
        raise AcceptanceError("Pandoc version changed without replacing its executable code")
    states = discover(str(project))
    declaration_mismatches = {
        package: state.versions
        for package, state in states.items()
        if state.versions != [TESTED_VERSIONS[package]]
    }
    if declaration_mismatches:
        raise AcceptanceError(f"declaration verification failed: {declaration_mismatches}")
    requirements = (project / "requirements.txt").read_text(encoding="utf-8")
    if "sphinx==8.0" not in requirements or "prodockit[index]>=" not in requirements:
        raise AcceptanceError("Adopt removed an unrelated requirement, operator or extras")
    if not (project / TOOLCHAIN_MANIFEST).is_file():
        raise AcceptanceError("Adopt did not write its supported-toolchain manifest")

    # Reinstall the genuine starting Pandoc from its validated cache, then
    # prove the supported release can also be restored without networking.
    _install_cached_pandoc(project, fixture_versions["pandoc"])
    cached = _run_cli(
        project,
        ["adopt", "--apply", "--offline", "--no-mermaid", "--no-maths"],
        input_text="y\n",
    )
    if cached.returncode:
        raise AcceptanceError(f"offline Pandoc cache repair failed:\n{_output(cached)}")

    pandoc_version = installed_pandoc_version()
    if pandoc_version != TESTED_VERSIONS["pandoc"]:
        raise AcceptanceError(
            f"Pandoc verification failed: expected {TESTED_VERSIONS['pandoc']}, "
            f"found {pandoc_version or 'unreadable'}"
        )

    pins = _run_cli(
        project,
        ["pins", "--root", str(project), "--check", "--offline"],
    )
    if pins.returncode:
        raise AcceptanceError(f"pins --check --offline failed:\n{_output(pins)}")
    report = diagnostics.inspect(project / "zensical.toml", online=False)
    pin_check = next(check for check in report.checks if check.id == "dependencies.pins")
    if pin_check.status != "pass":
        raise AcceptanceError(
            f"pdk diag still reports unsupported toolchain: {pin_check.summary} {pin_check.details}"
        )

    repeated = _run_cli(
        project,
        ["adopt", "--apply", "--no-mermaid", "--no-maths"],
    )
    repeated_output = _output(repeated)
    if repeated.returncode or "already configured" not in repeated_output:
        raise AcceptanceError(f"Adopt rerun was not idempotent:\n{repeated_output}")
    return {
        "passed": True,
        "scenario": scenario,
        "before": before,
        "after": versions,
        "pandoc": pandoc_version,
        "code_fingerprints": {
            "before": {**before_code, "pandoc": before_pandoc},
            "after": {**after_code, "pandoc": after_pandoc},
        },
        "offline_cache_hit": True,
        "declarations": {name: states[name].versions for name in DEFAULT_PACKAGES},
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--scenario", choices=("upgrade", "downgrade"), required=True)
    result.add_argument("--root", type=Path, required=True)
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--fixture-versions", type=Path, required=True)
    return result


def main(arguments: list[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    try:
        fixture_versions = json.loads(options.fixture_versions.read_text(encoding="utf-8"))
        if not isinstance(fixture_versions, dict) or not all(
            isinstance(package, str) and isinstance(version, str)
            for package, version in fixture_versions.items()
        ):
            raise AcceptanceError("fixture versions are not a string mapping")
        result = exercise(options.root.resolve(), options.scenario, fixture_versions)
    except (AcceptanceError, OSError, ValueError, json.JSONDecodeError) as error:
        options.report.write_text(
            json.dumps({"passed": False, "error": str(error)}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"acceptance failed: {error}", file=sys.stderr)
        return 1
    options.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

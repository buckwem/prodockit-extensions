# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Create and align one older or newer installed-toolchain fixture."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from typing import Any

import prodockit
from prodockit import diagnostics
from prodockit.pins import DEFAULT_PACKAGES, TESTED_VERSIONS, discover
from prodockit.toolchain import PYTHON_PACKAGES, TOOLCHAIN_MANIFEST


class AcceptanceError(RuntimeError):
    """The installed wheel did not align or verify the fixture."""


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _metadata_path(package: str, fixture_version: str) -> Path:
    try:
        distribution = importlib.metadata.distribution(package)
    except importlib.metadata.PackageNotFoundError:
        purelib = sysconfig.get_path("purelib")
        if not purelib:
            raise AcceptanceError("the wheel environment has no site-packages directory") from None
        path = Path(purelib) / f"{package.replace('-', '_')}-{fixture_version}.dist-info"
        _write(
            path / "METADATA",
            f"Metadata-Version: 2.1\nName: {package}\nVersion: {fixture_version}\n",
        )
        _write(path / "WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
        _write(
            path / "RECORD",
            "\n".join(
                (
                    f"{path.name}/METADATA,,",
                    f"{path.name}/WHEEL,,",
                    f"{path.name}/RECORD,,",
                    "",
                )
            ),
        )
        importlib.invalidate_caches()
        return path / "METADATA"
    dist_path_value = getattr(distribution, "_path", None)
    dist_path = dist_path_value if isinstance(dist_path_value, Path) else Path(str(dist_path_value))
    metadata = dist_path / "METADATA"
    if not metadata.is_file():
        raise AcceptanceError(f"cannot locate installed metadata for {package}: {metadata}")
    return metadata


def _set_installed_version(package: str, version: str) -> None:
    metadata = _metadata_path(package, version)
    source = metadata.read_text(encoding="utf-8")
    current = re.search(r"(?m)^Version: (.+)$", source)
    if current is None:
        raise AcceptanceError(f"cannot read installed fixture version for {package}")
    updated, count = re.subn(r"(?m)^Version: .+$", f"Version: {version}", source, count=1)
    if count != 1:
        raise AcceptanceError(f"cannot alter installed fixture version for {package}")
    metadata.write_text(updated, encoding="utf-8")
    directory = metadata.parent
    suffix = f"-{current.group(1)}.dist-info"
    if directory.name.endswith(suffix) and current.group(1) != version:
        renamed = directory.with_name(directory.name[: -len(suffix)] + f"-{version}.dist-info")
        record = directory / "RECORD"
        if record.is_file():
            record.write_text(
                record.read_text(encoding="utf-8").replace(directory.name, renamed.name),
                encoding="utf-8",
            )
        directory.replace(renamed)
    importlib.invalidate_caches()


def _fake_pandoc(version: str) -> Path:
    scripts_value = sysconfig.get_path("scripts")
    if not scripts_value:
        raise AcceptanceError("the wheel environment has no scripts directory")
    scripts = Path(scripts_value)
    scripts.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        (scripts / "pandoc.exe").unlink(missing_ok=True)
        path = scripts / "pandoc.cmd"
        _write(path, f"@echo off\necho pandoc {version}\n")
    else:
        path = scripts / "pandoc"
        _write(path, f"#!/bin/sh\nprintf 'pandoc {version}\\n'\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


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


def write_fixture(project: Path, scenario: str) -> dict[str, str]:
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
    fixture_version = "0.0.1" if scenario == "upgrade" else "999.0.0"
    changed: dict[str, str] = {}
    for package in PYTHON_PACKAGES:
        if package == "prodockit":
            continue
        _set_installed_version(package, fixture_version)
        changed[package] = fixture_version
    _fake_pandoc("2.19" if scenario == "upgrade" else "999.0")
    changed["pandoc"] = "2.19" if scenario == "upgrade" else "999.0"
    return changed


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


def exercise(project: Path, scenario: str) -> dict[str, Any]:
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

    before = write_fixture(project, scenario)
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

    # Break Pandoc alone, then prove the validated archive retained by the
    # first run is sufficient with networking explicitly disabled.
    _fake_pandoc("2.18" if scenario == "upgrade" else "999.1")
    cached = _run_cli(
        project,
        ["adopt", "--apply", "--offline", "--no-mermaid", "--no-maths"],
        input_text="y\n",
    )
    if cached.returncode:
        raise AcceptanceError(f"offline Pandoc cache repair failed:\n{_output(cached)}")

    pandoc_command = shutil.which("pandoc")
    if pandoc_command is None:
        raise AcceptanceError("Pandoc is absent after the cached repair")
    pandoc_result = subprocess.run(
        [pandoc_command, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    pandoc_version = pandoc_result.stdout.splitlines()[0].removeprefix("pandoc ").strip()
    if pandoc_result.returncode or pandoc_version != TESTED_VERSIONS["pandoc"]:
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
        "offline_cache_hit": True,
        "declarations": {name: states[name].versions for name in DEFAULT_PACKAGES},
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--scenario", choices=("upgrade", "downgrade"), required=True)
    result.add_argument("--root", type=Path, required=True)
    result.add_argument("--report", type=Path, required=True)
    return result


def main(arguments: list[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    try:
        result = exercise(options.root.resolve(), options.scenario)
    except (AcceptanceError, OSError, ValueError) as error:
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

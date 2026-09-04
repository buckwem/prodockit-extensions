# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise template-sync's real wheel handoff in both directions.

The starting wheels contain the candidate's actual code with deliberately
older/newer distribution metadata.  Pip therefore performs a genuine wheel
upgrade or downgrade, while both starting releases already understand the new
single-command handoff.  The exact candidate wheel is selected from an offline
wheelhouse; Adopt first prepares the remaining real supported toolchain.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

if __package__:
    from tools import adopt_acceptance as acceptance
else:  # pragma: no cover - direct ``python tools/...`` execution
    acceptance = importlib.import_module("adopt_acceptance")


def wheel_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")
    match = re.search(r"(?m)^Version: (.+)$", metadata)
    if match is None:
        raise acceptance.AcceptanceError(f"wheel has no Version metadata: {wheel}")
    return match.group(1).strip()


def adjacent_versions(version: str) -> tuple[str, str]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise acceptance.AcceptanceError(
            f"acceptance harness needs a three-part stable candidate version, found {version}"
        )
    major, minor, patch = (int(part) for part in match.groups())
    lower = f"{major}.{minor - 1}.999" if minor else f"{major}.0.{max(0, patch - 1)}"
    higher = f"{major}.{minor}.{patch + 1}"
    if lower == version:
        raise acceptance.AcceptanceError(f"could not derive an older version from {version}")
    return lower, higher


def _record_line(path: str, data: bytes) -> tuple[str, str, str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return path, f"sha256={digest}", str(len(data))


def versioned_wheel(candidate: Path, version: str, destination: Path) -> Path:
    """Clone a wheel with coherent metadata for a real cross-version install."""

    files: dict[str, bytes] = {}
    with zipfile.ZipFile(candidate) as archive:
        old_dist_info = next(
            name.split("/", 1)[0]
            for name in archive.namelist()
            if name.endswith(".dist-info/METADATA")
        )
        new_dist_info = re.sub(r"-[^-]+\.dist-info$", f"-{version}.dist-info", old_dist_info)
        for item in archive.infolist():
            if item.is_dir() or item.filename.endswith(".dist-info/RECORD"):
                continue
            name = item.filename.replace(old_dist_info + "/", new_dist_info + "/", 1)
            data = archive.read(item.filename)
            if name == f"{new_dist_info}/METADATA":
                data = re.sub(
                    rb"(?m)^Version: .+$",
                    f"Version: {version}".encode(),
                    data,
                    count=1,
                )
            elif name == "prodockit/__init__.py":
                data = re.sub(
                    rb'(?m)^__version__ = "[^"]+"$',
                    f'__version__ = "{version}"'.encode(),
                    data,
                    count=1,
                )
            files[name] = data

    record_name = f"{new_dist_info}/RECORD"
    rows = [_record_line(name, data) for name, data in sorted(files.items())]
    rows.append((record_name, "", ""))
    record = []
    for row in rows:
        stream = io.StringIO()
        csv.writer(stream, lineterminator="\n").writerow(row)
        record.append(stream.getvalue())
    files[record_name] = "".join(record).encode()

    output = destination / f"prodockit-{version}-py3-none-any.whl"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return output


def git(root: Path, *arguments: str) -> str:
    completed = acceptance.run(["git", "-C", str(root), *arguments], cwd=root)
    return completed.stdout.strip()


def prepare_template(root: Path, version: str) -> tuple[Path, str]:
    template = root / "template"
    template.mkdir()
    (template / ".prodockit-template.toml").write_text(
        """\
version = 1

[template]
owns = ["managed.txt"]

[project]
owns = ["docs/**", "requirements.txt"]

[shared]
files = []

[excluded]
paths = [".prodockit-template.toml"]
""",
        encoding="utf-8",
    )
    (template / "requirements.txt").write_text(f"prodockit>={version}\n", encoding="utf-8")
    (template / "managed.txt").write_text("before\n", encoding="utf-8")
    git(template, "init", "-b", "main", "-q")
    git(template, "config", "user.name", "Acceptance")
    git(template, "config", "user.email", "acceptance@example.com")
    git(template, "config", "commit.gpgsign", "false")
    git(template, "add", ".")
    git(template, "commit", "-qm", "starting template")
    old = git(template, "rev-parse", "HEAD")
    (template / "managed.txt").write_text("after\n", encoding="utf-8")
    git(template, "commit", "-qam", "template update")
    return template, old


def prepare_project(root: Path, python: Path, candidate: Path, old_revision: str) -> Path:
    project = root / "project with spaces"
    project.mkdir()
    acceptance.fixture(project, "zensical.toml", mermaid=False, maths=False)
    acceptance.install_candidate(python, candidate, project=None)
    acceptance.adopt(python, project, mermaid=False, maths=False, apply=True)
    (project / "managed.txt").write_text("before\n", encoding="utf-8")
    (project / ".prodockit-template").write_text(f"{old_revision}\n", encoding="utf-8")
    (project / ".gitignore").write_text(".prodockit-template.log\n", encoding="utf-8")
    git(project, "init", "-b", "main", "-q")
    git(project, "config", "user.name", "Acceptance")
    git(project, "config", "user.email", "acceptance@example.com")
    git(project, "config", "commit.gpgsign", "false")
    git(project, "add", ".")
    git(project, "commit", "-qm", "starting project")
    return project


@contextmanager
def environment(**values: str) -> Iterator[None]:
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def installed_version(python: Path, root: Path) -> str:
    return acceptance.run(
        [
            str(python),
            "-c",
            "from importlib.metadata import version; print(version('prodockit'))",
        ],
        cwd=root,
    ).stdout.strip()


def loaded_version(python: Path, root: Path) -> str:
    """Read the version from package code in a genuinely fresh interpreter."""

    return acceptance.run(
        [str(python), "-c", "import prodockit; print(prodockit.__version__)"],
        cwd=root,
    ).stdout.strip()


def scenario(
    root: Path,
    candidate: Path,
    starting: Path,
    target: str,
    action: str,
    cache: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    environment_root = root / "venv with spaces"
    venv.EnvBuilder(with_pip=True, clear=True).create(environment_root)
    python = acceptance.venv_python(environment_root)
    template, old = prepare_template(root, target)
    project = prepare_project(root, python, candidate, old)
    acceptance.run(
        [str(python), "-m", "pip", "install", "--force-reinstall", "--no-deps", str(starting)],
        cwd=root,
    )
    before = installed_version(python, root)
    if before == target:
        raise acceptance.AcceptanceError(f"{action}: starting wheel did not change version")

    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    shutil.copy2(candidate, wheelhouse / candidate.name)
    # A candidate import during setup leaves bytecode behind. On Windows a
    # rapid force-reinstall can preserve a still-valid timestamp for that
    # cache even though the starting wheel's source has changed. Point every
    # test interpreter, including the child handoff, at a new empty cache so
    # it must execute the installed starting wheel's source.
    bytecode_cache = root / "fresh bytecode cache"
    with environment(
        PDK_WHEELHOUSE=str(wheelhouse),
        PDK_NATIVE_DOWNLOAD_CACHE=str(cache),
        PYTHONPYCACHEPREFIX=str(bytecode_cache),
    ):
        loaded = loaded_version(python, root)
        if loaded != before:
            raise acceptance.AcceptanceError(
                f"{action}: loaded code is {loaded}, but installed metadata is {before}"
            )
        completed = acceptance.run(
            [
                str(python),
                "-m",
                "prodockit",
                "template-sync",
                "--template-path",
                str(template),
                "--apply",
                "--local-only",
                "--offline",
                "--accept-prodockit",
                "--accept-adopt",
            ],
            cwd=project,
            timeout=1500,
        )
    output = completed.stdout
    if f"Action:   {action.upper()}" not in output:
        raise acceptance.AcceptanceError(f"{action}: action was not reported\n{output}")
    if "fresh-process handoff required" not in output:
        raise acceptance.AcceptanceError(f"{action}: fresh-process handoff was not reported")
    if "Supported toolchain: verified after applying template declarations" not in output:
        raise acceptance.AcceptanceError(f"{action}: final toolchain was not verified")
    if installed_version(python, root) != target:
        raise acceptance.AcceptanceError(f"{action}: candidate target was not installed")
    if (project / "managed.txt").read_text(encoding="utf-8") != "after\n":
        raise acceptance.AcceptanceError(f"{action}: template file was not applied")
    if not git(project, "branch", "--show-current").startswith("template-update-"):
        raise acceptance.AcceptanceError(f"{action}: review branch was not created")
    if "managed.txt" not in git(project, "diff", "--cached", "--name-only"):
        raise acceptance.AcceptanceError(f"{action}: update was not staged")

    git(project, "commit", "-qm", "apply template update")
    clean = acceptance.run(
        [str(python), "-m", "prodockit", "template-sync", "--template-path", str(template)],
        cwd=project,
    ).stdout
    if "already up to date with the template" not in clean:
        raise acceptance.AcceptanceError(f"{action}: second run was not idempotent\n{clean}")
    acceptance.run(
        [str(python), "-m", "prodockit", "pins", "--check", "--offline"],
        cwd=project,
    )
    diagnostic = acceptance.run(
        [str(python), "-m", "prodockit", "diag", "--json"],
        cwd=project,
    )
    payload = json.loads(diagnostic.stdout)
    if payload.get("status") == "fail":
        raise acceptance.AcceptanceError(f"{action}: final diagnostics failed")
    return {
        "action": action,
        "starting_version": before,
        "loaded_starting_version": loaded,
        "target_version": target,
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Test template-sync wheel upgrade and downgrade")
    result.add_argument("--wheel", type=Path, required=True)
    architecture = result.add_mutually_exclusive_group()
    architecture.add_argument("--require-x64", action="store_true")
    architecture.add_argument("--require-arm64", action="store_true")
    result.add_argument("--report", type=Path)
    return result


def main(arguments: list[str] | None = None) -> int:
    started = time.perf_counter()
    args = parser().parse_args(arguments)
    candidate = acceptance.resolve_wheel(args.wheel)
    target = wheel_version(candidate)
    lower, higher = adjacent_versions(target)
    if args.require_x64:
        machine = acceptance.assert_x64()
    elif args.require_arm64:
        machine = acceptance.assert_arm64()
    else:
        machine = platform.machine()

    temporary = Path(tempfile.mkdtemp(prefix="prodockit-template-sync-"))
    results: list[dict[str, Any]] = []
    try:
        variants = temporary / "variants"
        variants.mkdir()
        older = versioned_wheel(candidate, lower, variants)
        newer = versioned_wheel(candidate, higher, variants)
        cache = temporary / "native-cache"
        for name, wheel in (("upgrade", older), ("downgrade", newer)):
            case = temporary / name
            case.mkdir()
            results.append(scenario(case, candidate, wheel, target, name, cache))
    except Exception:
        print(f"Work directory preserved for diagnosis: {temporary}", file=sys.stderr)
        raise
    else:
        shutil.rmtree(temporary)

    report = {
        "wheel": str(candidate),
        "platform": platform.platform(),
        "architecture": machine,
        "target_version": target,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "results": results,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: real template-sync upgrade and downgrade to Prodockit {target}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (acceptance.AcceptanceError, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error

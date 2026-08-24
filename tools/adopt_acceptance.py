# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Acceptance-test an installed prodockit wheel's ``adopt`` command.

CI uses the built-in fixtures. Authors can instead pass ``--project`` and
``--output`` to exercise a real site in a disposable, non-Git copy. This file
uses only the standard library so it runs before the candidate wheel exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CONFIG_NAMES = ("zensical.toml", "zensical.yml", "zensical.yaml", "mkdocs.yml", "mkdocs.yaml")
REQUIREMENTS = ("requirements.txt", "requirements/docs.txt", "docs/requirements.txt")
GENERATED_DIRS = {".cache", ".git", ".venv", "site", "__pycache__", "node_modules"}
ADOPTED_SITE_FILES = {
    "stylesheets/prodockit.css",
    "javascripts/mathjax.js",
    "javascripts/vendor/mathjax/tex-svg-full.js",
}
ASSET_TAG = re.compile(
    rb"(?:<link\b[^>]*prodockit\.css[^>]*>|"
    rb"<script\b[^>]*(?:javascripts/mathjax\.js|"
    rb"javascripts/vendor/mathjax/tex-svg-full\.js)[^>]*>\s*</script>)\s*",
    re.IGNORECASE | re.DOTALL,
)


class AcceptanceError(RuntimeError):
    """A candidate wheel failed an acceptance condition."""


@dataclass(frozen=True)
class Result:
    name: str
    config: str
    mermaid: bool
    maths: bool
    changed_files: tuple[str, ...]
    output: str
    passed: bool = True


def run(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=environment,
    )
    if completed.returncode:
        detail = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise AcceptanceError(f"command failed ({' '.join(command)}):\n{detail}")
    return completed


def venv_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def resolve_wheel(value: Path) -> Path:
    if value.is_file() and value.suffix == ".whl":
        return value.resolve()
    if value.is_dir():
        wheels = sorted(value.glob("prodockit-*.whl"))
        if len(wheels) == 1:
            return wheels[0].resolve()
        if not wheels:
            raise AcceptanceError(f"no prodockit wheel found in {value}")
        raise AcceptanceError(f"more than one prodockit wheel found in {value}")
    raise AcceptanceError(f"wheel does not exist: {value}")


def assert_x64() -> str:
    machine = platform.machine()
    if machine.lower() not in {"amd64", "x86_64"}:
        raise AcceptanceError(f"this job must be x64, but platform.machine() is {machine!r}")
    return machine


def find_config(project: Path) -> Path:
    found = [project / name for name in CONFIG_NAMES if (project / name).is_file()]
    if len(found) != 1:
        names = ", ".join(path.name for path in found) or "none"
        raise AcceptanceError(f"expected one supported config in {project}; found {names}")
    return found[0]


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in GENERATED_DIRS}


def copy_project(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if (
        source == destination
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise AcceptanceError("the disposable output must be separate from the source project")
    if destination.exists():
        raise AcceptanceError(f"refusing to replace existing output: {destination}")
    shutil.copytree(source, destination, ignore=ignored)
    assert not (destination / ".git").exists()


def fixture(project: Path, config_name: str, *, mermaid: bool, maths: bool) -> None:
    (project / "docs" / "stylesheets").mkdir(parents=True)
    optional = ""
    if mermaid:
        optional += "\n```mermaid\ngraph LR\n    A --> B\n```\n"
    if maths:
        optional += "\n\\[ x^2 + y^2 = z^2 \\]\n"
    (project / "docs" / "index.md").write_text(
        "# Existing document\n\n"
        "This prose and the existing configuration must survive adoption.\n\n"
        "## Highlighted code\n\n"
        '```python\nprint("still highlighted")\n```\n'
        f"{optional}",
        encoding="utf-8",
    )
    (project / "docs" / "stylesheets" / "existing.css").write_text(
        ":root { --existing-project-marker: 1; }\n", encoding="utf-8"
    )
    if config_name.endswith(".toml"):
        config = """\
[project]
site_name = "Existing document"
nav = [{ Home = "index.md" }]
extra_css = ["stylesheets/existing.css"]

[project.theme]
language = "en"
"""
    else:
        config = """\
site_name: Existing document
nav:
    - Home: index.md
extra_css:
    - stylesheets/existing.css
theme:
    language: en
"""
    (project / config_name).write_text(config, encoding="utf-8")


def snapshot(root: Path, *, site: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if any(part in GENERATED_DIRS - ({"site"} if site else set()) for part in relative.parts):
            continue
        data = path.read_bytes()
        if site:
            if relative.as_posix().endswith(tuple(ADOPTED_SITE_FILES)):
                continue
            if path.suffix == ".html":
                data = ASSET_TAG.sub(b"", data)
                data = re.sub(rb">\s+<", b"><", data)
        result[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    return result


def changed(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)
    )


def install_candidate(python: Path, wheel: Path, project: Path | None) -> None:
    if project is not None:
        for relative in REQUIREMENTS:
            requirement = project / relative
            if requirement.is_file():
                run([str(python), "-m", "pip", "install", "-r", str(requirement)], cwd=project)
                break
    run([str(python), "-m", "pip", "install", "--force-reinstall", str(wheel)], cwd=wheel.parent)
    location = run(
        [
            str(python),
            "-c",
            "import pathlib, prodockit; print(pathlib.Path(prodockit.__file__).resolve())",
        ],
        cwd=wheel.parent,
    ).stdout.strip()
    if str(wheel.parent.parent.resolve()) in location:
        raise AcceptanceError(
            f"candidate imported from the checkout instead of the wheel: {location}"
        )
    print(f"Installed candidate: {location}")


def build(python: Path, project: Path, config: Path, *, fixture_content: bool) -> None:
    run(
        [str(python), "-m", "zensical", "build", "-f", config.name, "--clean"],
        cwd=project,
    )
    index = project / "site" / "index.html"
    if not index.is_file():
        raise AcceptanceError(f"build did not create {index}")
    if fixture_content:
        html = index.read_text(encoding="utf-8")
        if "still highlighted" not in html or "highlight" not in html or "headerlink" not in html:
            raise AcceptanceError("build lost prose, code highlighting or heading permalinks")


def adopt(
    python: Path,
    project: Path,
    *,
    mermaid: bool,
    maths: bool,
    apply: bool,
) -> str:
    command = [str(python), "-m", "prodockit", "adopt"]
    command.append("--apply" if apply else "--dry-run")
    command.append("--mermaid" if mermaid else "--no-mermaid")
    command.append("--maths" if maths else "--no-maths")
    completed = run(command, cwd=project, input_text=("y\n" * 20 if apply else None))
    return completed.stdout


def exercise(
    python: Path,
    project: Path,
    *,
    name: str,
    mermaid: bool,
    maths: bool,
    fixture_content: bool = False,
) -> Result:
    config = find_config(project)
    source_before = snapshot(project)
    build(python, project, config, fixture_content=fixture_content)
    site_before = snapshot(project / "site", site=True)
    before_site_copy = project.parent / f"{project.name}-site-before"
    shutil.copytree(project / "site", before_site_copy)

    dry_output = adopt(python, project, mermaid=mermaid, maths=maths, apply=False)
    after_dry_run = snapshot(project)
    dry_changes = changed(source_before, after_dry_run)
    if dry_changes:
        raise AcceptanceError(f"{name}: dry-run changed project files: {', '.join(dry_changes)}")
    if "no changes made" not in dry_output.lower():
        raise AcceptanceError(f"{name}: dry-run did not clearly state that it made no changes")

    apply_output = adopt(python, project, mermaid=mermaid, maths=maths, apply=True)
    if "Nothing has been committed or pushed" not in apply_output:
        raise AcceptanceError(f"{name}: apply did not state its Git boundary")
    source_after = snapshot(project)
    modifications = changed(source_before, source_after)
    if not modifications:
        raise AcceptanceError(f"{name}: apply made no project changes")

    build(python, project, config, fixture_content=fixture_content)
    site_after = snapshot(project / "site", site=True)
    site_changes = changed(site_before, site_after)
    if site_changes:
        raise AcceptanceError(
            f"{name}: generated site changed beyond selected asset tags: {', '.join(site_changes)}"
        )

    stable = snapshot(project)
    second_output = adopt(python, project, mermaid=mermaid, maths=maths, apply=True)
    if snapshot(project) != stable:
        raise AcceptanceError(f"{name}: a second apply changed project files")
    if "Adoption stages finished" not in second_output:
        raise AcceptanceError(f"{name}: second apply did not finish cleanly")

    print(f"PASS {name}: {len(modifications)} project file(s) changed as planned")
    return Result(name, config.name, mermaid, maths, modifications, str(project))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Test prodockit adopt from a wheel without changing the source project."
    )
    result.add_argument("--wheel", type=Path, required=True, help="Wheel file or its directory")
    result.add_argument("--project", type=Path, help="Existing project to copy and test")
    result.add_argument("--output", type=Path, help="New directory for the disposable project copy")
    result.add_argument("--mermaid", action="store_true", help="Select Mermaid for --project")
    result.add_argument("--maths", action="store_true", help="Select maths for --project")
    result.add_argument(
        "--require-x64", action="store_true", help="Fail unless this machine is x64"
    )
    result.add_argument("--report", type=Path, help="Write a JSON result report")
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    wheel = resolve_wheel(args.wheel)
    machine = assert_x64() if args.require_x64 else platform.machine()
    print(f"Platform: {platform.platform()}")
    print(f"Architecture: {machine}")
    print(f"Wheel: {wheel}")

    if (args.project is None) != (args.output is None):
        raise AcceptanceError("--project and --output must be supplied together")

    temporary_path = Path(tempfile.mkdtemp(prefix="prodockit-adopt-acceptance-"))
    try:
        environment = temporary_path / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = venv_python(environment)

        if args.project is not None:
            source = args.project.resolve()
            if not source.is_dir():
                raise AcceptanceError(f"project does not exist: {source}")
            original_source = snapshot(source)
            output = args.output.resolve()
            copy_project(source, output)
            install_candidate(python, wheel, output)
            result_items = [
                exercise(
                    python,
                    output,
                    name=source.name,
                    mermaid=args.mermaid,
                    maths=args.maths,
                )
            ]
            if snapshot(source) != original_source:
                raise AcceptanceError("source project changed during acceptance testing")
        else:
            install_candidate(python, wheel, None)
            scenarios = (
                ("toml-core", "zensical.toml", False, False),
                ("yaml-core", "mkdocs.yml", False, False),
                ("toml-mermaid", "zensical.toml", True, False),
                ("yaml-maths", "mkdocs.yml", False, True),
                ("toml-both", "zensical.toml", True, True),
            )
            result_items = []
            for name, config_name, mermaid, maths in scenarios:
                project = temporary_path / name
                project.mkdir()
                fixture(project, config_name, mermaid=mermaid, maths=maths)
                result_items.append(
                    exercise(
                        python,
                        project,
                        name=name,
                        mermaid=mermaid,
                        maths=maths,
                        fixture_content=True,
                    )
                )
    except Exception:
        print(f"Work directory preserved for diagnosis: {temporary_path}", file=sys.stderr)
        raise
    else:
        shutil.rmtree(temporary_path)

    report: dict[str, Any] = {
        "wheel": str(wheel),
        "platform": platform.platform(),
        "architecture": machine,
        "results": [asdict(item) for item in result_items],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Report: {args.report.resolve()}")
    print(f"\nAll {len(result_items)} adoption acceptance scenario(s) passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AcceptanceError, OSError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error

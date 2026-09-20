# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Qualify G7 migration against a real prodockit-template checkout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sysconfig
import time
from pathlib import Path

import pymupdf
import tomlkit

from prodockit.adopt import AdoptOptions, apply_step
from prodockit.pdf.runtime_config import PDF_SETTING_PATHS, load_pdf_runtime_config
from prodockit.project_config import load_project_config


def _command(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    path = Path(sysconfig.get_path("scripts")) / f"{name}{suffix}"
    if not path.is_file():
        raise AssertionError(f"{name} is not installed in {path.parent}")
    return str(path)


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> float:
    started = time.monotonic()
    active = dict(environment or os.environ)
    scripts = str(Path(sysconfig.get_path("scripts")))
    active["PATH"] = scripts + os.pathsep + active.get("PATH", "")
    subprocess.run(command, cwd=cwd, env=active, check=True)
    return time.monotonic() - started


def _copy_template(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(".git", ".prodockit", ".venv", "site", "public"),
    )


def _legacy_pdf_fixture(config_path: Path) -> list[str]:
    """Return legacy settings, reconstructing them from a current template."""

    existing = sorted(
        set(load_project_config(config_path).extra) & set(PDF_SETTING_PATHS)
    )
    if existing:
        return existing

    policy_path = config_path.parent / "pdk-pdf.toml"
    if not policy_path.is_file():
        raise AssertionError("template fixture has neither legacy nor current PDF settings")
    policy = load_pdf_runtime_config(config_path)
    migrated = sorted(policy.pdf_explicit)
    if not migrated:
        raise AssertionError("template fixture has no explicit PDF settings to migrate")

    parsed = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    project = parsed.get("project")
    if not isinstance(project, dict):
        raise AssertionError("template fixture has no [project] table")
    extra = project.get("extra")
    if not isinstance(extra, dict):
        extra = tomlkit.table()
        project["extra"] = extra
    for key in migrated:
        extra[key] = policy.pdf_values[key]
    config_path.write_text(tomlkit.dumps(parsed), encoding="utf-8")
    policy_path.unlink()
    return migrated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    project = args.work_dir.resolve() / "template"
    _copy_template(args.template.resolve(), project)
    config_path = project / "zensical.toml"
    migrated = _legacy_pdf_fixture(config_path)

    apply_step(project, AdoptOptions(), "core")
    first_config = config_path.read_bytes()
    first_policy = (project / "pdk-pdf.toml").read_bytes()
    apply_step(project, AdoptOptions(), "core")
    if (
        config_path.read_bytes() != first_config
        or (project / "pdk-pdf.toml").read_bytes() != first_policy
    ):
        raise AssertionError("a second Adopt migration changed configuration")

    after = load_project_config(config_path).extra
    remaining = sorted(set(after) & set(PDF_SETTING_PATHS))
    if remaining:
        raise AssertionError(f"legacy PDF settings remain after Adopt: {remaining}")
    policy = load_pdf_runtime_config(config_path)
    if policy.pdf_values["pdf_margin_bottom"] != "2.75cm":
        raise AssertionError("template's author-selected bottom margin was not migrated")
    if policy.pdf_values["pdf_extra_css"] != [
        "stylesheets/pdk-pdf.css",
        "stylesheets/print.css",
    ]:
        raise AssertionError("template's PDF stylesheet cascade was not migrated")

    website_seconds = _run([_command("zensical"), "build", "--clean", "--strict"], cwd=project)
    cold_seconds = _run([_command("pdk"), "pdf"], cwd=project)
    pdf = project / "docs/site_documentation.pdf"
    with pymupdf.open(pdf) as document:  # type: ignore[no-untyped-call]
        if document.page_count < 1:
            raise AssertionError("template PDF has no pages")

    cache_state = project / ".prodockit/cache/pdf/current.json"
    known_good = cache_state.read_bytes()
    policy_path = project / "pdk-pdf.toml"
    working_policy = policy_path.read_bytes()
    policy_path.write_bytes(working_policy + b'\n[mermaid]\nversion = "999.0.0"\n')
    failure_environment = os.environ.copy()
    scripts = str(Path(sysconfig.get_path("scripts")))
    failure_environment["PATH"] = scripts + os.pathsep + failure_environment.get("PATH", "")
    failed = subprocess.run(
        [_command("pdk"), "pdf"],
        cwd=project,
        env=failure_environment,
        text=True,
        capture_output=True,
    )
    if failed.returncode == 0:
        raise AssertionError("unsupported renderer request unexpectedly succeeded")
    if cache_state.read_bytes() != known_good:
        raise AssertionError("failed preparation changed the last-known-good cache state")
    policy_path.write_bytes(working_policy)

    blocked = os.environ.copy()
    blocked.update(
        {
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
    )
    warm_seconds = _run([_command("pdk"), "pdf"], cwd=project, environment=blocked)

    report = {
        "migrated_settings": migrated,
        "website_seconds": website_seconds,
        "cold_pdf_seconds": cold_seconds,
        "offline_warm_pdf_seconds": warm_seconds,
        "failed_request_preserved_cache": True,
        "pdf_bytes": pdf.stat().st_size,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

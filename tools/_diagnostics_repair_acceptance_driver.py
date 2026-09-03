# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Create and repair one all-failures fixture using an installed wheel."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import sys
import sysconfig
import time
from collections import Counter
from pathlib import Path
from typing import Any

from click.testing import CliRunner

import prodockit
from prodockit import diagnostics
from prodockit.cli import main as prodockit_cli
from prodockit.init_tools import init_tools

REPAIRABLE_CHECKS = frozenset(
    {
        "installation.metadata",
        "project.configuration",
        "dependencies.pins",
        "dependencies.shared-files",
        "renderer.mermaid",
        "renderer.mathjax",
    }
)
EXPECTED_ACTIONS = Counter(
    {
        "installation.metadata": 1,
        "project.configuration": 1,
        "dependencies.pins": 1,
        "dependencies.shared-files": 2,
        "renderer.mermaid": 1,
        "renderer.mathjax": 1,
    }
)


class AcceptanceError(RuntimeError):
    """The installed wheel did not repair the complete fixture."""


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _site_packages() -> Path:
    path = sysconfig.get_path("purelib")
    if not path:
        raise AcceptanceError("the active wheel environment has no purelib directory")
    return Path(path).resolve()


def write_fixture(project: Path) -> Path:
    """Create all six independently repairable diagnostic failures."""
    project.mkdir(parents=True)
    config = project / "zensical.toml"
    _write(
        config,
        """\
[project]
site_name = "Diagnostic repair acceptance"
docs_dir = "docs"
nav = [{ Home = "index.md" }]
extra_css = ["stylesheets/pdk.css", "stylesheets/pdk-pdf.css"]
extra_javascript = [
  "javascripts/mathjax.js",
  "javascripts/vendor/mathjax/tex-svg-full.js",
]

[project.markdown_extensions.pymdownx.arithmatex]

[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  { name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" },
]
""",
    )
    _write(
        project / "docs" / "index.md",
        """\
# Home

See \\ref{target}.

## Target

```mermaid
graph LR
  A --> B
```

\\[ x^2 + y^2 = z^2 \\]
""",
    )

    # One managed file differs and the other is absent, exercising both
    # transactional shared-file paths.
    _write(
        project / ".prodockit-shared-files.toml",
        """\
version = 1

[[files]]
source = "pdk.css"
target = "docs/stylesheets/pdk.css"

[[files]]
source = "pdk-pdf.css"
target = "docs/stylesheets/pdk-pdf.css"
""",
    )
    _write(project / "docs" / "stylesheets" / "pdk.css", "/* deliberately stale */\n")

    # The configured MathJax browser assets exist so configuration inspection
    # is clean apart from the missing refs extension. Its Node inputs, and
    # Mermaid's, are deliberately absent until the repair runs npm ci.
    _write(project / "docs" / "javascripts" / "mathjax.js", "// deliberately stale\n")
    _write(
        project / "docs" / "javascripts" / "vendor" / "mathjax" / "tex-svg-full.js",
        "// deliberately stale\n",
    )
    init_tools(project / "tools")

    zensical_version = importlib.metadata.version("zensical")
    _write(project / "requirements.txt", "zensical>=0.0.1\n")
    _write(
        project / ".github" / "workflows" / "docs.yml",
        f"jobs:\n  docs:\n    steps:\n      - run: pip install zensical=={zensical_version}\n",
    )

    # A second, older but internally valid dist-info directory is the exact
    # case the metadata repair may quarantine safely.
    stale_metadata = _site_packages() / "prodockit-0.0.1.dist-info"
    if stale_metadata.exists():
        raise AcceptanceError(f"stale metadata fixture already exists: {stale_metadata}")
    _write(
        stale_metadata / "METADATA",
        "Metadata-Version: 2.1\nName: prodockit\nVersion: 0.0.1\n",
    )
    _write(stale_metadata / "WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
    _write(stale_metadata / "RECORD", "")
    importlib.invalidate_caches()
    return stale_metadata


def snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _repair_input(plan: diagnostics.RepairDryRun) -> tuple[str, int]:
    answers: list[str] = []
    actions = 0
    for candidate in plan.candidates:
        if candidate.status != "available" or not candidate.choices:
            continue
        selected = next(
            (
                (number, choice)
                for number, choice in enumerate(candidate.choices, 1)
                if choice.id not in {"leave-unchanged", "review-difference"}
            ),
            None,
        )
        if selected is None:
            raise AcceptanceError(f"no mutating choice for {candidate.id}")
        number, _choice = selected
        answers.extend((str(number), "y"))
        actions += 1
    return "\n".join((*answers, "")), actions


def _checks(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["id"]: check for check in payload["checks"]}


def _reported_path(value: str, project: Path) -> Path:
    """Resolve an absolute, project-relative, or home-relative report path."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else project / path


def exercise(project: Path) -> dict[str, Any]:
    started = time.perf_counter()
    installed = Path(prodockit.__file__).resolve()
    try:
        installed.relative_to(Path(sys.prefix).resolve())
    except ValueError as error:
        raise AcceptanceError(
            f"Prodockit was not imported from the wheel environment: {installed}"
        ) from error

    stale_metadata = write_fixture(project)
    config = project / "zensical.toml"
    project_before = snapshot(project)
    report_before = diagnostics.inspect(config, online=True)
    before = {check.id: check for check in report_before.checks}
    missing = sorted(
        check_id
        for check_id in REPAIRABLE_CHECKS
        if check_id not in before or before[check_id].status == "pass"
    )
    if missing:
        raise AcceptanceError(
            "fixture did not create every repairable diagnostic failure: " + ", ".join(missing)
        )

    plan = diagnostics.build_repair_dry_run(report_before)
    available = Counter(
        candidate.check_id for candidate in plan.candidates if candidate.status == "available"
    )
    if available != EXPECTED_ACTIONS:
        raise AcceptanceError(
            f"expected available actions {dict(EXPECTED_ACTIONS)}, found {dict(available)}"
        )
    if snapshot(project) != project_before or not stale_metadata.is_dir():
        raise AcceptanceError("building the dry-run plan changed the fixture")

    input_text, expected_confirmations = _repair_input(plan)
    # Click correctly rejects piped stdin in production. CliRunner supplies a
    # deterministic terminal transcript here; only this acceptance boundary
    # substitutes the terminal detector.
    import prodockit.cli as cli_module

    cli_module._is_interactive = lambda: True
    result = CliRunner().invoke(
        prodockit_cli,
        ["diag", "--config-file", str(config), "--online", "--fix", "--json"],
        input=input_text,
        catch_exceptions=False,
    )
    if result.exit_code:
        raise AcceptanceError(
            f"pdk diag --fix exited {result.exit_code}:\n{result.stdout}\n{result.stderr}"
        )
    payload = json.loads(result.stdout)
    actions = [action for action in payload["repair"]["actions"] if action["status"] == "applied"]
    applied = Counter(action["check_id"] for action in actions)
    if applied != EXPECTED_ACTIONS:
        raise AcceptanceError(
            f"expected applied actions {dict(EXPECTED_ACTIONS)}, found {dict(applied)}"
        )
    if any(action["confirmation"] != "y" for action in actions):
        raise AcceptanceError("one or more mutating repairs did not record an explicit y")
    if result.stderr.count("Apply this repair? [y/N]:") != expected_confirmations:
        raise AcceptanceError("the CLI did not ask one default-No confirmation per repair")

    after = _checks(payload["after"])
    failed = sorted(
        check_id
        for check_id in REPAIRABLE_CHECKS
        if after[check_id]["status"] != "pass"
    )
    if failed:
        raise AcceptanceError(
            "repairs did not clear every selected diagnostic: " + ", ".join(failed)
        )
    if stale_metadata.exists():
        raise AcceptanceError("the stale distribution metadata was not quarantined")
    for action in actions:
        manifest = action.get("manifest")
        if not manifest or not _reported_path(manifest, project).resolve().is_file():
            raise AcceptanceError(
                f"repair has no recovery manifest: {action['id']} ({manifest!r})"
            )

    return {
        "passed": True,
        "prodockit_version": prodockit.__version__,
        "installed_from": str(installed),
        "repairable_checks": sorted(REPAIRABLE_CHECKS),
        "actions": dict(applied),
        "confirmations": expected_confirmations,
        "after_status": payload["after"]["status"],
        "after_counts": payload["after"]["summary"],
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--root", type=Path, required=True)
    result.add_argument("--report", type=Path, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    result = exercise(args.root.resolve())
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS all diagnostic repairs: {result['confirmations']} explicit repairs across "
        f"{len(result['repairable_checks'])} checks"
    )


if __name__ == "__main__":
    try:
        main()
    except AcceptanceError as error:
        print(f"acceptance failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error

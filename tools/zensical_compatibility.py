# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT
"""Compare exact Zensical releases without modifying the calling environment.

Run --help for the configuration matrix and complete release-qualification modes.
Results, frozen environments, command logs and output inventories survive failure.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
from collections import Counter
from pathlib import Path

from compatibility.checks import (
    command,
    compare_snapshots,
    environment,
    junit_counts,
    probes,
    site_snapshot,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
BAD = {"failed", "error", "xpass"}


def python_in(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def checked(args: list[str], cwd: Path, log: Path) -> None:
    result = command(args, cwd, log)
    if result["exit"] != 0:
        raise RuntimeError(f"Command failed; see {log}: {result}")


def copy_project(source: Path, target: Path) -> None:
    # Git history is needed by the publishing macros; overlay tracked working
    # files so a local qualification tests the current edits as well.
    checked(
        ["git", "clone", "--quiet", "--shared", str(source), str(target)],
        source,
        target.parent / (target.name + "-clone.log"),
    )
    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=source, text=True
    ).strip()
    checked(["git", "remote", "set-url", "origin", remote], target, target.parent / "remote.log")
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).decode().split("\0")
    for name in filter(None, paths):
        if (source / name).is_file():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target / name)
        elif (target / name).is_file():
            (target / name).unlink()
    # Reuse already-installed locked renderer dependencies when available.
    for tool in ("mermaid", "mathjax"):
        src = source / "tools" / tool / "node_modules"
        dst = target / "tools" / tool / "node_modules"
        if src.is_dir() and os.name != "nt":
            dst.symlink_to(src.resolve(), target_is_directory=True)
        elif (target / "tools" / tool / "package-lock.json").exists():
            checked(
                ["npm.cmd" if os.name == "nt" else "npm", "ci", "--prefix", str(dst.parent)],
                target,
                target.parent / f"{target.name}-{tool}.log",
            )
    # The template workflow fetches this separately. Supply the same bytes to
    # both builds, not two independent network downloads.
    csl = source / "harvard-cite-them-right.csl"
    if csl.exists():
        shutil.copy2(csl, target / csl.name)


def historical_floor_mismatch(log: Path) -> bool:
    """Recognise only the deliberate baseline metadata conflict, never other failures."""
    from importlib.metadata import version

    from prodockit.pins import TESTED_VERSIONS

    try:
        payload = json.loads(log.read_text(encoding="utf-8"))
        failures = [check for check in payload["checks"] if check["status"] == "fail"]
        expected = (
            f"prodockit {version('prodockit')} has requirement "
            f"zensical>={TESTED_VERSIONS['zensical']}, "
            f"but you have zensical {version('zensical')}."
        )
        return (
            len(failures) == 1
            and failures[0]["id"] == "installation.dependencies"
            and failures[0]["details"] == [expected]
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def full_project(
    root: Path, output: Path, *, template: bool, historical_baseline: bool = False
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    scripts = Path(sys.executable).parent

    def exe(name: str) -> str:
        return str(scripts / (name + ".exe" if os.name == "nt" else name))

    steps = []
    if template:
        steps += [
            ("release", [exe("prodockit"), "_record-template-release"]),
            ("sync", [exe("prodockit"), "sync-repo"]),
        ]
    steps += [("mathjax", [exe("prodockit"), "init-mathjax", "--no-gitignore"])]
    if template:
        steps += [
            ("diagnostics", [exe("prodockit"), "diag", "--json"]),
            ("source-bundle", [exe("prodockit"), "source-bundle"]),
        ]
    steps += [
        ("site", [exe("zensical"), "build", "--clean", "--strict"]),
        ("pdf", [exe("prodockit"), "pdf"]),
    ]
    result = {"scope": "complete-document", "steps": [], "status": "passed"}
    for name, args in steps:
        run = command(args, root, output / (name + ".log"))
        result["steps"].append({"name": name, **run})
        if (
            run["exit"] == 1 and name == "diagnostics" and historical_baseline
            and historical_floor_mismatch(output / (name + ".log"))
        ):
            result["steps"][-1]["expected_failure"] = "historical-zensical-floor"
            continue
        if run["exit"] != 0:
            result.update(status="failed", incomplete_after=name)
            return result
    if not template:
        xml = output / "built.xml"
        run = command(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_built_docs.py",
                "-m",
                "built",
                "-q",
                "--junitxml=" + str(xml),
            ],
            root,
            output / "built.log",
        )
        result["tests"] = junit_counts(xml)
        if run["exit"] != 0:
            result["status"] = "failed"
    else:
        result["tests"] = {
            "status": "not-applicable",
            "reason": "template has no owned pytest suite",
        }
    snapshot = site_snapshot(root)
    write_json(output / "snapshot.json", snapshot)
    required = (
        {"site_documentation.pdf", "source_bundle.pdf"} if template else {"site_documentation.pdf"}
    )
    if (
        snapshot["nav_missing"]
        or snapshot["missing_assets"]
        or not required <= snapshot["pdfs"].keys()
    ):
        result.update(status="failed", error="Missing navigation/output")
    if not all(snapshot["publications"].values()):
        result.update(status="failed", error="Generated PDF was not published intact")
    result["existing_output_defects"] = {
        name: pdf["problems"] for name, pdf in snapshot["pdfs"].items() if pdf["problems"]
    }
    if result["existing_output_defects"]:
        result["status"] = "failed"
    result["snapshot"] = str(output / "snapshot.json")
    return result


def worker(args: argparse.Namespace) -> int:
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "environment": environment(),
        "scope": "complete-documents" if args.full else "consumer-configurations",
        "projects": {},
        "status": "passed",
    }
    # Console commands and subprocess tests must use the worker's own venv.
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    os.environ["VIRTUAL_ENV"] = str(Path(sys.executable).parent.parent)
    os.environ.pop("PYTHONPATH", None)
    try:
        result["sources"] = {}
        for name, source in [("extensions", ROOT), ("template", args.template)]:
            if source is not None:
                result["sources"][name] = {
                    "commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=source, text=True
                    ).strip(),
                    "working_tree": subprocess.check_output(
                        ["git", "status", "--short"], cwd=source, text=True
                    ),
                }
        version = result["environment"]["packages"]["zensical"]
        result["probes"] = probes(output / "probes", version, args.browser_script, full=args.full)
        result["counts"] = dict(Counter(row["status"] for row in result["probes"]))
        result["counts"]["executed"] = sum(
            result["counts"].get(status, 0) for status in ("passed", "failed", "xfail", "xpass")
        )
        if any(row["status"] in BAD for row in result["probes"]):
            result["status"] = "failed"
        if args.full:
            for name, source in [("extensions", ROOT), ("template", args.template)]:
                target = output / name
                copy_project(source, target)
                if args.historical_baseline:
                    # Project environment guards must see the version under test.
                    # Change only Zensical declarations in the disposable copy;
                    # runtime code and documentation content remain identical.
                    from prodockit.pins import apply_version, discover

                    state = discover(str(target))["zensical"]
                    changed = apply_version(str(target), state, version)
                    result.setdefault("baseline_declarations", {})[name] = [
                        site.path for site in changed
                    ]
                result["projects"][name] = full_project(
                    target, output / (name + "-results"), template=name == "template",
                    historical_baseline=args.historical_baseline
                )
                if result["projects"][name]["status"] != "passed":
                    result["status"] = "failed"
        else:
            result["full_documents"] = "not-run; configuration results do not qualify an upgrade"
    except Exception as error:
        result.update(status="error", error=f"{type(error).__name__}: {error}")
    finally:
        write_json(output / "result.json", result)
    return 1 if result["status"] != "passed" else 0


def report(output: Path) -> int:
    results = {
        name: json.loads((output / name / "result.json").read_text())
        for name in ("baseline", "candidate")
        if (output / name / "result.json").exists()
    }
    lines = [
        "# Zensical compatibility analysis",
        "",
        "Only Zensical varies between the two environments. The historical baseline installs "
        "the local Prodockit build without dependency resolution so it can test below "
        "the new supported floor. Its exact Prodockit/Zensical metadata mismatch may be "
        "recorded as an expected diagnostic failure; other diagnostic failures still fail "
        "qualification, and candidate diagnostics receive no exemption. Zensical declarations "
        "in disposable baseline projects are aligned to the historical version so project "
        "environment guards validate the version actually under test; runtime source and "
        "documentation content are unchanged.",
        "",
    ]
    failure = len(results) != 2
    if failure:
        lines += ["Qualification incomplete: a baseline or candidate result is missing.", ""]
    packages = [r["environment"]["packages"] for r in results.values()]
    if len(packages) == 2:
        differences = {
            k: [packages[0].get(k), packages[1].get(k)]
            for k in packages[0].keys() | packages[1].keys()
            if packages[0].get(k) != packages[1].get(k) and k != "zensical"
        }
        if differences:
            failure = True
            lines += ["Dependency isolation FAILED: " + json.dumps(differences), ""]
    for name, result in results.items():
        failure |= result["status"] != "passed"
        env = result["environment"]
        lines += [
            f"## {name}: Zensical {env['packages']['zensical']}",
            "",
            f"Environment: {env['platform']}; Python {env['python'].split()[0]}",
            "",
            "Native tools: " + json.dumps(env.get("binaries", {})),
            "",
            "Source revisions: " + json.dumps(result.get("sources", {})),
            "",
            f"Scope: {result['scope']}. Status: {result['status']}.",
            "",
            "| Consumer check | Result | Expectation |",
            "|---|---|---|",
        ]
        for row in result.get("probes", []):
            lines.append(
                f"| {row['name']} | {row['status']} | "
                f"{row.get('expectation', row.get('since', 'feature check'))} |"
            )
        lines += [
            "",
            "Counts: " + json.dumps(result.get("counts", {})),
            "",
            "XFAIL is a known upstream limitation, not a passing test. XPASS fails strictly.",
            "[Mike limitation and original evidence]"
            "(https://github.com/buckwem/prodockit-extensions/issues/799).",
            "",
        ]
        if "error" in result:
            lines += ["Error: " + result["error"], ""]
        if not result["projects"]:
            lines += [
                "Full extensions/template PDFs and browser checks without a result above: "
                "**not run**.",
                "",
            ]
        for project, check in result["projects"].items():
            lines += [
                f"### {project}",
                "",
                f"Status: {check['status']}; scope: {check['scope']}.",
                "",
                "Suite counts: " + json.dumps(check.get("tests", {"status": "not-run"})),
                "",
            ]
            if check.get("existing_output_defects"):
                lines += [
                    "Output defects detected (also check the baseline): "
                    + json.dumps(check["existing_output_defects"]),
                    "",
                ]
    if len(results) == 2:
        for project in ("extensions", "template"):
            paths = [output / side / (project + "-results") / "snapshot.json" for side in results]
            if all(p.exists() for p in paths):
                comparison = compare_snapshots(*(json.loads(p.read_text()) for p in paths))
                write_json(output / (project + "-comparison.json"), comparison)
                lines += [
                    f"## {project} complete-output comparison",
                    "",
                    "```json",
                    json.dumps(comparison, indent=2),
                    "```",
                    "",
                ]
    lines += [
        "Output differences require review; byte changes alone are not automatically regressions.",
        "When full snapshots are present, PDF links, text, dimensions and pixels are compared "
        "on every page, including added/removed pages.",
        "Browser coverage is limited to the listed redirect probes. Template Mermaid/MathJax "
        "browser rendering (#272), GLightbox interactions and instant navigation are not run.",
        "The executed suite counts above are not a claim that every Prodockit test ran.",
        "No check of JavaScript redirects implies PDF alias support.",
        "",
    ]
    (output / "analysis.md").write_text("\n".join(lines), encoding="utf-8")
    return int(failure)


def baseline_requirements(frozen: str, version: str) -> str:
    """Reuse candidate dependencies while excluding this release's new floor.

    The local Prodockit build is installed separately without dependency
    resolution only in the historical baseline. All other requirements remain
    frozen, and report() rejects any dependency difference except Zensical.
    """
    return "\n".join(
        "zensical==" + version if line.lower().startswith("zensical==") else line
        for line in frozen.splitlines()
        if not line.lower().startswith(("prodockit==", "prodockit @ "))
    ) + "\n"


def pair(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Use a new output directory; prior evidence is never overwritten")
    output.mkdir(parents=True)
    try:
        candidate = output / "venv-candidate"
        venv.EnvBuilder(with_pip=True).create(candidate)
        candidate_py = str(python_in(candidate))
        requirements = [
            str(ROOT) + "[testing]",
            "zensical==" + args.candidate,
            "weasyprint==69.0",
            "Markdown==3.10.3",
            "pymdown-extensions==11.0.2",
            "mkdocs-table-reader-plugin",
        ]
        if args.template:
            requirements += ["-r", str(args.template / "requirements.txt")]
        checked(
            [candidate_py, "-m", "pip", "install", *requirements],
            ROOT, output / "install-candidate.log",
        )
        frozen = subprocess.check_output([candidate_py, "-m", "pip", "freeze"], text=True)
        (output / "candidate-requirements.txt").write_text(frozen, encoding="utf-8")
        baseline = output / "venv-baseline"
        venv.EnvBuilder(with_pip=True).create(baseline)
        baseline_py = str(python_in(baseline))
        lock = output / "baseline-dependencies-requirements.txt"
        lock.write_text(baseline_requirements(frozen, args.baseline), encoding="utf-8")
        checked(
            [baseline_py, "-m", "pip", "install", "-r", str(lock)],
            ROOT, output / "install-baseline.log",
        )
        # The baseline deliberately predates the release's supported floor.
        # This exception applies only to the local project, never its dependencies.
        checked(
            [baseline_py, "-m", "pip", "install", "--no-deps", str(ROOT)],
            ROOT, output / "install-baseline-project.log",
        )
        baseline_frozen = subprocess.check_output([baseline_py, "-m", "pip", "freeze"], text=True)
        (output / "baseline-requirements.txt").write_text(baseline_frozen, encoding="utf-8")
        for side, env in [("baseline", baseline), ("candidate", candidate)]:
            cmd = [
                str(python_in(env)),
                str(Path(__file__).resolve()),
                "worker",
                "--output",
                str(output / side),
            ]
            if side == "baseline":
                cmd += ["--historical-baseline"]
            if args.full:
                cmd += ["--full", "--template", str(args.template.resolve())]
            if args.browser_script:
                cmd += ["--browser-script", str(args.browser_script.resolve())]
            command(cmd, ROOT, output / (side + ".log"), 3600)
        return report(output)
    except Exception as error:
        (output / "analysis.md").write_text(
            f"# Incomplete qualification\n\n{error}\n\n"
            "See installation logs. No compatibility conclusion is available.\n",
            encoding="utf-8",
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("pair", "worker"):
        p = sub.add_parser(mode)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--full", action="store_true")
        p.add_argument("--historical-baseline", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("--template", type=Path)
        p.add_argument("--browser-script", type=Path)
        if mode == "pair":
            p.add_argument("--baseline", required=True)
            p.add_argument("--candidate", required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.browser_script:
        args.browser_script = args.browser_script.resolve()
    if args.template:
        args.template = args.template.resolve()
    if args.full and not args.browser_script:
        args.browser_script = ROOT / "tools/compatibility/redirect_browser.cjs"
    if args.full and not args.template:
        parser.error("--full requires --template: both complete projects must be qualified")
    if args.mode == "pair":
        # Only exact release identifiers; reject requirement operators and pip arguments.
        import re

        if not all(
            re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", v)
            for v in (args.baseline, args.candidate)
        ):
            parser.error("baseline and candidate must be exact release versions")
    return pair(args) if args.mode == "pair" else worker(args)


if __name__ == "__main__":
    raise SystemExit(main())

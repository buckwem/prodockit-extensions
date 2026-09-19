# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise G4 project-local Pandoc/fonts through public production paths."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pymupdf

from prodockit.bibliography import _run_pandoc_citeproc


def _run(command: list[str], *, cwd: Path) -> float:
    started = time.monotonic()
    subprocess.run(command, cwd=cwd, check=True)
    return time.monotonic() - started


def _embedded_fonts(pdf: Path) -> set[str]:
    document = pymupdf.open(pdf)
    try:
        return {
            str(font[3])
            for page in document
            for font in page.get_fonts(full=True)
            if len(font) > 3
        }
    finally:
        document.close()


def _bibliography_only(work: Path) -> dict[str, object]:
    project = work / "bibliography-only"
    project.mkdir(parents=True)
    (project / "zensical.toml").write_text(
        '[project]\nsite_name = "G4 bibliography"\n', encoding="utf-8"
    )
    (project / "refs.bib").write_text(
        "@book{example, title={Runtime Isolation}, author={Example, Ada}, year={2026}}\n",
        encoding="utf-8",
    )
    previous = Path.cwd()
    try:
        os.chdir(project)
        started = time.monotonic()
        html, _stderr = _run_pandoc_citeproc(
            "[@example]", bib_files=["refs.bib"], csl_style=""
        )
        elapsed = time.monotonic() - started
    finally:
        os.chdir(previous)
    manifest = json.loads(
        (project / ".prodockit/cache/pdf/current.json").read_text(encoding="utf-8")
    )
    components = sorted(manifest)
    if components != ["pandoc"]:
        raise AssertionError(f"bibliography-only prepared {components}, expected only pandoc")
    if "Runtime Isolation" not in html:
        raise AssertionError("bibliography-only citeproc did not render the fixture")
    return {"seconds": elapsed, "components": components}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)

    cache = project / ".prodockit/cache/pdf"
    if cache.exists():
        raise SystemExit(f"refusing a non-cold acceptance cache: {cache}")
    components = ["pandoc", "fonts"]
    if sys.platform == "win32":
        components.append("weasyprint")
    prepare = ["pdk", "pdf"]
    for component in components:
        prepare.extend(("--prepare", component))
    cold = _run(prepare, cwd=project)
    warm = _run(prepare, cwd=project)

    _run(["zensical", "build", "--clean", "--strict"], cwd=project)
    build = _run(["pdk", "pdf", "--markdown-file", "gettingstarted.md"], cwd=project)
    pdf = project / "docs/gettingstarted.pdf"
    if not pdf.read_bytes().startswith(b"%PDF"):
        raise AssertionError(f"not a PDF: {pdf}")
    fonts = _embedded_fonts(pdf)
    if not any("Inter" in name for name in fonts):
        raise AssertionError(f"Inter is not embedded: {sorted(fonts)}")
    if not any("JetBrains" in name for name in fonts):
        raise AssertionError(f"JetBrains Mono is not embedded: {sorted(fonts)}")

    report = {
        "platform": sys.platform,
        "components": components,
        "cold_seconds": cold,
        "warm_seconds": warm,
        "build_seconds": build,
        "embedded_fonts": sorted(fonts),
        "bibliography_only": _bibliography_only(work),
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise real G5 renderer downloads through public production paths."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

import pymupdf
from packaging.requirements import Requirement


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> float:
    started = time.monotonic()
    subprocess.run(command, cwd=cwd, env=environment, check=True)
    return time.monotonic() - started


def _console_script(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    executable = Path(sysconfig.get_path("scripts")) / f"{name}{suffix}"
    if not executable.is_file():
        raise AssertionError(f"{name} is not installed in {executable.parent}")
    return str(executable)


def _base_dependencies() -> set[str]:
    selected: set[str] = set()
    environment = {"extra": ""}
    for value in importlib.metadata.requires("prodockit") or ():
        requirement = Requirement(value)
        if requirement.marker is None or requirement.marker.evaluate(environment):
            selected.add(requirement.name.lower())
    return selected


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_project(project: Path) -> None:
    docs = project / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text(
        """# G5 renderers

```mermaid
flowchart LR
  Start[Start] --> Finish[Finish]
```

$$
\\frac{1}{x^2-1}
$$
""",
        encoding="utf-8",
    )
    (project / "zensical.toml").write_text(
        """[project]
site_name = "G5 renderer acceptance"
nav = [{ Home = "index.md" }]

[project.extra]
pdf_output = "docs/g5.pdf"

[project.markdown_extensions.pymdownx.arithmatex]
generic = true

[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  { name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" },
]
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    project = work / "project"
    project.mkdir(parents=True)
    _write_project(project)

    forbidden = {"mermaidx", "quickjs-ng", "resvg-py", "termaid", "pypdf"}
    burden = sorted(_base_dependencies() & forbidden)
    if burden:
        raise AssertionError(f"renderer/test packages leaked into the base install: {burden}")

    prepare = [
        _console_script("pdk"),
        "pdf",
        "--prepare",
        "mathjax",
        "--prepare",
        "mermaid",
    ]
    cold = _run(prepare, cwd=project)
    cache = project / ".prodockit/cache/pdf"
    current_after_cold = json.loads((cache / "current.json").read_text(encoding="utf-8"))
    if sorted(current_after_cold) != ["mathjax", "mermaid"]:
        raise AssertionError(f"renderer preparation selected {sorted(current_after_cold)}")

    blocked_network = os.environ.copy()
    blocked_network.update(
        {
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
    )
    warm = _run(prepare, cwd=project, environment=blocked_network)

    _run([_console_script("zensical"), "build", "--clean", "--strict"], cwd=project)
    build = _run([_console_script("pdk"), "pdf"], cwd=project)
    pdf = project / "docs/g5.pdf"
    if not pdf.read_bytes().startswith(b"%PDF"):
        raise AssertionError(f"not a PDF: {pdf}")
    with pymupdf.open(pdf) as document:  # type: ignore[no-untyped-call]
        text = "\n".join(page.get_text() for page in document)
    if "Start" not in text or "Finish" not in text:
        raise AssertionError("Mermaid SVG labels are absent from the PDF")
    if r"\frac{1}{x^2-1}" in text:
        raise AssertionError("raw TeX reached the PDF")

    current = json.loads((cache / "current.json").read_text(encoding="utf-8"))
    renderers = {
        component: {
            "version": current[component]["version"],
            "sha256": current[component]["sha256"],
            "bytes": _tree_bytes(cache / current[component]["path"]),
        }
        for component in ("mathjax", "mermaid")
    }
    report = {
        "platform": sys.platform,
        "base_renderer_burden": burden,
        "cold_seconds": cold,
        "offline_warm_seconds": warm,
        "build_seconds": build,
        "renderers": renderers,
        "pdf_bytes": pdf.stat().st_size,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

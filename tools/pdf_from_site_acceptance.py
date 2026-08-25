# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise the public built-site PDF renderer from an installed wheel.

The harness deliberately needs no Git remote, GitHub or GitLab.  It creates a
local project, runs Zensical's public build CLI and checks the exact installed
Prodockit wheel can recover navigation, metadata and rendered extension HTML.
The Pandoc/WeasyPrint engine is covered independently by the main PDF suite;
this acceptance test targets the documented Zensical build-output boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


class AcceptanceError(RuntimeError):
    """The installed wheel failed an acceptance condition."""


def wheel_path(value: Path) -> Path:
    if value.is_file() and value.suffix == ".whl":
        return value.resolve()
    wheels = sorted(value.glob("prodockit-*.whl")) if value.is_dir() else []
    if len(wheels) != 1:
        raise AcceptanceError(f"expected one prodockit wheel in {value}; found {len(wheels)}")
    return wheels[0].resolve()


def environment_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if result.returncode:
        raise AcceptanceError(
            f"command failed ({' '.join(command)}):\n{result.stdout}\n{result.stderr}"
        )
    return result


def write_project(project: Path) -> None:
    docs = project / "docs"
    docs.mkdir(parents=True)
    (project / "zensical.toml").write_text(
        """[project]
site_name = "Built-site acceptance"
nav = [
    { "Home" = "index.md" },
    { "Development journey" = "journey/development-journey.md" },
    { "Test procedure" = "procedure/test-procedure.md" },
    { "Guide" = "guide.md" },
]

[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions."prodockit.tables"]
[project.markdown_extensions."prodockit.steps"]
[project.markdown_extensions."prodockit.tree"]
[project.markdown_extensions.pymdownx.blocks.caption]
types = [
    { name = "figure-caption", prefix = "{}.", classes = "prodockit-figure-caption" },
]
""",
        encoding="utf-8",
    )
    (docs / "index.md").write_text(
        "# Home\n\nForward reference to \\ref{guide}.\n", encoding="utf-8"
    )
    # Installed-wheel regression for #512: two forward figure references
    # target caption blocks nested four spaces beneath a later list item.
    # Both pages are nested so the built site's clean relative URLs are
    # exercised as well as nav pre-seeding and continuous figure numbers.
    (docs / "journey").mkdir()
    (docs / "journey" / "development-journey.md").write_text(
        "# Development journey\n\nThe default values are shown in "
        "\\ref{fig-grafana-admin-username-config} and "
        "\\ref{fig-grafana-admin-password-config}.\n",
        encoding="utf-8",
    )
    (docs / "procedure").mkdir()
    (docs / "procedure" / "test-procedure.md").write_text(
        """# Test procedure

## Step 8

2. Log in with the configured credentials.

    ![Username](username.png)
    /// figure-caption | #fig-grafana-admin-username-config
    Shows the username field
    ///

    ![Password](password.png)
    /// figure-caption | #fig-grafana-admin-password-config
    Shows the password field
    ///
""",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text(
        """---
is_appendix: true
recto_title: Short guide
---

# Guide

| Name | Value |
| --- | --- |
| Test | Passed |

/// steps
1. First step
///

/// tree
docs/
///
""",
        encoding="utf-8",
    )


CHECK = r"""
from pathlib import Path
from prodockit.pdf import config as pdf_config
from prodockit.pdf.config import build_pdf_from_built_site
from prodockit.pdf.site import page_html, page_metadata
from prodockit.project_config import load_project_config

config = load_project_config("zensical.toml")
captured = {}
def capture(pages, output_path, **kwargs):
    captured["pages"] = pages
    captured["output_path"] = output_path
    captured["kwargs"] = kwargs
pdf_config.build_pdf = capture
assert build_pdf_from_built_site("zensical.toml") == "docs/site_documentation.pdf"
home = page_html(config, "index.md")
journey = page_html(config, "journey/development-journey.md")
procedure = page_html(config, "procedure/test-procedure.md")
guide = page_html(config, "guide.md")
metadata = page_metadata(Path("docs/guide.md"))
assert [page.docs_rel_path for page in captured["pages"]] == [
    "index.md",
    "journey/development-journey.md",
    "procedure/test-procedure.md",
    "guide.md",
]
assert captured["pages"][3].is_appendix is True
assert captured["pages"][3].recto_title == "Short guide"
assert captured["kwargs"]["main_font"] == "Roboto"
assert captured["kwargs"]["mono_font"] == "Roboto Mono"
assert 'class="prodockit-ref"' in home, home
assert 'href="guide/#guide"' in home, home
# These are assertions against Zensical's completed build output, not the
# intermediate ``.md#fragment`` URLs emitted by the Markdown extension.
assert (
    'href="../../procedure/test-procedure/#fig-grafana-admin-username-config"'
    '>Figure 3.1</a>' in journey
), journey
assert (
    'href="../../procedure/test-procedure/#fig-grafana-admin-password-config"'
    '>Figure 3.2</a>' in journey
), journey
assert "??" not in journey, journey
assert 'id="fig-grafana-admin-username-config"' in procedure, procedure
assert 'id="fig-grafana-admin-password-config"' in procedure, procedure
assert "prodockit-steps" in guide, guide
assert "prodockit-tree" in guide, guide
assert metadata["is_appendix"] is True
assert metadata["recto_title"] == "Short guide"
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--require-x64", action="store_true")
    parser.add_argument("--require-arm64", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    machine = platform.machine().lower()
    if args.require_x64 and machine not in {"amd64", "x86_64"}:
        raise AcceptanceError(f"expected x64, found {machine}")
    if args.require_arm64 and machine not in {"arm64", "aarch64"}:
        raise AcceptanceError(f"expected ARM64, found {machine}")

    wheel = wheel_path(args.wheel)
    with tempfile.TemporaryDirectory(prefix="prodockit-pdf-site-") as temporary:
        root = Path(temporary)
        environment = root / ".venv"
        project = root / "project"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment_python(environment)
        run([str(python), "-m", "pip", "install", str(wheel)], root)
        write_project(project)
        run([str(python), "-c", CHECK], project)

    report = {
        "passed": True,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "wheel": wheel.name,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except AcceptanceError as error:
        print(f"acceptance failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise the public built-site PDF renderer from an installed wheel.

The harness deliberately needs no Git remote, GitHub or GitLab.  It creates a
local project, runs Zensical's public build CLI and checks the exact installed
Prodockit wheel can recover navigation, metadata and rendered extension HTML.
A second project exercises both public build modes through Pandoc and
WeasyPrint and compares the resulting PDFs on the same runner.
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


def environment_command(environment: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    directory = "Scripts" if os.name == "nt" else "bin"
    return environment / directory / f"{name}{suffix}"


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PATH"] = os.pathsep.join((str(Path(command[0]).parent), env.get("PATH", "")))
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
[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
    { name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" },
]
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

``` mermaid
flowchart LR
  Installed --> PythonOnly
```

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
    Path(output_path).write_bytes(b"%PDF-1.7 installed-wheel acceptance")
pdf_config.build_pdf = capture
output_path = build_pdf_from_built_site("zensical.toml")
assert Path(output_path) == Path("docs/site_documentation.pdf"), output_path
assert Path("site/site_documentation.pdf").read_bytes() == Path(output_path).read_bytes()
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
assert captured["kwargs"]["main_font"] == "Inter"
assert captured["kwargs"]["mono_font"] == "JetBrains Mono"
assert Path(captured["kwargs"]["pandoc_executable"]).is_file()
assert 'font-family: "Inter"' in captured["kwargs"]["font_face_css"]
assert 'font-family: "JetBrains Mono"' in captured["kwargs"]["font_face_css"]
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

DEFAULT_MERMAID_CHECK = r"""
import os
from pathlib import Path

from prodockit.pdf import config as pdf_config
from prodockit.pdf.config import build_pdf_from_built_site


def main():
    captured = {}
    def capture(_pages, output_path, **kwargs):
        original_path = os.environ.get("PATH")
        os.environ["PATH"] = ""
        try:
            captured["rendered"] = kwargs["render_mermaid"](
                "flowchart LR\n  Installed --> PythonOnly"
            )
        finally:
            if original_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = original_path
        Path(output_path).write_bytes(b"%PDF-1.7 standalone acceptance")
    pdf_config.build_pdf = capture
    build_pdf_from_built_site("zensical.toml")
    rendered = captured["rendered"]
    assert rendered is not None
    svg = Path(rendered).read_text(encoding="utf-8")
    assert "Installed" in svg
    assert "PythonOnly" in svg
    assert "foreignObject" not in svg


if __name__ == "__main__":
    main()
"""



PDF_PARITY_CHECK = """
import json
import sys

import pymupdf


def links(page):
    # PDF object numbers and annotation IDs may change between renders.
    return [
        {key: value for key, value in link.items() if key not in {"xref", "id"}}
        for link in page.get_links()
    ]


with pymupdf.open(sys.argv[1]) as ordinary, pymupdf.open(sys.argv[2]) as candidate:
    assert len(ordinary) == len(candidate) >= 2, "different PDF page counts"
    assert ordinary.get_toc() == candidate.get_toc(), "different PDF outlines"
    text = "".join(page.get_text() for page in candidate)
    assert "1.1 Installation" in text, "numbered section missing"
    assert "Figure 1.1" in text, "figure numbering or reference missing"
    assert "Captured snippet" in text, "fenced snippet missing"
    assert "Rendered native note" in text, "admonition missing"
    assert any(
        link.get("uri") == "https://example.test/guide"
        for page in candidate for link in page.get_links()
    ), "external link missing"
    for number, (a, b) in enumerate(zip(ordinary, candidate, strict=True), start=1):
        assert a.rect == b.rect, f"page {number}: dimensions differ"
        assert a.get_text() == b.get_text(), f"page {number}: extracted text differs"
        assert links(a) == links(b), f"page {number}: links differ"
        assert a.get_pixmap(dpi=96).samples == b.get_pixmap(dpi=96).samples, (
            f"page {number}: rendered pixels differ"
        )
    print(json.dumps({"pages": len(ordinary), "render_dpi": 96}))
"""


def check_pdf_parity(environment: Path, project: Path) -> dict[str, object]:
    """Compare real installed-wheel CLI output and switch back on the same sources."""
    docs = project / "docs"
    (docs / "guide").mkdir(parents=True)
    (project / "output").mkdir()
    (project / "theme").mkdir()
    authored = {
        project / "zensical.toml": """[project]
site_name = "Portable PDF acceptance"
site_url = "https://example.test/manual/"
nav = [{Home = "index.md"}, {Guide = "guide/install.md"}]

[project.theme]
font = false
custom_dir = "theme"
[project.markdown_extensions.admonition]
[project.markdown_extensions.attr_list]
[project.markdown_extensions.toc]
[project.markdown_extensions.pymdownx.snippets]
[project.markdown_extensions."zensical.extensions.macros"]
module_name = "macros"
on_error_fail = true
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions."pymdownx.blocks.caption"]
types = [
  { name = "figure-caption", prefix = "{}.", classes = "prodockit-figure-caption" },
]
""",
        project / "theme/main.html": (
            '{% extends "base.html" %}'
            '{% block extrahead %}{{ super() }}'
            '<meta name="pdk-parity-theme" content="captured">{% endblock %}'
        ),
        project / "example.txt": "Captured snippet\n",
        project / "macros.py": "from prodockit.zensical_macros import define_env as define_env\n",
        project / "pdk-pdf.toml": """schema_version = 1

[document]
output = "output/site_documentation.pdf"
""",
        docs / "index.md": """# Home {: #home .unnumbered }

See \\ref{installation} and \\autoref{map}.
""",
        docs / "guide/install.md": """{{ pdk_heading_counter_reset(page) }}

{{ pdk_reference_style() }}

# Guide

## Installation

Return to \\ref{home} or visit the [guide website](https://example.test/guide).

![Map](map.svg)
/// figure-caption | #map
Installation map.
///

!!! note "Fixture note"

    Rendered native note.

```text
--8<-- "example.txt"
```
""",
        docs / "guide/map.svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="30">'
            '<rect width="80" height="30" fill="#174b78"/></svg>'
        ),
    }
    for path, source in authored.items():
        path.write_text(source, encoding="utf-8")
    python = environment_python(environment)
    pdk = str(environment_command(environment, "pdk"))
    run(
        [pdk, "pdf", "--prepare", "pandoc", "--prepare", "fonts", "--prepare", "weasyprint"],
        project,
    )
    originals = {path: path.read_bytes() for path in authored}
    run([pdk, "build", "--clean", "--strict"], project)
    run([pdk, "pdf"], project)
    ordinary = project / "output/site_documentation.pdf"
    baseline = project / "baseline.pdf"
    baseline.write_bytes(ordinary.read_bytes())
    ordinary_html = project / "site/index.html"
    original_html = ordinary_html.read_bytes()

    built = run([pdk, "-p", "build"], project)
    manifests = [
        line.removeprefix("Manifest: ")
        for line in built.stdout.splitlines()
        if line.startswith("Manifest: ")
    ]
    if len(manifests) != 1:
        raise AcceptanceError(f"expected one portable manifest:\n{built.stdout}")
    manifest = Path(manifests[0])
    portable_html = (manifest.parent / "site/index.html").read_bytes()
    guide = Path("guide/install/index.html")
    for site in (project / "site", manifest.parent / "site"):
        rendered = (site / guide).read_bytes()
        if b"counter-reset: h1-count 0" not in rendered:
            raise AcceptanceError("heading-counter styling missing from a build")
        if b"p.reference + p.reference" not in rendered:
            raise AcceptanceError("native reference styling missing from a build")
        if b'class="admonition note"' not in rendered:
            raise AcceptanceError("native admonition missing from a build")
    theme = b'<meta name="pdk-parity-theme" content="captured">'
    if theme not in original_html or theme not in portable_html:
        raise AcceptanceError("custom theme marker missing from a build")
    run([pdk, "-p", "pdf", "--manifest", str(manifest)], project)
    portable = manifest.parent / "pdf/site_documentation.pdf"
    if ordinary.read_bytes() != baseline.read_bytes() or (
        ordinary_html.read_bytes() != original_html
    ):
        raise AcceptanceError("portable mode changed the ordinary build outputs")
    report = json.loads(
        run([str(python), "-c", PDF_PARITY_CHECK, str(baseline), str(portable)], project).stdout
    )

    run([pdk, "build", "--clean", "--strict"], project)
    run([pdk, "pdf"], project)
    run([str(python), "-c", PDF_PARITY_CHECK, str(baseline), str(ordinary)], project)
    if any(path.read_bytes() != original for path, original in originals.items()):
        raise AcceptanceError("switching build modes changed authored files")
    return {"passed": True, **report}


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
        requirements = [f"{wheel}[portable,index]"]
        if os.name != "nt":
            requirements.append("weasyprint==70.0")
        run([str(python), "-m", "pip", "install", *requirements], root)
        write_project(project)
        zensical = environment_command(environment, "zensical")
        run(
            [str(zensical), "build", "--clean", "--strict", "--config-file", "zensical.toml"],
            project,
        )
        if (project / "site" / "site_documentation.pdf").exists():
            raise AcceptanceError("the first Zensical build unexpectedly contained a PDF")
        run([str(python), "-c", CHECK], project)
        default_mermaid_check = project / "default_mermaid_acceptance.py"
        default_mermaid_check.write_text(DEFAULT_MERMAID_CHECK, encoding="utf-8")
        run([str(python), str(default_mermaid_check)], project)
        parity = check_pdf_parity(environment, root / "pdf-parity")

    report = {
        "passed": True,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "wheel": wheel.name,
        "portable_pdf_parity": parity,
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

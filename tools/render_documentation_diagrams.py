"""Export the documentation's editable draw.io diagrams as committed PNGs.

The generated files are raster images so the website and PDF use the same
pixels. The draw.io files remain editable and are the maintained sources.

Run ``python tools/render_documentation_diagrams.py`` after changing a source
file under ``tools/documentation-diagrams``. The draw.io desktop application
must be installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "documentation-diagrams"
OUTPUT = ROOT / "docs" / "assets" / "diagrams"

DIAGRAMS = (
    "21.1-website-stylesheet-cascade",
    "21.2-pdf-stylesheet-cascade",
    "32.3-bibliography-pipeline",
    "33.1-pdf-pipeline",
    "24.1-publication-pipeline",
    "29.1-release-workflow",
    "32.2-cross-reference-resolution",
    "3.1-adoption-workflow",
    "23.1-template-sync-decision",
    "5.1-template-file-ownership",
    "28.1-version-pinning-drift",
    "4.1-bootstrap-journey",
    "18.1-page-update-dates",
    "32.1-extension-integration-flow",
    "7.1-authoring-feature-map",
    "25.1-output-testing-layers",
    "29.2-downstream-release-cascade",
)


def _drawio_command() -> list[str]:
    override = os.environ.get("DRAWIO")
    if override:
        return [override]
    if sys.platform == "darwin":
        return ["open", "-W", "-n", "-a", "draw.io", "--args"]
    executable = shutil.which("drawio") or shutil.which("draw.io")
    if executable:
        return [executable]
    if sys.platform == "win32":
        for variable in ("ProgramFiles", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidate = Path(root) / "draw.io" / "draw.io.exe"
                if candidate.is_file():
                    return [str(candidate)]
    raise SystemExit(
        "draw.io was not found; install the desktop application or set DRAWIO "
        "to its command-line executable"
    )


def render(name: str) -> None:
    source = SOURCE / f"{name}.drawio"
    destination = OUTPUT / f"{name}.png"
    subprocess.run(
        [
            *_drawio_command(),
            "--export",
            "--format",
            "png",
            # A fixed width keeps type at the same size when diagrams are
            # placed in the website and PDF, even when their source canvases
            # have slightly different bounds.
            "--width",
            "2509",
            "--output",
            str(destination),
            str(source),
        ],
        check=True,
        cwd=ROOT,
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in DIAGRAMS:
        render(name)


if __name__ == "__main__":
    main()

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Pre-renders Mermaid diagrams to static SVGs for a PDF build.

WeasyPrint has no JS engine to run Mermaid.js client-side the way a live
Zensical site does, so a ``<pre class="mermaid">``'s diagram source has to
become an image before Pandoc ever sees it - via a local `mermaid-cli`
install (https://github.com/mermaid-js/mermaid-cli).

Mermaid's default node/edge labels are HTML ``<foreignObject>`` content,
which WeasyPrint's SVG renderer can't display (text silently vanishes) -
worked around here by forcing ``htmlLabels`` off, so Mermaid emits plain SVG
``<text>``/``<tspan>`` labels instead.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

# Forces plain SVG text labels instead of the <foreignObject>-based default
# WeasyPrint can't render (see module docstring).
_MERMAID_CONFIG: dict[str, Any] = {
    "htmlLabels": False,
    "flowchart": {"htmlLabels": False},
    "class": {"htmlLabels": False},
    "state": {"htmlLabels": False},
}

# CI runners commonly launch Chromium as root, where its sandbox refuses to
# start without this; harmless when running unprivileged locally too.
_PUPPETEER_CONFIG: dict[str, Any] = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}


def render_mermaid_diagram(
    diagram_source: str,
    mmdc_bin: str,
    output_dir: str,
    index: int,
    timeout: int = 60,
) -> str | None:
    """Renders a single Mermaid diagram's source to a static SVG file under
    output_dir, returning its absolute path - or None if `mmdc_bin` doesn't
    exist or the render failed (logged to stderr, never raised, so one bad
    diagram can't fail an entire build).

    `mmdc_bin` is the caller's resolved path to mermaid-cli's own `mmdc`
    executable (e.g. under a local ``tools/mermaid/node_modules/.bin/mmdc``
    install) - not discovered here, since where a project chooses to
    install mermaid-cli is a caller concern, not this package's.

    `index` distinguishes this diagram's own working files
    (``diagram_{index}.mmd``/``.svg``) from any other diagram rendered into
    the same output_dir in the same build - pass a running counter.
    """
    if not os.path.exists(mmdc_bin):
        return None

    os.makedirs(output_dir, exist_ok=True)
    mmd_path = os.path.abspath(os.path.join(output_dir, f"diagram_{index}.mmd"))
    svg_path = os.path.abspath(os.path.join(output_dir, f"diagram_{index}.svg"))
    mmdc_config_path = os.path.abspath(os.path.join(output_dir, f"diagram_{index}_mermaid_config.json"))
    puppeteer_config_path = os.path.abspath(os.path.join(output_dir, f"diagram_{index}_puppeteer_config.json"))

    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(diagram_source)
    with open(mmdc_config_path, "w", encoding="utf-8") as f:
        json.dump(_MERMAID_CONFIG, f)
    with open(puppeteer_config_path, "w", encoding="utf-8") as f:
        json.dump(_PUPPETEER_CONFIG, f)

    try:
        subprocess.run(
            [
                mmdc_bin,
                "-i", mmd_path,
                "-o", svg_path,
                "-b", "transparent",
                "-c", mmdc_config_path,
                "-p", puppeteer_config_path,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        detail = getattr(e, "stderr", None) or str(e)
        print(f"⚠️  Mermaid render failed for diagram {index}: {detail}")
        return None
    return svg_path

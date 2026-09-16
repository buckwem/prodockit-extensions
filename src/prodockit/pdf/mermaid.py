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

import contextlib
import json
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from ._standalone_quickjs import (
    StandaloneBackendUnavailableError as StandaloneRuntimeUnavailableError,
)
from ._standalone_quickjs import (
    StandaloneRenderError,
    StandaloneResourceLimitError,
    require_standalone_runtime,
)
from ._standalone_worker import (
    StandaloneMermaidWorker,
    StandaloneWorkerCrashError,
    StandaloneWorkerProtocolError,
    StandaloneWorkerTimeoutError,
)

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
    def _path(suffix: str) -> str:
        return os.path.abspath(os.path.join(output_dir, f"diagram_{index}{suffix}"))

    mmd_path = _path(".mmd")
    svg_path = _path(".svg")
    mmdc_config_path = _path("_mermaid_config.json")
    puppeteer_config_path = _path("_puppeteer_config.json")

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
            encoding="utf-8",
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        detail = getattr(e, "stderr", None) or str(e)
        print(f"⚠️  Mermaid render failed for diagram {index}: {detail}")
        return None
    return svg_path


class MermaidRenderer(Protocol):
    """Backend boundary used by the PDF configuration layer."""

    def render_source(self, source: str) -> str | None:
        """Renders one diagram and returns its image path, or None."""
        ...

    def close(self) -> None:
        """Releases resources owned by the renderer."""
        ...


class MmdcMermaidRenderer:
    """Adapts the existing one-shot mmdc renderer to the boundary.

    The adapter owns the per-build diagram counter, preserving the existing
    diagram_1, diagram_2, ... filenames in document order.
    """

    def __init__(self, mmdc_bin: str, output_dir: str, *, timeout: int = 60) -> None:
        self._mmdc_bin = mmdc_bin
        self._output_dir = output_dir
        self._timeout = timeout
        self._next_index = 0

    def render_source(self, source: str) -> str | None:
        self._next_index += 1
        return render_mermaid_diagram(
            source,
            self._mmdc_bin,
            self._output_dir,
            self._next_index,
            timeout=self._timeout,
        )

    def close(self) -> None:
        """No-op: the current backend owns no persistent resources."""


class MermaidBackend(str, Enum):
    """A Mermaid renderer selectable by the PDF configuration layer."""

    MMDC = "mmdc"
    STANDALONE = "standalone"


class MermaidBackendUnavailableError(RuntimeError):
    """The selected Mermaid backend is unavailable in this release."""


class _StandaloneWorker(Protocol):
    def render_svg(
        self,
        source: str,
        *,
        theme: str = "default",
        config: dict[str, Any] | None = None,
        css: str | None = None,
    ) -> str: ...

    def close(self) -> None: ...


_STANDALONE_RENDER_ERRORS = (
    OSError,
    StandaloneRenderError,
    StandaloneResourceLimitError,
    StandaloneWorkerCrashError,
    StandaloneWorkerProtocolError,
    StandaloneWorkerTimeoutError,
)


class StandaloneMermaidRenderer:
    """Writes static SVG returned by the isolated Python-only worker."""

    def __init__(
        self,
        output_dir: str,
        *,
        worker: _StandaloneWorker | None = None,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._worker = worker or StandaloneMermaidWorker()
        self._next_index = 0

    def render_source(self, source: str) -> str | None:
        self._next_index += 1
        index = self._next_index
        temporary_path: Path | None = None
        try:
            svg = self._worker.render_svg(source, config=_MERMAID_CONFIG)
            self._output_dir.mkdir(parents=True, exist_ok=True)
            svg_path = (self._output_dir / f"diagram_{index}.svg").resolve()
            temporary_path = svg_path.with_suffix(".svg.tmp")
            temporary_path.write_text(svg, encoding="utf-8")
            os.replace(temporary_path, svg_path)
            return str(svg_path)
        except StandaloneRuntimeUnavailableError as error:
            raise MermaidBackendUnavailableError(str(error)) from error
        except _STANDALONE_RENDER_ERRORS as error:
            if temporary_path is not None:
                with contextlib.suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
            print(f"⚠️  Mermaid render failed for diagram {index}: {error}")
            return None

    def close(self) -> None:
        self._worker.close()


def create_mermaid_renderer(
    backend: MermaidBackend,
    *,
    mmdc_bin: str | None,
    output_dir: str,
) -> MermaidRenderer | None:
    """Creates the selected backend without silently falling back."""
    if backend is MermaidBackend.MMDC:
        if mmdc_bin is None:
            return None
        return MmdcMermaidRenderer(mmdc_bin, output_dir)
    try:
        require_standalone_runtime()
    except StandaloneRuntimeUnavailableError as error:
        raise MermaidBackendUnavailableError(str(error)) from error
    return StandaloneMermaidRenderer(output_dir)

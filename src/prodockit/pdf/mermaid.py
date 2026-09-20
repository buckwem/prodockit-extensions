# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Pre-renders Mermaid diagrams to static SVGs for a PDF build.

WeasyPrint has no JS engine to run Mermaid.js client-side the way a live
Zensical site does, so a ``<pre class="mermaid">``'s diagram source has to
become an image before Pandoc ever sees it. The renderer uses the audited
Python-packaged Mermaid/QuickJS runtime.

Mermaid's default node/edge labels are HTML ``<foreignObject>`` content,
which WeasyPrint's SVG renderer can't display (text silently vanishes) -
worked around here by forcing ``htmlLabels`` off, so Mermaid emits plain SVG
``<text>``/``<tspan>`` labels instead.
"""

from __future__ import annotations

import contextlib
import os
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
from .mermaid_runtime import runtime_site_packages

# Forces plain SVG text labels instead of the <foreignObject>-based default
# WeasyPrint can't render (see module docstring).
_MERMAID_CONFIG: dict[str, Any] = {
    "htmlLabels": False,
    "flowchart": {"htmlLabels": False},
    "class": {"htmlLabels": False},
    "state": {"htmlLabels": False},
}

class MermaidRenderer(Protocol):
    """Backend boundary used by the PDF configuration layer."""

    def render_source(self, source: str) -> str:
        """Render one required diagram and return its image path."""
        ...

    def close(self) -> None:
        """Releases resources owned by the renderer."""
        ...


class MermaidBackendUnavailableError(RuntimeError):
    """The Mermaid renderer is unavailable in this release."""


class MermaidRenderError(RuntimeError):
    """One required Mermaid diagram could not be converted to SVG."""


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
        runtime_path: Path | None = None,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._worker = worker or StandaloneMermaidWorker(
            runtime_site_packages=(
                str(runtime_site_packages(runtime_path)) if runtime_path is not None else None
            )
        )
        self._next_index = 0

    def render_source(self, source: str) -> str:
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
            if isinstance(error, StandaloneWorkerTimeoutError):
                detail = "the isolated worker exceeded its time limit"
            elif isinstance(error, StandaloneWorkerCrashError):
                detail = "the isolated worker exited unexpectedly"
            elif isinstance(error, StandaloneWorkerProtocolError):
                detail = "the isolated worker returned invalid data"
            elif isinstance(error, StandaloneResourceLimitError):
                detail = "the renderer reached a resource limit; simplify or split the diagram"
            elif isinstance(error, StandaloneRenderError):
                detail = "Mermaid rejected the diagram or produced invalid SVG"
            else:
                detail = "the rendered SVG could not be written"
            raise MermaidRenderError(
                f"Mermaid diagram {index} could not be rendered: {detail}"
            ) from error

    def close(self) -> None:
        self._worker.close()


def create_mermaid_renderer(
    *,
    output_dir: str,
    runtime_path: Path | None = None,
) -> MermaidRenderer:
    """Create the audited Python renderer without an external fallback."""
    if runtime_path is None:
        try:
            require_standalone_runtime()
        except StandaloneRuntimeUnavailableError as error:
            raise MermaidBackendUnavailableError(str(error)) from error
    else:
        try:
            runtime_site_packages(runtime_path)
        except RuntimeError as error:
            raise MermaidBackendUnavailableError(str(error)) from error
    if runtime_path is None:
        return StandaloneMermaidRenderer(output_dir)
    return StandaloneMermaidRenderer(output_dir, runtime_path=runtime_path)

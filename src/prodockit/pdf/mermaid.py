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
import tempfile
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


class MermaidOutputError(MermaidRenderError):
    """The configured Mermaid output path is unsafe to write."""


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


def _validate_output_directory(directory: Path) -> None:
    """Reject an existing symlink or non-directory without creating anything."""

    current = Path(directory.anchor)
    try:
        for part in directory.parts[1:]:
            current /= part
            if current.is_symlink():
                raise MermaidOutputError(
                    "Unsafe Mermaid output directory contains a symbolic link: "
                    f"{current}. Remove the link and retry."
                )
            if current.exists() and not current.is_dir():
                raise MermaidOutputError(
                    f"Unsafe Mermaid output directory: {current}. "
                    "Replace it with a directory and retry."
                )
    except OSError as error:
        raise MermaidOutputError(
            f"Could not inspect the Mermaid output directory {directory}: {error}"
        ) from error


def _safe_output_directory(directory: Path) -> None:
    """Create ``directory`` without following a symbolic-link component."""

    current = Path(directory.anchor)
    try:
        for part in directory.parts[1:]:
            current /= part
            if current.is_symlink():
                raise MermaidOutputError(
                    "Unsafe Mermaid output directory contains a symbolic link: "
                    f"{current}. Remove the link and retry."
                )
            try:
                current.mkdir()
            except FileExistsError:
                if current.is_symlink() or not current.is_dir():
                    raise MermaidOutputError(
                        f"Unsafe Mermaid output directory: {current}. "
                        "Replace it with a directory and retry."
                    ) from None
    except OSError as error:
        raise MermaidOutputError(
            f"Could not prepare the Mermaid output directory {directory}: {error}"
        ) from error


def _safe_svg_path(output_dir: Path, index: int) -> Path:
    """Return a local SVG destination, rejecting an existing link or non-file."""

    svg_path = output_dir / f"diagram_{index}.svg"
    if svg_path.parent != output_dir:
        raise MermaidOutputError(f"Mermaid output path escapes its directory: {svg_path}")
    if svg_path.is_symlink():
        raise MermaidOutputError(
            f"Unsafe Mermaid output is a symbolic link: {svg_path}. "
            "Remove the link and retry."
        )
    if svg_path.exists() and not svg_path.is_file():
        raise MermaidOutputError(
            f"Unsafe Mermaid output is not a regular file: {svg_path}. "
            "Remove it and retry."
        )
    return svg_path


class StandaloneMermaidRenderer:
    """Writes static SVG returned by the isolated Python-only worker."""

    def __init__(
        self,
        output_dir: str,
        *,
        worker: _StandaloneWorker | None = None,
        runtime_path: Path | None = None,
    ) -> None:
        self._output_dir = Path(os.path.abspath(output_dir))
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
            _validate_output_directory(self._output_dir)
            svg_path = _safe_svg_path(self._output_dir, index)
            svg = self._worker.render_svg(source, config=_MERMAID_CONFIG)
            _safe_output_directory(self._output_dir)
            svg_path = _safe_svg_path(self._output_dir, index)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self._output_dir,
                prefix=f".{svg_path.name}.",
                suffix=".tmp",
                text=True,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
                temporary_file.write(svg)
            _safe_output_directory(self._output_dir)
            _safe_svg_path(self._output_dir, index)
            os.replace(temporary_path, svg_path)
            return str(svg_path)
        except StandaloneRuntimeUnavailableError as error:
            raise MermaidBackendUnavailableError(str(error)) from error
        except _STANDALONE_RENDER_ERRORS as error:
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
        finally:
            if temporary_path is not None:
                with contextlib.suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

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

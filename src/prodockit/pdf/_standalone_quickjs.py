# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Callback-free, resource-bounded runtime used by Mermaid ``--swap``.

This private module uses the exact audited mermaidx 0.9.5 assets and owns the
QuickJS context so every untrusted render has memory, time, and stack limits.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast
from xml.etree import ElementTree

from ._mermaid_provenance import load_mermaid_provenance

_PROVENANCE = load_mermaid_provenance()
_MERMAIDX_VERSION = _PROVENANCE.mermaidx_version
_QUICKJS_VERSION = "0.16.2.1"

_ASSET_HASHES = {
    "dom_shim.js": "624a5c42b2d01d4eb5496969ddb856cab0f12975661ab660aad67f346ef2c24e",
    "mermaid.js": _PROVENANCE.asset_sha256,
    "fonts/DejaVuSans.ttf": "3fdf69cabf06049ea70a00b5919340e2ce1e6d02b0cc3c4b44fb6801bd1e0d22",
    "fonts/DejaVuSans-Bold.ttf": "b184b89e3c1075f22f6b71575b6fc20d4972b3cfd3b23322ca6fd596dcaef167",
}

_UNSAFE_SVG_ELEMENTS = {"foreignobject", "iframe", "object", "script"}
_EXTERNAL_URL = re.compile(r"url\(\s*['\"]?(?!#)", re.IGNORECASE)

_BOOTSTRAP_JS = """
globalThis.__log = () => {};
globalThis.mermaid = (globalThis.__esbuild_esm_mermaid_nm.mermaid.default
    || globalThis.__esbuild_esm_mermaid_nm.mermaid);
"""

_RENDER_JS = """
globalThis.__renderResult = null;
globalThis.__renderError = null;
mermaid.initialize(JSON.parse(__config));
(function () {
  if (__css) {
    const el = document.getElementById("prodockit-mermaid-css")
      || document.createElement("style");
    el.setAttribute("id", "prodockit-mermaid-css");
    el.textContent = __css;
    document.head.appendChild(el);
  }
})();
mermaid.render(__renderId, __code)
  .then((result) => { globalThis.__renderResult = result.svg; })
  .catch((error) => {
    globalThis.__renderError = error && error.name
      ? error.name + ": " + error.message
      : String(error);
  });
"""


class StandaloneBackendUnavailableError(RuntimeError):
    """The exact audited standalone runtime is absent or incompatible."""


class StandaloneResourceLimitError(RuntimeError):
    """QuickJS stopped a render at an explicit resource boundary."""


class StandaloneRenderError(RuntimeError):
    """Mermaid or QuickJS failed without crossing a resource boundary."""


@dataclass(frozen=True)
class QuickJSMermaidLimits:
    """Fail-closed limits for one in-process QuickJS context."""

    memory_bytes: int = 256 * 1024 * 1024
    maximum_stack_bytes: int = 512 * 1024
    execution_time_seconds: float = 5.0
    promise_jobs: int = 200_000
    source_bytes: int = 1024 * 1024
    output_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        _require_range("memory_bytes", self.memory_bytes, 32 * 1024 * 1024, 512 * 1024 * 1024)
        _require_range("maximum_stack_bytes", self.maximum_stack_bytes, 64 * 1024, 1024 * 1024)
        _require_range("execution_time_seconds", self.execution_time_seconds, 0.01, 30.0)
        _require_range("promise_jobs", self.promise_jobs, 1, 1_000_000)
        _require_range("source_bytes", self.source_bytes, 1, 4 * 1024 * 1024)
        _require_range("output_bytes", self.output_bytes, 1024, 64 * 1024 * 1024)


def _require_range(
    name: str,
    value: int | float,
    minimum: int | float,
    maximum: int | float,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def _validate_static_svg(svg: str) -> None:
    """Reject active or externally loaded content before SVG leaves the worker."""
    lowered = svg.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise StandaloneRenderError("Mermaid SVG contains a prohibited declaration.")
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise StandaloneRenderError("Mermaid rendering produced invalid SVG.") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise StandaloneRenderError("Mermaid rendering did not produce an SVG document.")

    for element in root.iter():
        element_name = element.tag.rsplit("}", 1)[-1].lower()
        if element_name in _UNSAFE_SVG_ELEMENTS:
            raise StandaloneRenderError(
                f"Mermaid SVG contains prohibited <{element_name}> content."
            )
        if element_name == "style" and element.text and _EXTERNAL_URL.search(element.text):
            raise StandaloneRenderError("Mermaid SVG CSS references an external resource.")
        for raw_name, value in element.attrib.items():
            name = raw_name.rsplit("}", 1)[-1].lower()
            normalized_value = value.strip().lower()
            if name.startswith("on"):
                raise StandaloneRenderError(
                    f"Mermaid SVG contains prohibited event attribute {name!r}."
                )
            if "javascript:" in normalized_value:
                raise StandaloneRenderError("Mermaid SVG contains a prohibited JavaScript URL.")
            if (
                name in {"href", "src"}
                and normalized_value
                and not normalized_value.startswith("#")
            ):
                raise StandaloneRenderError("Mermaid SVG references an external resource.")
            if name == "style" and _EXTERNAL_URL.search(value):
                raise StandaloneRenderError("Mermaid SVG CSS references an external resource.")


class _QuickJSContext(Protocol):
    def eval(self, source: str) -> Any: ...

    def set(self, name: str, value: Any) -> None: ...

    def set_memory_limit(self, limit: int) -> None: ...

    def set_time_limit(self, limit: float) -> None: ...

    def set_max_stack_size(self, limit: int) -> None: ...

    def execute_pending_job(self) -> bool: ...


@dataclass(frozen=True)
class _Runtime:
    context_factory: Callable[[], _QuickJSContext]
    dom_shim_js: str
    mermaid_js: str
    measure_text_js: str
    path_bbox_js: str
    patch_svg: Callable[[str], str]


def _distribution_version(name: str, expected: str) -> None:
    try:
        actual = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise StandaloneBackendUnavailableError(
            f"The standalone Mermaid backend requires {name}=={expected}."
        ) from exc
    if actual != expected:
        raise StandaloneBackendUnavailableError(
            f"The standalone Mermaid backend requires {name}=={expected}; found {actual}."
        )


def _read_audited_asset(assets_dir: Path, relative_path: str) -> str:
    path = assets_dir / relative_path
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise StandaloneBackendUnavailableError(
            f"The audited Mermaid asset {relative_path!r} is unavailable."
        ) from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != _ASSET_HASHES[relative_path]:
        raise StandaloneBackendUnavailableError(
            f"The audited Mermaid asset {relative_path!r} failed its integrity check."
        )
    return data.decode("utf-8")


def _verify_font_assets(assets_dir: Path) -> None:
    for relative_path in ("fonts/DejaVuSans.ttf", "fonts/DejaVuSans-Bold.ttf"):
        path = assets_dir / relative_path
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise StandaloneBackendUnavailableError(
                f"The audited Mermaid asset {relative_path!r} is unavailable."
            ) from exc
        if actual != _ASSET_HASHES[relative_path]:
            raise StandaloneBackendUnavailableError(
                f"The audited Mermaid asset {relative_path!r} failed its integrity check."
            )


def _load_runtime() -> _Runtime:
    """Loads only the exact packages and private symbols audited in S0."""
    _distribution_version("mermaidx", _MERMAIDX_VERSION)
    _distribution_version("quickjs-ng", _QUICKJS_VERSION)
    try:
        quickjs = importlib.import_module("quickjs")
        mermaidx = importlib.import_module("mermaidx")
        v8_engine = importlib.import_module("mermaidx.engines.v8_engine")
        path_bbox = importlib.import_module("mermaidx.path_bbox")
        svg_patches = importlib.import_module("mermaidx.engines._svg_patches")
        context_factory = quickjs.Context
        measure_text_js = v8_engine._measure_text_js
        path_bbox_js = path_bbox.PATH_BBOX_JS
        patch_journey = svg_patches.patch_journey_task_text_color
        patch_mindmap = svg_patches.patch_mindmap_centering
    except (AttributeError, ImportError) as exc:
        raise StandaloneBackendUnavailableError(
            "The audited standalone Mermaid runtime has incompatible private symbols."
        ) from exc

    package_file = getattr(mermaidx, "__file__", None)
    if not package_file:
        raise StandaloneBackendUnavailableError(
            "The audited mermaidx package location is unavailable."
        )
    assets_dir = Path(package_file).resolve().parent / "assets"
    _verify_font_assets(assets_dir)

    def patch_svg(svg: str) -> str:
        return cast(str, patch_journey(patch_mindmap(svg)))

    return _Runtime(
        context_factory=context_factory,
        dom_shim_js=_read_audited_asset(assets_dir, "dom_shim.js"),
        mermaid_js=_read_audited_asset(assets_dir, "mermaid.js"),
        measure_text_js=measure_text_js(),
        path_bbox_js=path_bbox_js,
        patch_svg=patch_svg,
    )


def require_standalone_runtime() -> None:
    """Verifies the exact audited packages, symbols and assets are usable."""
    try:
        _load_runtime()
    except StandaloneBackendUnavailableError as error:
        raise StandaloneBackendUnavailableError(
            "The standalone Mermaid backend requires mermaidx==0.9.5 and "
            f"quickjs-ng==0.16.2.1; {error}"
        ) from error


class StandaloneQuickJSMermaidEngine:
    """Owns one callback-free QuickJS context on its creating thread."""

    def __init__(self, limits: QuickJSMermaidLimits | None = None) -> None:
        self._limits = limits or QuickJSMermaidLimits()
        self._runtime: _Runtime | None = None
        self._context: _QuickJSContext | None = None
        self._owner_thread: int | None = None
        self._render_count = 0

    @property
    def started(self) -> bool:
        return self._context is not None

    def start(self) -> None:
        if self.started:
            self._check_owner_thread()
            return
        runtime = _load_runtime()
        try:
            context = runtime.context_factory()
            context.set_memory_limit(self._limits.memory_bytes)
            context.set_max_stack_size(self._limits.maximum_stack_bytes)
            context.eval("globalThis.__log = () => {};")
            context.eval(runtime.measure_text_js)
            context.eval(runtime.path_bbox_js)
            context.eval(runtime.dom_shim_js)
            context.eval(runtime.mermaid_js)
            context.eval(_BOOTSTRAP_JS)
        except Exception as exc:
            raise StandaloneBackendUnavailableError(
                "The audited standalone Mermaid runtime failed to initialize."
            ) from exc
        self._runtime = runtime
        self._context = context
        self._owner_thread = threading.get_ident()

    def close(self) -> None:
        if self.started:
            self._check_owner_thread()
        self._context = None
        self._runtime = None
        self._owner_thread = None

    def render_svg(
        self,
        source: str,
        *,
        theme: str = "default",
        config: dict[str, Any] | None = None,
        css: str | None = None,
    ) -> str:
        if not self.started:
            raise RuntimeError("The standalone Mermaid engine is not started.")
        self._check_owner_thread()
        if not isinstance(source, str):
            raise TypeError("Mermaid source must be text.")
        _require_utf8_size("Mermaid source", source, self._limits.source_bytes)
        css_text = css or ""
        _require_utf8_size("Mermaid CSS", css_text, self._limits.source_bytes)
        config_json = json.dumps(self._controlled_config(theme, config), ensure_ascii=False)
        _require_utf8_size("Mermaid configuration", config_json, self._limits.source_bytes)

        context = self._require_context()
        self._render_count += 1
        deadline = time.monotonic() + self._limits.execution_time_seconds
        try:
            self._set_remaining_time(context, deadline)
            context.eval("__resetDocument();")
            context.set("__config", config_json)
            context.set("__css", css_text)
            context.set("__code", source)
            context.set("__renderId", f"pdk{self._render_count}")
            self._eval_untrusted(context, _RENDER_JS, deadline)
            self._pump_jobs(context, deadline)
            error = self._eval_untrusted(context, "globalThis.__renderError", deadline)
            if error:
                raise StandaloneRenderError(f"Mermaid rendering failed: {error}")
            svg = self._eval_untrusted(context, "globalThis.__renderResult", deadline)
        except (StandaloneRenderError, StandaloneResourceLimitError):
            raise
        except Exception as exc:
            self._raise_quickjs_error(exc)

        if not isinstance(svg, str) or not svg:
            raise StandaloneRenderError("Mermaid rendering produced no SVG output.")
        runtime = self._runtime
        assert runtime is not None
        patched_svg = runtime.patch_svg(svg)
        _require_utf8_size(
            "Mermaid SVG output",
            patched_svg,
            self._limits.output_bytes,
            resource=True,
        )
        _validate_static_svg(patched_svg)
        return patched_svg

    def _pump_jobs(self, context: _QuickJSContext, deadline: float) -> None:
        for _ in range(self._limits.promise_jobs):
            complete = self._eval_untrusted(
                context,
                "!!globalThis.__renderResult || !!globalThis.__renderError",
                deadline,
            )
            if complete:
                return
            self._set_remaining_time(context, deadline)
            if not context.execute_pending_job():
                return
        raise StandaloneResourceLimitError("Mermaid rendering exceeded the Promise-job limit.")

    def _eval_untrusted(self, context: _QuickJSContext, script: str, deadline: float) -> Any:
        self._set_remaining_time(context, deadline)
        return context.eval(script)

    def _set_remaining_time(self, context: _QuickJSContext, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StandaloneResourceLimitError(
                "Mermaid rendering exceeded the execution-time limit."
            )
        context.set_time_limit(remaining)

    def _controlled_config(self, theme: str, config: dict[str, Any] | None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "startOnLoad": False,
            "securityLevel": "strict",
            "theme": theme or "default",
            "journey": {"textPlacement": "tspan"},
            "timeline": {"textPlacement": "tspan"},
        }
        if config:
            result.update(config)
        result["startOnLoad"] = False
        result["securityLevel"] = "strict"
        result["htmlLabels"] = False
        for section in ("flowchart", "class", "state"):
            section_config = result.get(section)
            if not isinstance(section_config, dict):
                section_config = {}
            result[section] = {**section_config, "htmlLabels": False}
        return result

    def _check_owner_thread(self) -> None:
        if self._owner_thread is not None and self._owner_thread != threading.get_ident():
            raise RuntimeError("A QuickJS context may only be used from its creating thread.")

    def _require_context(self) -> _QuickJSContext:
        context = self._context
        if context is None:
            raise RuntimeError("The standalone Mermaid engine is not started.")
        return context

    @staticmethod
    def _raise_quickjs_error(exc: Exception) -> NoReturn:
        detail = str(exc).lower()
        if any(marker in detail for marker in ("interrupted", "out of memory", "stack size")):
            raise StandaloneResourceLimitError(
                "QuickJS stopped Mermaid at a resource limit."
            ) from exc
        if type(exc).__name__ == "StackOverflow":
            raise StandaloneResourceLimitError(
                "QuickJS stopped Mermaid at the stack limit."
            ) from exc
        raise StandaloneRenderError("QuickJS failed while rendering Mermaid.") from exc


def _require_utf8_size(label: str, value: str, maximum: int, *, resource: bool = False) -> None:
    if len(value.encode("utf-8")) <= maximum:
        return
    message = f"{label} exceeds its {maximum}-byte limit."
    if resource:
        raise StandaloneResourceLimitError(message)
    raise ValueError(message)

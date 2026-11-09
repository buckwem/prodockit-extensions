# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Compatibility boundary for Zensical's current-page context.

This module describes the small public API prodockit would ideally consume
from Zensical::

    current_page_path(markdown) -> str | None

Zensical does not currently expose that API.  Keep the translation from its
private ``ContextPreprocessor`` representation here, so the rest of
prodockit neither imports nor understands that representation.  If Zensical
adds an equivalent public API, only this module needs to change.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from markdown import Markdown


class ZensicalPageContextAPIError(RuntimeError):
    """Zensical is installed, but its private page-context contract moved."""


_CONTRACT_ERROR = (
    "Zensical's current-page context is no longer available as "
    "ContextPreprocessor.from_markdown(md).page.path"
)


class _Page(Protocol):
    path: str | None


class _Context(Protocol):
    page: _Page | None
    config: Mapping[str, object]


def _rendering_context(md: Markdown) -> _Context | None:
    try:
        context_module = import_module("zensical.extensions.context")
    except ModuleNotFoundError as error:
        # Zensical is optional, so its genuinely being absent is normal.  A
        # missing submodule or dependency inside an installed Zensical is a
        # changed/broken compatibility contract and must not fail silently.
        if error.name == "zensical":
            return None
        raise ZensicalPageContextAPIError(_CONTRACT_ERROR) from error
    except ImportError as error:
        raise ZensicalPageContextAPIError(_CONTRACT_ERROR) from error

    try:
        return cast("_Context | None", context_module.ContextPreprocessor.from_markdown(md))
    except (AttributeError, TypeError) as error:
        raise ZensicalPageContextAPIError(_CONTRACT_ERROR) from error


def current_page_path(md: Markdown) -> str | None:
    """Return the source path of the page Zensical is currently rendering."""
    context = _rendering_context(md)
    if context is None:
        return None
    try:
        page = context.page
        if page is None:
            return None
        path = page.path
        if path is None:
            raise ZensicalPageContextAPIError(_CONTRACT_ERROR)
        return str(path)
    except (AttributeError, TypeError) as error:
        raise ZensicalPageContextAPIError(_CONTRACT_ERROR) from error


def current_docs_dir(md: Markdown) -> Path:
    """Resolve the active Zensical docs directory independently of the shell cwd."""
    context = _rendering_context(md)
    if context is None:
        raise ZensicalPageContextAPIError("Zensical's rendering context is unavailable")
    root = context.config.get("root_dir")
    docs = context.config.get("docs_dir", "docs")
    if not isinstance(root, str) or not isinstance(docs, str):
        raise ZensicalPageContextAPIError("Zensical's documentation directory is unavailable")
    return (Path(root) / docs).resolve()

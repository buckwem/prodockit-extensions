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

from importlib import import_module

from markdown import Markdown


class ZensicalPageContextAPIError(RuntimeError):
    """Zensical is installed, but its private page-context contract moved."""


_CONTRACT_ERROR = (
    "Zensical's current-page context is no longer available as "
    "ContextPreprocessor.from_markdown(md).page.path"
)


def current_page_path(md: Markdown) -> str | None:
    """Return the source path of the page Zensical is currently rendering.

    ``None`` means that this Markdown conversion is not running with a
    Zensical page context.  A changed Zensical contract is different: it
    raises :class:`ZensicalPageContextAPIError`, allowing the caller to issue
    a compatibility diagnostic instead of silently treating every page as
    the same source.
    """
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
        ContextPreprocessor = context_module.ContextPreprocessor
        context = ContextPreprocessor.from_markdown(md)
        if context is None or context.page is None:
            return None
        path = context.page.path
        if path is None:
            raise ZensicalPageContextAPIError(_CONTRACT_ERROR)
        return str(path)
    except ZensicalPageContextAPIError:
        raise
    except (AttributeError, TypeError) as error:
        raise ZensicalPageContextAPIError(_CONTRACT_ERROR) from error

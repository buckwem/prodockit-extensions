# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Internal helpers for Zensical-aware, cross-page state sharing.

Not part of zendoc's public API - shared by zendoc.headings and
zendoc.citations, both of which face the same problem: Zensical builds each
page with its own fresh ``Markdown`` instance, so a plain per-instance
default registry can never see another page's entries. ``nav_pages`` (used
by zendoc.citations) additionally addresses pages being built in a single,
one-shot pass: a forward reference to a page not yet built can't resolve
without pre-scanning ahead of time.
"""

from __future__ import annotations

from typing import TypeVar

from markdown import Markdown

T = TypeVar("T")


def page_source(md: Markdown) -> str | None:
    """Returns the current page's path if running under Zensical's per-page
    ``render()``, else None.

    Zensical stashes a ``Page`` (with a stable, per-page path) on every
    ``Markdown`` instance it builds, via its own ``ContextPreprocessor`` -
    used as a best-effort default for ``source`` when the caller hasn't set
    one explicitly, since without it every page would silently share the
    same default source (``""``), each page wiping the previous one's
    registry entries on every render. Returns None (falling back to
    ordinary behaviour) under any other Python-Markdown tool, or if
    Zensical isn't installed.
    """
    try:
        from zensical.extensions.context import ContextPreprocessor
    except ImportError:
        return None
    context = ContextPreprocessor.from_markdown(md)
    if context is None or context.page is None:
        return None
    return context.page.path


def share(md: Markdown, attr: str, value: T) -> T:
    """Order-independent same-page sharing between two zendoc extensions
    that both want the same piece of state (e.g. zendoc.headings and
    zendoc.refs sharing an IdRegistry): whichever extension's
    extendMarkdown() runs first claims `value` by stashing it on `md` under
    `attr`; whichever runs second reuses what's already there - regardless
    of which order the two extensions were listed in (Zensical's own
    TOML-to-extension-list conversion doesn't preserve list order, so this
    can't be assumed).
    """
    existing = getattr(md, attr, None)
    if existing is not None:
        return existing  # type: ignore[no-any-return]
    setattr(md, attr, value)
    return value


def nav_pages() -> tuple[str, list[str]] | None:
    """Returns (docs_dir, [nav markdown file paths]) from Zensical's own
    already-parsed build configuration, if running under Zensical with that
    configuration actually populated (i.e. mid-build - `zensical.config.get_config()`
    returns an empty/absent config otherwise, e.g. under a plain script
    import). Returns None in that case, or if Zensical isn't installed.

    Used to pre-scan every page's raw text for something (currently
    zendoc.citations' citation definitions) before any single page has
    actually been converted - needed because Zensical's `render()` builds
    one page a time, in one pass, so a page late in nav order (e.g. a
    references page kept as an appendix) hasn't been touched yet at the
    point an early page might already want to resolve something defined
    there.
    """
    try:
        from zensical.config import get_config
    except ImportError:
        return None
    config = get_config()
    if not config:
        return None
    docs_dir = config.get("docs_dir")
    nav = config.get("nav")
    if not docs_dir or not nav:
        return None
    return str(docs_dir), _flatten_nav(nav)


def _flatten_nav(items: object) -> list[str]:
    """Flattens Zensical's normalised nav structure (a list of
    {"url": ..., "children": [...]} dicts, possibly nested) into a plain
    list of markdown file paths, in nav order."""
    paths: list[str] = []
    if not isinstance(items, list):
        return paths
    for item in items:
        if isinstance(item, dict):
            url = item.get("url")
            if url:
                paths.append(url)
            paths.extend(_flatten_nav(item.get("children")))
        elif isinstance(item, list):
            paths.extend(_flatten_nav(item))
    return paths

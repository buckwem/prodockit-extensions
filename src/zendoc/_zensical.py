# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Internal helpers for Zensical-aware, cross-page state sharing.

Not part of zendoc's public API - shared by zendoc.headings,
zendoc.citations, and zendoc.glossary, all of which face the same problem:
Zensical builds each page with its own fresh ``Markdown`` instance, so a
plain per-instance default registry can never see another page's entries.
``nav_pages``/``preseed_attr_from_nav`` (used by zendoc.citations and
zendoc.glossary) additionally address pages being built in a single,
one-shot pass: a forward reference to a page not yet built can't resolve
without pre-scanning ahead of time.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, TypeVar

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


class _Preseedable(Protocol):
    def preseed(self, source: str, id: str, text: str) -> None: ...


_ATTR_RE = re.compile(r"\{:\s*([^}]+?)\s*\}")
_ID_RE = re.compile(r"#([\w-]+)")
_FENCE_RE = re.compile(
    r"^[ \t]*```.*?^[ \t]*```[ \t]*$|^[ \t]*~~~.*?^[ \t]*~~~[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def _strip_fences(text: str) -> str:
    """Blanks out fenced code blocks before a raw-text regex scan, so a
    documentation page showing a definition syntax as a *literal example*
    inside a fenced code block isn't mistaken for a real definition by
    preseed_attr_from_nav (which, unlike the real per-page treeprocessor,
    scans raw text directly rather than the parsed, fence-aware
    Python-Markdown tree)."""
    return _FENCE_RE.sub("", text)


def preseed_attr_from_nav(registry: _Preseedable, attr_name: str) -> None:
    """Pre-scans every page in the current Zensical build's nav for a
    ``{: #id <attr_name>="..." }`` attr_list definition, provisionally
    registering each one (via ``registry.preseed``) before any page has
    actually been converted.

    Fixes the classic "cited/referenced before defined" ordering problem: a
    source is usually cited/referenced from an early chapter but defined on
    a references/acronyms/glossary page kept at the end of nav, which -
    without this - is a forward reference to a page `zensical build`'s
    single, one-shot process hasn't rendered yet (unlike `zensical serve`'s
    live-reload, which eventually rebuilds every page at least once). Reads
    raw file text directly rather than waiting for Python-Markdown to parse
    it - safe here because the id/value are already literal attr_list
    attribute values, unlike e.g. zendoc.headings' section numbers, which
    genuinely depend on running the real Python-Markdown pipeline to
    compute. Skips fenced code blocks, so a documentation page showing this
    exact attr_list syntax as a literal example doesn't get mistaken for a
    real definition.

    Used by zendoc.citations (`attr_name="data-cite-text"`) and
    zendoc.glossary (`attr_name="data-term"`) - both need the identical
    scan, differing only in which attribute they're looking for and which
    registry they feed.
    """
    located = nav_pages()
    if located is None:
        return
    docs_dir, pages = located
    value_re = re.compile(attr_name + r'="([^"]*)"')
    for rel_path in pages:
        try:
            text = (Path(docs_dir) / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        text = _strip_fences(text)
        for attr_match in _ATTR_RE.finditer(text):
            attrs = attr_match.group(1)
            id_match = _ID_RE.search(attrs)
            value_match = value_re.search(attrs)
            if id_match and value_match:
                registry.preseed(rel_path, id_match.group(1), value_match.group(1))

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Internal helpers for Zensical-aware, cross-page state sharing.

Not part of prodockit's public API - shared by prodockit.headings,
prodockit.citations, prodockit.glossary, and prodockit.bibliography, all of
which face the same problem: Zensical builds each page with its own fresh
``Markdown`` instance, so a plain per-instance default registry can never
see another page's entries. ``nav_pages``/``preseed_attr_from_nav``/
``find_page_with_marker``/``prescan_bibliography`` additionally address
pages being built in a single, one-shot pass: a forward reference to a
page not yet built can't resolve without pre-scanning ahead of time.
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
    """Order-independent same-page sharing between two prodockit extensions
    that both want the same piece of state (e.g. prodockit.headings and
    prodockit.refs sharing an IdRegistry): whichever extension's
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
    prodockit.citations' citation definitions) before any single page has
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


def _front_matter_flag(text: str, key: str) -> bool:
    """True if raw file text's YAML front matter sets ``key: true``. Used by
    prescan_headings() to detect an appendix-flagged page ahead of that page
    actually being converted."""
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    return bool(
        re.search(rf"^{re.escape(key)}:\s*true\s*$", parts[1], re.MULTILINE | re.IGNORECASE)
    )


def _count_top_level_headings(text: str) -> int:
    """Counts top-level (single ``#``) ATX headings in raw markdown text,
    skipping fenced code blocks, HTML comments, and headings tagged
    ``{.unnumbered}`` - used by prescan_headings() to work out how many
    numbered h1s appear on a page before any page has actually been
    converted. Line-based rather than a single regex (unlike _strip_fences()
    above) since it also needs to track HTML comments, not just fences, in
    one pass."""
    count = 0
    in_fence = False
    in_comment = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_comment and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not in_comment and "<!--" in stripped:
            in_comment = True
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if re.match(r"^#\s+\S", line) and ".unnumbered" not in line:
            count += 1
    return count


def prescan_headings(appendix_attr: str) -> tuple[dict[str, int], dict[str, str]] | None:
    """Returns ``(start_counts, appendix_letters)``, both keyed by
    nav-relative page path, by pre-scanning every page in the current
    Zensical build's nav - the same "before any page has actually been
    converted" pre-scan preseed_attr_from_nav does for citation/glossary
    definitions, applied to heading counts instead.

    ``start_counts[page]`` is how many numbered h1s appear on every earlier
    nav page, for prodockit.headings' "continuous" numbering mode to seed this
    page's own h1 counter with - so numbering continues seamlessly from one
    page to the next instead of resetting per page. A page whose front
    matter sets `appendix_attr` is skipped entirely for this count (it
    doesn't consume a number from the sequence) and instead gets a
    sequential letter in ``appendix_letters`` - "A" for the first such page
    in nav order, "B" for the second, and so on.

    Returns None outside a Zensical build (mirrors nav_pages()).
    """
    located = nav_pages()
    if located is None:
        return None
    docs_dir, pages = located
    start_counts: dict[str, int] = {}
    appendix_letters: dict[str, str] = {}
    running_total = 0
    next_letter_index = 0
    for rel_path in pages:
        try:
            text = (Path(docs_dir) / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        if _front_matter_flag(text, appendix_attr):
            next_letter_index += 1
            appendix_letters[rel_path] = chr(ord("A") + next_letter_index - 1)
            continue
        start_counts[rel_path] = running_total
        running_total += _count_top_level_headings(text)
    return start_counts, appendix_letters


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
    attribute values, unlike e.g. prodockit.headings' section numbers, which
    genuinely depend on running the real Python-Markdown pipeline to
    compute. Skips fenced code blocks, so a documentation page showing this
    exact attr_list syntax as a literal example doesn't get mistaken for a
    real definition.

    Used by prodockit.citations (`attr_name="data-cite-text"`) and
    prodockit.glossary (`attr_name="data-term"`) - both need the identical
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


def find_page_with_marker(marker: str) -> str | None:
    """Pre-scans every page in the current Zensical build's nav for a bare
    text marker (e.g. prodockit.bibliography's own ``\\bibliography``),
    returning the first page found - the same "cited/referenced before
    defined" ordering problem prescan_headings()/preseed_attr_from_nav()
    solve for their own kind of definition, applied to a plain marker
    string instead of an attr_list attribute value. Returns None outside a
    Zensical build, or if no page has the marker (yet).

    Skips fenced code blocks, so a documentation page showing this marker
    as a literal example isn't mistaken for the real thing.
    """
    located = nav_pages()
    if located is None:
        return None
    docs_dir, pages = located
    for rel_path in pages:
        try:
            text = (Path(docs_dir) / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        if marker in _strip_fences(text):
            return rel_path
    return None


def prescan_bibliography(
    cite_re: str, marker_re: str, default_bib_file: str
) -> tuple[set[str], dict[str, str]] | None:
    """Returns ``(all_cited_keys, first_page_for_file)``, by pre-scanning
    every page in the current Zensical build's nav before any page has
    actually been converted - the same ordering problem
    find_page_with_marker() solves, generalized to also collect *which*
    citation keys were used and *which* distinct ``.bib`` file each
    ``\\bibliography{...}`` marker references (falling back to
    `default_bib_file` for a marker that omits its own file argument).

    ``all_cited_keys`` is every distinct key ever passed to a citation
    pattern (`cite_re`) anywhere in nav - used to filter a
    ``cited_only=True`` marker down to just what's actually cited.

    ``first_page_for_file`` maps each distinct ``.bib`` file path
    referenced by any marker anywhere in nav to the first nav-order page
    with a marker for that specific file - used to cross-link a
    ``\\citebib{id}`` citation to whichever page's marker actually lists
    that entry, rather than assuming a single global bibliography page.
    In the common single-file case this map has exactly one entry, so
    cross-linking stays exactly as it was before per-marker file
    overrides existed.

    Returns None outside a Zensical build (mirrors nav_pages()).
    """
    located = nav_pages()
    if located is None:
        return None
    docs_dir, pages = located
    all_cited_keys: set[str] = set()
    first_page_for_file: dict[str, str] = {}
    cite_pattern = re.compile(cite_re)
    marker_pattern = re.compile(marker_re)
    for rel_path in pages:
        try:
            text = (Path(docs_dir) / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        text = _strip_fences(text)
        for match in cite_pattern.finditer(text):
            all_cited_keys.add(match.group(1))
        for match in marker_pattern.finditer(text):
            file = (match.group(1) or "").strip() or default_bib_file
            first_page_for_file.setdefault(file, rel_path)
    return all_cited_keys, first_page_for_file

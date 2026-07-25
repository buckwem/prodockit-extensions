# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Internal helpers for Zensical-aware, cross-page state sharing.

Not part of prodockit's public API - shared by prodockit.headings,
prodockit.citations, prodockit.glossary, and prodockit.bibliography, all of
which face the same problem: Zensical builds each page with its own fresh
``Markdown`` instance, so a plain per-instance default registry can never
see another page's entries. ``nav_pages``/``preseed_attr_from_nav``/
``preseed_heading_ids_from_nav``/``find_page_with_marker``/
``prescan_bibliography`` additionally address pages being built in a
single, one-shot pass - and, under ``zensical build``, not necessarily all
within one shared Python context at all (see prodockit-extensions#54): a
reference to a page this context never rendered can't resolve without
pre-scanning ahead of time.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

from markdown import Markdown
from markdown.extensions.toc import unique

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


class _HeadingPreseedable(Protocol):
    def preseed(
        self, source: str, id: str, level: int, text: str, number: str | None = None
    ) -> None: ...


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


# An h1 underline is one or more "=" (a "-" underline is a setext *h2*),
# optionally trailing whitespace, indented no more than 3 spaces - 4 or more
# makes it an indented code block instead. Confirmed directly against the
# real renderer: a single "=" is enough, and trailing spaces are fine.
_SETEXT_H1_UNDERLINE_RE = re.compile(r"^ {0,3}=+[ \t]*$")
_ATX_H1_RE = re.compile(r"^#\s+\S")
_ANY_ATX_HEADING_RE = re.compile(r"^#{1,6}\s")


def _is_numbered_atx_h1(line: str) -> bool:
    """True for a ``# Heading`` line that isn't tagged ``{.unnumbered}``."""
    return bool(_ATX_H1_RE.match(line)) and ".unnumbered" not in line


def _is_numbered_setext_h1_underline(
    line: str, text_line: str, *, text_line_opens_a_block: bool
) -> bool:
    """True when `line` is a setext h1 underline genuinely heading
    `text_line` - the line immediately above it.

    Matching the real renderer's own rules, confirmed directly rather than
    assumed: the underline heads a *single* text line, so a two-line
    paragraph followed by ``=====`` is no heading at all
    (`text_line_opens_a_block` carries whether the line above `text_line`
    was blank); an underline split from its text by a blank line isn't one
    either; four spaces of indent makes both lines an indented code block;
    and ``attr_list`` puts a setext heading's own ``{: .unnumbered }`` on
    the text line rather than after the underline.
    """
    if not _SETEXT_H1_UNDERLINE_RE.match(line):
        return False
    return bool(
        text_line_opens_a_block
        and text_line.strip()
        and not text_line.startswith("    ")
        # An ATX heading has already counted itself; a "=====" line under it
        # is a paragraph to the renderer, not a second heading.
        and not _ANY_ATX_HEADING_RE.match(text_line)
        and ".unnumbered" not in text_line
    )


def _count_top_level_headings(text: str) -> int:
    """Counts top-level h1s in raw markdown text - both ``# ATX`` and
    ``Setext``/``=====`` styles - skipping fenced code blocks, HTML
    comments, and headings tagged ``{.unnumbered}``. Used by
    prescan_headings() to work out how many numbered h1s appear on a page
    before any page has actually been converted. Line-based rather than a
    single regex (unlike _strip_fences() above) since it also needs to track
    HTML comments, not just fences, in one pass.

    Setext support matters because nothing else in either pipeline
    distinguishes the two styles - Zensical's renderer and Pandoc both
    produce a real h1 either way - so missing them here silently
    desynchronised continuous chapter numbering: later pages' start counts
    came out short, duplicating a chapter number on the website and putting
    it one behind the PDF (see issue #106).

    Matching the real renderer's own rules, confirmed directly rather than
    assumed: the underline has to follow a *single* text line (a two-line
    paragraph followed by ``=====`` is no heading at all), that line has to
    open its own block (a blank line, or the start of the page, before it),
    and neither line may be indented into a code block. ``attr_list`` puts a
    setext heading's own ``{: .unnumbered }`` on the *text* line, not after
    the underline, so that's where it's checked.
    """
    count = 0
    in_fence = False
    in_comment = False
    # The previous line, and whether the line before *it* was blank - a
    # setext underline is only a heading if its text line stands alone.
    previous_line = ""
    line_before_previous_was_blank = True
    for line in text.splitlines():
        stripped = line.strip()
        if not in_comment and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = not in_fence
            previous_line, line_before_previous_was_blank = "", True
            continue
        if in_fence:
            previous_line, line_before_previous_was_blank = "", True
            continue
        if not in_comment and "<!--" in stripped:
            in_comment = True
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            previous_line, line_before_previous_was_blank = "", True
            continue
        if _is_numbered_atx_h1(line) or _is_numbered_setext_h1_underline(
            line, previous_line, text_line_opens_a_block=line_before_previous_was_blank
        ):
            count += 1
        line_before_previous_was_blank = not previous_line.strip()
        previous_line = line
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


_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_TRAILING_ATTR_RE = re.compile(r"\s*\{:\s*([^}]*?)\s*\}\s*$")
_INLINE_MARKUP_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)|[*_`~]")


def _strip_front_matter(text: str) -> str:
    """Drops a leading YAML front matter block, so its own ``---`` fences
    and keys can't be mistaken for content by a raw-text heading scan."""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip("\n") if len(parts) >= 3 else text


def _heading_display_text(raw: str) -> str:
    """Approximates the rendered text of a heading line - what
    ``HeadingsTreeprocessor`` sees via ``itertext()`` once Python-Markdown
    has parsed it - by unwrapping links and dropping emphasis/code markers.
    Best-effort: it only has to be good enough to slugify a heading that
    has no explicit ``{: #id }`` of its own."""
    return _INLINE_MARKUP_RE.sub(lambda m: m.group(1) or "", raw).strip()


def _scan_page_headings(text: str) -> list[tuple[int, str, str | None, bool]]:
    """Returns ``(level, display_text, explicit_id, unnumbered)`` for every
    ATX heading in one page's raw markdown, in document order - skipping
    fenced code blocks and HTML comments, the same way
    _count_top_level_headings() does, so a heading shown as a literal
    example isn't mistaken for a real one."""
    headings: list[tuple[int, str, str | None, bool]] = []
    in_fence = False
    in_comment = False
    for line in _strip_front_matter(text).splitlines():
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
        match = _HEADING_LINE_RE.match(line)
        if match is None:
            continue
        level = len(match.group(1))
        rest = match.group(2)
        explicit_id: str | None = None
        unnumbered = False
        if attr_match := _TRAILING_ATTR_RE.search(rest):
            attrs = attr_match.group(1)
            if id_match := _ID_RE.search(attrs):
                explicit_id = id_match.group(1)
            unnumbered = ".unnumbered" in attrs
            rest = rest[: attr_match.start()]
        # A closed ATX heading ("## Title ##") - the trailing hashes aren't
        # part of the text.
        rest = re.sub(r"\s+#+\s*$", "", rest)
        headings.append((level, _heading_display_text(rest), explicit_id, unnumbered))
    return headings


def preseed_heading_ids_from_nav(
    registry: _HeadingPreseedable,
    appendix_attr: str,
    continuous: bool,
    slugify: Callable[[str, str], str],
    separator: str = "-",
) -> bool:
    """Pre-scans every page in the current Zensical build's nav for its
    headings' ids and section numbers, provisionally registering each one
    (via ``registry.preseed``) before any page has actually been converted -
    the same idea as ``preseed_attr_from_nav`` for citation/glossary
    definitions, applied to headings.

    Fixes prodockit-extensions#54: a ``\\ref{id}`` pointing at a heading on
    another page can only resolve if that page's own real registration is
    visible from the rendering context resolving the reference. Under
    ``zensical build`` that isn't guaranteed - a page rendered in a
    different process/interpreter never populated *this* context's shared
    registry, so the reference silently fell back to ``??`` for every id
    defined on such a page (reported on Linux CI for the first nav page
    specifically, while ids from later pages resolved fine). Pre-scanning
    every nav page's raw text up front makes resolution independent of
    which pages this particular context happens to render.

    Numbers mirror ``HeadingsTreeprocessor``'s own computation exactly
    (skipped levels backfilled rather than left at 0, ``.unnumbered``
    headings given an id but no number and no counter position, and - when
    `continuous` - h1 numbering carried across pages in nav order with
    ``appendix_attr``-flagged pages lettered instead). A real registration
    always supersedes what's preseeded here, so a page this context *does*
    render is unaffected.

    Returns True if the scan actually ran. Does nothing and returns False
    outside a Zensical build (mirrors nav_pages()) - so a caller that only
    wants to do this once can tell "already done" apart from "not
    applicable yet", and retry on a later page rather than latching a
    no-op.
    """
    located = nav_pages()
    if located is None:
        return False
    docs_dir, pages = located

    start_counts: dict[str, int] = {}
    appendix_letters: dict[str, str] = {}
    if continuous:
        prescanned = prescan_headings(appendix_attr)
        if prescanned is not None:
            start_counts, appendix_letters = prescanned

    for rel_path in pages:
        try:
            text = (Path(docs_dir) / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        appendix_letter = appendix_letters.get(rel_path)
        counters = [start_counts.get(rel_path, 0), 0, 0, 0, 0, 0]
        seen_ids: set[str] = set()
        for level, text_content, explicit_id, unnumbered in _scan_page_headings(text):
            heading_id = explicit_id or unique(slugify(text_content, separator), seen_ids)
            seen_ids.add(heading_id)
            if unnumbered:
                number = None
            else:
                for shallower in range(level - 1):
                    if counters[shallower] == 0:
                        counters[shallower] = 1
                counters[level - 1] += 1
                for deeper in range(level, 6):
                    counters[deeper] = 0
                first = appendix_letter if appendix_letter is not None else str(counters[0])
                number = ".".join([first] + [str(c) for c in counters[1:level]])
            registry.preseed(
                source=rel_path,
                id=heading_id,
                level=level,
                text=text_content,
                number=number,
            )
    return True


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

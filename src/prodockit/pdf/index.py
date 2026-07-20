# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""A back-of-book style index, PDF-only: an alphabetised list of terms
with the page number(s) they appear on, generated automatically from
`\\index{Term}` markers scattered through the document.

Unlike prodockit.headings/refs/citations/glossary - all "collect entries
the author writes explicitly, in one place" - an index term's own page
number can only be known *after* WeasyPrint has laid the PDF out, not
while still preprocessing Markdown/HTML. This needs a real two-pass
build: render once (with each `.index` occurrence carrying a unique,
near-invisible text marker), inspect that first-pass PDF with PyMuPDF to
find which page each marker landed on, then render again with the real
generated index content substituted in.

Confirmed directly, before settling on this design: WeasyPrint does
support CSS `target-counter()` (a single-pass alternative - no PyMuPDF,
no second render), but it can't deduplicate a term mentioned twice on
the same page (Python-side code has no way to know two markers share a
page without already knowing layout) - accepted as a real limitation and
deliberately not used here in favour of a genuinely clean, deduplicated
index. Also confirmed directly: a `font-size: 0` marker is dropped from
the rendered PDF's own text layer entirely (nothing for PyMuPDF to find),
but a merely tiny non-zero size (`0.1pt`) survives and is reliably
findable, while remaining visually imperceptible.

Because the index is always placed at the very end of the document (the
standard back-of-book convention, and the only position where growing or
shrinking its own content can't retroactively shift the page numbers
already recorded for every earlier marker), the two passes are exactly
two - never an iterative "rebuild until stable" loop.

**Hierarchical entries**: `\\index{Parent!Child!Grandchild}` (see
`prodockit.index`) builds a nested tree, up to three levels deep in
practice, rendered with a fixed indent step per level - see
`build_index_entries()`/`render_index_content()`.

**Code-styled entries**: `\\index{`Term`}`/`\\index{Parent!`Term`}` (see
`prodockit.index`) render that entry's own text in a real `<code>`
element in the generated index, matching how it displays inline in the
prose itself.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

#: The class an author writes inline - see this module's own docstring.
INDEX_TERM_CLASS = "index"

#: Marks the trigger heading build_pdf() inserts at the very end of the
#: document - the same "magic heading text" convention prodockit.pdf.lua
#: already uses for the Table of Contents.
DEFAULT_INDEX_TITLE = "Index"

#: Deepest nesting level `prodockit.pdf.css` defines its own indent step
#: for (`div.prodockit-index-level-3`) - render_index_content() clamps to
#: this so a term nested deeper still gets the deepest available indent
#: instead of silently rendering flush with the top level.
MAX_RENDERED_INDEX_LEVEL = 3

#: The div build_pdf()'s own trigger heading is followed by - empty on the
#: first pass, replaced with the real generated index content for the
#: second. Also this module's own `id`, so it's trivially find-and-
#: replaceable in the concatenated HTML between passes.
INDEX_CONTENT_ID = "prodockit-index-content"

_MARKER_PATTERN = re.compile(r"⟦prodockit-index-(\d+)⟧")


def _marker_text(occurrence_number: int) -> str:
    """The literal (near-invisible, but real) text inserted right after
    each `.index` occurrence - `⟦`/`⟧` (mathematical white
    square brackets) chosen only because real prose is vanishingly
    unlikely to contain them, not for any semantic meaning."""
    return f"⟦prodockit-index-{occurrence_number}⟧"


def mark_index_terms(html: str) -> tuple[str, list[str], list[bool]]:
    """Finds every `<span class="index">` in `html` (i.e. every
    `\\index{Term}` an author wrote) and inserts a unique, sequentially
    numbered marker (see `_marker_text`) directly after each one - a
    `font-size: 0.1pt` span, findable by `extract_term_pages()` in the
    finished PDF's own text layer while remaining visually imperceptible
    (confirmed directly: `font-size: 0` is dropped from the PDF's text
    layer entirely, unlike a merely tiny non-zero size).

    Returns `(html_with_markers, terms, code_flags)`, where `terms[i]` is
    the term's full path for marker number `i + 1` - a flat `\\index{Term}`
    gives `"Term"`, a hierarchical `\\index{Parent!Child}` (see
    `prodockit.index`) gives `"Parent!Child"` (its own `data-index-term`
    attribute, not the span's visible text, which for that case is just
    `"Child"`) - and `code_flags[i]` is whether that occurrence was a
    code-styled `\\index{`Term`}` (its own `data-index-code` attribute).
    Every occurrence recorded separately, even repeats of the same term,
    since which page each one lands on is still unknown at this point.
    """
    soup = BeautifulSoup(html, "html.parser")
    terms: list[str] = []
    code_flags: list[bool] = []
    for span in soup.find_all("span", class_=INDEX_TERM_CLASS):
        terms.append(span.get("data-index-term") or span.get_text())
        code_flags.append(span.get("data-index-code") == "true")
        marker = soup.new_tag("span")
        marker["style"] = "font-size: 0.1pt !important; color: transparent !important;"
        marker.string = _marker_text(len(terms))
        span.insert_after(marker)
    return str(soup), terms, code_flags


def extract_term_pages(pdf_path: str, occurrence_count: int) -> dict[int, int | None]:
    """Opens the first-pass PDF at `pdf_path` and finds which page each
    marker `mark_index_terms()` inserted landed on, by searching every
    page's own text layer for that marker's own (near-invisible) text -
    confirmed directly to work even for two occurrences of the same term
    landing on the same page (both correctly resolve to that one page).

    Returns `{occurrence_number: page_number}` (1-indexed, matching the
    numbers `mark_index_terms()` assigned) for every occurrence found;
    `None` for one that mysteriously isn't (shouldn't happen - the marker
    is written by this same module - but silently dropping the entry
    would understate a term's own page list rather than surfacing a
    genuine bug in whatever changed the HTML between the two functions).

    Requires `pymupdf` (an optional dependency - see this module's own
    docstring for why it isn't a hard `prodockit` dependency); raises
    `ModuleNotFoundError` with a clear message if it isn't installed.
    """
    try:
        import pymupdf
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "prodockit.pdf.index requires pymupdf - install it with "
            "'pip install prodockit[index]' (or plain 'pip install pymupdf') "
            "to use pdf_include_index/include_index."
        ) from exc

    # pymupdf ships a `py.typed` marker but its own members are still
    # effectively untyped (Any) - the type: ignore comments below are for
    # that gap, not a missing-stub situation `ignore_missing_imports` would
    # otherwise cover.
    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    try:
        pages: dict[int, int | None] = dict.fromkeys(range(1, occurrence_count + 1), None)
        for page_number, page in enumerate(doc, start=1):  # type: ignore[arg-type,var-annotated]
            for match in _MARKER_PATTERN.finditer(page.get_text()):
                occurrence_number = int(match.group(1))
                if occurrence_number in pages:
                    pages[occurrence_number] = page_number
        return pages
    finally:
        doc.close()  # type: ignore[no-untyped-call]


@dataclass
class IndexEntry:
    """One node in the tree `build_index_entries()` returns - `display` is
    this node's own text (a `\\index{Parent!Child}`'s `Child` segment, not
    the full path); `pages` are this exact node's own resolved page
    numbers (empty for a pure grouping node with no page of its own - see
    `render_index_content()`'s own docstring for a real example);
    `children`, keyed the same case-insensitively-normalised way as the
    top-level dict `build_index_entries()` returns, are this node's own
    sub-entries, already sorted (see `_sort_key()`); `code` is whether
    this entry came from a code-styled `\\index{`Term`}` marker - if any
    occurrence of this exact entry was code-styled, the whole merged
    entry renders that way (see `render_index_content()`)."""

    display: str
    pages: list[int]
    children: dict[str, IndexEntry]
    code: bool = False


#: Strips leading characters that aren't a letter or digit, so a
#: technical term like "--set-upstream option (git push)" alphabetises
#: (and letter-groups) under "S", not under a separate "symbols" section -
#: standard back-of-book index practice, confirmed directly to match how
#: e.g. an O'Reilly book's own index treats command-line options.
_SORT_KEY_STRIP_RE = re.compile(r"^[^a-zA-Z0-9]+")


def _sort_key(display: str) -> str:
    stripped = _SORT_KEY_STRIP_RE.sub("", display)
    return (stripped or display).lower()


def format_pages(pages: list[int]) -> str:
    """Formats a term's own resolved pages for display: a run of
    consecutive pages collapses into an en-dash range (`"67–70"`), while
    non-consecutive pages/ranges are comma-separated (`"64, 175"`) -
    standard back-of-book index convention. `pages` needn't already be
    sorted or deduplicated; this does both. Returns `""` for an empty
    list (a pure grouping node with no page of its own)."""
    unique_sorted = sorted(set(pages))
    if not unique_sorted:
        return ""
    ranges: list[str] = []
    start = end = unique_sorted[0]
    for page in unique_sorted[1:]:
        if page == end + 1:
            end = page
            continue
        ranges.append(str(start) if start == end else f"{start}–{end}")
        start = end = page
    ranges.append(str(start) if start == end else f"{start}–{end}")
    return ", ".join(ranges)


def build_index_entries(
    terms: list[str],
    occurrence_pages: dict[int, int | None],
    code_flags: list[bool] | None = None,
) -> dict[str, IndexEntry]:
    """Groups `terms` (as returned by `mark_index_terms()`, one entry per
    occurrence - a flat `"Term"` or a hierarchical `"Parent!Child!
    Grandchild"`, up to three levels deep in practice) into a nested tree,
    each level keyed by its own case-insensitively-normalised text and
    alphabetised (`_sort_key()`, so e.g. a leading `--` doesn't send a
    command-line option to its own separate section) - occurrence number
    `i + 1` in `terms[i]` looks up its own page via `occurrence_pages` (as
    returned by `extract_term_pages()`), attached to the *last* segment's
    own node (a new intermediate/parent segment gets no page of its own
    from this occurrence - see `IndexEntry`). `code_flags[i]` (as returned
    by `mark_index_terms()`; defaults to all `False` if omitted) marks
    that occurrence's own leaf node as code-styled if `True` - if any
    occurrence of an entry is code-styled, the merged entry renders that
    way (see `render_index_content()`).

    The *first* occurrence's own original casing is kept for display at
    each level (e.g. "Widget" and "widget" merge into one "Widget" entry,
    not two) - a deliberate simplification, not true linguistic
    normalisation (a plural "widgets" is still a separate entry from
    singular "widget"). An occurrence with no resolved page at all
    (shouldn't happen - see `extract_term_pages()`) is dropped rather than
    shown with no pages - though an intermediate grouping node it would
    have created (e.g. "Parent" in "Parent!Child") still exists if some
    *other* occurrence's own path passes through it.
    """
    root: dict[str, IndexEntry] = {}
    for i, path in enumerate(terms):
        page = occurrence_pages.get(i + 1)
        if page is None:
            continue
        segments = [segment.strip() for segment in path.split("!") if segment.strip()]
        if not segments:
            continue
        level = root
        node = None
        for segment in segments:
            node = level.setdefault(segment.lower(), IndexEntry(segment, [], {}))
            level = node.children
        assert node is not None  # segments is non-empty, so the loop above always runs
        if page not in node.pages:
            node.pages.append(page)
        if code_flags is not None and code_flags[i]:
            node.code = True

    def sort_tree(level: dict[str, IndexEntry]) -> dict[str, IndexEntry]:
        sorted_level: dict[str, IndexEntry] = {}
        for key in sorted(level, key=lambda k: _sort_key(level[k].display)):
            entry = level[key]
            entry.pages.sort()
            sorted_level[key] = IndexEntry(
                entry.display, entry.pages, sort_tree(entry.children), entry.code
            )
        return sorted_level

    return sort_tree(root)


def render_index_content(entries: dict[str, IndexEntry], level: int = 1) -> str:
    """Renders `build_index_entries()`'s own nested tree as the HTML that
    replaces the empty `id="prodockit-index-content"` placeholder div for
    the second pass - a traditional back-of-book layout: a letter heading
    (`<h2 class="prodockit-index-letter">`) per first letter *at the top
    level only*, then one `<div class="prodockit-index-entry
    prodockit-index-level-N">` per entry at every level, `N` (1-3, clamped
    at `MAX_RENDERED_INDEX_LEVEL` for anything nested deeper - `prodockit.
    pdf.css` only defines an indent step up to level 3) driving that
    entry's own indentation in `prodockit.pdf.css`.
    A `<div>`, not a `<p>` - confirmed directly, Pandoc's native `Para` AST
    node has no attribute field at all, so a plain `<p class="...">` here
    (this content is inserted raw in `build_pdf()`, never passed through
    `prodockit.pdf.html`'s own general `<p>`-with-a-class-or-id -> `<div>`
    retagging, since it isn't a real page) would silently lose its class -
    and with it, every level's own indentation - by the time Pandoc's
    reader is done with it.
    `entries` is already alphabetised (`build_index_entries()`'s own
    `_sort_key()` order), so a new letter group starts exactly when a
    top-level entry's own sort key first letter differs from the previous
    one, with no separate re-sorting needed here.

    A code-styled entry (`entry.code` - see `IndexEntry`) wraps its own
    `display` text in a real `<code>` element, before the page list is
    appended - no separate CSS rule needed for this to pick up the
    document-wide monospace `code {}` styling `prodockit.pdf.css` already
    defines.

    A node with sub-entries but no page of its own (e.g. "files" grouping
    "adding"/"modified" beneath "staging area" with no "files, N" page
    itself) renders with no trailing page list at all, matching a real
    printed index's own use of a bare category label part-way through a
    hierarchy.

    Each letter heading carries `unnumbered unlisted` (the same convention
    `build_pdf()` already uses for its own Table of Contents/Index page
    titles) - it's a typographic marker, not a real document section, so it
    must not receive a chapter/section number from the heading-numbering
    Lua filter, or an entry in the Table of Contents.
    """
    if not entries:
        return ""
    lines = []
    current_letter = None
    for entry in entries.values():
        if level == 1:
            letter = (_sort_key(entry.display)[:1] or entry.display[:1]).upper()
            if letter != current_letter:
                current_letter = letter
                lines.append(
                    '<h2 class="prodockit-index-letter unnumbered unlisted">'
                    f"{html.escape(letter)}</h2>"
                )
        escaped_display = html.escape(entry.display)
        text = f"<code>{escaped_display}</code>" if entry.code else escaped_display
        page_list = format_pages(entry.pages)
        if page_list:
            text += f", {page_list}"
        css_level = min(level, MAX_RENDERED_INDEX_LEVEL)
        div_class = f"prodockit-index-entry prodockit-index-level-{css_level}"
        lines.append(f'<div class="{div_class}">{text}</div>')
        if entry.children:
            lines.append(render_index_content(entry.children, level + 1))
    return "\n".join(lines)

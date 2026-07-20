# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""A back-of-book style index, PDF-only: an alphabetised list of terms
with the page number(s) they appear on, generated automatically from
`[Term]{.index}` markers scattered through the document.

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
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

#: The class an author writes inline - see this module's own docstring.
INDEX_TERM_CLASS = "index"

#: Marks the trigger heading build_pdf() inserts at the very end of the
#: document - the same "magic heading text" convention prodockit.pdf.lua
#: already uses for the Table of Contents.
DEFAULT_INDEX_TITLE = "Index"

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


def mark_index_terms(html: str) -> tuple[str, list[str]]:
    """Finds every `<span class="index">` in `html` (i.e. every
    `[Term]{.index}` an author wrote) and inserts a unique, sequentially
    numbered marker (see `_marker_text`) directly after each one - a
    `font-size: 0.1pt` span, findable by `extract_term_pages()` in the
    finished PDF's own text layer while remaining visually imperceptible
    (confirmed directly: `font-size: 0` is dropped from the PDF's text
    layer entirely, unlike a merely tiny non-zero size).

    Returns `(html_with_markers, terms)`, where `terms[i]` is the
    (unnormalised, exactly-as-written) term text for marker number
    `i + 1` - every occurrence recorded separately, even repeats of the
    same term, since which page each one lands on is still unknown at
    this point.
    """
    soup = BeautifulSoup(html, "html.parser")
    terms: list[str] = []
    for span in soup.find_all("span", class_=INDEX_TERM_CLASS):
        terms.append(span.get_text())
        marker = soup.new_tag("span")
        marker["style"] = "font-size: 0.1pt !important; color: transparent !important;"
        marker.string = _marker_text(len(terms))
        span.insert_after(marker)
    return str(soup), terms


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


def build_index_entries(
    terms: list[str], occurrence_pages: dict[int, int | None]
) -> dict[str, list[int]]:
    """Groups `terms` (as returned by `mark_index_terms()`, one entry per
    occurrence) by their own case-insensitively-normalised text, into
    `{term: [sorted, deduplicated page numbers]}` - occurrence number
    `i + 1` in `terms[i]` looks up its own page via `occurrence_pages`
    (as returned by `extract_term_pages()`).

    The *first* occurrence's own original casing is kept for display
    (e.g. "Widget" and "widget" merge into one "Widget" entry, not two) -
    a deliberate simplification, not true linguistic normalisation (a
    plural "widgets" is still a separate entry from singular "widget").
    Entries with no resolved page at all (shouldn't happen - see
    `extract_term_pages()`) are dropped rather than shown with no pages.
    """
    entries: dict[str, list[int]] = {}
    display_case: dict[str, str] = {}
    for i, term in enumerate(terms):
        occurrence_number = i + 1
        page = occurrence_pages.get(occurrence_number)
        if page is None:
            continue
        key = term.strip().lower()
        display_case.setdefault(key, term.strip())
        pages_for_term = entries.setdefault(key, [])
        if page not in pages_for_term:
            pages_for_term.append(page)

    return {
        display_case[key]: sorted(pages)
        for key, pages in sorted(entries.items(), key=lambda item: item[0])
    }


def render_index_content(entries: dict[str, list[int]]) -> str:
    """Renders `build_index_entries()`'s own output as the HTML that
    replaces the empty `id="prodockit-index-content"` placeholder div for
    the second pass - a traditional back-of-book layout, grouped under a
    letter heading (`<h2 class="prodockit-index-letter">`) per first
    letter, with one `<p class="prodockit-index-entry">Term, pages</p>`
    per term - `entries` is already alphabetised (dict insertion order, as
    `build_index_entries()` already sorted it), so a new letter group
    starts exactly when an entry's first letter differs from the previous
    one, with no separate re-sorting needed here.

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
    for term, pages in entries.items():
        letter = term[0].upper()
        if letter != current_letter:
            current_letter = letter
            lines.append(
                '<h2 class="prodockit-index-letter unnumbered unlisted">'
                f"{html.escape(letter)}</h2>"
            )
        page_list = ", ".join(str(page) for page in pages)
        lines.append(f'<p class="prodockit-index-entry">{html.escape(term)}, {page_list}</p>')
    return "\n".join(lines)

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Rotates a landscape "insert" page (see ``<div class="prodockit-table-rotated">``
in :mod:`prodockit.pdf.css`) for correct anticlockwise on-page display, after
WeasyPrint has already written the PDF.

WeasyPrint lays out ``prodockit-table-rotated``'s content unrotated, on its own
landscape-sized page (via a named CSS ``@page``) - normal pagination, and
thead's own repeat-on-every-page behaviour, both apply exactly as they would
on any other table, which a CSS ``transform: rotate()`` was confirmed
directly *not* to preserve (it clips to a single page instead of splitting,
and pushes the heading row and first few rows off-page entirely). What's
left is telling a PDF viewer/printer to *display* that finished page rotated
- a PDF page's own ``/Rotate`` entry, a pure display flag that doesn't move
or re-flow any content, unlike a CSS transform.
"""

from __future__ import annotations

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

# A PDF's own /Rotate value is a clockwise display angle (per the PDF
# spec) - 270 degrees clockwise here displays/prints as content rotated 90
# degrees anticlockwise, confirmed directly by rendering both 90 and 270
# and comparing reading direction against prodockit-table-rotated's own
# unrotated (landscape) layout. Also the `double_sided` odd-page value - an
# odd (recto, right-hand) page's spine is on its left, the same side a
# single-sided document's spine is always on.
_ROTATE_DEGREES_ODD = 270

# `double_sided` even-page (verso, left-hand) value: the spine is on its
# *right* instead, the opposite physical side from a recto page, so a
# landscape insert has to rotate the other way to keep its own top edge
# facing the fore-edge rather than the spine.
_ROTATE_DEGREES_EVEN = 90

# Loose float tolerance for comparing page dimensions, in points - well
# under a hairline, just enough to absorb floating-point rounding from
# whatever produced the PDF.
_SIZE_TOLERANCE = 0.5


def rotate_landscape_pages(pdf_path: str, *, double_sided: bool = False) -> int:
    """Finds every page in `pdf_path` whose own page box is the width/height
    swap of the first page's - i.e. a `prodockit-table-rotated` landscape
    insert amid an otherwise-portrait (or otherwise-landscape) document -
    and sets that page's `/Rotate` to display/print it rotated 90 degrees
    anticlockwise. Returns how many pages were rotated; leaves `pdf_path`
    completely untouched (not even re-written) if none matched, e.g. a
    build with no `prodockit-table-rotated` content at all.

    `double_sided` (default off, matching a single-sided `build_pdf()`)
    alternates the rotation direction by each matched page's own final
    1-indexed position in the document: 270 degrees (anticlockwise) for an
    odd/recto page, 90 degrees (clockwise) for an even/verso one - the
    spine sits on the opposite physical side for a verso vs. a recto page,
    so the rotation has to compensate to keep landscape content's own top
    edge facing the fore-edge rather than the spine either way. Off, every
    matched page always rotates 270 degrees, exactly as before this
    parameter existed.

    A single-page document, or one whose first page is itself square,
    can't meaningfully be compared this way and is always left alone (0
    pages rotated) - there's no "the rest of the document" shape to diverge
    from. Anything pypdf can't parse as a PDF at all is left alone too,
    returning 0 rather than raising - `build_pdf()` only ever calls this
    after `pandoc`/WeasyPrint has already reported success, so a genuinely
    unparseable file at this point isn't something rotating pages can fix
    anyway (a caller providing its own stand-in `pandoc` for testing, not a
    real WeasyPrint build, is the only case this is expected to matter for).
    """
    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) < 2:
            return 0

        first_box = reader.pages[0].mediabox
        first_width, first_height = float(first_box.width), float(first_box.height)
        if abs(first_width - first_height) < _SIZE_TOLERANCE:
            return 0

        writer = PdfWriter()
        rotated_count = 0
        for index, page in enumerate(reader.pages):
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            added_page = writer.add_page(page)
            is_swapped = (
                abs(width - first_height) < _SIZE_TOLERANCE
                and abs(height - first_width) < _SIZE_TOLERANCE
            )
            if is_swapped:
                page_number = index + 1
                degrees = (
                    _ROTATE_DEGREES_ODD
                    if not double_sided or page_number % 2 == 1
                    else _ROTATE_DEGREES_EVEN
                )
                added_page.rotate(degrees)
                rotated_count += 1

        if rotated_count:
            with open(pdf_path, "wb") as f:
                writer.write(f)
        return rotated_count
    except PyPdfError:
        return 0

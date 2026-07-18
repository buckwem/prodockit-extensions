# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from prodockit.pdf.rotate import rotate_landscape_pages

# A4 in points, matching WeasyPrint's own default page size.
_PORTRAIT = (595.28, 841.89)
_LANDSCAPE = (841.89, 595.28)


def _write_pdf(path: Path, page_sizes: list[tuple[float, float]]) -> None:
    writer = PdfWriter()
    for width, height in page_sizes:
        writer.add_blank_page(width=width, height=height)
    with open(path, "wb") as f:
        writer.write(f)


def test_rotates_only_the_landscape_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    _write_pdf(pdf_path, [_PORTRAIT, _LANDSCAPE, _LANDSCAPE, _PORTRAIT])

    rotated_count = rotate_landscape_pages(str(pdf_path))

    assert rotated_count == 2
    reader = PdfReader(str(pdf_path))
    assert reader.pages[0].get("/Rotate") in (None, 0)
    assert reader.pages[1].rotation == 270
    assert reader.pages[2].rotation == 270
    assert reader.pages[3].get("/Rotate") in (None, 0)


def test_leaves_an_all_portrait_document_untouched(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    _write_pdf(pdf_path, [_PORTRAIT, _PORTRAIT, _PORTRAIT])
    original_bytes = pdf_path.read_bytes()

    rotated_count = rotate_landscape_pages(str(pdf_path))

    assert rotated_count == 0
    assert pdf_path.read_bytes() == original_bytes


def test_single_page_document_is_left_alone(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    _write_pdf(pdf_path, [_PORTRAIT])

    assert rotate_landscape_pages(str(pdf_path)) == 0


def test_square_first_page_is_left_alone(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    _write_pdf(pdf_path, [(600.0, 600.0), _LANDSCAPE])

    assert rotate_landscape_pages(str(pdf_path)) == 0


def test_a_page_matching_neither_orientation_is_left_alone(tmp_path: Path) -> None:
    """A page that's neither the first page's own shape nor its exact
    width/height swap (e.g. a custom-sized image page) shouldn't be
    mistaken for a prodockit-table-rotated landscape insert."""
    pdf_path = tmp_path / "doc.pdf"
    _write_pdf(pdf_path, [_PORTRAIT, (400.0, 300.0)])

    rotated_count = rotate_landscape_pages(str(pdf_path))

    assert rotated_count == 0
    reader = PdfReader(str(pdf_path))
    assert reader.pages[1].get("/Rotate") in (None, 0)

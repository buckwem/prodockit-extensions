# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
from pathlib import Path

import markdown
import pytest

from prodockit.tables import TableError, TablesExtension

REPO = Path(__file__).resolve().parents[1]
EXTRA_CSS = REPO / "docs" / "stylesheets" / "extra.css"

PLAIN_TABLE = "| Name | Description |\n|---|---|\n| a | b |\n"

PERCENT_TABLE = '| Name {: width="30%" } | Description | Date {: width="15%" } |\n|---|---|---|\n| a | b | c |\n'

FIXED_TABLE = '| Name {: width="120px" } | Description |\n|---|---|\n| a | b |\n'


def _css_defaults() -> dict[str, object]:
    """Whatever `build_css` needs, so a test can ask for a stylesheet
    without restating every typography option."""
    import inspect

    from prodockit.pdf.css import build_css

    out: dict[str, object] = {}
    for name, param in inspect.signature(build_css).parameters.items():
        if param.default is not inspect.Parameter.empty:
            out[name] = param.default
        elif name == "main_font":
            out[name] = "Inter"
        elif name == "mono_font":
            out[name] = "JetBrains Mono"
        elif name == "site_name":
            out[name] = "Doc"
        elif name == "page_size":
            out[name] = "A4"
        elif "margin" in name:
            out[name] = "2cm"
        elif "size" in name:
            out[name] = "9pt"
        elif "color" in name:
            out[name] = "#666"
        else:
            out[name] = False
    return out


def _convert(text: str) -> str:
    md = markdown.Markdown(extensions=["attr_list", TablesExtension()])
    return md.convert(text)


def test_website_tables_draw_a_theme_coloured_border_around_every_cell() -> None:
    """Merged headers expose the old row-only style immediately: their
    internal boundaries had no rule until the first body row (#524)."""
    css = EXTRA_CSS.read_text(encoding="utf-8")

    for selector in (
        ".md-typeset table:not([class]) th",
        ".md-typeset table:not([class]) td",
        ".md-typeset table.prodockit-table-sized th",
        ".md-typeset table.prodockit-table-sized td",
        ".md-typeset table.prodockit-table-compact th",
        ".md-typeset table.prodockit-table-compact td",
    ):
        assert selector in css
    assert "border-collapse: collapse;" in css
    assert "border: 0.05rem solid var(--md-typeset-table-color);" in css


def test_website_table_headers_use_a_five_percent_theme_aware_shaded_band() -> None:
    css = EXTRA_CSS.read_text(encoding="utf-8")

    for selector in (
        ".md-typeset table:not([class]) th",
        ".md-typeset table.prodockit-table-sized th",
        ".md-typeset table.prodockit-table-compact th",
    ):
        assert selector in css
    assert "background-color: rgba(var(--prodockit-table-shade-rgb), 0.05);" in css
    assert '--prodockit-table-shade-rgb: 255, 255, 255;' in css


def test_pdf_table_grid_matches_the_light_website_line_style() -> None:
    from prodockit.pdf.css import build_css

    css = build_css(**_css_defaults())
    table_css = css.split("TABLE LAYOUT")[1].split("ADMONITIONS & TABS LAYOUT")[0]

    assert table_css.count("border: 0.05rem solid rgba(0, 0, 0, 0.12) !important;") == 2
    assert "table th { background-color: rgba(0, 0, 0, 0.05) !important;" in table_css
    assert "border: 0.5pt solid #555555" not in table_css


def test_pdf_merged_cells_render_with_every_boundary_visible() -> None:
    """Check the laid-out grid, not only its CSS: collapsed borders share
    their width between adjacent cells, including rowspan/colspan edges."""
    weasyprint = pytest.importorskip("weasyprint")

    from prodockit.pdf.css import build_css

    css = build_css(**_css_defaults())
    html = _convert(TWO_ROW_HEADER)
    page = weasyprint.HTML(
        string=f"<!DOCTYPE html><html><head><style>{css}</style></head><body>{html}</body></html>"
    ).render().pages[0]
    cells: list[object] = []
    seen: set[int] = set()

    def walk(box: object) -> None:
        element = getattr(box, "element", None)
        if getattr(box, "element_tag", None) in {"th", "td"} and id(element) not in seen:
            seen.add(id(element))
            cells.append(box)
        for child in getattr(box, "children", []):
            walk(child)

    walk(page._page_box)

    assert len(cells) == 9
    assert all(
        min(
            cell.border_top_width,
            cell.border_right_width,
            cell.border_bottom_width,
            cell.border_left_width,
        )
        > 0
        for cell in cells
    )
    assert all("/ 0.12" in str(cell.style["border_right_color"]) for cell in cells)


def test_table_without_any_width_is_left_untouched() -> None:
    html = _convert(PLAIN_TABLE)
    assert "<colgroup>" not in html
    assert "prodockit-table-sized" not in html


def test_percentage_width_becomes_a_colgroup_entry() -> None:
    html = _convert(PERCENT_TABLE)
    assert (
        '<colgroup><col style="width: 30%;" /><col /><col style="width: 15%;" /></colgroup>'
        in html
    )


def test_fixed_width_becomes_a_colgroup_entry_the_same_way() -> None:
    html = _convert(FIXED_TABLE)
    assert '<colgroup><col style="width: 120px;" /><col /></colgroup>' in html


def test_width_attribute_is_stripped_from_the_header_cell() -> None:
    html = _convert(PERCENT_TABLE)
    assert "width=" not in html.split("</colgroup>")[1]


def test_sized_table_gets_the_marker_class() -> None:
    html = _convert(PERCENT_TABLE)
    assert '<table class="prodockit-table-sized">' in html


def test_colgroup_is_the_tables_first_child() -> None:
    html = _convert(PERCENT_TABLE)
    assert html.index("<colgroup>") < html.index("<thead>")


def test_table_nested_inside_an_admonition_is_still_sized() -> None:
    """TableWidthTreeprocessor walks root.iter("table"), which recurses
    into any ancestor regardless of nesting - confirmed directly for the
    realistic case of a table inside an admonition, since the docs use
    these together often."""
    md = markdown.Markdown(extensions=["attr_list", "admonition", TablesExtension()])
    indented_table = (
        '    | Name {: width="30%" } | Description | Date {: width="15%" } |\n'
        "    |---|---|---|\n"
        "    | a | b | c |\n"
    )
    html = md.convert(f"!!! note\n\n{indented_table}")
    assert (
        '<colgroup><col style="width: 30%;" /><col /><col style="width: 15%;" /></colgroup>'
        in html
    )
    assert '<table class="prodockit-table-sized">' in html


def test_multiple_tables_are_each_sized_independently() -> None:
    """Two tables in one document, one with widths and one without -
    confirmed directly the unwidthed table is left alone while the
    widthed one still gets its own colgroup, with no cross-contamination
    between them."""
    html = _convert(PLAIN_TABLE + "\n" + PERCENT_TABLE)
    assert html.count("<colgroup>") == 1
    assert html.count('<table class="prodockit-table-sized">') == 1
    assert html.count("<table>") == 1


def test_two_differently_widthed_tables_each_get_their_own_colgroup() -> None:
    html = _convert(PERCENT_TABLE + "\n" + FIXED_TABLE)
    assert (
        '<colgroup><col style="width: 30%;" /><col /><col style="width: 15%;" /></colgroup>'
        in html
    )
    assert '<colgroup><col style="width: 120px;" /><col /></colgroup>' in html
    assert html.count('<table class="prodockit-table-sized">') == 2


def test_auto_enables_the_tables_extension() -> None:
    md = markdown.Markdown(extensions=["attr_list", TablesExtension()])
    assert "table" in md.parser.blockprocessors
    html = md.convert(PLAIN_TABLE)
    assert "<table>" in html


def test_does_not_duplicate_the_tables_extension_if_already_enabled() -> None:
    md = markdown.Markdown(extensions=["tables", "attr_list", TablesExtension()])
    html = md.convert(PERCENT_TABLE)
    assert html.count("<table") == 1


# ---------------------------------------------------------------------------
# Dense tables: `{: .compact }`
# ---------------------------------------------------------------------------

COMPACT_TABLE = "| Name {: .compact } | Description |\n|---|---|\n| a | b |\n"


def test_compact_marker_moves_from_the_cell_to_the_table() -> None:
    """`{: .compact }` describes the table, not the cell it is written on.

    It has to be written on a cell because that is the only thing
    `attr_list` can reach in a Markdown table - there is no syntax for
    attaching a class to the table itself. Left on the cell it would
    style that one cell as well (prodockit-extensions#489).
    """
    html = _convert(COMPACT_TABLE)

    assert 'class="prodockit-table-compact"' in html
    assert "<th>Name</th>" in html, f"marker left on the cell: {html}"


def test_compact_is_read_from_any_header_cell() -> None:
    """An author marks the column they happen to be looking at."""
    html = _convert("| Name | Description {: .compact } |\n|---|---|\n| a | b |\n")

    assert 'class="prodockit-table-compact"' in html
    assert "<th>Description</th>" in html


def test_a_table_without_the_marker_is_not_compact() -> None:
    """The dense style is opt-in: a table that is comfortable at its
    default has to stay that way, and a table changing shape as a column
    is added is exactly the surprise this avoids."""
    assert "prodockit-table-compact" not in _convert(PLAIN_TABLE)
    assert "prodockit-table-compact" not in _convert(PERCENT_TABLE)


def test_compact_and_width_can_be_used_together() -> None:
    """They answer different questions - how wide this column is, and how
    tightly every cell is set - so a table may need both."""
    html = _convert('| Name {: width="30%" .compact } | Description |\n|---|---|\n| a | b |\n')

    assert "prodockit-table-compact" in html
    assert "prodockit-table-sized" in html
    assert "<colgroup>" in html
    # And neither marker is left behind on the cell.
    assert "compact" not in html.split("<tbody>")[0].split("<colgroup>")[1]


def test_compact_narrows_a_wide_table_in_the_pdf() -> None:
    """Marked compact, a table has to actually come out narrower.

    The website's problem is the theme's own `min-width: 5rem` on every
    header cell; the PDF has no such minimum, so only the padding is at
    stake there - and a class that changed nothing in one of the two
    outputs would be the silent half-failure this project keeps meeting
    (prodockit-extensions#489).
    """
    import inspect

    import pytest

    weasyprint = pytest.importorskip("weasyprint")
    from prodockit.pdf.css import build_css

    sig = inspect.signature(build_css)
    args = {
        n: (
            p.default
            if p.default is not inspect._empty
            else (
                "Inter"
                if n == "main_font"
                else "JetBrains Mono"
                if n == "mono_font"
                else "Doc"
                if n == "site_name"
                else "A4"
                if n == "page_size"
                else "2cm"
                if "margin" in n
                else "9pt"
                if "size" in n
                else "#666"
                if "color" in n
                else False
            )
        )
        for n, p in sig.parameters.items()
    }
    css = build_css(**args)

    heads = ["Threat Target", "Attack Technique", "Threat Agent"] + [
        f"Head {i}" for i in range(1, 10)
    ]
    body = "\n".join(
        "| " + " | ".join(f"c{i}" for i in range(len(heads))) + " |" for _ in range(3)
    )

    def width(marker: str) -> float:
        cells = list(heads)
        if marker:
            cells[0] += " " + marker
        text = (
            "| " + " | ".join(cells) + " |\n"
            "| " + " | ".join("---" for _ in heads) + " |\n" + body + "\n"
        )
        page = weasyprint.HTML(
            string=f"<!DOCTYPE html><html><head><meta charset=utf-8>"
            f"<style>{css}</style></head><body>{_convert(text)}</body></html>"
        ).render().pages[0]
        widest = [0.0]

        def walk(box: object) -> None:
            if getattr(box, "element_tag", "") == "table":
                widest[0] = max(widest[0], float(box.width))  # type: ignore[attr-defined]
            for child in getattr(box, "children", []):
                walk(child)

        walk(page._page_box)
        return widest[0]

    plain, compact = width(""), width("{: .compact }")
    assert compact < plain - 50, f"compact saved only {plain - compact:.0f}px: {plain}, {compact}"


# ---------------------------------------------------------------------------
# Headers of more than one row, merged cells, rotated headings (#474)
# ---------------------------------------------------------------------------

TWO_ROW_HEADER = (
    "| Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |\n"
    "|---|---|---|---|\n"
    "| | Before {: .header } | After | |\n"
    "| Widget | 1 | 2 | ok |\n"
)


def test_shading_can_be_disabled_on_one_merged_header_cell() -> None:
    html = _convert(
        '| Target {: rowspan=2 shade="off" } | Measured {: colspan=2 } | |\n'
        '|---|---|---|\n'
        '| | Before {: .header } | After |\n'
        '| Widget | 1 | 2 |\n'
    )
    head = html.split("<tbody>")[0]

    assert (
        '<th class="prodockit-table-cell-unshaded" rowspan="2">Target</th>' in head
    )
    assert head.count("</th>") == 4, "shade handling must not restore span placeholders"
    assert "shade=" not in html


def test_a_percentage_can_shade_a_specific_merged_cell() -> None:
    html = _convert(
        '| Group {: colspan=2 shade="7.5%" } | | Note |\n'
        '|---|---|---|\n'
        '| a | b | c |\n'
    )

    assert (
        'class="prodockit-table-cell-shaded" colspan="2" '
        'style="--prodockit-table-cell-shade: 7.5%;">Group</th>' in html
    )
    assert "shade=" not in html


def test_a_percentage_can_turn_shading_on_for_a_body_cell() -> None:
    html = _convert('| A | B |\n|---|---|\n| highlighted {: shade="9%" } | plain |\n')

    assert (
        '<td class="prodockit-table-cell-shaded" '
        'style="--prodockit-table-cell-shade: 9%;">highlighted</td>' in html
    )


def test_pdf_cell_shading_works_on_merged_and_unmerged_cells() -> None:
    weasyprint = pytest.importorskip("weasyprint")

    from prodockit.pdf.css import build_css

    text = (
        '| Off {: shade="off" } | Custom {: colspan=2 shade="7.5%" } | |\n'
        '|---|---|---|\n'
        '| plain | Highlighted {: shade="9%" } | plain |\n'
    )
    page = weasyprint.HTML(
        string=(
            f"<!DOCTYPE html><html><head><style>{build_css(**_css_defaults())}</style>"
            f"</head><body>{_convert(text)}</body></html>"
        )
    ).render().pages[0]
    cells: dict[str, object] = {}

    def walk(box: object) -> None:
        element = getattr(box, "element", None)
        if getattr(box, "element_tag", None) in {"th", "td"} and element is not None:
            label = "".join(element.itertext())
            cells.setdefault(label, box.style["background_color"])
        for child in getattr(box, "children", []):
            walk(child)

    walk(page._page_box)

    assert cells["Off"].alpha == 0
    assert cells["Custom"].alpha == pytest.approx(0.075)
    assert cells["Highlighted"].alpha == pytest.approx(0.09)


@pytest.mark.parametrize("value", ["on", "5", "-1%", "101%", "wat%"])
def test_invalid_cell_shades_are_refused(value: str) -> None:
    with pytest.raises(TableError, match='shade must be "off" or a percentage'):
        _convert(f'| A {{: shade="{value}" }} | B |\n|---|---|\n| a | b |\n')


def test_a_marked_row_joins_the_header() -> None:
    """`{: .header }` moves a row out of the body and into `<thead>`.

    That is the whole fix: only what is inside `<thead>` repeats when a
    table breaks across pages, so a second heading line written as a body
    row - the only way a Markdown table can express one - stops repeating
    exactly when it is needed (prodockit-extensions#474).
    """
    html = _convert(TWO_ROW_HEADER)
    head = html.split("<tbody>")[0]

    assert head.count("<tr>") == 2, f"expected two header rows: {head}"
    assert "<th>Before</th>" in head and "<th>After</th>" in head
    # Promoted cells are `th`, not `td`, and the marker does not survive.
    assert "<td" not in head
    assert "header" not in head


def test_only_the_leading_run_of_rows_is_promoted() -> None:
    """A header is the top of a table. A marked row further down is a
    mistake worth leaving visible rather than silently re-ordering the
    table around."""
    html = _convert(
        "| A | B |\n|---|---|\n| x | y |\n| p {: .header } | q |\n"
    )

    assert html.split("<tbody>")[0].count("<tr>") == 1
    # Still a body cell, and still carrying its marker: unpromoted, and
    # visibly so, rather than quietly tidied away.
    assert '<td class="header">p</td>' in html


def test_the_placeholder_cells_a_span_covers_are_removed() -> None:
    """A pipe table needs its columns to parse, so a merged cell is
    written with empty cells after it. Left in place they push the row
    wider than the header and the table comes out ragged."""
    head = _convert(TWO_ROW_HEADER).split("<tbody>")[0]

    # Four columns of markup, five header cells: three in the first row
    # (`Measured` covering two of them) and two in the second. Counted on
    # the closing tag, since "<th" also matches "<thead".
    assert head.count("</th>") == 5, head
    assert 'colspan="2"' in head and 'rowspan="2"' in head
    assert "<th></th>" not in head, "an empty placeholder survived"


def test_a_placeholder_with_content_is_left_alone() -> None:
    """Only an empty cell is filler. One with text in it is somebody's
    content, and dropping it silently would be worse than the ragged row
    it causes."""
    html = _convert("| A {: colspan=2 } | kept | C |\n|---|---|---|\n| 1 | 2 | 3 |\n")

    assert "kept" in html


def test_rotate_turns_the_heading_and_keeps_the_cell_in_place() -> None:
    """The text moves into a span; the cell keeps its place in the grid."""
    html = _convert('| Availability {: rotate=270 width="1.6em" height="110pt" } | V |\n|---|---|\n| a | b |\n')

    assert 'class="prodockit-rotate"' in html
    assert "rotate(270deg)" in html
    assert "height: 110pt" in html
    # The width became a column width, as any `width` does.
    assert "width: 1.6em" in html
    # And the attributes themselves are gone from the markup.
    assert "rotate=" not in html


def test_rotate_without_a_width_is_refused() -> None:
    """`transform` never affects layout, so rotation alone cannot narrow
    a column - the heading turns and the column stays exactly as wide.
    That renders as though the feature worked, which is the failure this
    project keeps meeting, so it is refused instead."""
    with pytest.raises(TableError, match="needs a width"):
        _convert("| A {: rotate=270 } | B |\n|---|---|\n| a | b |\n")


@pytest.mark.parametrize("angle", ["45", "180", "up"])
def test_only_the_two_readable_angles_are_allowed(angle: str) -> None:
    """270 reads bottom-to-top and 90 top-to-bottom. Anything else gives a
    heading nobody can read and a row height nobody can predict."""
    with pytest.raises(TableError):
        _convert(f'| A {{: rotate={angle} width="2em" }} | B |\n|---|---|\n| a | b |\n')


def test_a_rotated_heading_really_is_rotated_in_the_pdf() -> None:
    """Measured out of the PDF, not asserted from the CSS.

    WeasyPrint ignores `writing-mode` silently - the text stays
    horizontal while the column still narrows, so it looks merely wrapped
    rather than broken. `transform` is used precisely because it does
    not, and that is worth checking rather than trusting.
    """
    import os
    import tempfile

    weasyprint = pytest.importorskip("weasyprint")
    fitz = pytest.importorskip("pymupdf")

    from prodockit.pdf.css import build_css

    css = build_css(**_css_defaults())
    html = _convert(
        '| Availability requirement {: rotate=270 width="1.8em" height="105pt" } | V |\n'
        "|---|---|\n| a | b |\n"
    )
    out = os.path.join(tempfile.mkdtemp(), "rotated.pdf")
    weasyprint.HTML(
        string=f"<!DOCTYPE html><html><head><meta charset=utf-8>"
        f"<style>{css}</style></head><body>{html}</body></html>"
    ).write_pdf(out)

    directions = set()
    with fitz.open(out) as pdf:
        for block in pdf[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "Availability" in span["text"]:
                        directions.add(tuple(round(v, 2) for v in line["dir"]))

    assert directions, "the heading is missing from the PDF - clipped, not rotated"
    # (0, -1) is bottom-to-top. (1, 0) would be the silent `writing-mode`
    # failure: present, readable, and not turned at all.
    assert directions == {(0.0, -1.0)}, directions


def test_both_header_rows_repeat_when_the_table_breaks() -> None:
    """The reason the marker exists, measured on a table that paginates."""
    fitz = pytest.importorskip("pymupdf")
    pytest.importorskip("weasyprint")

    from prodockit.pdf.build import Page, build_pdf

    rows = "\n".join(f"| Item {i} | {'text ' * 6} | 1 | 2 | ok |" for i in range(1, 80))
    html = _convert(
        "| Target {: rowspan=2 } | Detail {: rowspan=2 } | Measured {: colspan=2 } | "
        "| Note {: rowspan=2 } |\n|---|---|---|---|---|\n"
        "| | | Before {: .header } | After | |\n" + rows + "\n"
    )
    import tempfile

    out = os.path.join(tempfile.mkdtemp(), "paginated.pdf")
    build_pdf([Page(docs_rel_path="p.md", html=f"<h1>T</h1>{html}", is_index=False)], out)

    with fitz.open(out) as pdf:
        pages = [page.get_text() for page in pdf]

    body = [i for i, t in enumerate(pages) if "Item 5" in t or "Item 40" in t]
    assert len(body) >= 2, f"the table should span pages: {len(pages)}"
    missing_first = [i for i in body if "Measured" not in pages[i]]
    missing_second = [i for i in body if "Before" not in pages[i]]
    assert not missing_first, f"first header row missing from {missing_first}"
    assert not missing_second, f"second header row missing from {missing_second}"

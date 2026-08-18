# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown

from prodockit.tables import TablesExtension

PLAIN_TABLE = "| Name | Description |\n|---|---|\n| a | b |\n"

PERCENT_TABLE = '| Name {: width="30%" } | Description | Date {: width="15%" } |\n|---|---|---|\n| a | b | c |\n'

FIXED_TABLE = '| Name {: width="120px" } | Description |\n|---|---|\n| a | b |\n'


def _convert(text: str) -> str:
    md = markdown.Markdown(extensions=["attr_list", TablesExtension()])
    return md.convert(text)


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

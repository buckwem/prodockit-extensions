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


def test_auto_enables_the_tables_extension() -> None:
    md = markdown.Markdown(extensions=["attr_list", TablesExtension()])
    assert "table" in md.parser.blockprocessors
    html = md.convert(PLAIN_TABLE)
    assert "<table>" in html


def test_does_not_duplicate_the_tables_extension_if_already_enabled() -> None:
    md = markdown.Markdown(extensions=["tables", "attr_list", TablesExtension()])
    html = md.convert(PERCENT_TABLE)
    assert html.count("<table") == 1

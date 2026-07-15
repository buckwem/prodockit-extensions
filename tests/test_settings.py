# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from zendoc.settings import flatten_nav, heading_numbering_enabled, reference_style_values


def test_flatten_nav_recurses_into_groups_and_skips_group_headings() -> None:
    nav = [
        {"url": "index.md", "children": []},
        {
            "url": None,
            "children": [
                {"url": "a.md", "children": []},
                {"url": "b.md", "children": []},
            ],
        },
    ]
    flattened = flatten_nav(nav)
    assert [page["url"] for page in flattened] == ["index.md", "a.md", "b.md"]


def test_heading_numbering_enabled_defaults_to_true() -> None:
    assert heading_numbering_enabled(None) is True
    assert heading_numbering_enabled({}) is True


def test_heading_numbering_enabled_reads_the_configured_value() -> None:
    assert heading_numbering_enabled({"heading_numbering": False}) is False


def test_reference_style_values_defaults() -> None:
    assert reference_style_values(None) == ("european", "-0.8em", "1.27cm", "2em")
    assert reference_style_values({}) == ("european", "-0.8em", "1.27cm", "2em")


def test_reference_style_values_reads_the_configured_values() -> None:
    values = reference_style_values(
        {
            "reference_style": "global",
            "reference_spacing_european": "-1em",
            "reference_indent_global": "2cm",
            "reference_spacing_global": "3em",
        }
    )
    assert values == ("global", "-1em", "2cm", "3em")


def test_reference_style_values_falls_back_to_european_for_an_unrecognised_value() -> None:
    style, *_ = reference_style_values({"reference_style": "typo"})
    assert style == "european"

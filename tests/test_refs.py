# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown

from zendoc.headings import HeadingsExtension
from zendoc.refs import RefsExtension
from zendoc.util import IdRegistry


def _convert(text: str, source: str = "doc.md") -> str:
    """Standalone use: zendoc.refs alone, auto-enabling zendoc.headings."""
    md = markdown.Markdown(extensions=["attr_list", RefsExtension()])
    return md.convert(text)


def test_ref_resolves_to_section_number() -> None:
    html = _convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_ref_resolves_nested_heading_number() -> None:
    html = _convert(
        "# Chapter\n\n## Setup\n\nSee \\ref{setup}.\n\n## Usage\n\nSee \\ref{usage}.\n"
    )
    assert '<a class="zendoc-ref" href="#setup">1.1</a>' in html
    assert '<a class="zendoc-ref" href="#usage">1.2</a>' in html


def test_forward_reference_within_same_document_resolves() -> None:
    html = _convert("See \\ref{introduction} below.\n\n# Introduction\n")
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_unknown_id_is_unresolved() -> None:
    html = _convert("See \\ref{does-not-exist}.\n")
    assert '<a class="zendoc-ref zendoc-ref-unresolved">??</a>' in html


def test_unnumbered_heading_is_unresolved_but_linkable() -> None:
    html = _convert("# Cover Page {: .unnumbered }\n\nSee \\ref{cover-page}.\n")
    assert '<a class="zendoc-ref zendoc-ref-unresolved" href="#cover-page">??</a>' in html


def test_custom_unresolved_marker() -> None:
    md = markdown.Markdown(extensions=[RefsExtension(unresolved="[MISSING]")])
    html = md.convert("See \\ref{nope}.\n")
    assert ">[MISSING]</a>" in html


def test_ref_inside_code_span_is_not_resolved() -> None:
    html = _convert("# Introduction\n\nType `\\ref{introduction}` literally.\n")
    assert "\\ref{introduction}" in html
    assert "zendoc-ref" not in html


def test_ref_inside_fenced_code_block_is_not_resolved() -> None:
    html = _convert("# Introduction\n\n```\n\\ref{introduction}\n```\n")
    assert "\\ref{introduction}" in html
    assert "zendoc-ref" not in html


def test_shares_registry_with_explicitly_enabled_headings_extension() -> None:
    """zendoc.headings listed first, zendoc.refs second - the recommended
    multi-page pattern: both share one registry across separate conversions."""
    registry = IdRegistry()
    md_page1 = markdown.Markdown(
        extensions=[
            HeadingsExtension(registry=registry, source="intro.md"),
            RefsExtension(registry=registry),
        ]
    )
    md_page1.convert("# Introduction\n")

    md_page2 = markdown.Markdown(
        extensions=[
            HeadingsExtension(registry=registry, source="usage.md"),
            RefsExtension(registry=registry),
        ]
    )
    html = md_page2.convert("See \\ref{introduction}.\n")
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_entry_point_names_resolve_together() -> None:
    md = markdown.Markdown(extensions=["zendoc.headings", "zendoc.refs"])
    html = md.convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html

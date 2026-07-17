# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown

from prodockit.headings import HeadingsExtension
from prodockit.refs import RefsExtension
from prodockit.util import IdRegistry


def _convert(text: str, source: str = "doc.md") -> str:
    """Standalone use: prodockit.refs alone, auto-enabling prodockit.headings."""
    md = markdown.Markdown(extensions=["attr_list", RefsExtension()])
    return md.convert(text)


def test_ref_resolves_to_section_number() -> None:
    html = _convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="prodockit-ref" href="#introduction">1</a>' in html


def test_ref_resolves_nested_heading_number() -> None:
    html = _convert(
        "# Chapter\n\n## Setup\n\nSee \\ref{setup}.\n\n## Usage\n\nSee \\ref{usage}.\n"
    )
    assert '<a class="prodockit-ref" href="#setup">1.1</a>' in html
    assert '<a class="prodockit-ref" href="#usage">1.2</a>' in html


def test_forward_reference_within_same_document_resolves() -> None:
    html = _convert("See \\ref{introduction} below.\n\n# Introduction\n")
    assert '<a class="prodockit-ref" href="#introduction">1</a>' in html


def test_unknown_id_is_unresolved() -> None:
    html = _convert("See \\ref{does-not-exist}.\n")
    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def test_unnumbered_heading_is_unresolved_but_linkable() -> None:
    html = _convert("# Cover Page {: .unnumbered }\n\nSee \\ref{cover-page}.\n")
    assert '<a class="prodockit-ref prodockit-ref-unresolved" href="#cover-page">??</a>' in html


def test_custom_unresolved_marker() -> None:
    md = markdown.Markdown(extensions=[RefsExtension(unresolved="[MISSING]")])
    html = md.convert("See \\ref{nope}.\n")
    assert ">[MISSING]</a>" in html


def test_ref_inside_code_span_is_not_resolved() -> None:
    html = _convert("# Introduction\n\nType `\\ref{introduction}` literally.\n")
    assert "\\ref{introduction}" in html
    assert "prodockit-ref" not in html


def test_ref_inside_fenced_code_block_is_not_resolved() -> None:
    html = _convert("# Introduction\n\n```\n\\ref{introduction}\n```\n")
    assert "\\ref{introduction}" in html
    assert "prodockit-ref" not in html


def test_shares_registry_with_explicitly_enabled_headings_extension() -> None:
    """prodockit.headings listed first, prodockit.refs second - the recommended
    multi-page pattern: both share one registry across separate conversions,
    and RefsExtension's own source (matching HeadingsExtension's) lets it
    build a correct cross-page link rather than a same-page-only fragment."""
    registry = IdRegistry()
    md_page1 = markdown.Markdown(
        extensions=[
            HeadingsExtension(registry=registry, source="intro.md"),
            RefsExtension(registry=registry, source="intro.md"),
        ]
    )
    md_page1.convert("# Introduction\n")

    md_page2 = markdown.Markdown(
        extensions=[
            HeadingsExtension(registry=registry, source="usage.md"),
            RefsExtension(registry=registry, source="usage.md"),
        ]
    )
    html = md_page2.convert("See \\ref{introduction}.\n")
    assert '<a class="prodockit-ref" href="intro.md#introduction">1</a>' in html


def test_entry_point_names_resolve_together() -> None:
    md = markdown.Markdown(extensions=["prodockit.headings", "prodockit.refs"])
    html = md.convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="prodockit-ref" href="#introduction">1</a>' in html


def test_entry_point_names_resolve_in_reverse_order() -> None:
    """prodockit.refs listed before prodockit.headings - order shouldn't matter,
    since Zensical's own TOML-to-extension-list conversion doesn't preserve
    the order extensions were written in (it round-trips through a set())."""
    md = markdown.Markdown(extensions=["prodockit.refs", "prodockit.headings"])
    html = md.convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="prodockit-ref" href="#introduction">1</a>' in html
    # Only one heading treeprocessor's worth of ids should exist - not a
    # duplicate registration from two independently-created registries.
    assert html.count('id="introduction"') == 1

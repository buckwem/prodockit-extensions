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
    assert '<a class="prodockit-ref" href="#introduction">1 Introduction</a>' in html


def test_ref_resolves_nested_heading_number() -> None:
    html = _convert(
        "# Chapter\n\n## Setup\n\nSee \\ref{setup}.\n\n## Usage\n\nSee \\ref{usage}.\n"
    )
    assert '<a class="prodockit-ref" href="#setup">1.1 Setup</a>' in html
    assert '<a class="prodockit-ref" href="#usage">1.2 Usage</a>' in html


def test_forward_reference_within_same_document_resolves() -> None:
    html = _convert("See \\ref{introduction} below.\n\n# Introduction\n")
    assert '<a class="prodockit-ref" href="#introduction">1 Introduction</a>' in html


def test_unknown_id_is_unresolved() -> None:
    html = _convert("See \\ref{does-not-exist}.\n")
    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def test_unnumbered_heading_is_unresolved_but_linkable() -> None:
    html = _convert("# Cover Page {: .unnumbered }\n\nSee \\ref{cover-page}.\n")
    # A reference renders the target's name, and an unnumbered heading
    # has one - so this resolves rather than falling back to `unresolved`.
    # Only a genuinely unknown id is unresolved.
    assert '<a class="prodockit-ref" href="#cover-page">Cover Page</a>' in html


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
    assert '<a class="prodockit-ref" href="intro.md#introduction">1 Introduction</a>' in html


def test_entry_point_names_resolve_together() -> None:
    md = markdown.Markdown(extensions=["prodockit.headings", "prodockit.refs"])
    html = md.convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="prodockit-ref" href="#introduction">1 Introduction</a>' in html


def test_entry_point_names_resolve_in_reverse_order() -> None:
    """prodockit.refs listed before prodockit.headings - order shouldn't matter,
    since Zensical's own TOML-to-extension-list conversion doesn't preserve
    the order extensions were written in (it round-trips through a set())."""
    md = markdown.Markdown(extensions=["prodockit.refs", "prodockit.headings"])
    html = md.convert("# Introduction\n\nSee \\ref{introduction}.\n")
    assert '<a class="prodockit-ref" href="#introduction">1 Introduction</a>' in html
    # Only one heading treeprocessor's worth of ids should exist - not a
    # duplicate registration from two independently-created registries.
    assert html.count('id="introduction"') == 1


def test_autoref_resolves_to_the_heading_name() -> None:
    """`\\ref{}` gives the number, `\\autoref{}` gives the name - the thing a
    printed reference needs, since "see 1.1" tells a reader holding paper
    nothing about where to turn."""
    html = _convert("# Introduction\n\nSee \\autoref{introduction}.\n")

    assert '<a class="prodockit-autoref" href="#introduction">1 Introduction</a>' in html


def test_autoref_resolves_an_unnumbered_heading_where_ref_cannot() -> None:
    """A cover page or appendix front matter has no number to show, so
    `\\ref{}` falls back to `unresolved` - but it does have a name, and
    "see Cover Page on page 1" is exactly as useful as a numbered
    reference. Only a genuinely unknown id is unresolved for `\\autoref`."""
    text = "# Cover Page {: .unnumbered #cover }\n\nRef: \\ref{cover}. Auto: \\autoref{cover}.\n"

    html = _convert(text)

    assert '<a class="prodockit-ref" href="#cover">Cover Page</a>' in html
    assert '<a class="prodockit-autoref" href="#cover">Cover Page</a>' in html


def test_autoref_falls_back_for_an_unknown_id() -> None:
    html = _convert("# Introduction\n\nSee \\autoref{nope}.\n")

    assert '<a class="prodockit-autoref prodockit-autoref-unresolved">??</a>' in html


def test_autoref_resolves_a_forward_reference() -> None:
    """Same deferral as `\\ref{}` - resolution happens in a treeprocessor,
    after every heading in the document has been registered."""
    html = _convert("See \\autoref{background} below.\n\n## Background\n")

    assert '<a class="prodockit-autoref" href="#background">1.1 Background</a>' in html


def test_autoref_is_protected_inside_a_code_span() -> None:
    """Registered at the same low inline priority as `\\ref{}`, so the
    syntax can be shown as literal example text."""
    html = _convert("Type `\\autoref{intro}` to reference a section.\n\n# Intro\n")

    assert "prodockit-autoref" not in html
    assert "\\autoref{intro}" in html


def test_ref_and_autoref_can_target_the_same_heading() -> None:
    html = _convert("# Introduction\n\n\\ref{introduction} and \\autoref{introduction}.\n")

    assert '<a class="prodockit-ref" href="#introduction">1 Introduction</a>' in html
    assert '<a class="prodockit-autoref" href="#introduction">1 Introduction</a>' in html

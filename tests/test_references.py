# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown

from zendoc import IdRegistry
from zendoc.extension import ZendocExtension


def _convert(text: str, registry: IdRegistry, source: str = "doc.md") -> str:
    md = markdown.Markdown(
        extensions=["attr_list", ZendocExtension(registry=registry, source=source)]
    )
    return md.convert(text)


def test_ref_resolves_to_section_number() -> None:
    registry = IdRegistry()
    html = _convert("# Introduction\n\nSee \\ref{introduction}.\n", registry)
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_ref_resolves_nested_heading_number() -> None:
    registry = IdRegistry()
    html = _convert(
        "# Chapter\n\n## Setup\n\nSee \\ref{setup}.\n\n## Usage\n\nSee \\ref{usage}.\n",
        registry,
    )
    assert '<a class="zendoc-ref" href="#setup">1.1</a>' in html
    assert '<a class="zendoc-ref" href="#usage">1.2</a>' in html


def test_forward_reference_within_same_document_resolves() -> None:
    registry = IdRegistry()
    html = _convert("See \\ref{introduction} below.\n\n# Introduction\n", registry)
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_cross_document_reference_resolves() -> None:
    registry = IdRegistry()
    _convert("# Introduction\n", registry, source="intro.md")
    html = _convert("See \\ref{introduction}.\n", registry, source="usage.md")
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_unknown_id_is_unresolved() -> None:
    registry = IdRegistry()
    html = _convert("See \\ref{does-not-exist}.\n", registry)
    assert 'class="zendoc-ref zendoc-ref-unresolved"' in html
    assert ">??</a>" in html
    assert "href" not in html.split(">??</a>")[0].split("<a")[-1]


def test_unnumbered_heading_is_unresolved_but_linkable() -> None:
    registry = IdRegistry()
    html = _convert(
        "# Cover Page {: .unnumbered }\n\nSee \\ref{cover-page}.\n",
        registry,
    )
    assert '<a class="zendoc-ref zendoc-ref-unresolved" href="#cover-page">??</a>' in html


def test_custom_unresolved_marker() -> None:
    registry = IdRegistry()
    md = markdown.Markdown(
        extensions=[ZendocExtension(registry=registry, unresolved="[MISSING]")]
    )
    html = md.convert("See \\ref{nope}.\n")
    assert ">[MISSING]</a>" in html


def test_ref_inside_code_span_is_not_resolved() -> None:
    registry = IdRegistry()
    html = _convert("# Introduction\n\nType `\\ref{introduction}` literally.\n", registry)
    assert "\\ref{introduction}" in html
    assert "zendoc-ref" not in html


def test_ref_inside_fenced_code_block_is_not_resolved() -> None:
    registry = IdRegistry()
    html = _convert(
        "# Introduction\n\n```\n\\ref{introduction}\n```\n",
        registry,
    )
    assert "\\ref{introduction}" in html
    assert "zendoc-ref" not in html

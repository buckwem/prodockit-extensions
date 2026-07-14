# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown
import pytest

from zendoc.glossary import GlossaryExtension
from zendoc.util import DuplicateIdError, GlossaryRegistry


def _convert(text: str, registry: GlossaryRegistry | None = None, source: str = "doc.md") -> str:
    extension = (
        GlossaryExtension(registry=registry, source=source)
        if registry is not None
        else GlossaryExtension()
    )
    md = markdown.Markdown(extensions=["attr_list", extension])
    return md.convert(text)


CSS_DEF = '**CSS** - Cascading Style Sheets.\n{: #css .acronym data-term="CSS" }'
CSS_GLOSSARY_DEF = (
    "**Cascading Style Sheets** - The language used to control appearance.\n"
    '{: #css-def .glossary data-term="Cascading Style Sheets" }'
)


def test_term_definition_strips_internal_attribute_but_keeps_id_and_class() -> None:
    html = _convert(CSS_DEF)
    assert 'id="css"' in html
    assert 'class="acronym"' in html
    assert "data-term" not in html


def test_gls_resolves_to_the_terms_own_text() -> None:
    html = _convert(f"{CSS_DEF}\n\nThis template uses \\gls{{css}} to style pages.\n")
    assert 'This template uses <a class="zendoc-gls" href="#css">CSS</a> to style pages.' in html


def test_forward_reference_within_same_document_resolves() -> None:
    html = _convert(f"See \\gls{{css}} above.\n\n{CSS_DEF}\n")
    assert '<a class="zendoc-gls" href="#css">CSS</a>' in html


def test_unknown_id_is_unresolved() -> None:
    html = _convert("See \\gls{does-not-exist}.\n")
    assert '<a class="zendoc-gls zendoc-gls-unresolved">?</a>' in html


def test_unresolved_id_has_no_href() -> None:
    html = _convert("See \\gls{does-not-exist}.\n")
    assert 'href' not in html[html.index('<a class="zendoc-gls zendoc-gls-unresolved">') :].split(">")[0]


def test_custom_unresolved_marker() -> None:
    md = markdown.Markdown(extensions=[GlossaryExtension(unresolved="[MISSING]")])
    html = md.convert("See \\gls{nope}.\n")
    assert ">[MISSING]</a>" in html


def test_gls_inside_code_span_is_not_resolved() -> None:
    html = _convert(f"{CSS_DEF}\n\nType `\\gls{{css}}` literally.\n")
    assert "\\gls{css}" in html
    assert "zendoc-gls" not in html


def test_gls_inside_fenced_code_block_is_not_resolved() -> None:
    html = _convert(f"{CSS_DEF}\n\n```\n\\gls{{css}}\n```\n")
    assert "\\gls{css}" in html
    assert "zendoc-gls" not in html


def test_shares_registry_across_explicit_sources() -> None:
    registry = GlossaryRegistry()
    _convert(CSS_DEF, registry=registry, source="acronyms.md")
    html = _convert("See \\gls{css}.\n", registry=registry, source="section1.md")
    # A different source references this, so the link must be a real
    # cross-page reference (acronyms.md#css), not a bare same-page
    # fragment - a bare "#css" would 404 on the actual multi-page website.
    assert '<a class="zendoc-gls" href="acronyms.md#css">CSS</a>' in html


def test_duplicate_id_across_explicit_sources_raises() -> None:
    registry = GlossaryRegistry()
    _convert(CSS_DEF, registry=registry, source="acronyms.md")
    with pytest.raises(DuplicateIdError):
        _convert(CSS_DEF, registry=registry, source="other.md")


def test_acronyms_and_glossary_share_one_registry() -> None:
    """Acronym entries and glossary entries are the same kind of thing (an
    id with a short display text) - one registry covers both, so an
    acronym and its glossary counterpart can each reference the other by
    id, or be referenced from a third page, without any special wiring."""
    registry = GlossaryRegistry()
    _convert(CSS_DEF, registry=registry, source="acronyms.md")
    _convert(CSS_GLOSSARY_DEF, registry=registry, source="glossary.md")
    html = _convert(
        "See \\gls{css} and \\gls{css-def}.\n", registry=registry, source="section1.md"
    )
    assert '<a class="zendoc-gls" href="acronyms.md#css">CSS</a>' in html
    assert '<a class="zendoc-gls" href="glossary.md#css-def">Cascading Style Sheets</a>' in html


def test_entry_point_name_resolves() -> None:
    md = markdown.Markdown(extensions=["attr_list", "zendoc.glossary"])
    html = md.convert(f"{CSS_DEF}\n\nSee \\gls{{css}}.\n")
    assert '<a class="zendoc-gls" href="#css">CSS</a>' in html

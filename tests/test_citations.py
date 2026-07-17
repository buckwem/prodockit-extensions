# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown
import pytest

from prodockit.citations import CitationsExtension
from prodockit.util import CitationRegistry, DuplicateIdError


def _convert(text: str, registry: CitationRegistry | None = None, source: str = "doc.md") -> str:
    extension = (
        CitationsExtension(registry=registry, source=source)
        if registry is not None
        else CitationsExtension()
    )
    md = markdown.Markdown(extensions=["attr_list", extension])
    return md.convert(text)


SKOU_DEF = (
    "Skoulikari, A. (2023) *Learning Git*.\n"
    '{: #skou2023 .reference data-cite-text="Skoulikari, 2023" }'
)
CHACON_DEF = (
    "Chacon, S. and Straub, B. (2014) *Pro Git*.\n"
    '{: #chacon2014 .reference data-cite-text="Chacon and Straub, 2014" }'
)


def test_citation_definition_strips_internal_attribute_but_keeps_id_and_class() -> None:
    html = _convert(SKOU_DEF)
    assert 'id="skou2023"' in html
    assert 'class="reference"' in html
    assert "data-cite-text" not in html


def test_cite_resolves_to_bracketed_link() -> None:
    html = _convert(f"{SKOU_DEF}\n\nSee \\cite{{skou2023}}.\n")
    assert (
        '<span class="prodockit-cite">[<a class="prodockit-cite-resolved" '
        'href="#skou2023">Skoulikari, 2023</a>]</span>' in html
    )


def test_multiple_keys_join_with_semicolons() -> None:
    html = _convert(f"{SKOU_DEF}\n\n{CHACON_DEF}\n\nSee \\cite{{skou2023,chacon2014}}.\n")
    assert (
        '<a class="prodockit-cite-resolved" href="#skou2023">Skoulikari, 2023</a>; '
        '<a class="prodockit-cite-resolved" href="#chacon2014">Chacon and Straub, 2014</a>]'
        in html
    )


def test_forward_reference_within_same_document_resolves() -> None:
    html = _convert(f"See \\cite{{skou2023}} above.\n\n{SKOU_DEF}\n")
    assert '<a class="prodockit-cite-resolved" href="#skou2023">Skoulikari, 2023</a>' in html


def test_unknown_key_is_unresolved() -> None:
    html = _convert("See \\cite{does-not-exist}.\n")
    assert '<span class="prodockit-cite">[<a class="prodockit-cite-unresolved">?</a>]</span>' in html


def test_unresolved_key_has_no_href() -> None:
    html = _convert("See \\cite{does-not-exist}.\n")
    assert "href" not in html.split("</span>")[0].split("<span")[-1]


def test_custom_unresolved_marker() -> None:
    md = markdown.Markdown(extensions=[CitationsExtension(unresolved="[MISSING]")])
    html = md.convert("See \\cite{nope}.\n")
    assert ">[MISSING]</a>" in html


def test_partial_resolution_in_multi_key_citation() -> None:
    html = _convert(f"{SKOU_DEF}\n\nSee \\cite{{skou2023,does-not-exist}}.\n")
    assert (
        '<a class="prodockit-cite-resolved" href="#skou2023">Skoulikari, 2023</a>; '
        '<a class="prodockit-cite-unresolved">?</a>]' in html
    )


def test_cite_inside_code_span_is_not_resolved() -> None:
    html = _convert(f"{SKOU_DEF}\n\nType `\\cite{{skou2023}}` literally.\n")
    assert "\\cite{skou2023}" in html
    assert "prodockit-cite" not in html


def test_cite_inside_fenced_code_block_is_not_resolved() -> None:
    html = _convert(f"{SKOU_DEF}\n\n```\n\\cite{{skou2023}}\n```\n")
    assert "\\cite{skou2023}" in html
    assert "prodockit-cite" not in html


def test_shares_registry_across_explicit_sources() -> None:
    registry = CitationRegistry()
    _convert(SKOU_DEF, registry=registry, source="references.md")
    html = _convert("See \\cite{skou2023}.\n", registry=registry, source="section1.md")
    # A different source cites this, so the link must be a real cross-page
    # reference (references.md#skou2023), not a bare same-page fragment -
    # a bare "#skou2023" would 404 on the actual multi-page website, even
    # though it happens to "work" in a single concatenated PDF document.
    assert '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>' in html


def test_duplicate_key_across_explicit_sources_raises() -> None:
    registry = CitationRegistry()
    _convert(SKOU_DEF, registry=registry, source="references.md")
    with pytest.raises(DuplicateIdError):
        _convert(SKOU_DEF, registry=registry, source="other.md")


def test_entry_point_name_resolves() -> None:
    md = markdown.Markdown(extensions=["attr_list", "prodockit.citations"])
    html = md.convert(f"{SKOU_DEF}\n\nSee \\cite{{skou2023}}.\n")
    assert '<a class="prodockit-cite-resolved" href="#skou2023">Skoulikari, 2023</a>' in html

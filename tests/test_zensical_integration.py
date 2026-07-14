# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Simulates Zensical's per-page render(): a fresh Markdown() instance per
page, each carrying a zensical.extensions.context.ContextPreprocessor - see
zendoc.headings._zensical_page_source, added to fix zendoc-template#85
(cross-page \\ref resolution not working under Zensical's per-page build)."""

import markdown
import pytest
from zensical.extensions.context import ContextExtension, Page

import zendoc.citations as zendoc_citations
import zendoc.headings as zendoc_headings
from zendoc.util import CitationRegistry, IdRegistry


@pytest.fixture(autouse=True)
def _isolated_zensical_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own shared-singleton stand-ins, so tests can't
    leak registrations into one another via the real module-level
    singletons (which, in production, are deliberately shared for the whole
    build's lifetime)."""
    monkeypatch.setattr(zendoc_headings, "_ZENSICAL_SHARED_REGISTRY", IdRegistry())
    monkeypatch.setattr(zendoc_citations, "_ZENSICAL_SHARED_REGISTRY", CitationRegistry())


def _convert_as_zensical_page(text: str, path: str) -> str:
    """Mirrors zensical/markdown/render.py: a brand new Markdown() instance
    per page, with a ContextExtension carrying that page's Page(path=...) -
    and zendoc.headings/zendoc.refs configured as plain strings, exactly as
    zensical.toml's [project.markdown_extensions."zendoc.headings"] does."""
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            "zendoc.headings",
            "zendoc.refs",
        ]
    )
    return md.convert(text)


def test_cross_page_reference_resolves_under_zensical() -> None:
    _convert_as_zensical_page("# Introduction\n", "intro.md")
    html = _convert_as_zensical_page("See \\ref{introduction}.\n", "usage.md")
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html


def test_each_page_gets_its_own_source_automatically() -> None:
    """Without explicit source= config (impossible to vary per page via
    zensical.toml alone), each page must still be scoped independently -
    otherwise the second page's clear_source() call would wipe the first
    page's headings before this test's own assertion even runs."""
    _convert_as_zensical_page("# Introduction\n", "intro.md")
    _convert_as_zensical_page("# Setup\n", "setup.md")
    html = _convert_as_zensical_page(
        "See \\ref{introduction} and \\ref{setup}.\n", "summary.md"
    )
    assert '<a class="zendoc-ref" href="#introduction">1</a>' in html
    assert '<a class="zendoc-ref" href="#setup">1</a>' in html


def test_duplicate_heading_text_across_pages_does_not_crash_the_build() -> None:
    """A real, common scenario (confirmed present in zendoc-template's own
    docs/): two unrelated pages both happen to have an identically-titled
    heading (e.g. "Overview"). Under the strict (explicit multi-page) path
    this would raise DuplicateIdError - here, under Zensical auto-detection,
    it must not, or installing zendoc would risk breaking any Zensical site
    with a common heading title used on more than one page."""
    _convert_as_zensical_page("# Overview\n", "page-a.md")
    # Must not raise:
    html = _convert_as_zensical_page("# Overview\n", "page-b.md")
    assert 'id="overview"' in html


def test_non_zensical_use_is_unaffected() -> None:
    """Without a ContextExtension/Page on md (i.e. not under Zensical), two
    independent conversions must keep behaving exactly as before this fix -
    each gets its own private registry, not the shared Zensical singleton."""
    md1 = markdown.Markdown(extensions=["zendoc.headings"])
    md1.convert("# Introduction\n")
    md2 = markdown.Markdown(extensions=["zendoc.headings", "zendoc.refs"])
    html = md2.convert("See \\ref{introduction}.\n")
    # Page 2 never saw page 1's heading - falls back to unresolved, exactly
    # as it did before Zensical auto-detection existed.
    assert '<a class="zendoc-ref zendoc-ref-unresolved">??</a>' in html


def _convert_as_zensical_page_with_citations(text: str, path: str) -> str:
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            "attr_list",
            "zendoc.citations",
        ]
    )
    return md.convert(text)


def test_cross_page_citation_resolves_under_zensical() -> None:
    _convert_as_zensical_page_with_citations(
        'Skoulikari, A. (2023) *Learning Git*.\n'
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        "references.md",
    )
    html = _convert_as_zensical_page_with_citations(
        "See \\cite{skou2023}.\n", "section1.md"
    )
    assert '<a href="#skou2023">Skoulikari, 2023</a>' in html


def test_duplicate_citation_key_across_pages_does_not_crash_the_build() -> None:
    definition = (
        'Skoulikari, A. (2023) *Learning Git*.\n'
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n'
    )
    _convert_as_zensical_page_with_citations(definition, "page-a.md")
    # Must not raise, even though the same key is (implausibly, but
    # possibly) defined twice across two different pages:
    html = _convert_as_zensical_page_with_citations(definition, "page-b.md")
    assert 'id="skou2023"' in html

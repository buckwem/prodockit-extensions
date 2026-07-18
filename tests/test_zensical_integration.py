# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Simulates Zensical's per-page render(): a fresh Markdown() instance per
page, each carrying a zensical.extensions.context.ContextPreprocessor - see
prodockit.headings._zensical_page_source, added to fix cross-page \\ref
resolution not working under Zensical's per-page build."""

import shutil
from pathlib import Path

import markdown
import pytest
from zensical.extensions.context import ContextExtension, Page

import prodockit._zensical as prodockit_zensical
import prodockit.bibliography as prodockit_bibliography
import prodockit.citations as prodockit_citations
import prodockit.glossary as prodockit_glossary
import prodockit.headings as prodockit_headings
from prodockit.bibliography import BibliographyExtension
from prodockit.util import CitationRegistry, GlossaryRegistry, IdRegistry

pandoc_required = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="prodockit.bibliography's citation/bibliography formatting is delegated "
    "entirely to `pandoc --citeproc` - these tests need a real pandoc install.",
)


@pytest.fixture(autouse=True)
def _isolated_zensical_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own shared-singleton stand-ins, so tests can't
    leak registrations into one another via the real module-level
    singletons (which, in production, are deliberately shared for the whole
    build's lifetime)."""
    monkeypatch.setattr(prodockit_headings, "_ZENSICAL_SHARED_REGISTRY", IdRegistry())
    monkeypatch.setattr(prodockit_citations, "_ZENSICAL_SHARED_REGISTRY", CitationRegistry())
    monkeypatch.setattr(prodockit_glossary, "_ZENSICAL_SHARED_REGISTRY", GlossaryRegistry())
    monkeypatch.setattr(prodockit_bibliography, "_ZENSICAL_SHARED_CACHES", {})


def _convert_as_zensical_page(text: str, path: str) -> str:
    """Mirrors zensical/markdown/render.py: a brand new Markdown() instance
    per page, with a ContextExtension carrying that page's Page(path=...) -
    and prodockit.headings/prodockit.refs configured as plain strings, exactly as
    zensical.toml's [project.markdown_extensions."prodockit.headings"] does."""
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            "prodockit.headings",
            "prodockit.refs",
        ]
    )
    return md.convert(text)


def test_cross_page_reference_resolves_under_zensical() -> None:
    _convert_as_zensical_page("# Introduction\n", "intro.md")
    html = _convert_as_zensical_page("See \\ref{introduction}.\n", "usage.md")
    # A real cross-page link (intro.md#introduction), not a bare same-page
    # fragment - the latter would 404 on the actual multi-page website.
    assert '<a class="prodockit-ref" href="intro.md#introduction">1</a>' in html


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
    assert '<a class="prodockit-ref" href="intro.md#introduction">1</a>' in html
    assert '<a class="prodockit-ref" href="setup.md#setup">1</a>' in html


def test_same_page_reference_still_uses_bare_fragment_under_zensical() -> None:
    """A reference to a heading on the *same* page keeps the simpler bare
    fragment - only a genuinely cross-page reference needs the page-prefixed
    form."""
    html = _convert_as_zensical_page(
        "# Introduction\n\nSee \\ref{introduction}.\n", "intro.md"
    )
    assert '<a class="prodockit-ref" href="#introduction">1</a>' in html


def test_duplicate_heading_text_across_pages_does_not_crash_the_build() -> None:
    """A real, common scenario: two unrelated pages both happen to have an
    identically-titled heading (e.g. "Overview"). Under the strict
    (explicit multi-page) path this would raise DuplicateIdError - here,
    under Zensical auto-detection, it must not, or installing prodockit would
    risk breaking any Zensical site with a common heading title used on
    more than one page."""
    _convert_as_zensical_page("# Overview\n", "page-a.md")
    # Must not raise:
    html = _convert_as_zensical_page("# Overview\n", "page-b.md")
    assert 'id="overview"' in html


def test_non_zensical_use_is_unaffected() -> None:
    """Without a ContextExtension/Page on md (i.e. not under Zensical), two
    independent conversions must keep behaving exactly as before this fix -
    each gets its own private registry, not the shared Zensical singleton."""
    md1 = markdown.Markdown(extensions=["prodockit.headings"])
    md1.convert("# Introduction\n")
    md2 = markdown.Markdown(extensions=["prodockit.headings", "prodockit.refs"])
    html = md2.convert("See \\ref{introduction}.\n")
    # Page 2 never saw page 1's heading - falls back to unresolved, exactly
    # as it did before Zensical auto-detection existed.
    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def test_default_numbering_is_still_per_document_under_zensical() -> None:
    """Zensical auto-detection alone must not switch numbering to
    "continuous" - that's an explicit opt-in, not a side effect of running
    under Zensical."""
    _convert_as_zensical_page("# One\n", "page1.md")
    _convert_as_zensical_page("# Two\n", "page2.md")
    registry = prodockit_headings._ZENSICAL_SHARED_REGISTRY
    assert registry.get("one").number == "1"  # type: ignore[union-attr]
    assert registry.get("two").number == "1"  # type: ignore[union-attr]


def _convert_as_zensical_page_with_continuous_headings(text: str, path: str) -> str:
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            prodockit_headings.HeadingsExtension(numbering="continuous"),
        ]
    )
    return md.convert(text)


def test_continuous_numbering_seeds_from_earlier_nav_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n\n## Sub\n", encoding="utf-8")
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["page1.md", "page2.md"])
    )
    _convert_as_zensical_page_with_continuous_headings("# One\n\n## Sub\n", "page1.md")
    _convert_as_zensical_page_with_continuous_headings("# Two\n", "page2.md")
    registry = prodockit_headings._ZENSICAL_SHARED_REGISTRY
    assert registry.get("one").number == "1"  # type: ignore[union-attr]
    assert registry.get("sub").number == "1.1"  # type: ignore[union-attr]
    assert registry.get("two").number == "2"  # type: ignore[union-attr]


def test_continuous_numbering_letters_appendix_pages_without_consuming_a_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n", encoding="utf-8")
    (docs_dir / "appendix.md").write_text(
        "---\nis_appendix: true\n---\n\n# App Heading\n\n## Sub\n", encoding="utf-8"
    )
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page1.md", "appendix.md", "page2.md"]),
    )
    _convert_as_zensical_page_with_continuous_headings("# One\n", "page1.md")
    _convert_as_zensical_page_with_continuous_headings(
        "# App Heading\n\n## Sub\n", "appendix.md"
    )
    _convert_as_zensical_page_with_continuous_headings("# Two\n", "page2.md")
    registry = prodockit_headings._ZENSICAL_SHARED_REGISTRY
    assert registry.get("one").number == "1"  # type: ignore[union-attr]
    assert registry.get("app-heading").number == "A"  # type: ignore[union-attr]
    assert registry.get("sub").number == "A.1"  # type: ignore[union-attr]
    # page2 continues the numeric sequence as if the appendix page never
    # consumed a number from it - "2", not "3".
    assert registry.get("two").number == "2"  # type: ignore[union-attr]


def test_ref_to_a_continuously_numbered_heading_on_another_page_shows_the_right_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """\\ref{} must show the number actually displayed on the target page
    (continuing across earlier pages), not a per-document number that
    resets to 1 on every page."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n", encoding="utf-8")
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["page1.md", "page2.md"])
    )

    def _convert(text: str, path: str) -> str:
        md = markdown.Markdown(
            extensions=[
                ContextExtension(page=Page(url=path, path=path), config={}),
                prodockit_headings.HeadingsExtension(numbering="continuous"),
                "prodockit.refs",
            ]
        )
        return md.convert(text)

    _convert("# One\n", "page1.md")
    _convert("# Two\n", "page2.md")
    html = _convert("See \\ref{two}.\n", "page3.md")
    assert '<a class="prodockit-ref" href="page2.md#two">2</a>' in html


def _convert_as_zensical_page_with_citations(text: str, path: str) -> str:
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            "attr_list",
            "prodockit.citations",
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
    # A real cross-page link (references.md#skou2023), not a bare
    # same-page fragment - the latter would 404 on the actual website.
    assert '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>' in html


def test_cross_page_citation_from_nested_page_uses_relative_path() -> None:
    """Regression test: a top-level record_source ("references.md") isn't a
    valid link as-is from a page nested in a subdirectory - it needs the
    same "../" prefix a hand-typed relative link between the same two
    pages would need."""
    _convert_as_zensical_page_with_citations(
        'Skoulikari, A. (2023) *Learning Git*.\n'
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        "references.md",
    )
    html = _convert_as_zensical_page_with_citations(
        "See \\cite{skou2023}.\n", "starthere/customise.md"
    )
    assert '<a class="prodockit-cite-resolved" href="../references.md#skou2023">Skoulikari, 2023</a>' in html


def test_same_page_citation_still_uses_bare_fragment_under_zensical() -> None:
    html = _convert_as_zensical_page_with_citations(
        'Skoulikari, A. (2023) *Learning Git*.\n'
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n\n'
        'See \\cite{skou2023}.\n',
        "references.md",
    )
    assert '<a class="prodockit-cite-resolved" href="#skou2023">Skoulikari, 2023</a>' in html


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


def test_forward_citation_resolves_via_nav_preseed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The realistic ordering problem this fix solves: a source cited from
    an early page (built first in nav order), but defined on a references
    page kept as an appendix at the *end* of nav - a forward reference
    `zensical build`'s single, one-shot pass couldn't otherwise resolve,
    since references.md is never actually converted in this test at all;
    only pre-scanned."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "references.md").write_text(
        'Skoulikari, A. (2023) *Learning Git*.\n'
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["section1.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_citations(
        "See \\cite{skou2023}.\n", "section1.md"
    )
    assert '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>' in html


def test_nav_preseed_ignores_fenced_documentation_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A doc page showing prodockit.citations' own definition syntax as a
    literal example inside a fenced code block must not be mistaken for a
    real definition by the raw-text nav pre-scan (which, unlike
    CitationDefTreeprocessor, isn't fence-aware via the real parser).
    Regression test for a real bug: a page with such an example earlier in
    nav order than the real references page was "winning" the preseed
    slot, sending every \\cite{skou2023} to the wrong page."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "customise.md").write_text(
        "Define a source like this:\n\n"
        "``` markdown\n"
        "Skoulikari, A. (2023) *Learning Git*.\n"
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n'
        "```\n",
        encoding="utf-8",
    )
    (docs_dir / "references.md").write_text(
        "Skoulikari, A. (2023) *Learning Git*.\n"
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["customise.md", "section1.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_citations(
        "See \\cite{skou2023}.\n", "section1.md"
    )
    assert '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>' in html


def test_real_definition_supersedes_preseeded_stub() -> None:
    """Once a page's own CitationDefTreeprocessor has genuinely registered
    an id, that takes precedence over any provisional preseed() value for
    the same id - preseed() is only ever a stand-in for this."""
    registry = CitationRegistry()
    registry.preseed("references.md", "skou2023", "stale placeholder text")
    registry.register(source="references.md", id="skou2023", text="Skoulikari, 2023")
    record = registry.get("skou2023")
    assert record is not None
    assert record.text == "Skoulikari, 2023"


def _convert_as_zensical_page_with_glossary(text: str, path: str) -> str:
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            "attr_list",
            "prodockit.glossary",
        ]
    )
    return md.convert(text)


def test_cross_page_gls_resolves_under_zensical() -> None:
    _convert_as_zensical_page_with_glossary(
        '**CSS** - Cascading Style Sheets.\n{: #css data-term="CSS" }\n',
        "acronyms.md",
    )
    html = _convert_as_zensical_page_with_glossary(
        "This uses \\gls{css}.\n", "section1.md"
    )
    # A real cross-page link (acronyms.md#css), not a bare same-page
    # fragment - the latter would 404 on the actual website.
    assert '<a class="prodockit-gls" href="acronyms.md#css">CSS</a>' in html


def test_gls_forward_reference_resolves_via_nav_preseed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same "cited before defined" ordering problem prodockit.citations
    solves: acronyms.md is usually kept as an appendix at the end of nav,
    but referenced from early chapters."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "acronyms.md").write_text(
        '**CSS** - Cascading Style Sheets.\n{: #css data-term="CSS" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["section1.md", "acronyms.md"]),
    )
    html = _convert_as_zensical_page_with_glossary(
        "This uses \\gls{css}.\n", "section1.md"
    )
    assert '<a class="prodockit-gls" href="acronyms.md#css">CSS</a>' in html


def test_duplicate_glossary_term_across_pages_does_not_crash_the_build() -> None:
    definition = '**CSS** - Cascading Style Sheets.\n{: #css data-term="CSS" }\n'
    _convert_as_zensical_page_with_glossary(definition, "page-a.md")
    # Must not raise, even though the same id is (implausibly, but
    # possibly) defined twice across two different pages:
    html = _convert_as_zensical_page_with_glossary(definition, "page-b.md")
    assert 'id="css"' in html


_BIB_FIXTURE = """
@book{skou2023,
  author = {Skoulikari, Angela},
  title = {Learning Git},
  year = {2023},
  publisher = {O'Reilly Media}
}
"""


def _convert_as_zensical_page_with_bibliography(text: str, path: str, bib_file: str) -> str:
    md = markdown.Markdown(
        extensions=[
            ContextExtension(page=Page(url=path, path=path), config={}),
            BibliographyExtension(bib_file=bib_file),
        ]
    )
    return md.convert(text)


@pandoc_required
def test_bibliography_forward_reference_resolves_via_nav_prescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same "cited before defined" ordering problem prodockit.citations/
    prodockit.glossary solve: references.md is usually kept as an appendix
    at the end of nav, but cited from early chapters - unlike those two,
    prodockit.bibliography's own definitions all live in one external .bib
    file, so this is a pre-scan for the \\bibliography *marker's own page*,
    not for individual citation definitions."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(_BIB_FIXTURE, encoding="utf-8")
    (docs_dir / "references.md").write_text("# References\n\n\\bibliography\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["section1.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_bibliography(
        "See \\cite{skou2023}.\n", "section1.md", str(bib_file)
    )
    assert 'href="references.md#ref-skou2023"' in html


@pandoc_required
def test_bibliography_cross_page_citation_from_nested_page_uses_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(_BIB_FIXTURE, encoding="utf-8")
    (docs_dir / "references.md").write_text("# References\n\n\\bibliography\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["starthere/customise.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_bibliography(
        "See \\cite{skou2023}.\n", "starthere/customise.md", str(bib_file)
    )
    assert 'href="../references.md#ref-skou2023"' in html


@pandoc_required
def test_bibliography_prescan_ignores_fenced_documentation_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A doc page showing the \\bibliography marker as a literal example
    inside a fenced code block must not be mistaken for the real marker by
    the raw-text nav pre-scan."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(_BIB_FIXTURE, encoding="utf-8")
    (docs_dir / "extending.md").write_text(
        "Add a marker like this:\n\n``` markdown\n\\bibliography\n```\n", encoding="utf-8"
    )
    (docs_dir / "references.md").write_text("# References\n\n\\bibliography\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["extending.md", "section1.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_bibliography(
        "See \\cite{skou2023}.\n", "section1.md", str(bib_file)
    )
    assert 'href="references.md#ref-skou2023"' in html

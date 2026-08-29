# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Simulates Zensical's per-page build at Prodockit's adapter boundary.

Each page gets a fresh ``Markdown`` instance and an isolated source path.
The installed-wheel acceptance harness exercises the real documented
Zensical CLI; these focused extension tests do not import private types.
"""

import shutil
from pathlib import Path

import markdown
import pytest
from markdown.extensions import Extension

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
    monkeypatch.setattr(prodockit_headings, "_ZENSICAL_PRESEED_STATE", None)
    monkeypatch.setattr(prodockit_citations, "_ZENSICAL_SHARED_REGISTRY", CitationRegistry())
    monkeypatch.setattr(prodockit_glossary, "_ZENSICAL_SHARED_REGISTRY", GlossaryRegistry())
    monkeypatch.setattr(prodockit_bibliography, "_ZENSICAL_SHARED_CACHES", {})
    monkeypatch.setattr(
        prodockit_zensical,
        "current_page_path",
        lambda md: getattr(md, "_prodockit_test_page_path", None),
    )


class _PageContextExtension(Extension):
    """Test double for the page-path API Prodockit's extensions consume."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md._prodockit_test_page_path = self.path


def _page_context(path: str) -> Extension:
    return _PageContextExtension(path)


def _convert_as_zensical_page(text: str, path: str) -> str:
    """Create one fresh Markdown conversion carrying a distinct page path."""
    md = markdown.Markdown(
        extensions=[
            _page_context(path),
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
    assert '<a class="prodockit-ref" href="intro.md#introduction">1 Introduction</a>' in html


def test_cross_page_reference_from_nested_page_uses_relative_path() -> None:
    """Regression test: a top-level record_source ("intro.md") isn't a
    valid link as-is from a page nested in a subdirectory - it needs the
    same "../" prefix a hand-typed relative link between the same two
    pages would need (see the equivalent test for prodockit.citations)."""
    _convert_as_zensical_page("# Introduction\n", "intro.md")
    html = _convert_as_zensical_page("See \\ref{introduction}.\n", "starthere/usage.md")
    assert '<a class="prodockit-ref" href="../intro.md#introduction">1 Introduction</a>' in html


def test_each_page_gets_its_own_source_automatically() -> None:
    """Without explicit source= config (impossible to vary per page via
    zensical.toml alone), each page must still be scoped independently -
    otherwise the second page's clear_source() call would wipe the first
    page's headings before this test's own assertion even runs."""
    _convert_as_zensical_page("# Introduction\n", "intro.md")
    _convert_as_zensical_page("# Setup\n", "setup.md")
    html = _convert_as_zensical_page("See \\ref{introduction} and \\ref{setup}.\n", "summary.md")
    assert '<a class="prodockit-ref" href="intro.md#introduction">1 Introduction</a>' in html
    assert '<a class="prodockit-ref" href="setup.md#setup">1 Setup</a>' in html


def test_same_page_reference_still_uses_bare_fragment_under_zensical() -> None:
    """A reference to a heading on the *same* page keeps the simpler bare
    fragment - only a genuinely cross-page reference needs the page-prefixed
    form."""
    html = _convert_as_zensical_page("# Introduction\n\nSee \\ref{introduction}.\n", "intro.md")
    assert '<a class="prodockit-ref" href="#introduction">1 Introduction</a>' in html


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
    """Without a page context (i.e. not under Zensical), two
    independent conversions must keep behaving exactly as before this fix -
    each gets its own private registry, not the shared Zensical singleton."""
    md1 = markdown.Markdown(extensions=["prodockit.headings"])
    md1.convert("# Introduction\n")
    md2 = markdown.Markdown(extensions=["prodockit.headings", "prodockit.refs"])
    html = md2.convert("See \\ref{introduction}.\n")
    # Page 2 never saw page 1's heading - falls back to unresolved, exactly
    # as it did before Zensical auto-detection existed.
    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def test_ref_resolves_for_a_page_never_rendered_in_this_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for prodockit-extensions#54: `zensical build` doesn't
    guarantee every page renders in one shared Python context, so a page's
    own real registration may never reach the context resolving a
    \\ref{} to it - reported as every id defined on the *first* nav page
    silently rendering "??" on Linux CI, while later pages resolved fine.

    Reproduced deterministically here by converting *only* the referencing
    page, never the page defining the ids - which is exactly what a
    context that didn't render section1.md sees. The nav pre-scan must
    resolve them anyway."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "section1.md").write_text(
        "# Section One\n\n"
        "## Citations example {: #citations-example }\n\n"
        "## Acronyms example {: #acronyms-example }\n",
        encoding="utf-8",
    )
    (docs_dir / "section4.md").write_text(
        "# Section Four\n\nSee \\ref{citations-example}.\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["section1.md", "section4.md"]),
    )
    html = _convert_as_zensical_page(
        "# Section Four\n\nSee \\ref{citations-example} and \\ref{acronyms-example}.\n",
        "section4.md",
    )
    assert (
        '<a class="prodockit-ref" href="section1.md#citations-example">1.1 Citations example</a>'
        in html
    )
    assert (
        '<a class="prodockit-ref" href="section1.md#acronyms-example">1.2 Acronyms example</a>'
        in html
    )
    assert "??" not in html


def _convert_as_zensical_page_with_captions(
    text: str, path: str, *, continuous: bool = False
) -> str:
    md = markdown.Markdown(
        extensions=[
            _page_context(path),
            "attr_list",
            "tables",
            "pymdownx.blocks.caption",
            prodockit_headings.HeadingsExtension(
                numbering="continuous" if continuous else "per-document"
            ),
            "prodockit.refs",
        ],
        extension_configs={
            "pymdownx.blocks.caption": {
                "types": [
                    {
                        "name": "figure-caption",
                        "prefix": "{}.",
                        "classes": "prodockit-figure-caption",
                    },
                    {
                        "name": "table-caption",
                        "prefix": "{}.",
                        "classes": "prodockit-table-caption",
                    },
                ]
            }
        },
    )
    return md.convert(text)


def test_generated_caption_ids_do_not_collide_across_zensical_pages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression for the warning reported after a clean template install.

    pymdown starts its internal caption counter at one on each page. Those
    repeated page-local anchors must not enter Prodockit's shared registry.
    """
    table = """| Item | Value |
|---|---|
| One | 1 |
/// table-caption
Example table
///
"""

    first = _convert_as_zensical_page_with_captions(
        f"# Originality\n\n{table}", "originality.md"
    )
    second = _convert_as_zensical_page_with_captions(
        f"# Section four\n\n{table}", "section4.md"
    )

    assert 'id="__table-caption_1"' in first
    assert 'id="__table-caption_1"' in second
    assert "collides with an existing one" not in caplog.text


def test_forward_cross_page_caption_references_resolve_via_nav_preseed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The later target page is never converted, so only the nav pre-scan
    can resolve these forward references (prodockit-extensions#512)."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    earlier = "# Earlier\n\nSee \\ref{fig-later} and \\ref{tab-later}.\n"
    later = """# Later

![Example](example.png)
/// figure-caption | #fig-later
Later figure
///

| a | b |
| - | - |
| 1 | 2 |
/// table-caption
    attrs: {id: tab-later}

Later table
///
"""
    (docs_dir / "earlier.md").write_text(earlier, encoding="utf-8")
    (docs_dir / "later.md").write_text(later, encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["earlier.md", "later.md"]),
    )

    html = _convert_as_zensical_page_with_captions(earlier, "earlier.md", continuous=True)

    assert '<a class="prodockit-ref" href="later.md#fig-later">Figure 2.1</a>' in html
    assert '<a class="prodockit-ref" href="later.md#tab-later">Table 2.1</a>' in html
    assert "??" not in html


def test_forward_references_resolve_to_two_figures_nested_in_a_later_list_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for the real #512 report after its first fix.

    Caption blocks nested beneath an ordered-list step are indented four
    spaces. Pymdown renders and numbers them, but the raw nav pre-scan used
    to accept at most three spaces and therefore left both earlier-page
    references as ``??``.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    earlier = (
        "# Development journey\n\nThe default values are shown in "
        "\\ref{fig-grafana-admin-username-config} and "
        "\\ref{fig-grafana-admin-password-config}.\n"
    )
    later = """# Test procedure

## Step 8

2. Log in with the configured credentials.

    ![Username](username.png)
    /// figure-caption | #fig-grafana-admin-username-config
    Shows the username field
    ///

    ![Password](password.png)
    /// figure-caption | #fig-grafana-admin-password-config
    Shows the password field
    ///
"""
    (docs_dir / "development-journey.md").write_text(earlier, encoding="utf-8")
    (docs_dir / "test-procedure.md").write_text(later, encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (
            str(docs_dir),
            ["development-journey.md", "test-procedure.md"],
        ),
    )

    html = _convert_as_zensical_page_with_captions(
        earlier, "development-journey.md", continuous=True
    )

    assert (
        '<a class="prodockit-ref" '
        'href="test-procedure.md#fig-grafana-admin-username-config">Figure 2.1</a>' in html
    )
    assert (
        '<a class="prodockit-ref" '
        'href="test-procedure.md#fig-grafana-admin-password-config">Figure 2.2</a>' in html
    )
    assert "??" not in html


def test_forward_cross_page_caption_preseed_preserves_caption_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Id-less captions still consume a number on the real target page."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "earlier.md").write_text("# Earlier\n", encoding="utf-8")
    (docs_dir / "later.md").write_text(
        """# Later

![First](one.png)
/// figure-caption
Unreferenced first figure
///

![Second](two.png)
/// figure-caption | #fig-second
Referenced second figure
///
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["earlier.md", "later.md"]),
    )

    html = _convert_as_zensical_page_with_captions(
        "# Earlier\n\nSee \\ref{fig-second}.\n", "earlier.md", continuous=True
    )

    assert '<a class="prodockit-ref" href="later.md#fig-second">Figure 2.2</a>' in html


def test_forward_cross_page_caption_preseed_uses_appendix_letter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "appendix.md").write_text(
        """---
is_appendix: true
---

# Appendix

![Example](example.png)
/// figure-caption | #fig-appendix
Appendix figure
///
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["earlier.md", "appendix.md"]),
    )

    html = _convert_as_zensical_page_with_captions(
        "# Earlier\n\nSee \\ref{fig-appendix}.\n", "earlier.md", continuous=True
    )

    assert '<a class="prodockit-ref" href="appendix.md#fig-appendix">Figure A.1</a>' in html


def test_caption_preseed_ignores_fenced_documentation_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        """# Guide

```md
/// figure-caption | #not-a-real-figure
Example caption syntax
///
```
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["guide.md", "other.md"]),
    )

    html = _convert_as_zensical_page_with_captions("See \\ref{not-a-real-figure}.\n", "other.md")

    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def test_caption_preseed_ignores_four_space_indented_code_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Four spaces are a caption only inside a four-space-indented list.

    Outside a list they are Markdown's traditional indented code syntax and
    must not become a phantom reference target merely because nested caption
    blocks are now supported.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        """# Guide

    /// figure-caption | #not-a-real-indented-figure
    Example caption syntax
    ///
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["guide.md", "other.md"]),
    )

    html = _convert_as_zensical_page_with_captions(
        "See \\ref{not-a-real-indented-figure}.\n", "other.md"
    )

    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def test_preseeded_heading_is_superseded_by_its_real_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preseeded data is only ever a stand-in - once the defining page is
    actually converted in this context, its real registration (the
    authoritative text/level/number from the parsed tree) must win."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "intro.md").write_text("# Introduction\n", encoding="utf-8")
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["intro.md"]))
    _convert_as_zensical_page("# Introduction\n", "intro.md")
    registry = prodockit_headings._ZENSICAL_SHARED_REGISTRY
    assert registry._headings["introduction"].source == "intro.md"
    assert "introduction" not in registry._preseeded


def test_preseed_ignores_headings_inside_fenced_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A docs page showing heading syntax as a literal example inside a
    fenced code block must not be preseeded as a real heading - the same
    protection the citation/glossary nav pre-scans already have."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        "# Guide\n\n```md\n## Not A Real Heading {: #not-real }\n```\n", encoding="utf-8"
    )
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["guide.md"]))
    html = _convert_as_zensical_page("See \\ref{not-real}.\n", "other.md")
    assert '<a class="prodockit-ref prodockit-ref-unresolved">??</a>' in html


def _convert_as_zensical_page_with_attr_list(text: str, path: str) -> str:
    """As _convert_as_zensical_page, plus 'attr_list' - which every prodockit
    project enables (it's what makes `{: #id }`/`{: .unnumbered }` mean
    anything at all), and which the nav pre-scan therefore assumes when it
    reads those same markers straight out of raw text."""
    md = markdown.Markdown(
        extensions=[
            _page_context(path),
            "attr_list",
            "prodockit.headings",
            "prodockit.refs",
        ]
    )
    return md.convert(text)


def test_preseeded_numbers_match_a_real_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-scan computes section numbers itself, from raw text - they
    have to agree with what HeadingsTreeprocessor produces from the parsed
    tree, including a skipped level (h1 -> h3 numbers "1.1.1", not "1.0.1")
    and an .unnumbered heading consuming no counter position."""
    page = "# Cover {: .unnumbered }\n\n# One\n\n### Deep\n\n## Two\n\n# Three\n"
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page.md").write_text(page, encoding="utf-8")
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["page.md"]))
    # Preseeded only - this context never converts page.md itself.
    _convert_as_zensical_page_with_attr_list("placeholder\n", "other.md")
    preseeded = dict(prodockit_headings._ZENSICAL_SHARED_REGISTRY._preseeded)

    # Now the real thing, in a registry of its own.
    monkeypatch.setattr(prodockit_headings, "_ZENSICAL_SHARED_REGISTRY", IdRegistry())
    monkeypatch.setattr(
        prodockit_headings, "_ZENSICAL_PRESEED_STATE", ((False, "is_appendix"), None)
    )
    _convert_as_zensical_page_with_attr_list(page, "page.md")
    real = prodockit_headings._ZENSICAL_SHARED_REGISTRY._headings

    assert {k: v.number for k, v in preseeded.items()} == {k: v.number for k, v in real.items()}
    assert real["deep"].number == "1.1.1"
    assert real["cover"].number is None


def test_preseeded_numbers_are_redone_when_refs_preseeds_first_with_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extension order isn't guaranteed, so prodockit.refs' extendMarkdown can
    run first and create a *default* HeadingsExtension (per-document
    numbering) of its own - which would otherwise trigger the nav pre-scan
    with the wrong settings and latch it, leaving every cross-page reference
    showing a per-document number instead of the configured continuous one.

    Caught by real repeated `zensical build` runs: ~1 in 12 rendered
    \\ref{} to a heading on page two as "1.1" instead of "2.1"."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# Page One\n", encoding="utf-8")
    (docs_dir / "two.md").write_text("# Page Two\n\n## Target {: #target }\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["one.md", "two.md"])
    )
    # 'prodockit.refs' listed *before* 'prodockit.headings' - the order that
    # makes refs build its own default HeadingsExtension first.
    md = markdown.Markdown(
        extensions=[
            _page_context("one.md"),
            "attr_list",
            "prodockit.refs",
            "prodockit.headings",
        ],
        extension_configs={"prodockit.headings": {"numbering": "continuous"}},
    )
    html = md.convert("# Page One\n\nSee \\ref{target}.\n")
    # Page Two's h1 is the second in nav order, so its "Target" subheading is
    # 2.1 under continuous numbering - not 1.1.
    assert '<a class="prodockit-ref" href="two.md#target">2.1 Target</a>' in html


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
            _page_context(path),
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
    _convert_as_zensical_page_with_continuous_headings("# App Heading\n\n## Sub\n", "appendix.md")
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
                _page_context(path),
                prodockit_headings.HeadingsExtension(numbering="continuous"),
                "prodockit.refs",
            ]
        )
        return md.convert(text)

    _convert("# One\n", "page1.md")
    _convert("# Two\n", "page2.md")
    html = _convert("See \\ref{two}.\n", "page3.md")
    assert '<a class="prodockit-ref" href="page2.md#two">2 Two</a>' in html


def _convert_as_zensical_page_with_citations(text: str, path: str) -> str:
    md = markdown.Markdown(
        extensions=[
            _page_context(path),
            "attr_list",
            "prodockit.citations",
        ]
    )
    return md.convert(text)


def test_cross_page_citation_resolves_under_zensical() -> None:
    _convert_as_zensical_page_with_citations(
        'Skoulikari, A. (2023) *Learning Git*.\n{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        "references.md",
    )
    html = _convert_as_zensical_page_with_citations("See \\citeref{skou2023}.\n", "section1.md")
    # A real cross-page link (references.md#skou2023), not a bare
    # same-page fragment - the latter would 404 on the actual website.
    assert (
        '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>'
        in html
    )


def test_cross_page_citation_from_nested_page_uses_relative_path() -> None:
    """Regression test: a top-level record_source ("references.md") isn't a
    valid link as-is from a page nested in a subdirectory - it needs the
    same "../" prefix a hand-typed relative link between the same two
    pages would need."""
    _convert_as_zensical_page_with_citations(
        'Skoulikari, A. (2023) *Learning Git*.\n{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        "references.md",
    )
    html = _convert_as_zensical_page_with_citations(
        "See \\citeref{skou2023}.\n", "starthere/customise.md"
    )
    assert (
        '<a class="prodockit-cite-resolved" href="../references.md#skou2023">Skoulikari, 2023</a>'
        in html
    )


def test_same_page_citation_still_uses_bare_fragment_under_zensical() -> None:
    html = _convert_as_zensical_page_with_citations(
        "Skoulikari, A. (2023) *Learning Git*.\n"
        '{: #skou2023 data-cite-text="Skoulikari, 2023" }\n\n'
        "See \\citeref{skou2023}.\n",
        "references.md",
    )
    assert '<a class="prodockit-cite-resolved" href="#skou2023">Skoulikari, 2023</a>' in html


def test_duplicate_citation_key_across_pages_does_not_crash_the_build() -> None:
    definition = (
        'Skoulikari, A. (2023) *Learning Git*.\n{: #skou2023 data-cite-text="Skoulikari, 2023" }\n'
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
        'Skoulikari, A. (2023) *Learning Git*.\n{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["section1.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_citations("See \\citeref{skou2023}.\n", "section1.md")
    assert (
        '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>'
        in html
    )


def test_nav_preseed_ignores_fenced_documentation_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A doc page showing prodockit.citations' own definition syntax as a
    literal example inside a fenced code block must not be mistaken for a
    real definition by the raw-text nav pre-scan (which, unlike
    CitationDefTreeprocessor, isn't fence-aware via the real parser).
    Regression test for a real bug: a page with such an example earlier in
    nav order than the real references page was "winning" the preseed
    slot, sending every \\citeref{skou2023} to the wrong page."""
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
        'Skoulikari, A. (2023) *Learning Git*.\n{: #skou2023 data-cite-text="Skoulikari, 2023" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["customise.md", "section1.md", "references.md"]),
    )
    html = _convert_as_zensical_page_with_citations("See \\citeref{skou2023}.\n", "section1.md")
    assert (
        '<a class="prodockit-cite-resolved" href="references.md#skou2023">Skoulikari, 2023</a>'
        in html
    )


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
            _page_context(path),
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
    html = _convert_as_zensical_page_with_glossary("This uses \\gls{css}.\n", "section1.md")
    # A real cross-page link (acronyms.md#css), not a bare same-page
    # fragment - the latter would 404 on the actual website.
    assert '<a class="prodockit-gls" href="acronyms.md#css">CSS</a>' in html


def test_cross_page_gls_from_nested_page_uses_relative_path() -> None:
    """Regression test: a top-level record_source ("acronyms.md") isn't a
    valid link as-is from a page nested in a subdirectory - it needs the
    same "../" prefix a hand-typed relative link between the same two
    pages would need (see the equivalent test for prodockit.citations)."""
    _convert_as_zensical_page_with_glossary(
        '**CSS** - Cascading Style Sheets.\n{: #css data-term="CSS" }\n',
        "acronyms.md",
    )
    html = _convert_as_zensical_page_with_glossary(
        "This uses \\gls{css}.\n", "starthere/customise.md"
    )
    assert '<a class="prodockit-gls" href="../acronyms.md#css">CSS</a>' in html


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
    html = _convert_as_zensical_page_with_glossary("This uses \\gls{css}.\n", "section1.md")
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
            _page_context(path),
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


@pandoc_required
def test_bibliography_cross_links_to_the_page_whose_marker_defines_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#89: a build with two \\bibliography{...}
    markers on two different pages, drawing from two different files -
    a References page (cited_only=true, the default bib_file) and a
    separate Bibliography/Further-reading page (a broader background.bib).
    A \\cite{id} should cross-link to whichever page's marker actually
    lists that entry - here, references.md, since skou2023 lives in
    refs.bib, not background.bib."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(_BIB_FIXTURE, encoding="utf-8")
    background_file = tmp_path / "background.bib"
    background_file.write_text(
        "@book{knuth1997,\n"
        "  author = {Knuth, Donald},\n"
        "  title = {The Art of Computer Programming},\n"
        "  year = {1997},\n"
        "  publisher = {Addison-Wesley}\n"
        "}\n",
        encoding="utf-8",
    )
    (docs_dir / "section1.md").write_text("See \\cite{skou2023}.\n", encoding="utf-8")
    (docs_dir / "references.md").write_text(
        "# References\n\n\\bibliography{}{true}\n", encoding="utf-8"
    )
    (docs_dir / "bibliography.md").write_text(
        f"# Bibliography\n\n\\bibliography{{{background_file}}}\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["section1.md", "references.md", "bibliography.md"]),
    )
    html = _convert_as_zensical_page_with_bibliography(
        "See \\cite{skou2023}.\n", "section1.md", str(bib_file)
    )
    assert 'href="references.md#ref-skou2023"' in html

    references_html = _convert_as_zensical_page_with_bibliography(
        "\\bibliography{}{true}\n", "references.md", str(bib_file)
    )
    assert "Skoulikari" in references_html
    assert "Knuth" not in references_html

    bibliography_html = _convert_as_zensical_page_with_bibliography(
        f"\\bibliography{{{background_file}}}\n", "bibliography.md", str(bib_file)
    )
    assert "Knuth" in bibliography_html
    assert "Skoulikari" not in bibliography_html


def test_heading_prescan_picks_up_a_page_edited_since_the_last_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test (#99): under `zensical serve` the process outlives the
    files. prodockit.headings caches its nav-wide pre-scan because the scan
    reads every page (repeating it per page would be O(pages^2)), but that
    cache used to be keyed on the numbering settings alone - so an edit to a
    page *this* render doesn't touch was invisible, and a \\ref{} to it kept
    resolving against the pre-scan taken when the server started.

    Keying the cache on nav_signature() as well - one stat() per page, far
    cheaper than the scan - invalidates it when a page really does change.
    Simulated here by rendering one page, editing a *different* page on
    disk, then rendering the first page again in the same process.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    referencing = docs_dir / "page.md"
    referencing.write_text("# Page\n", encoding="utf-8")
    defining = docs_dir / "other.md"
    defining.write_text("# Other\n\n## Target {: #target }\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page.md", "other.md"]),
    )

    _convert_as_zensical_page_with_attr_list(referencing.read_text(), "page.md")
    before = prodockit_headings._ZENSICAL_SHARED_REGISTRY.get("target")
    assert before is not None and before.number == "1.1"

    # The author adds a heading ahead of the target, on a page this render
    # never touches - "1.1" is now "1.2".
    defining.write_text(
        "# Other\n\n## Inserted {: #inserted }\n\n## Target {: #target }\n", encoding="utf-8"
    )
    _convert_as_zensical_page_with_attr_list(referencing.read_text(), "page.md")

    after = prodockit_headings._ZENSICAL_SHARED_REGISTRY.get("target")
    assert after is not None
    assert after.number == "1.2", (
        f"Heading pre-scan went stale: target still numbered {after.number}, "
        "so the cached scan survived an edit to another page (#99)"
    )

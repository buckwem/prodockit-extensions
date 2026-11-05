# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Assertions over the built rendering catalogue website and PDF."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from bs4 import BeautifulSoup

pytestmark = pytest.mark.built

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_ROOT = ROOT / "tests" / "rendering_catalogue"
DOCS = CATALOGUE_ROOT / "docs"
SITE = CATALOGUE_ROOT / "site"
PDF = CATALOGUE_ROOT / "build" / "rendering-catalogue.pdf"


def _load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _site_path(markdown_path: str) -> Path:
    source = Path(markdown_path)
    if source.name == "index.md":
        return SITE / source.parent / "index.html"
    return SITE / source.with_suffix("") / "index.html"


def _soup(markdown_path: str) -> BeautifulSoup:
    return BeautifulSoup(_site_path(markdown_path).read_text(encoding="utf-8"), "html.parser")


def test_every_implemented_capability_and_required_nested_case_has_a_built_anchor() -> None:
    capabilities = _load(CATALOGUE_ROOT / "catalogue.toml")["capability"]

    for item in capabilities:
        if item["status"] != "implemented":
            continue
        assert _soup(item["page"]).select_one(f"#{item['anchor']}") is not None, item["id"]
        if item["nested"] == "required":
            assert (
                _soup(item["nested_page"]).select_one(f"#{item['nested_anchor']}") is not None
            ), item["id"]


def test_core_markdown_has_representative_inline_and_block_output() -> None:
    article = _soup("markdown/index.md").select_one("article.md-content__inner")
    assert article is not None
    assert article.select_one("strong") is not None
    assert article.select_one("em") is not None
    assert article.select_one("blockquote") is not None
    assert article.select_one("ul ul") is not None
    assert article.select_one("ol") is not None
    assert article.select_one("hr") is not None
    assert article.select_one("pre code") is not None
    image = article.select_one('img[alt="Two panels showing website output flowing to PDF output"]')
    assert image is not None
    assert image.get("src", "").endswith("assets/core-sample.svg")


def test_python_markdown_extensions_have_their_expected_html_shapes() -> None:
    abbreviation = _soup("python-markdown/abbreviations.md")
    assert abbreviation.select_one('article abbr[title="HyperText Markup Language"]') is not None

    admonitions = _soup("python-markdown/admonitions.md")
    assert admonitions.select_one("article .admonition.note") is not None
    assert admonitions.select_one("article .admonition.warning") is not None
    assert admonitions.select_one("article .admonition.tip") is not None

    attributes = _soup("python-markdown/attribute-lists.md")
    target = attributes.select_one("article #attribute-target.catalogue-accent")
    assert target is not None and target.get("data-review") == "attribute-list"
    assert attributes.select_one("article a#attribute-link.md-button") is not None

    definitions = _soup("python-markdown/definition-lists.md")
    assert [item.get_text(" ", strip=True) for item in definitions.select("article dl dt")] == [
        "Website",
        "PDF",
    ]
    assert len(definitions.select("article dl dd")) == 2

    footnotes = _soup("python-markdown/footnotes.md")
    assert footnotes.select_one("article a.footnote-ref") is not None
    assert footnotes.select_one("article .footnote a.footnote-backref") is not None

    markdown_in_html = _soup("python-markdown/markdown-in-html.md")
    container = markdown_in_html.select_one("article div.markdown-in-html-sample")
    assert container is not None
    assert container.select_one("strong") is not None
    assert len(container.select("li")) == 2

    table = _soup("python-markdown/tables.md").select_one("article table")
    assert table is not None
    assert [cell.get("style") for cell in table.select("thead th")] == [
        "text-align: left;",
        "text-align: center;",
        "text-align: right;",
    ]


def test_table_of_contents_settings_change_the_built_page() -> None:
    page = _soup("python-markdown/table-of-contents.md")
    secondary = page.select("nav.md-nav--secondary")

    assert secondary
    assert all(item.get("aria-label") == "Catalogue contents" for item in secondary)
    assert page.select_one("#mixed-case-heading") is not None
    assert page.select_one(
        'a.headerlink[title="Permanent link to this catalogue section"]'
    ) is not None
    assert any(nav.select_one('a[href="#included-level-three-heading"]') for nav in secondary)
    assert not any(nav.select_one('a[href="#excluded-level-four-heading"]') for nav in secondary)


def test_nested_core_and_python_markdown_shapes_are_real() -> None:
    page = _soup("nested-content/python-markdown.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None
    assert article.select_one("blockquote strong") is not None
    assert article.select_one("blockquote ol") is not None

    admonition = article.select_one(".admonition.info")
    assert admonition is not None
    assert admonition.select_one('abbr[title="HyperText Markup Language"]') is not None
    assert admonition.select_one("dl") is not None
    assert admonition.select_one("table") is not None
    assert admonition.select_one('#nested-attribute-target[data-review="nested-attribute"]')
    assert admonition.select_one(".nested-markdown-in-html strong") is not None
    assert article.select_one("li a.footnote-ref") is not None


def test_pymdown_maths_captions_formatting_and_details_render_semantically() -> None:
    maths = _soup("pymdown/maths-and-captions.md")
    assert maths.select_one("article span.arithmatex") is not None
    assert maths.select_one("article div.arithmatex") is not None
    figure = maths.select_one("article figure")
    assert figure is not None
    assert figure.select_one('img[alt="Website output flows to PDF output"]') is not None
    assert figure.select_one("figcaption").get_text(" ", strip=True) == (
        "Phase 3 caption attached to an image"
    )

    formatting = _soup("pymdown/formatting-and-details.md")
    for selector in ("article ins", "article sup", "article mark", "article del", "article sub"):
        assert formatting.select_one(selector) is not None
    details = formatting.select_one("article details.note[open]")
    assert details is not None
    assert details.select_one("summary").get_text(" ", strip=True) == "Expanded review details"
    assert "This body can be collapsed on the website." in details.get_text(" ", strip=True)


def test_pymdown_emoji_highlighting_keys_and_symbols_render_semantically() -> None:
    emoji = _soup("pymdown/emoji.md")
    icons = emoji.select("article span.twemoji svg")
    assert len(icons) == 2
    assert emoji.select_one('article span.twemoji[title="Bundled test-tube icon"]') is not None
    assert emoji.select_one('article span.twemoji[title="Custom Phase 3 icon"]') is not None

    code = _soup("pymdown/code-highlighting.md")
    block = code.select_one("article div.language-python.highlight")
    assert block is not None
    assert block.select_one(".filename").get_text(" ", strip=True) == "Python"
    assert len(block.select("span.linenos")) == 2
    assert len(block.select('span[id^="__span-"]')) == 2
    assert len(block.select('a[href^="#__codelineno-"]')) == 2
    assert code.select_one("article code.language-python.highlight") is not None

    symbols = _soup("pymdown/keys-and-symbols.md")
    assert [key.get_text(" ", strip=True) for key in symbols.select("article kbd")] == [
        "Ctrl",
        "Alt",
        "Del",
    ]
    rendered_text = symbols.select_one("article").get_text(" ", strip=True)
    for marker in ("©", "™", "½", "→", "←"):
        assert marker in rendered_text


def test_pymdown_snippets_superfences_tabs_and_tasks_render_semantically() -> None:
    snippets = _soup("pymdown/snippets.md")
    article = snippets.select_one("article.md-content__inner")
    assert article is not None
    assert article.select_one("pre code").get_text(" ", strip=True).startswith("--8<--")
    rendered = [
        paragraph.get_text(" ", strip=True)
        for paragraph in article.select("p")
        if "checked-in Phase 3 snippet file" in paragraph.get_text()
    ]
    assert rendered == ["This sentence came from the checked-in Phase 3 snippet file."]

    fences = _soup("pymdown/superfences.md")
    assert fences.select_one("article .admonition.note .language-python.highlight") is not None
    custom = fences.select_one("article pre.catalogue-fence code")
    assert custom is not None and custom.get_text(strip=True) == "phase three custom fence"

    tabs = _soup("pymdown/tabs.md")
    tab_set = tabs.select_one("article .tabbed-set.tabbed-alternate")
    assert tab_set is not None
    assert [item.get("id") for item in tab_set.select('input[type="radio"]')] == [
        "review-group-mixed-case-tab",
        "review-group-second-tab",
    ]
    assert [item.get_text(" ", strip=True) for item in tab_set.select(".tabbed-block")] == [
        "First tab body.",
        "Second tab body.",
    ]

    tasks = _soup("pymdown/task-lists.md")
    inputs = tasks.select("article ul.task-list input[type=checkbox]")
    assert len(inputs) == 2
    assert inputs[0].has_attr("checked") and not inputs[1].has_attr("checked")
    assert all(not item.has_attr("disabled") for item in inputs)


def test_nested_pymdown_shapes_cover_every_required_phase_three_case() -> None:
    page = _soup("nested-content/pymdown.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None
    assert article.select_one(".admonition.info span.arithmatex") is not None
    assert article.select_one("blockquote figure figcaption") is not None
    assert article.select_one("ol details.note") is not None
    assert len(article.select(".admonition.tip span.twemoji svg")) == 2
    assert len(article.select(".admonition.tip kbd")) == 3
    assert article.select_one(".tabbed-set .language-python.highlight") is not None
    snippet_heading = article.select_one("#nested-snippet")
    assert snippet_heading is not None
    assert snippet_heading.find_next("blockquote").get_text(" ", strip=True) == (
        "This sentence came from the checked-in Phase 3 snippet file."
    )
    assert article.select_one(".admonition.note pre.catalogue-fence") is not None
    assert article.select_one(".admonition.example .tabbed-set.tabbed-alternate") is not None
    assert article.select_one("blockquote ul.task-list") is not None


def test_phase_two_specimens_are_present_in_the_catalogue_pdf() -> None:
    assert PDF.is_file()
    with pymupdf.open(PDF) as document:
        assert document.page_count >= 12
        text = "\n".join(page.get_text() for page in document)

    for marker in (
        "Core Markdown",
        "HyperText Markup Language",
        "Reviewed warning",
        "This is the review footnote content.",
        "Markdown remains active",
        "Mixed CASE heading",
        "Core and Python-Markdown nesting",
        "This footnote was referenced from inside a list item.",
    ):
        assert marker in text


def test_phase_three_specimens_and_static_fallbacks_are_present_in_the_catalogue_pdf() -> None:
    assert PDF.is_file()
    with pymupdf.open(PDF) as document:
        assert document.page_count >= 35
        pages = [(page.get_text(), len(page.get_drawings())) for page in document]
        text = "\n".join(page_text for page_text, _ in pages)
        maths_page = next(
            page for page in document if "The website uses MathJax to typeset" in page.get_text()
        )
        words = maths_page.get_text("words")
        trailing_stop = next(word for word in words if word[4] == ".")
        inline_label = next(
            word
            for word in words
            if word[4] == "mathematics:" and abs(word[1] - trailing_stop[1]) < 2
        )
        assert any(
            inline_label[2] < drawing["rect"].x0 < trailing_stop[0]
            for drawing in maths_page.get_drawings()
        ), "inline Arithmatex is absent from the catalogue PDF"

    for marker in (
        "Phase 3 caption attached to an image",
        "Expanded review details",
        "This body can be collapsed on the website.",
        "Ctrl + Alt + Del",
        "© ™ ½ → ←",
        "This sentence came from the checked-in Phase 3 snippet file.",
        "phase three custom fence",
        "Mixed CASE Tab",
        "First tab body.",
        "Second tab body.",
        "Phase 3 implemented",
        "Visual review pending",
        "Nested task complete",
        "Nested task pending",
    ):
        assert marker in text

    maths_page = next(
        drawings
        for page_text, drawings in pages
        if "The website uses MathJax to typeset" in page_text
    )
    emoji_page = next(
        drawings for page_text, drawings in pages if "The custom icon directory" in page_text
    )
    assert maths_page >= 10
    assert emoji_page >= 8

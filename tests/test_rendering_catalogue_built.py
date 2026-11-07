# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Assertions over the built rendering catalogue website and PDF."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from bs4 import BeautifulSoup

from tools import rendering_catalogue as review_bundle

pytestmark = pytest.mark.built

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_ROOT = ROOT / "tests" / "rendering_catalogue"
DOCS = CATALOGUE_ROOT / "docs"
SITE = CATALOGUE_ROOT / "site"
PDF = CATALOGUE_ROOT / "build" / "rendering-catalogue.pdf"
BUNDLE = CATALOGUE_ROOT / "build" / "review-bundle"


def _load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _site_path(markdown_path: str) -> Path:
    source = Path(markdown_path)
    if source.name == "index.md":
        return SITE / source.parent / "index.html"
    return SITE / source.with_suffix("") / "index.html"


def _soup(markdown_path: str) -> BeautifulSoup:
    return BeautifulSoup(_site_path(markdown_path).read_text(encoding="utf-8"), "html.parser")


def _pdf_text_pages() -> list[str]:
    with pymupdf.open(PDF) as document:
        return [page.get_text() for page in document]


def _marker_pages(pages: list[str], marker: str) -> set[int]:
    return {number for number, text in enumerate(pages, start=1) if marker in text}


def _compact_marker_pages(pages: list[str], marker: str) -> set[int]:
    compact_marker = "".join(marker.split())
    return {
        number
        for number, text in enumerate(pages, start=1)
        if compact_marker in "".join(text.split())
    }


def test_phase_six_review_bundle_is_complete_and_self_consistent() -> None:
    review_bundle.verify()
    sources = review_bundle.catalogue_sources()
    page_pdfs = sorted((BUNDLE / "page-pdfs").rglob("*.pdf"))
    assert len(page_pdfs) == len(sources)
    assert all(path.read_bytes().startswith(b"%PDF-") for path in page_pdfs)

    report = json.loads((BUNDLE / "coverage-report.json").read_text(encoding="utf-8"))
    capabilities = _load(CATALOGUE_ROOT / "catalogue.toml")["capability"]
    assert len(report["capabilities"]) == len(capabilities)
    assert all(item["source_url"] for item in report["capabilities"])
    assert all(item["complete_pdf"] == "rendering-catalogue.pdf" for item in report["capabilities"])

    layers = json.loads((BUNDLE / "test-layers.json").read_text(encoding="utf-8"))
    assert [layer["name"] for layer in layers["layers"]] == [
        "inventory",
        "source/config",
        "strict build",
        "website semantics",
        "PDF semantics",
        "visual review",
    ]
    assert (BUNDLE / "test-layers.html").is_file()

    with pymupdf.open(BUNDLE / "rendering-catalogue.pdf") as document:
        assert len(list((BUNDLE / "thumbnails").glob("page-*.png"))) == document.page_count


def test_phase_six_hidden_website_has_crawler_metadata_without_discovery_files() -> None:
    expected = {"noindex", "nofollow", "noarchive", "nosnippet", "noimageindex"}
    for page in BUNDLE.rglob("*.html"):
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        metadata = soup.select_one('meta[name="robots"]')
        assert metadata is not None, page
        assert {item.strip() for item in metadata.get("content", "").split(",")} == expected
    assert not list(BUNDLE.rglob("search.json"))
    assert not list(BUNDLE.rglob("sitemap.xml"))

    report = BeautifulSoup(
        (BUNDLE / "coverage-report.html").read_text(encoding="utf-8"), "html.parser"
    )
    assert len(report.select("tbody tr")) == 73
    assert report.select_one('a[href="rendering-catalogue.pdf"]') is not None
    assert report.select_one('a[href^="page-pdfs/"]') is not None


def test_every_implemented_capability_and_required_nested_case_has_a_built_anchor() -> None:
    capabilities = _load(CATALOGUE_ROOT / "catalogue.toml")["capability"]

    for item in capabilities:
        if item["status"] != "implemented":
            continue
        assert _soup(item["page"]).select_one(f"#{item['anchor']}") is not None, item["id"]
        if item["nested"] == "required":
            assert _soup(item["nested_page"]).select_one(f"#{item['nested_anchor']}") is not None, (
                item["id"]
            )


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
    assert (
        page.select_one('a.headerlink[title="Permanent link to this catalogue section"]')
        is not None
    )
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


def test_phase_four_zensical_authoring_and_configured_integrations_render() -> None:
    layout = _soup("zensical-authoring/layout-and-integrations.md")
    assert layout.title is not None
    assert layout.title.get_text(strip=True).startswith("Layout and integrations specimen")
    description = layout.select_one('meta[name="description"]')
    assert description is not None
    assert description.get("content") == (
        "Phase 4 review cases for Zensical layout and configured integrations."
    )
    assert layout.select_one('.md-status--new[title="Added for Phase 4 review"]') is not None
    assert layout.select_one("article strong em") is not None
    assert (
        layout.select_one('article a[href="https://example.com/catalogue-phase-four"]') is not None
    )
    assert layout.select_one("article a.md-button.md-button--primary") is not None
    assert len(layout.select("article .grid.cards > ul > li")) == 2
    image = layout.select_one('article a.glightbox > img[loading="lazy"]')
    assert image is not None and image.get("width") == "360"
    assert layout.select_one('article a[title="Phase 4 tooltip text"]') is not None
    assert "Phase 4 macro output" in layout.select_one("article").get_text(" ", strip=True)

    diagram = _soup("zensical-authoring/diagrams.md")
    mermaid = diagram.select_one("article pre.mermaid code")
    assert mermaid is not None and "S[Source specimen]" in mermaid.get_text()


def test_phase_four_prodockit_extensions_render_semantically() -> None:
    page = _soup("prodockit/index.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    section_ref = article.select_one('a.prodockit-ref[href="#prodockit-review-target"]')
    assert section_ref is not None
    assert section_ref.get_text(" ", strip=True).startswith("24.1.1")
    assert article.select_one('a.prodockit-autoref[href="#prodockit-review-target"]')
    citation = article.select_one('span.prodockit-cite a[href="#catalogue-source"]')
    assert citation is not None and "Catalogue Maintainers, 2026" in citation.get_text()
    assert article.select_one("p.reference#catalogue-source") is not None
    assert article.select_one('a.prodockit-gls[href="#css"]') is not None
    assert article.select_one("dd.glossary#css") is not None

    figure = article.select_one("figure.prodockit-table-caption#tab-phase-four-output")
    assert figure is not None
    assert (
        figure.select_one("figcaption").get_text(" ", strip=True).endswith("Phase 4 output review")
    )
    assert figure.select_one('table.prodockit-table-sized col[style="width: 34%;"]')
    assert len(article.select(".prodockit-tree li")) == 4
    assert [
        item.get_text(" ", strip=True)
        for item in article.select(".prodockit-steps .prodockit-step-title")
    ] == ["Build the website", "Build the PDF"]

    bib_citation = article.select_one('span.prodockit-bib-cite a[href="#ref-chacon2014"]')
    assert bib_citation is not None
    assert "Pro Git" in article.select_one("#ref-chacon2014").get_text(" ", strip=True)
    assert "\\index{" not in article.get_text(" ", strip=True)


def test_phase_four_nested_authoring_and_prodockit_cases_render() -> None:
    authoring = _soup("nested-content/zensical-authoring.md")
    assert authoring.select_one("article .admonition strong em") is not None
    assert (
        authoring.select_one('article .admonition a[href="https://example.com/nested-phase-four"]')
        is not None
    )
    assert "Phase 4 macro output" in authoring.select_one("article").get_text(" ", strip=True)
    assert authoring.select_one("article .admonition a.md-button") is not None
    assert authoring.select_one("article .grid.cards a.glightbox > img") is not None
    assert authoring.select_one("article .admonition pre.mermaid code") is not None

    prodockit = _soup("nested-content/prodockit.md")
    assert prodockit.select_one("article .admonition a.prodockit-ref") is not None
    assert prodockit.select_one("article blockquote a.prodockit-cite-resolved") is not None
    assert prodockit.select_one("article blockquote a.prodockit-gls") is not None
    assert prodockit.select_one("article .admonition figure.prodockit-table-caption")
    assert prodockit.select_one("article .admonition .prodockit-tree") is not None
    assert len(prodockit.select("article .admonition .prodockit-steps > li")) == 2


def test_phase_five_nested_matrix_and_added_combinations_render_semantically() -> None:
    matrix = _soup("nested-content/index.md")
    matrix_heading = matrix.select_one("article #nested-matrix")
    assert matrix_heading is not None
    table = matrix_heading.find_next("table")
    assert table is not None
    assert len(table.select("tbody tr")) == 11
    assert len(table.select("a[href]")) >= 10

    python_markdown = _soup("nested-content/python-markdown.md")
    list_heading = python_markdown.select_one("article #nested-list-combinations")
    assert list_heading is not None
    outer_list = list_heading.find_next("ul")
    assert outer_list is not None
    assert outer_list.select_one("ol") is not None
    assert outer_list.select_one("ol ul") is not None
    assert outer_list.select_one("a") is not None

    authoring = _soup("nested-content/zensical-authoring.md")
    table_heading = authoring.select_one("article #nested-table-cells")
    assert table_heading is not None
    nested_table = table_heading.find_next("table")
    assert nested_table is not None
    assert nested_table.select_one("a") is not None
    assert nested_table.select_one("code") is not None
    assert nested_table.select_one("abbr") is not None
    assert nested_table.select_one("span.arithmatex") is not None
    assert nested_table.select_one("span.twemoji svg") is not None


def test_complex_indentation_combinations_retain_their_container_hierarchy() -> None:
    page = _soup("nested-content/complex-combinations.md")

    list_section = page.select_one("#complex-list-admonition")
    assert list_section is not None
    ordered = list_section.find_next("ol")
    assert ordered is not None
    assert len(ordered.find_all("li", recursive=False)) == 2
    list_admonition = ordered.select_one("li > .admonition.note")
    assert list_admonition is not None
    assert len(list_admonition.select("ul > li")) == 2
    assert "pdk diag" in list_admonition.select_one("pre code").get_text()

    tabs_section = page.select_one("#complex-tabs-grid")
    assert tabs_section is not None
    tabs = tabs_section.find_next("div", class_="tabbed-set")
    assert tabs is not None
    assert len(tabs.select(":scope > .tabbed-content > .tabbed-block")) == 2
    assert len(tabs.select(".tabbed-block .grid.cards > ul > li")) == 2
    assert tabs.select_one(".grid.cards .admonition.tip") is not None

    grid_section = page.select_one("#complex-grid-list-admonition")
    assert grid_section is not None
    grid = grid_section.find_next("div", class_="grid")
    assert grid is not None
    assert len(grid.select(":scope > ul > li")) == 2
    assert grid.select_one("ol > li > .admonition.warning") is not None
    assert grid.select_one("ul ul ol ul") is not None

    steps_section = page.select_one("#complex-steps-tabs-grid")
    assert steps_section is not None
    steps = steps_section.find_next("ol", class_="prodockit-steps")
    assert steps is not None
    assert len(steps.find_all("li", recursive=False)) == 2
    assert steps.select_one(".tabbed-set .admonition.info") is not None
    assert len(steps.select(".grid.cards > ul > li")) == 2
    assert steps.select_one(".grid.cards .admonition.success") is not None

    source_blocks = page.select("article .language-markdown.highlight")
    assert len(source_blocks) == 4
    assert "!!! note" in source_blocks[0].get_text()
    assert '=== "Website review"' in source_blocks[1].get_text()
    assert '<div class="grid cards" markdown>' in source_blocks[2].get_text()
    assert "/// steps" in source_blocks[3].get_text()


def test_complex_indentation_combinations_flatten_cleanly_in_the_page_pdf() -> None:
    path = BUNDLE / "page-pdfs" / "nested-content" / "complex-combinations.pdf"
    with pymupdf.open(path) as document:
        text = "\n".join(page.get_text() for page in document)

    for marker in (
        "List-owned call-out",
        "Card-owned call-out",
        "List-owned warning",
        "Tab-owned call-out",
        "Final nested result",
        "pdk diag",
        "zensical build --clean --strict",
    ):
        assert marker in text
    assert text.count("Markdown used") == 4
    assert "!!! note" in text
    assert '<div class="grid cards" markdown>' in text


def test_deep_admonition_examples_retain_all_container_levels() -> None:
    page = _soup("nested-content/deep-admonitions.md")

    tab_section = page.select_one("#deep-tab-list-admonition-code")
    assert tab_section is not None
    tabs = tab_section.find_next("div", class_="tabbed-set")
    assert tabs is not None
    warning = tabs.select_one(".tabbed-block ol > li > .admonition.warning")
    assert warning is not None
    assert len(warning.select("ul > li")) == 2
    assert "pdk config --check" in warning.select_one("pre code").get_text()

    grid_section = page.select_one("#deep-grid-admonition-steps")
    assert grid_section is not None
    grid = grid_section.find_next("div", class_="grid")
    assert grid is not None
    cards = grid.select(":scope > ul > li")
    assert len(cards) == 2
    procedure = cards[0].select_one(".admonition.example .prodockit-steps")
    assert procedure is not None
    assert len(procedure.find_all("li", recursive=False)) == 2
    assert procedure.select_one("ul > li") is not None
    assert "pdk diag" in procedure.select_one("pre code").get_text()
    assert "Stable sibling card" in cards[1].get_text(" ", strip=True)

    source_blocks = page.select("article .language-markdown.highlight")
    assert len(source_blocks) == 2
    assert '=== "Deep review path"' in source_blocks[0].get_text()
    assert "/// steps" in source_blocks[1].get_text()


def test_deep_admonition_examples_flatten_cleanly_in_the_page_pdf() -> None:
    path = BUNDLE / "page-pdfs" / "nested-content" / "deep-admonitions.pdf"
    with pymupdf.open(path) as document:
        text = "\n".join(page.get_text() for page in document)

    for marker in (
        "Four-level warning",
        "pdk config --check",
        "Card-owned procedure",
        "Inspect the nested structure",
        "Run the nested check",
        "Stable sibling card",
    ):
        assert marker in text
    assert text.count("Markdown used") == 2
    assert "!!! warning" in text
    assert '<div class="grid cards" markdown>' in text


def test_phase_five_page_boundary_website_specimens_remain_reviewable() -> None:
    kept = _soup("page-breaks/forced-and-kept.md")
    assert kept.select_one("article #pb-forced-after-start") is not None
    assert kept.select_one("article #pb-forced-after-end") is not None
    assert kept.select_one("article #pb-keep-box.catalogue-keep-together") is not None
    assert len(kept.select("article .catalogue-boundary-spacer")) == 3
    assert kept.select_one("article #fig-page-break-review figcaption") is not None

    flow = _soup("page-breaks/flow-and-overflow.md")
    article = flow.select_one("article.md-content__inner")
    assert article is not None
    text = article.get_text(" ", strip=True)
    for marker in (
        "PB-CODE-FIRST",
        "PB-CODE-LAST",
        "PB-TABLE-ROW-01",
        "PB-TABLE-ROW-52",
        "PB-NATURAL-FIRST",
        "PB-NATURAL-LAST",
        "PB-ADMONITION-TITLE",
        "PB-TAB-FIRST",
        "PB-TAB-SECOND",
        "PB-GRID-FIRST",
        "PB-GRID-SECOND",
        "PB-FOOTNOTE-CONTENT",
        "PB-MERMAID-START",
        "PB-MATH-VECTOR",
        "PB-LONG-TOKEN-END",
    ):
        assert marker in text
    assert len(article.select("table tbody tr")) == 52
    assert article.select_one(".admonition.warning") is not None
    assert article.select_one(".tabbed-set.tabbed-alternate") is not None
    assert len(article.select(".grid.cards > ul > li")) == 2
    assert article.select_one("pre.mermaid code") is not None
    assert article.select_one("div.arithmatex") is not None


def test_multiple_long_notes_retain_complete_website_structure() -> None:
    page = _soup("page-breaks/multiple-long-notes.md")
    notes = page.select("article .admonition.note")

    assert len(notes) == 8
    for number, note in enumerate(notes, start=1):
        marker = f"MULTILINE-NOTE-{number:02d}"
        assert note.select_one(".admonition-title").get_text(" ", strip=True) == marker
        assert len(note.select(":scope > p:not(.admonition-title)")) == 2
        text = note.get_text(" ", strip=True)
        assert f"{marker}-START" in text
        assert f"{marker}-END" in text


def test_multiple_long_notes_remain_intact_across_pdf_pages() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "multiple-long-notes.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    assert len(pages) >= 2
    occupied_pages: set[int] = set()
    for number in range(1, 9):
        marker = f"MULTILINE-NOTE-{number:02d}"
        title_pages = {
            page_number
            for page_number, text in enumerate(pages, start=1)
            if marker in {line.strip() for line in text.splitlines()}
        }
        start_pages = _marker_pages(pages, f"{marker}-START")
        end_pages = _marker_pages(pages, f"{marker}-END")
        assert len(title_pages) == 1
        assert title_pages == start_pages == end_pages
        occupied_pages.update(title_pages)

    assert len(occupied_pages) >= 2
    assert all(page.strip() for page in pages)


def test_multiple_long_footnotes_retain_references_bodies_and_returns() -> None:
    page = _soup("page-breaks/multiple-long-footnotes.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    references = article.select("a.footnote-ref")
    footnotes = article.select(".footnote > ol > li")
    assert len(references) == len(footnotes) == 12
    for number, footnote in enumerate(footnotes, start=1):
        text = footnote.get_text(" ", strip=True)
        assert f"FOOTNOTE-BODY-{number:02d}-START" in text
        assert f"FOOTNOTE-BODY-{number:02d}-END" in text
        assert footnote.select_one("a.footnote-backref") is not None


def test_multiple_long_footnotes_remain_complete_across_pages() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "multiple-long-footnotes.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    assert len(pages) > 2
    bodies_per_page: dict[int, int] = {}
    for number in range(1, 13):
        reference_pages = _marker_pages(pages, f"FNREF{number:02d}")
        start_marker = f"FOOTNOTE-BODY-{number:02d}-START"
        end_marker = f"FOOTNOTE-BODY-{number:02d}-END"
        start_pages = {
            page_number
            for page_number, text in enumerate(pages, start=1)
            if start_marker in "".join(text.split())
        }
        end_pages = {
            page_number
            for page_number, text in enumerate(pages, start=1)
            if end_marker in "".join(text.split())
        }
        assert len(reference_pages) == 1
        assert len(start_pages) == 1
        assert start_pages == end_pages
        reference_page = next(iter(reference_pages))
        page_number = next(iter(start_pages))
        assert reference_page == page_number
        bodies_per_page[page_number] = bodies_per_page.get(page_number, 0) + 1

    assert len(bodies_per_page) >= 2
    assert max(bodies_per_page.values()) >= 2
    assert _marker_pages(pages, "FOOTNOTE-BODY-SEQUENCE-END")


def test_multiple_long_footnotes_keep_numeric_order_when_the_area_overflows() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "multiple-long-footnotes.pdf"
    with pymupdf.open(path) as document:
        compact_text = "".join("".join(page.get_text().split()) for page in document)

    rendered_order = [
        int(number)
        for number in re.findall(r"FOOTNOTE-BODY-(\d{2})-START", compact_text)
    ]
    assert rendered_order == list(range(1, 13))


def test_footnote_edge_cases_retain_their_website_structures() -> None:
    page = _soup("page-breaks/footnote-edge-cases.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    oversized = article.find(id="fn:oversized")
    assert oversized is not None
    assert len(oversized.find_all("p", recursive=False)) == 31
    repeated_refs = article.select('a.footnote-ref[href="#fn:repeated"]')
    assert len(repeated_refs) == 2
    assert len(article.find_all(id="fn:repeated")) == 1
    multi = article.find(id="fn:multi-paragraph")
    assert multi is not None
    assert len(multi.find_all("p", recursive=False)) == 2
    assert article.select_one("li a.footnote-ref[href='#fn:nested-list']") is not None
    assert article.select_one(".admonition a.footnote-ref[href='#fn:nested-admonition']") is not None
    assert article.select_one(".prodockit-steps a.footnote-ref[href='#fn:nested-step']") is not None
    assert "LONG-TOKEN-START" in article.get_text(" ", strip=True)


def test_admonition_pagination_specimens_retain_nested_website_content() -> None:
    page = _soup("page-breaks/admonition-pagination.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    notes = article.select(".admonition")
    assert len(notes) == 2
    assert notes[0].select_one(".admonition-title").get_text(" ", strip=True) == (
        "ADMONITION-OVERSIZED-TITLE"
    )
    oversized_text = notes[0].get_text(" ", strip=True)
    assert "ADMONITION-OVERSIZED-START" in oversized_text
    assert "ADMONITION-OVERSIZED-END" in oversized_text
    for number in range(1, 46):
        assert f"Oversized line {number:02d}" in oversized_text

    rich = notes[1]
    assert rich.select_one("ul ol") is not None
    assert len(rich.select("table tbody tr")) == 2
    assert rich.select_one("pre code") is not None
    rich_text = rich.get_text(" ", strip=True)
    for marker in (
        "RICH-ADMONITION-START",
        "RICH-TABLE-HEADER",
        "RICH-CODE-START",
        "RICH-CODE-END",
        "RICH-ADMONITION-END",
    ):
        assert marker in rich_text


def test_container_pagination_specimens_retain_website_hierarchy() -> None:
    page = _soup("page-breaks/container-pagination.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    tabs = article.select_one(".tabbed-set.tabbed-alternate")
    assert tabs is not None
    assert [label.get_text(" ", strip=True) for label in tabs.select(".tabbed-labels label")] == [
        "TAB-OVERSIZED-TITLE",
        "TAB-STABLE-SIBLING",
    ]
    assert len(tabs.select(".tabbed-block")) == 2
    assert "TAB-OVERSIZED-END" in tabs.select(".tabbed-block")[0].get_text(" ", strip=True)
    assert "TAB-SIBLING-BODY" in tabs.select(".tabbed-block")[1].get_text(" ", strip=True)

    cards = article.select(".grid.cards > ul > li")
    assert len(cards) == 2
    first_card = cards[0]
    assert first_card.select_one(".prodockit-steps") is not None
    assert len(first_card.select(".prodockit-steps > li")) == 2
    assert first_card.select_one("pre code") is not None
    first_card_text = first_card.get_text(" ", strip=True)
    assert "GRID-OVERSIZED-START" in first_card_text
    assert "GRID-OVERSIZED-END" in first_card_text
    for number in range(1, 46):
        assert f"Grid continuation {number:02d}" in first_card_text

    assert article.select_one("dl dt").get_text(" ", strip=True) == "DEFINITION-TERM"
    assert "DEFINITION-BODY" in article.select_one("dl dd").get_text(" ", strip=True)
    tasks = article.select("ul.task-list > li")
    assert len(tasks) == 2
    assert tasks[0].select_one('input[type="checkbox"][checked]') is not None
    assert tasks[1].select_one('input[type="checkbox"]:not([checked])') is not None


def test_rich_block_pagination_specimens_retain_captions_and_rows() -> None:
    page = _soup("page-breaks/rich-block-pagination.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    table_figure = article.select_one("figure.prodockit-table-caption")
    assert table_figure is not None
    assert len(table_figure.select("table tbody tr")) == 20
    assert "COMPLEX-TABLE-CAPTION" in table_figure.select_one("figcaption").get_text(
        " ", strip=True
    )
    for number in range(1, 21):
        row_text = table_figure.select("table tbody tr")[number - 1].get_text(" ", strip=True)
        assert f"COMPLEX-ROW-{number:02d}-START" in row_text
        assert f"COMPLEX-ROW-{number:02d}-END" in row_text

    figure = article.select_one("figure.prodockit-figure-caption")
    assert figure is not None
    caption = figure.select_one("figcaption").get_text(" ", strip=True)
    assert "FIGURE-LONG-CAPTION-START" in caption
    assert "FIGURE-LONG-CAPTION-END" in caption
    assert figure.select_one("img") is not None
    assert "FIGURE-FOLLOWING-CONTENT" in article.get_text(" ", strip=True)


def test_page_bibliography_pagination_retains_local_links_and_backlinks() -> None:
    page = _soup("page-breaks/page-bibliography-pagination.md")
    article = page.select_one("article.md-content__inner")
    assert article is not None

    citations = article.select("span.prodockit-bib-cite[id]")
    entries = article.select("#refs .csl-entry.reference")
    backlinks = article.select("#refs a.prodockit-bib-backlink")
    assert len(citations) == 32
    assert len(entries) == 30
    assert len(backlinks) == 32
    citation_ids = {citation["id"] for citation in citations}
    assert {link.get("href", "").removeprefix("#") for link in backlinks} == citation_ids
    assert len(article.select("#ref-pagination01 a.prodockit-bib-backlink")) == 2
    assert len(article.select("#ref-pagination02 a.prodockit-bib-backlink")) == 2
    assert len(article.select("a.footnote-ref")) == 3
    assert len(article.select(".footnote > ol > li")) == 3
    assert len(article.select(".footnote a.footnote-backref")) == 3


def test_adjacent_page_bibliographies_keep_source_entries_separate() -> None:
    paginated = _soup("page-breaks/page-bibliography-pagination.md")
    adjacent = _soup("page-breaks/page-bibliography-adjacent.md")
    paginated_article = paginated.select_one("article.md-content__inner")
    adjacent_article = adjacent.select_one("article.md-content__inner")
    assert paginated_article is not None
    assert adjacent_article is not None

    assert paginated_article.select_one("#ref-chacon2014") is None
    assert len(paginated_article.select("#refs .csl-entry.reference")) == 30
    assert adjacent_article.select_one("#ref-chacon2014") is not None
    assert len(adjacent_article.select("#refs .csl-entry.reference")) == 1
    assert adjacent_article.select_one("#ref-pagination01") is None


def test_oversized_footnote_splits_complete_and_in_order() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "footnote-edge-cases.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    start_pages = _marker_pages(pages, "OVERSIZED-FOOTNOTE-START")
    end_pages = _marker_pages(pages, "OVERSIZED-FOOTNOTE-END")
    assert len(start_pages) == len(end_pages) == 1
    assert next(iter(start_pages)) < next(iter(end_pages))
    compact = "".join("".join(page.split()) for page in pages)
    positions = [compact.index(f"OVERSIZED-PARAGRAPH-{number:02d}") for number in range(1, 31)]
    assert positions == sorted(positions)


def test_two_footnotes_in_one_paragraph_share_the_reference_page() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "footnote-edge-cases.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    paragraph_pages = _marker_pages(pages, "TWO-CALLS-PARAGRAPH")
    assert len(paragraph_pages) == 1
    assert paragraph_pages == _marker_pages(pages, "TWO-CALLS-FIRST-BODY")
    assert paragraph_pages == _marker_pages(pages, "TWO-CALLS-SECOND-BODY")


def test_multi_paragraph_footnote_preserves_visible_separation() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "footnote-edge-cases.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text("words") for page in document]

    first = [
        (page_number, word)
        for page_number, page in enumerate(pages, start=1)
        for word in page
        if "MULTI-PARAGRAPH-FIRST" in word[4]
    ]
    second = [
        (page_number, word)
        for page_number, page in enumerate(pages, start=1)
        for word in page
        if "MULTI-PARAGRAPH-SECOND" in word[4]
    ]
    assert len(first) == len(second) == 1
    assert first[0][0] == second[0][0]
    assert second[0][1][1] - first[0][1][3] > 5


def test_repeated_reference_renders_one_body_for_both_calls() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "footnote-edge-cases.pdf"
    with pymupdf.open(path) as document:
        text = "\n".join(page.get_text() for page in document)

    assert text.count("REPEATED-FIRST-CALL") == 1
    assert text.count("REPEATED-SECOND-CALL") == 1
    assert text.count("REPEATED-FOOTNOTE-BODY") == 1


def test_nested_footnotes_stay_with_list_admonition_and_step_calls() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "footnote-edge-cases.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    for container in ("LIST", "ADMONITION", "STEP"):
        assert _marker_pages(pages, f"NESTED-{container}-REFERENCE") == _marker_pages(
            pages, f"NESTED-{container}-BODY"
        )


def test_long_footnote_url_and_token_stay_inside_the_page() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "footnote-edge-cases.pdf"
    with pymupdf.open(path) as document:
        matching = [page for page in document if "LONG-TOKEN-REFERENCE" in page.get_text()]
        assert len(matching) == 1
        page = matching[0]
        text = page.get_text()
        compact = "".join(text.split())
        assert "LONG-URL-START" in text
        assert "LONG-URL-END" in text
        assert "LONG-TOKEN-START" in compact
        assert "LONG-TOKEN-END" in compact
        assert all(word[0] >= page.rect.x0 - 0.5 for word in page.get_text("words"))
        assert all(word[2] <= page.rect.x1 + 0.5 for word in page.get_text("words"))


def test_oversized_admonition_continues_without_losing_content() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "admonition-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    title_pages = _marker_pages(pages, "ADMONITION-OVERSIZED-TITLE")
    start_pages = _marker_pages(pages, "ADMONITION-OVERSIZED-START")
    end_pages = _marker_pages(pages, "ADMONITION-OVERSIZED-END")
    assert len(title_pages) == len(start_pages) == len(end_pages) == 1
    assert title_pages == start_pages
    assert next(iter(start_pages)) < next(iter(end_pages))
    compact = "".join("".join(page.split()) for page in pages)
    positions = [compact.index(f"Oversizedline{number:02d}") for number in range(1, 46)]
    assert positions == sorted(positions)


def test_rich_admonition_keeps_its_nested_structures_together() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "admonition-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    expected_page = _marker_pages(pages, "RICH-ADMONITION-TITLE")
    assert len(expected_page) == 1
    for marker in (
        "RICH-ADMONITION-START",
        "RICH-TABLE-HEADER",
        "RICH-TABLE-ROW-1",
        "RICH-TABLE-ROW-2",
        "RICH-CODE-START",
        "RICH-CODE-END",
        "RICH-ADMONITION-END",
    ):
        assert _marker_pages(pages, marker) == expected_page


def test_oversized_tab_and_grid_continue_before_their_siblings() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "container-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    for prefix, sibling in (
        ("TAB", "TAB-SIBLING-BODY"),
        ("GRID", "GRID-SIBLING-BODY"),
    ):
        title_pages = _marker_pages(pages, f"{prefix}-OVERSIZED-TITLE")
        start_pages = _marker_pages(pages, f"{prefix}-OVERSIZED-START")
        end_pages = _marker_pages(pages, f"{prefix}-OVERSIZED-END")
        sibling_pages = _marker_pages(pages, sibling)
        assert len(title_pages) == len(start_pages) == len(end_pages) == len(sibling_pages) == 1
        assert title_pages == start_pages
        assert next(iter(start_pages)) < next(iter(end_pages))
        assert next(iter(end_pages)) <= next(iter(sibling_pages))

    compact = "".join("".join(page.split()) for page in pages)
    tab_positions = [compact.index(f"Tabline{number:02d}") for number in range(1, 41)]
    grid_positions = [compact.index(f"Gridcontinuation{number:02d}") for number in range(1, 46)]
    assert tab_positions == sorted(tab_positions)
    assert grid_positions == sorted(grid_positions)
    for marker in ("GRID-STEP-ONE", "GRID-STEP-TWO", "GRID-CODE-START", "GRID-CODE-END"):
        assert _marker_pages(pages, marker)


def test_definition_and_task_list_labels_remain_with_their_content() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "container-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    assert _marker_pages(pages, "DEFINITION-TERM") == _marker_pages(pages, "DEFINITION-BODY")
    task_pages = _marker_pages(pages, "TASK-COMPLETE") | _marker_pages(pages, "TASK-PENDING")
    assert len(task_pages) == 1
    assert task_pages == _marker_pages(pages, "LIST-BOUNDARY-END")


def test_complex_table_repeats_its_header_without_splitting_rows() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "rich-block-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    assert len(_compact_marker_pages(pages, "COMPLEX-TABLE-HEADER")) >= 2
    first_pages = _compact_marker_pages(pages, "COMPLEX-ROW-01-START")
    last_pages = _compact_marker_pages(pages, "COMPLEX-ROW-20-START")
    assert len(first_pages) == len(last_pages) == 1
    assert first_pages != last_pages
    for number in range(1, 21):
        assert _compact_marker_pages(pages, f"COMPLEX-ROW-{number:02d}-START") == (
            _compact_marker_pages(pages, f"COMPLEX-ROW-{number:02d}-END")
        )
    assert _compact_marker_pages(pages, "COMPLEX-TABLE-CAPTION") == last_pages


def test_figure_and_long_caption_remain_on_one_page() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "rich-block-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]
        caption_pages = _compact_marker_pages(pages, "FIGURE-LONG-CAPTION-START")
        assert len(caption_pages) == 1
        assert caption_pages == _compact_marker_pages(pages, "FIGURE-LONG-CAPTION-END")
        assert caption_pages == _compact_marker_pages(pages, "FIGURE-FOLLOWING-CONTENT")
        figure_page = document[next(iter(caption_pages)) - 1]
        assert len(figure_page.get_drawings()) >= 4


def test_page_local_bibliography_entries_paginate_without_splitting() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "page-bibliography-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    first_pages = _compact_marker_pages(pages, "PAGINATION-REFERENCE-01")
    # Pandoc's default CSL sorts by author, so Zulu's entry is the final one.
    last_pages = _compact_marker_pages(pages, "PAGINATION-REFERENCE-26")
    assert len(first_pages) == len(last_pages) == 1
    assert first_pages != last_pages
    for number in range(1, 31):
        assert len(_compact_marker_pages(pages, f"PAGINATION-REFERENCE-{number:02d}")) == 1
    following_pages = _compact_marker_pages(pages, "PAGE-BIBLIOGRAPHY-FOLLOWING")
    assert len(following_pages) == 1
    assert next(iter(following_pages)) >= next(iter(last_pages))


def test_page_local_bibliography_shares_one_source_with_physical_page_footnotes() -> None:
    path = BUNDLE / "page-pdfs" / "page-breaks" / "page-bibliography-pagination.pdf"
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]

    source_pages: list[int] = []
    footnote_pages: set[int] = set()
    for span in ("ONE", "TWO", "THREE"):
        call_pages = _compact_marker_pages(pages, f"SOURCE-PAGE-{span}-CALL")
        body_pages = _compact_marker_pages(pages, f"SOURCE-PAGE-{span}-FOOTNOTE")
        assert len(call_pages) == len(body_pages) == 1
        assert call_pages == body_pages
        source_pages.append(next(iter(call_pages)))
        footnote_pages.update(body_pages)

    assert source_pages == sorted(source_pages)
    assert len(set(source_pages)) == 3

    bibliography_pages = set().union(
        *(
            _compact_marker_pages(pages, f"PAGINATION-REFERENCE-{number:02d}")
            for number in range(1, 31)
        )
    )
    assert len(bibliography_pages) >= 2
    assert footnote_pages & bibliography_pages


def test_adjacent_source_does_not_leak_into_page_local_bibliography_pdf() -> None:
    paginated_path = BUNDLE / "page-pdfs" / "page-breaks" / "page-bibliography-pagination.pdf"
    adjacent_path = BUNDLE / "page-pdfs" / "page-breaks" / "page-bibliography-adjacent.pdf"
    with pymupdf.open(paginated_path) as document:
        paginated_text = "\n".join(page.get_text() for page in document)
    with pymupdf.open(adjacent_path) as document:
        adjacent_text = "\n".join(page.get_text() for page in document)

    assert "Pro Git" not in paginated_text
    assert "PAGINATION-REFERENCE-01" not in adjacent_text
    assert "Pro Git" in adjacent_text
    assert "ADJACENT-SOURCE-FOLLOWING" in adjacent_text


def test_phase_five_pdf_page_relationships_are_stable() -> None:
    pages = _pdf_text_pages()
    assert len(pages) >= 70

    assert _marker_pages(pages, "PB-FORCED-AFTER-START") != _marker_pages(
        pages, "PB-FORCED-AFTER-END"
    )
    assert _marker_pages(pages, "PB-FORCED-BEFORE-START") != _marker_pages(
        pages, "PB-FORCED-BEFORE-END"
    )
    assert _marker_pages(pages, "PB-KEEP-START") == _marker_pages(pages, "PB-KEEP-END")
    assert _marker_pages(pages, "PB-KEEP-LEAD") != _marker_pages(pages, "PB-KEEP-START")
    assert max(_marker_pages(pages, "PB-HEADING-TITLE")) in _marker_pages(
        pages, "PB-HEADING-FOLLOWING-CONTENT"
    )
    assert _marker_pages(pages, "PB-CODE-FIRST") != _marker_pages(pages, "PB-CODE-LAST")
    assert _marker_pages(pages, "PB-TABLE-ROW-01") != _marker_pages(pages, "PB-TABLE-ROW-52")
    assert len(_marker_pages(pages, "PB-TABLE-HEADER")) >= 2
    assert _marker_pages(pages, "PB-NATURAL-FIRST") != _marker_pages(pages, "PB-NATURAL-LAST")
    assert _marker_pages(pages, "PB-FOOTNOTE-REFERENCE") == _marker_pages(
        pages, "PB-FOOTNOTE-CONTENT"
    )
    assert max(_marker_pages(pages, "PB-LONG-TOKEN-END")) < max(
        _marker_pages(pages, "Catalogue index")
    )

    for marker in (
        "PB-ADMONITION-TITLE",
        "PB-ADMONITION-END",
        "PB-TAB-FIRST",
        "PB-TAB-SECOND",
        "PB-GRID-FIRST",
        "PB-GRID-SECOND",
        "PB-MERMAID-START",
        "PB-MERMAID-END",
        "PB-MATH-VECTOR",
        "PB-LONG-TOKEN-START",
        "PB-LONG-TOKEN-END",
    ):
        assert _marker_pages(pages, marker), marker


def test_phase_five_pdf_figure_vectors_and_long_token_stay_inside_the_page() -> None:
    with pymupdf.open(PDF) as document:
        figure_page = next(page for page in document if "PB-FIGURE-CAPTION" in page.get_text())
        vector_page = next(page for page in document if "PB-MERMAID-START" in page.get_text())
        token_page = next(page for page in document if "PB-LONG-TOKEN-START" in page.get_text())

        assert len(figure_page.get_drawings()) >= 4
        assert len(vector_page.get_drawings()) >= 10
        token_words = [
            word
            for word in token_page.get_text("words")
            if "PB-LONG" in word[4] or "CATALOGUE" in word[4]
        ]
        assert token_words
        assert all(0 <= word[0] < word[2] <= token_page.rect.width for word in token_words)


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


def test_phase_four_specimens_and_static_fallbacks_are_present_in_the_catalogue_pdf() -> None:
    assert PDF.is_file()
    with pymupdf.open(PDF) as document:
        assert document.page_count >= 45
        pages = [(page.get_text(), len(page.get_drawings())) for page in document]
        text = "\n".join(page_text for page_text, _ in pages)

    for marker in (
        "Layout and integrations specimen",
        "Phase 4 macro output",
        "Mermaid flowchart",
        "Prodockit integrations",
        "Catalogue Maintainers (2026)",
        "Cascading Style Sheets",
        "Phase 4 output review",
        "Build the website",
        "Chacon, Scott, and Ben Straub",
        "Nested Prodockit content",
        "Catalogue index",
        "rendering catalogue",
    ):
        assert marker in text

    assert "{{ catalogue_phase }}" not in text
    assert "\\citeref{" not in text
    assert "\\gls{" not in text
    assert "\\cite{" not in text
    assert "\\index{" not in text

    diagram_drawings = next(
        drawings for page_text, drawings in pages if "Mermaid flowchart" in page_text
    )
    assert diagram_drawings >= 4

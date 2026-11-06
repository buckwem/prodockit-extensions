# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Assertions over the built rendering catalogue website and PDF."""

from __future__ import annotations

import json
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
    assert max(_marker_pages(pages, "PB-LONG-TOKEN-END")) + 1 == max(
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

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise the carousel runtime in real Chrome with self-contained fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _pdf_web_render_support import find_browser

ROOT = Path(__file__).resolve().parents[1]


def test_real_browser_carousel() -> None:
    node = shutil.which("node")
    browser = find_browser()
    module = ROOT / "tools/browser-test/node_modules/puppeteer-core"
    if not node or not browser or not module.is_dir():
        pytest.skip("Node, Chrome and npm ci --prefix tools/browser-test are required")
    command = [node, str(ROOT / "tools/browser-test/carousel.cjs"), str(browser)]
    if evidence := os.environ.get("PDK_CAROUSEL_EVIDENCE"):
        command.append(evidence)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    not shutil.which("pandoc") or not shutil.which("weasyprint"),
    reason="Real Pandoc and WeasyPrint are needed to verify static card output",
)
def test_pdf_keeps_all_cards_and_long_card_continuation(tmp_path: Path) -> None:
    from pypdf import PdfReader

    from prodockit.pdf.build import Page, build_pdf

    cards = "".join(
        f'<li><p><strong>Unique resource {index:02}</strong></p>'
        '<p><a href="https://example.org/">Read the resource</a></p></li>'
        for index in range(25)
    )
    continuation = "".join(f"<p>Long card paragraph {index:03}</p>" for index in range(100))
    html = (
        '<h1>Static carousel output</h1>'
        '<div class="grid cards pdk-carousel" data-carousel-autoplay="true"><ul>'
        f"{cards}<li><p><strong>Long resource</strong></p>{continuation}"
        "<p>End of long resource</p></li></ul></div>"
    )
    output = tmp_path / "carousel.pdf"
    build_pdf(
        [Page(docs_rel_path="index.md", html=html, is_index=True)],
        str(output),
        include_table_of_contents=False,
    )
    reader = PdfReader(output)
    text = "\n".join(page.extract_text() for page in reader.pages)
    for index in range(25):
        assert text.count(f"Unique resource {index:02}") == 1
    assert text.count("Long card paragraph") == 100
    assert text.count("End of long resource") == 1
    assert "Previous cards" not in text
    assert "Pause automatic rotation" not in text
    links = [
        annotation.get_object().get("/A", {}).get("/URI")
        for page in reader.pages
        for annotation in page.get("/Annots", [])
    ]
    assert links.count("https://example.org/") == 25


def test_country_example_uses_sized_local_photos_and_wikipedia_links() -> None:
    import markdown
    from bs4 import BeautifulSoup
    from PIL import Image

    source = (ROOT / "docs/extensions/carousel.md").read_text(encoding="utf-8")
    html = markdown.markdown(source, extensions=["md_in_html", "attr_list", "fenced_code"])
    soup = BeautifulSoup(html, "html.parser")
    carousel = soup.select_one('[data-carousel-label="Explore countries"]')
    assert carousel is not None
    assert carousel["data-carousel-visible"] == "3"
    assert carousel["data-carousel-min-width"] == "160"
    cards = carousel.select(":scope > ul > li")
    assert len(cards) == 6
    for card in cards:
        image = card.find("img")
        assert image is not None and image["alt"]
        link = image.find_parent("a")
        assert link is not None
        assert str(link["href"]).startswith("https://en.wikipedia.org/wiki/")
        photo = (ROOT / "docs/extensions" / str(image["src"])).resolve()
        assert photo.is_relative_to(ROOT / "docs/assets/carousel")
        with Image.open(photo) as asset:
            assert asset.size == (640, 426)
        assert card.select_one('a[href^="https://unsplash.com/photos/"]') is not None


@pytest.mark.skipif(
    not shutil.which("pandoc") or not shutil.which("weasyprint"),
    reason="Real Pandoc and WeasyPrint are needed to verify photo tile pagination",
)
def test_pdf_photo_tiles_keep_image_title_and_credit_together(tmp_path: Path) -> None:
    from pypdf import PdfReader

    from prodockit.pdf.build import Page, build_pdf

    photos = sorted((ROOT / "docs/assets/carousel").glob("*.jpg"))
    html = '<h1>Country photos</h1><div class="grid cards pdk-carousel pdk-carousel-tiles"><ul>'
    for index, photo in enumerate(photos):
        html += (
            f'<li><p><img class="pdk-carousel-image" src="{photo.as_uri()}" '
            'width="640" height="426"></p>'
            f"<p>Unique photo resource {index}</p><p>End of photo resource {index}</p></li>"
        )
    html += "</ul></div>"
    output = tmp_path / "photos.pdf"
    build_pdf(
        [Page(docs_rel_path="index.md", html=html, is_index=True)],
        str(output),
        include_table_of_contents=False,
    )
    reader = PdfReader(output)
    pages = [page.extract_text() for page in reader.pages]
    assert len(reader.pages) <= 3, "short picture cards should fit several on a page"
    for index in range(len(photos)):
        containing = [text for text in pages if f"Unique photo resource {index}" in text]
        assert len(containing) == 1
        assert f"End of photo resource {index}" in containing[0]
    images = [image for page in reader.pages for image in page.images]
    assert len({image.name for image in images}) == len(photos)
    draws = sum(
        operator == b"Do"
        for page in reader.pages
        for _operands, operator in page.get_contents().operations
    )
    assert draws == len(photos)

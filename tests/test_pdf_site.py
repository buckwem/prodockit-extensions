# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from prodockit.pdf.site import (
    BuiltSiteError,
    output_path,
    page_html,
    page_metadata,
    publish_pdf_to_built_site,
    published_pdf_path,
    validate_built_site,
)
from prodockit.project_config import load_project_config


def _config(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "site").mkdir()
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name = "Test"\n', encoding="utf-8")
    return load_project_config(path)


@pytest.mark.parametrize(
    ("source", "directory_urls", "expected"),
    [
        ("index.md", True, "index.html"),
        ("guide/index.md", True, "guide/index.html"),
        ("guide/start.md", True, "guide/start/index.html"),
        ("guide/start.md", False, "guide/start.html"),
    ],
)
def test_output_path_matches_zensical_routing(
    tmp_path: Path, source: str, directory_urls: bool, expected: str
) -> None:
    assert output_path(source, tmp_path, directory_urls=directory_urls) == tmp_path / expected


def test_page_html_extracts_content_and_drops_website_only_controls(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text(
        '<html><article class="md-content__inner md-typeset">'
        '<a class="md-content__button md-icon">edit</a>'
        '<h1 id="hello">Hello</h1><p>Body</p>'
        '<nav class="md-tags"><a class="md-tag">Get started</a></nav>'
        '<div class="md-feedback"><button>Helpful?</button></div>'
        '<footer class="sponsorship"><a href="/sponsor">Sponsor</a></footer>'
        "</article></html>",
        encoding="utf-8",
    )

    html = page_html(config, "index.md")

    assert "md-content__button" not in html
    assert "md-tags" not in html
    assert "Get started" not in html
    assert "md-feedback" not in html
    assert "Helpful?" not in html
    assert "sponsorship" not in html
    assert "Sponsor" not in html
    assert '<h1 id="hello">Hello</h1>' in html
    assert "<p>Body</p>" in html


def test_page_html_preserves_comments_as_comments(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text(
        '<article class="md-content__inner md-typeset">'
        "<!-- internal author note -->"
        "<p>Visible</p></article>",
        encoding="utf-8",
    )

    html = page_html(config, "index.md")

    assert "<!-- internal author note -->" in html
    assert html.endswith("<p>Visible</p>")


def test_page_html_fails_clearly_when_article_layout_changes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text("<main>content</main>", encoding="utf-8")

    with pytest.raises(BuiltSiteError, match="generated HTML layout changed"):
        page_html(config, "index.md")


def test_page_metadata_reads_pdf_fields(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(
        '---\nis_appendix: true\nrecto_title: "Short"\npdf_include: false\n---\n# Page\n',
        encoding="utf-8",
    )
    assert page_metadata(page) == {
        "is_appendix": True,
        "recto_title": "Short",
        "pdf_include": False,
    }


def test_validate_built_site_accepts_all_selected_pages(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text("index", encoding="utf-8")
    page = config.site_dir / "guide" / "start" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("page", encoding="utf-8")

    validate_built_site(config, ["index.md", "guide/start.md"])


def test_validate_built_site_requires_the_site_directory(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.site_dir.rmdir()

    with pytest.raises(BuiltSiteError, match=r"zensical build --clean --strict"):
        validate_built_site(config, ["index.md"])


def test_validate_built_site_requires_the_root_index(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with pytest.raises(BuiltSiteError, match="has no index page"):
        validate_built_site(config, ["guide/start.md"])


@pytest.mark.parametrize(
    ("directory_urls", "missing"),
    [(True, "guide/start/index.html"), (False, "guide/start.html")],
)
def test_validate_built_site_names_missing_pages_for_both_url_layouts(
    tmp_path: Path, directory_urls: bool, missing: str
) -> None:
    config = _config(tmp_path)
    config.project["use_directory_urls"] = directory_urls
    (config.site_dir / "index.html").write_text("index", encoding="utf-8")

    with pytest.raises(BuiltSiteError, match="built site is incomplete") as exc_info:
        validate_built_site(config, ["index.md", "guide/start.md"])

    assert missing in str(exc_info.value)


def test_published_pdf_path_maps_only_docs_assets(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert published_pdf_path(config, "docs/site_documentation.pdf") == (
        config.site_dir / "site_documentation.pdf"
    )
    assert published_pdf_path(config, "docs/chapters/one.pdf") == (
        config.site_dir / "chapters" / "one.pdf"
    )
    assert published_pdf_path(config, "dist/site_documentation.pdf") is None


def test_publish_pdf_to_built_site_copies_identical_bytes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = config.docs_dir / "site_documentation.pdf"
    source.write_bytes(b"%PDF-1.7\x00same bytes")

    destination = publish_pdf_to_built_site(config, source)

    assert destination == config.site_dir / "site_documentation.pdf"
    assert destination.read_bytes() == source.read_bytes()


def test_publish_pdf_to_built_site_does_not_publish_external_output(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "dist" / "out.pdf"
    source.parent.mkdir()
    source.write_bytes(b"outside docs")

    assert publish_pdf_to_built_site(config, source) is None
    assert list(config.site_dir.rglob("*.pdf")) == []


def test_publish_pdf_to_built_site_keeps_existing_file_if_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    source = config.docs_dir / "site_documentation.pdf"
    destination = config.site_dir / "site_documentation.pdf"
    source.write_bytes(b"new complete PDF")
    destination.write_bytes(b"old complete PDF")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr("prodockit.pdf.site.os.replace", fail_replace)

    with pytest.raises(OSError, match="interrupted"):
        publish_pdf_to_built_site(config, source)

    assert destination.read_bytes() == b"old complete PDF"
    assert not list(config.site_dir.glob(".*.tmp"))

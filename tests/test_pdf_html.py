# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from bs4 import BeautifulSoup

from zendoc.pdf.html import (
    build_page_anchor_map,
    build_virtual_page_map,
    fix_up_page_html,
    to_base64_data_uri,
    virtual_page_path,
)


def _fix(html: str, **kwargs) -> str:
    defaults = dict(
        current_docs_rel_path="page.md",
        docs_dir="docs",
        page_anchor_map={},
    )
    defaults.update(kwargs)
    return fix_up_page_html(html, **defaults)


# ---------------------------------------------------------------------------
# virtual_page_path / anchor maps
# ---------------------------------------------------------------------------

def test_virtual_page_path_nests_one_level_deeper_than_the_source_file() -> None:
    assert virtual_page_path("starthere/installtooling.md") == "starthere/installtooling"


def test_virtual_page_path_index_stays_at_its_own_directory() -> None:
    assert virtual_page_path("starthere/index.md") == "starthere"
    assert virtual_page_path("index.md") == ""


def test_build_page_anchor_map_produces_deterministic_slugs() -> None:
    anchors = build_page_anchor_map(["starthere/installtooling.md", "index.md"])
    assert anchors["starthere/installtooling.md"] == "page-starthere-installtooling"
    assert anchors["index.md"] == "page-index"


def test_build_virtual_page_map_keys_by_virtual_path() -> None:
    virtual_map = build_virtual_page_map(["starthere/installtooling.md"])
    assert virtual_map["starthere/installtooling"] == "page-starthere-installtooling"


# ---------------------------------------------------------------------------
# to_base64_data_uri
# ---------------------------------------------------------------------------

def test_to_base64_data_uri_leaves_existing_data_uris_unchanged() -> None:
    uri = "data:image/png;base64,AAAA"
    assert to_base64_data_uri(uri, "/some/dir") == uri


def test_to_base64_data_uri_embeds_a_real_file(tmp_path) -> None:
    img = tmp_path / "logo.png"
    img.write_bytes(b"\x89PNG\r\n")
    result = to_base64_data_uri("logo.png", str(tmp_path))
    assert result.startswith("data:image/png;base64,")


def test_to_base64_data_uri_returns_src_unchanged_when_file_missing() -> None:
    assert to_base64_data_uri("does-not-exist.png", "/nowhere") == "does-not-exist.png"


# ---------------------------------------------------------------------------
# Website-only cleanup
# ---------------------------------------------------------------------------

def test_style_tags_and_permalinks_are_stripped() -> None:
    html = _fix('<style>.x{color:red}</style><h1>T<a class="headerlink" href="#t">#</a></h1>')
    assert "<style>" not in html
    assert "headerlink" not in html


def test_glightbox_wrapper_is_unwrapped_leaving_just_the_image() -> None:
    html = _fix('<a class="glightbox" href="../images/x.png"><img src="images/x.png"></a>')
    assert "glightbox" not in html
    assert "<img" in html
    assert "<a" not in html


# ---------------------------------------------------------------------------
# iframe -> admonition
# ---------------------------------------------------------------------------

def test_youtube_iframe_becomes_a_watch_video_admonition() -> None:
    html = _fix('<iframe src="https://www.youtube.com/embed/abc123" title="Demo"></iframe>')
    assert "<iframe" not in html
    assert "admonition" in html
    assert 'href="https://www.youtube.com/watch?v=abc123"' in html
    assert "Watch Video" in html


def test_iframe_without_src_is_just_removed() -> None:
    html = _fix("<iframe></iframe>")
    assert "<iframe" not in html
    assert "admonition" not in html


# ---------------------------------------------------------------------------
# Content tabs
# ---------------------------------------------------------------------------

def test_tabbed_labels_become_their_own_paragraph() -> None:
    html = _fix(
        '<div class="tabbed-set"><div class="tabbed-labels"><label>Python</label></div></div>'
    )
    assert "<label>" not in html
    assert '<p class="zendoc-tab-label">Python</p>' in html


def test_radio_inputs_are_removed() -> None:
    html = _fix('<input type="radio" name="tab">')
    assert "<input" not in html


# ---------------------------------------------------------------------------
# svg -> base64 img
# ---------------------------------------------------------------------------

def test_every_svg_becomes_a_base64_twemoji_img() -> None:
    html = _fix("<p>Before <svg><path/></svg> After</p>")
    assert "<svg>" not in html
    assert 'class="twemoji"' in html
    assert "data:image/svg+xml;base64," in html


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------

def test_footnote_text_moves_inline_to_its_reference_point() -> None:
    html = _fix(
        '<p>A sentence with a note.<sup id="fnref:1">'
        '<a class="footnote-ref" href="#fn:1">1</a></sup></p>'
        '<div class="footnote"><ol><li id="fn:1">'
        '<p>The footnote text. <a class="footnote-backref" href="#fnref:1">&#8617;</a></p>'
        "</li></ol></div>"
    )
    assert 'class="footnote"' not in html
    assert "footnote-backref" not in html
    assert '<span class="pdf-footnote">The footnote text. </span>' in html
    # The span replaces the <sup>, staying at the same point in the flow.
    assert html.index("pdf-footnote") < html.index("</p>")


def test_footnote_without_a_matching_reference_is_dropped_not_left_visible() -> None:
    """The <div class="footnote"> collection is always removed once
    processed, whether or not each entry found a matching <sup> reference
    to move its text to - an orphaned entry's text is silently dropped
    rather than left behind as a floating, referenceless <div>, which would
    be worse (visible, unstyled leftover markup with no obvious home)."""
    html = _fix(
        '<div class="footnote"><ol><li id="fn:1"><p>Orphaned.</p></li></ol></div>'
    )
    assert html == ""


# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------

def test_mermaid_pre_is_replaced_by_the_callbacks_image() -> None:
    html = _fix(
        '<pre class="mermaid">graph TD; A--&gt;B;</pre>',
        render_mermaid=lambda source: "/tmp/diagram_1.svg",
    )
    assert "<pre" not in html
    assert 'src="/tmp/diagram_1.svg"' in html


def test_mermaid_pre_is_left_alone_when_callback_returns_none() -> None:
    html = _fix(
        '<pre class="mermaid">graph TD; A--&gt;B;</pre>',
        render_mermaid=lambda source: None,
    )
    assert 'class="mermaid"' in html


def test_mermaid_pre_is_left_alone_without_a_callback() -> None:
    html = _fix('<pre class="mermaid">graph TD; A--&gt;B;</pre>')
    assert 'class="mermaid"' in html


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_local_image_src_is_base64_embedded(tmp_path) -> None:
    # startediting.md's own *virtual* directory is "starthere/startediting"
    # (one level deeper than its containing directory - see
    # virtual_page_path()), so a real page's own "../images/shot.png"
    # resolves to "docs/starthere/images/shot.png", not
    # "docs/starthere/startediting/images/shot.png" as a naive
    # relative-to-the-source-file resolution would assume.
    docs_dir = tmp_path / "docs"
    (docs_dir / "starthere" / "images").mkdir(parents=True)
    (docs_dir / "starthere" / "images" / "shot.png").write_bytes(b"\x89PNG\r\n")
    html = _fix(
        '<img src="../images/shot.png">',
        current_docs_rel_path="starthere/startediting.md",
        docs_dir=str(docs_dir),
    )
    assert "data:image/png;base64," in html


# ---------------------------------------------------------------------------
# Cross-page + repo file links
# ---------------------------------------------------------------------------

def test_cross_page_link_resolves_to_an_in_document_anchor() -> None:
    # startediting.md's own virtual directory is "startediting" (one level
    # deeper than the docs root - see virtual_page_path()), so a real link
    # to another top-level page's own virtual path ("installtooling") has
    # to climb back up one level first, matching how Zensical itself
    # rewrites a hand-typed relative link under its clean-URL convention.
    anchor_map = build_page_anchor_map(["installtooling.md", "startediting.md"])
    html = _fix(
        '<a href="../installtooling">Install tooling</a>',
        current_docs_rel_path="startediting.md",
        page_anchor_map=anchor_map,
    )
    assert 'href="#page-installtooling"' in html


def test_cross_page_link_with_fragment_keeps_only_the_fragment() -> None:
    anchor_map = build_page_anchor_map(["installtooling.md", "startediting.md"])
    html = _fix(
        '<a href="../installtooling#some-heading">Install tooling</a>',
        current_docs_rel_path="startediting.md",
        page_anchor_map=anchor_map,
    )
    assert 'href="#some-heading"' in html


def test_external_and_fragment_only_links_are_left_alone() -> None:
    html = _fix('<a href="https://example.com">Ext</a><a href="#local">Local</a>')
    assert 'href="https://example.com"' in html
    assert 'href="#local"' in html


def test_repo_file_link_rewrites_to_a_github_blob_url() -> None:
    html = _fix(
        '<a href="../stylesheets/extra.css">extra.css</a>',
        current_docs_rel_path="starthere/customise.md",
        repo_url="https://github.com/example/repo",
    )
    assert 'href="https://github.com/example/repo/blob/main/docs/stylesheets/extra.css"' in html


def test_repo_file_link_rewrites_to_a_gitlab_blob_url() -> None:
    html = _fix(
        '<a href="../stylesheets/extra.css">extra.css</a>',
        current_docs_rel_path="starthere/customise.md",
        repo_url="https://gitlab.com/example/repo",
    )
    assert "/-/blob/main/" in html


def test_repo_file_link_is_unwrapped_when_no_repo_url_is_known() -> None:
    html = _fix('<a href="../stylesheets/extra.css">extra.css</a>', current_docs_rel_path="starthere/customise.md")
    assert "<a " not in html
    assert "extra.css" in html


# ---------------------------------------------------------------------------
# Prepend-position figure/table caption reordering
# ---------------------------------------------------------------------------

def test_prepend_position_figure_caption_becomes_a_div_with_caption_first() -> None:
    html = _fix(
        '<figure class="zendoc-figure-caption" id="f1">'
        "<figcaption><p>A caption</p></figcaption>"
        '<img src="x.png">'
        "</figure>"
    )
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_="zendoc-figure-caption")
    assert div is not None
    assert div.find("figcaption") is None
    first_child = div.find(True, recursive=False)
    assert first_child.name == "p"
    assert first_child.get_text() == "A caption"


def test_append_position_figure_caption_is_left_as_a_figure() -> None:
    html = _fix(
        '<figure class="zendoc-figure-caption" id="f1">'
        '<img src="x.png">'
        "<figcaption><p>A caption</p></figcaption>"
        "</figure>"
    )
    assert "<figure" in html
    assert "<figcaption>" in html


# ---------------------------------------------------------------------------
# <p> with id/class -> <div>
# ---------------------------------------------------------------------------

def test_paragraph_with_class_is_retagged_to_a_div() -> None:
    html = _fix('<p class="reference" id="ref1">Some reference</p>')
    assert "<div" in html
    assert '<p class="reference"' not in html


def test_plain_paragraph_without_class_or_id_stays_a_paragraph() -> None:
    html = _fix("<p>Just text</p>")
    assert "<p>Just text</p>" in html


def test_tab_label_paragraph_is_not_retagged_to_a_div() -> None:
    html = _fix('<p class="zendoc-tab-label">Python</p>')
    assert '<p class="zendoc-tab-label">Python</p>' in html


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------

def test_is_index_wraps_content_in_a_cover_page_div_and_hides_headings() -> None:
    html = _fix("<h1>My Report</h1><p>Intro</p>", is_index=True)
    soup = BeautifulSoup(html, "html.parser")
    cover = soup.find("div", class_="cover-page")
    assert cover is not None
    h1 = cover.find("h1")
    assert "hidden" in h1["class"]
    assert "unnumbered" in h1["class"]
    assert "unlisted" in h1["class"]


def test_non_index_page_is_not_wrapped_in_a_cover_page_div() -> None:
    html = _fix("<h1>A Chapter</h1><p>Intro</p>", is_index=False)
    assert "cover-page" not in html


# ---------------------------------------------------------------------------
# Own-page anchor + appendix flag
# ---------------------------------------------------------------------------

def test_first_heading_gets_its_own_pages_anchor_id() -> None:
    html = _fix(
        "<h1>Chapter</h1><h2>Section</h2>",
        current_docs_rel_path="chapter1.md",
        page_anchor_map={"chapter1.md": "page-chapter1"},
    )
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("h1")["id"] == "page-chapter1"
    assert soup.find("h2").get("id") is None


def test_appendix_page_flags_its_first_heading() -> None:
    html = _fix(
        "<h1>Appendix A</h1>",
        current_docs_rel_path="acronyms.md",
        page_anchor_map={"acronyms.md": "page-acronyms"},
        is_appendix=True,
    )
    soup = BeautifulSoup(html, "html.parser")
    assert "appendix" in soup.find("h1")["class"]

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from bs4 import BeautifulSoup

from prodockit.pdf.html import (
    build_page_anchor_map,
    build_virtual_page_map,
    fix_up_page_html,
    to_base64_data_uri,
    virtual_page_path,
)


def _fix(html: str, **kwargs) -> str:
    defaults = {
        "current_docs_rel_path": "page.md",
        "docs_dir": "docs",
        "page_anchor_map": {},
    }
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


def test_non_youtube_iframe_uses_its_own_src_as_the_watch_video_link() -> None:
    """The `else: video_url = src` branch - a Vimeo (or any other) embed,
    not YouTube - had no test at all; only the YouTube-specific
    embed-to-watch URL rewrite was covered."""
    html = _fix('<iframe src="https://player.vimeo.com/video/12345" title="Demo"></iframe>')
    assert "<iframe" not in html
    assert "admonition" in html
    assert 'href="https://player.vimeo.com/video/12345"' in html
    assert "Watch Video" in html


# ---------------------------------------------------------------------------
# Content tabs
# ---------------------------------------------------------------------------

def test_tabbed_labels_become_their_own_paragraph() -> None:
    html = _fix(
        '<div class="tabbed-set"><div class="tabbed-labels"><label>Python</label></div></div>'
    )
    assert "<label>" not in html
    assert '<p class="prodockit-tab-label">Python</p>' in html


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


def test_only_dark_image_is_dropped_not_embedded(tmp_path) -> None:
    """A PDF has no light/dark toggle - only the #only-light half of a
    light/dark image pair should survive; the #only-dark half used to get
    base64-embedded and left permanently visible, since the data: URI it
    became has no trace of "#only-dark" left for any stylesheet to hide it
    by."""
    (tmp_path / "dark.svg").write_bytes(b"<svg></svg>")
    html = _fix(
        '<img src="dark.svg#only-dark">',
        current_docs_rel_path="index.md",
        docs_dir=str(tmp_path),
    )
    assert "<img" not in html
    assert "data:" not in html


def test_gh_dark_mode_only_image_is_dropped_too(tmp_path) -> None:
    """Same convention, GitHub's own README-image spelling."""
    (tmp_path / "dark.png").write_bytes(b"\x89PNG\r\n")
    html = _fix(
        '<img src="dark.png#gh-dark-mode-only">',
        current_docs_rel_path="index.md",
        docs_dir=str(tmp_path),
    )
    assert "<img" not in html


def test_only_light_image_is_kept_and_embedded(tmp_path) -> None:
    """The other half of the same pair is unaffected - still resolved and
    embedded exactly as any other local image would be."""
    (tmp_path / "light.svg").write_bytes(b"<svg></svg>")
    html = _fix(
        '<img src="light.svg#only-light">',
        current_docs_rel_path="index.md",
        docs_dir=str(tmp_path),
    )
    assert "data:image/svg+xml;base64," in html


def test_a_light_dark_pair_leaves_exactly_one_image_in_the_pdf(tmp_path) -> None:
    """End-to-end version of the two tests above: a real light/dark pair,
    as docs/index.md's own cover page hero graphic uses, ends up as
    exactly one <img> in the PDF, not two stacked on top of each other."""
    (tmp_path / "hero-light.svg").write_bytes(b"<svg></svg>")
    (tmp_path / "hero-dark.svg").write_bytes(b"<svg></svg>")
    html = _fix(
        '<img src="hero-light.svg#only-light">'
        '<img src="hero-dark.svg#only-dark">',
        current_docs_rel_path="index.md",
        docs_dir=str(tmp_path),
    )
    assert html.count("<img") == 1


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
        '<figure class="prodockit-figure-caption" id="f1">'
        "<figcaption><p>A caption</p></figcaption>"
        '<img src="x.png">'
        "</figure>"
    )
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_="prodockit-figure-caption")
    assert div is not None
    assert div.find("figcaption") is None
    first_child = div.find(True, recursive=False)
    assert first_child.name == "p"
    assert first_child.get_text() == "A caption"


def test_append_position_figure_caption_is_left_as_a_figure() -> None:
    html = _fix(
        '<figure class="prodockit-figure-caption" id="f1">'
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
    html = _fix('<p class="prodockit-tab-label">Python</p>')
    assert '<p class="prodockit-tab-label">Python</p>' in html


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


def test_appendix_letter_is_stamped_on_the_heading_for_lua_to_read() -> None:
    """Regression test (#104): the Lua filter used to count appendix
    headings itself, which silently drifted from the website whenever an
    appendix page contributed no numbered h1. build_pdf() now computes each
    page's letter and passes it here to stamp on the heading instead."""
    html = _fix(
        "<h1>References</h1>",
        current_docs_rel_path="references.md",
        page_anchor_map={"references.md": "page-references"},
        is_appendix=True,
        appendix_letter="C",
    )
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("h1")["data-appendix-letter"] == "C"


def test_appendix_letter_is_omitted_when_not_supplied() -> None:
    """Optional: without a letter the attribute is left off entirely, and
    the Lua filter falls back to counting appendix headings itself."""
    html = _fix(
        "<h1>References</h1>",
        current_docs_rel_path="references.md",
        page_anchor_map={"references.md": "page-references"},
        is_appendix=True,
    )
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("h1").get("data-appendix-letter") is None


# ---------------------------------------------------------------------------
# recto_title
# ---------------------------------------------------------------------------

def test_recto_title_inserts_an_override_directly_after_the_first_heading() -> None:
    html = _fix(
        "<h1>A Rather Long Chapter Title</h1><p>Body text.</p>",
        recto_title="Short Title",
    )
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    override = heading.find_next_sibling()
    assert override.name == "div"
    assert "prodockit-recto-title" in override["class"]
    assert override.get_text() == "Short Title"


def test_recto_title_none_inserts_nothing() -> None:
    html = _fix("<h1>Chapter</h1><p>Body text.</p>")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find(class_="prodockit-recto-title") is None


def test_recto_title_empty_string_inserts_nothing() -> None:
    html = _fix("<h1>Chapter</h1><p>Body text.</p>", recto_title="")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find(class_="prodockit-recto-title") is None


def test_revision_date_marker_follows_the_heading_without_changing_its_text() -> None:
    html = _fix(
        "<h1>Chapter</h1><p>Body text.</p>",
        revision_date="2026-08-27",
    )
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    marker = heading.find_next_sibling(class_="prodockit-revision-date")
    assert heading.get_text() == "Chapter"
    assert marker.get_text() == "Updated on 2026-08-27"


def test_cover_page_has_no_revision_date_marker() -> None:
    html = _fix("<h1>Cover</h1>", revision_date="2026-08-27", is_index=True)
    assert BeautifulSoup(html, "html.parser").find(class_="prodockit-revision-date") is None


def test_first_heading_keeps_its_own_id_and_gains_the_page_anchor() -> None:
    """prodockit-extensions#163: the page anchor used to *replace* the first
    heading's id, so every `\\ref{}`/`\\autoref{}` pointing at a page's title
    heading linked to an anchor that no longer existed. The reference still
    rendered its text, so nothing looked wrong - the link was simply dead,
    and `\\autoref` printed "on page" with nothing after it.

    Both anchors are needed: the page's own, for a cross-page link with no
    fragment, and the heading's, for a reference to the heading itself."""
    html = _fix(
        '<h1 id="chapter-two">Chapter Two</h1><h2 id="deep">Deep</h2>',
        current_docs_rel_path="chapter2.md",
        page_anchor_map={"chapter2.md": "page-chapter2"},
    )
    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find("h1")
    assert heading["id"] == "chapter-two", "the heading's own id must survive"
    assert soup.find(id="page-chapter2") is not None, "the page anchor must still exist"
    assert soup.find("h2")["id"] == "deep"


def test_the_page_anchor_sits_inside_the_heading_not_before_it() -> None:
    """A numbered h1 carries `break-before: page` (recto under
    double_sided), so an anchor placed immediately *before* one sits at the
    foot of the previous page - and `target-counter()` would report a page
    number one too low."""
    html = _fix(
        '<h1 id="chapter-two">Chapter Two</h1>',
        current_docs_rel_path="chapter2.md",
        page_anchor_map={"chapter2.md": "page-chapter2"},
    )
    soup = BeautifulSoup(html, "html.parser")

    anchor = soup.find(id="page-chapter2")
    assert anchor.name == "span"
    assert anchor.parent.name == "h1"
    assert anchor.get_text() == "", "an empty span generates no glyphs and no width"


def test_a_heading_with_no_id_carries_the_page_anchor_directly() -> None:
    """Nothing to preserve, so no extra element is needed."""
    html = _fix(
        "<h1>Chapter</h1>",
        current_docs_rel_path="chapter1.md",
        page_anchor_map={"chapter1.md": "page-chapter1"},
    )
    soup = BeautifulSoup(html, "html.parser")

    assert soup.find("h1")["id"] == "page-chapter1"
    assert soup.find("h1").find("span") is None


def test_an_appendix_page_still_flags_a_heading_that_has_its_own_id() -> None:
    """The `.appendix` class and its letter are read by the Lua filter to
    letter rather than number the heading - preserving the id must not cost
    that."""
    html = _fix(
        '<h1 id="glossary">Glossary</h1>',
        current_docs_rel_path="glossary.md",
        page_anchor_map={"glossary.md": "page-glossary"},
        is_appendix=True,
        appendix_letter="A",
    )
    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find("h1")
    assert heading["id"] == "glossary"
    assert "appendix" in heading["class"]
    assert heading["data-appendix-letter"] == "A"
    assert soup.find(id="page-glossary") is not None


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

# Exactly what Zensical's highlighter emits: a leading empty <span>, a
# `__codelineno` anchor per line, and per-token <span>s.
_HIGHLIGHTED = (
    '<div class="highlight"><pre><span></span><code>'
    '<a href="#__codelineno-1-1" id="__codelineno-1-1" name="__codelineno-1-1"></a>'
    'git<span class="w"> </span>clone<span class="w"> </span>example\n'
    '<a href="#__codelineno-1-2" id="__codelineno-1-2" name="__codelineno-1-2"></a>'
    '<span class="nb">cd</span><span class="w"> </span>example\n'
    "</code></pre></div>"
)


def test_code_blocks_are_flattened_to_plain_text() -> None:
    """Pandoc's HTML reader only takes `<pre><code>` as a code block when
    the `<code>` holds nothing but text. Zensical's token spans, line
    anchors and leading empty span each defeat that on their own, and the
    `<pre>` is then absent from Pandoc's output entirely - so
    `white-space: pre-wrap` has nothing to apply to and the block reflows
    as justified prose (prodockit-extensions#207).
    """
    soup = BeautifulSoup(_fix(_HIGHLIGHTED), "html.parser")
    pre = soup.find("pre")
    assert pre is not None
    assert pre.find_all("span") == []
    assert pre.find_all("a") == []
    children = list(pre.children)
    assert len(children) == 1 and children[0].name == "code"


def test_flattening_keeps_the_text_and_its_line_breaks() -> None:
    """The point of the block is its line structure - losing the newlines
    is what turned a three-line snippet into one wrapped paragraph."""
    soup = BeautifulSoup(_fix(_HIGHLIGHTED), "html.parser")
    text = soup.find("pre").get_text()
    assert text.splitlines()[:2] == ["git clone example", "cd example"]
    # The spaces live in <span class="w"> tokens; dropping the spans must
    # not drop the spaces with them.
    assert "gitclone" not in text


def test_flattening_carries_highlight_tokens_for_writer_side_restoration() -> None:
    """The Pandoc-readable block stays plain, but the website's already
    language-aware token markup is not discarded (#724)."""
    soup = BeautifulSoup(_fix(_HIGHLIGHTED), "html.parser")
    code = soup.find("pre").find("code")
    encoded = code["data-prodockit-highlight"]
    markup = bytes.fromhex(encoded).decode("utf-8")

    assert '<span class="nb">cd</span>' in markup
    assert '<span class="w"> </span>' in markup
    assert "__codelineno" not in markup
    assert code.find("span") is None, "Pandoc must still receive plain text"


def test_plain_code_does_not_gain_a_highlight_payload() -> None:
    soup = BeautifulSoup(_fix("<pre><code>plain text</code></pre>"), "html.parser")

    assert "data-prodockit-highlight" not in soup.find("code").attrs


def test_flattening_leaves_mermaid_pre_alone() -> None:
    """`pre.mermaid` carries diagram source that a separate step replaces
    with a rendered image - flattening it here would be harmless but
    pointless, and skipping it keeps the two transforms independent."""
    html = '<pre class="mermaid">graph LR\n  A --> B</pre>'
    soup = BeautifulSoup(_fix(html), "html.parser")
    pre = soup.find("pre", class_="mermaid")
    assert pre is not None
    assert pre.find("code") is None


def test_inline_code_outside_pre_is_untouched() -> None:
    """Only `<pre>` is rewritten. Inline `<code>` in prose renders fine and
    must keep any markup it carries."""
    html = '<p>Run <code>prodockit <em>pdf</em></code> now.</p>'
    soup = BeautifulSoup(_fix(html), "html.parser")
    assert soup.find("code").find("em") is not None

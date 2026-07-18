# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Fixes up one page's Zensical-rendered HTML for Pandoc/WeasyPrint.

Pandoc is a completely different parser from Python-Markdown/Zensical, with
its own HTML reader/writer quirks - this module fixes up already-rendered
HTML (the caller renders each page through Zensical's own Markdown pipeline
first, e.g. ``zensical.markdown.render.render()``, then passes the result
here) rather than hand-translating markdown syntax, so Pandoc's own HTML
reader can read genuinely standard HTML with no per-feature translation
needed. See each function's own docstring for the specific Pandoc/WeasyPrint
limitation it works around.

:func:`fix_up_page_html` is the main entry point, applying every fixup in
the order they need to happen. The standalone helpers (link/anchor mapping,
image embedding) are exported separately since a caller building a
multi-page PDF needs to call some of them once, up front, across every page
- not just from within this function.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Callable
from typing import Any

from bs4 import BeautifulSoup, Tag

HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


def virtual_page_path(docs_rel_path: str) -> str:
    """The clean-URL "virtual directory" a docs_dir-relative page path maps
    to under Zensical's ``use_directory_urls`` convention - e.g.
    ``"starthere/installtooling.md"`` becomes ``"starthere/installtooling"``
    (one level deeper than its own containing directory), while an
    ``index.md`` stays at its containing directory rather than nesting
    deeper (``"starthere/index.md"`` -> ``"starthere"``, top-level
    ``"index.md"`` -> ``""``).

    Used to resolve a real ``<a href>``/``<img src>`` - already rewritten
    to this same clean-URL form by Zensical's own link-rewriting treeprocessor
    (or prodockit.refs/prodockit.citations/prodockit.glossary's own cross-page href
    building) by the time ``render()`` returns a page's HTML - back to the
    real page/file it points at.
    """
    dirname = os.path.dirname(docs_rel_path)
    basename = os.path.basename(docs_rel_path)
    if basename.lower() == "index.md":
        return dirname
    slug = basename.rsplit(".", 1)[0]
    return os.path.join(dirname, slug).replace("\\", "/") if dirname else slug


def build_page_anchor_map(md_files: list[str]) -> dict[str, str]:
    """Maps each nav markdown file (docs_dir-relative, e.g.
    ``"starthere/installtooling.md"``) to a deterministic anchor id (e.g.
    ``"page-starthere-installtooling"``).

    A multi-page PDF concatenates every page into one document, so a link
    that resolves fine on the website (a separate page) has nothing to
    point at there - Pandoc would otherwise treat it as a link to an
    external file at whatever absolute path the PDF happened to be built
    from. Rewriting such links to in-document anchors instead (see
    :func:`fix_up_page_html`'s cross-page link handling) fixes that.
    """
    page_anchor_map = {}
    for f in md_files:
        key = os.path.normpath(f).replace("\\", "/")
        slug = re.sub(r"[^a-z0-9]+", "-", key.lower().rsplit(".", 1)[0]).strip("-")
        page_anchor_map[key] = f"page-{slug}"
    return page_anchor_map


def build_virtual_page_map(md_files: list[str]) -> dict[str, str]:
    """Maps each nav markdown file's clean-URL virtual directory path (see
    :func:`virtual_page_path`) to the same anchor id
    :func:`build_page_anchor_map` assigns it, so a rewritten ``<a href>``
    can be resolved without needing to know the original ``.md`` filename
    at all."""
    anchor_map = build_page_anchor_map(md_files)
    virtual_map = {}
    for f in md_files:
        key = os.path.normpath(f).replace("\\", "/")
        virtual_map[virtual_page_path(key)] = anchor_map[key]
    return virtual_map


def to_base64_data_uri(img_src: str, base_dir: str) -> str:
    """Resolves a (possibly relative) image src to an absolute path under
    base_dir and returns it as a base64 ``data:`` URI, so a standalone
    compiled document doesn't depend on relative file paths resolving
    correctly from wherever Pandoc happens to run.

    Returns `img_src` unchanged if it's already a ``data:`` URI, or the
    resolved file doesn't exist.
    """
    if img_src.startswith("data:"):
        return img_src

    path_part = img_src.split("#")[0]
    if path_part.startswith("file://"):
        path_part = path_part[7:]

    img_path = os.path.abspath(os.path.join(base_dir, path_part))
    if not os.path.exists(img_path):
        img_path = os.path.abspath(path_part)

    if os.path.exists(img_path) and os.path.isfile(img_path):
        try:
            ext = os.path.splitext(img_path)[1].lower().strip(".")
            mime_type = f"image/{ext}"
            if ext == "svg":
                mime_type = "image/svg+xml"
            elif ext == "jpg":
                mime_type = "image/jpeg"
            with open(img_path, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime_type};base64,{b64_content}"
        except Exception:
            pass
    return img_src


def fix_up_page_html(
    html: str,
    *,
    current_docs_rel_path: str,
    docs_dir: str,
    page_anchor_map: dict[str, str],
    is_index: bool = False,
    is_appendix: bool = False,
    recto_title: str | None = None,
    repo_url: str = "",
    admonition_icon_config: dict[str, Any] | None = None,
    icon_registry: dict[str, str] | None = None,
    render_mermaid: Callable[[str], str | None] | None = None,
) -> str:
    """Fixes up one page's already-Zensical-rendered `html` for Pandoc/
    WeasyPrint, returning the fixed-up HTML (fed to Pandoc with ``-f
    html``).

    `current_docs_rel_path` is this page's own docs_dir-relative path (e.g.
    ``"starthere/installtooling.md"``) - used to resolve this page's own
    relative image/link references and its own anchor id.
    `page_anchor_map` is shared across every page in the build (see
    :func:`build_page_anchor_map`), used to rewrite cross-page links to
    in-document anchors.

    `is_index` marks this as the document's cover page - every heading on
    it is treated as decorative (unnumbered/unlisted/hidden), and its whole
    content is wrapped in a ``.cover-page`` div. `is_appendix` gives this
    page's first heading an ``appendix`` class, for a Lua filter's own
    ``Header()`` handler (see :mod:`prodockit.pdf.lua`) to letter instead of
    number it. `recto_title` (a page's own front matter, e.g. `recto_title:
    "Short Title"`) overrides the running header's auto-detected chapter
    title text from the *next* page onward - the H1 itself is untouched,
    only the header - by inserting a hidden element carrying the override
    text directly after this page's first heading, with its own
    `string-set` (see `prodockit.pdf.css`). Confirmed directly: CSS
    `string()`'s default policy takes a page's own *first* value for a
    given name, so the heading's own page still shows its full title (the
    heading's own string-set is first in document order there); only the
    following page - which has no string-set of its own, so inherits the
    last value from the previous page - shows the override. Meaningful
    whether or not `pdf_double_sided` is enabled - the running chapter
    title appears in both layouts, just in different corners.

    `admonition_icon_config`/`icon_registry` (see :mod:`prodockit.pdf.icons`)
    are needed to insert an admonition's own icon; omit either to skip icon
    insertion entirely (an admonition still renders, just without one).

    `render_mermaid`, if given, is called with each ``<pre class="mermaid">``
    diagram's own source text and should return an image src (a file path
    or ``data:`` URI) or None if rendering failed (in which case the
    diagram is left as an unrendered ``<pre>``, rather than raising) - see
    :func:`prodockit.pdf.mermaid.render_mermaid_diagram` for a ready-made
    callback (partially applied with its own `mmdc_bin`/`output_dir`
    arguments).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Website-only presentational output with no PDF equivalent - a caller's
    # own heading-numbering/reference-style <style> injection (if any), and
    # a table of contents' hover-to-copy permalink links, are meaningless in
    # a PDF, which gets its own equivalent numbering/styling some other way
    # (see prodockit.pdf.lua's Header()/Figure(), and prodockit.pdf.css).
    for style in soup.find_all("style"):
        style.decompose()
    for permalink in soup.select("a.headerlink"):
        permalink.decompose()

    # zensical.extensions.glightbox wraps every image in a click-to-zoom
    # <a class="glightbox" href="..."> - a website-only JS lightbox feature
    # with no PDF equivalent, and whose href uses a different relative-path
    # convention than the <img> it wraps (an artifact of Zensical's URL
    # cleaning - the href assumes the page's own clean URL is itself a
    # directory, one level deeper than the <img src>'s own resolution),
    # which Pandoc/WeasyPrint then fails to resolve as a broken link.
    # Unwrapping to just the <img> avoids resolving that href at all.
    for lightbox_link in soup.select("a.glightbox"):
        lightbox_link.unwrap()

    # Embedded videos (e.g. a YouTube <iframe>): confirmed a raw <iframe>
    # left for Pandoc/WeasyPrint to handle produces a stray, unwanted
    # heading in the compiled PDF (WeasyPrint attempting to fetch the
    # iframe's src and something in that response ending up parsed as real
    # page content) - a static PDF can't embed a live video player
    # regardless, so replace it with a "Watch Video" admonition link
    # instead.
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if not src:
            iframe.decompose()
            continue
        if "youtube.com/embed/" in src:
            # Strip any pre-existing query string (e.g. "?rel=0") from the
            # *embed* URL before adding the watch URL's own "?v=..." - doing
            # this the other way around (replace first, split second, as an
            # earlier version of this function did) strips the just-added
            # "?v=..." too, silently dropping the video id from every
            # single conversion, with or without a pre-existing query
            # string on the source iframe.
            video_url = src.split("?")[0].replace("youtube.com/embed/", "youtube.com/watch?v=")
        else:
            video_url = src
        video_title = iframe.get("title", "").strip() or "Video Tutorial"
        admonition = soup.new_tag("div")
        admonition["class"] = ["admonition", "info"]
        title_p = soup.new_tag("p")
        title_p["class"] = "admonition-title"
        title_p.string = video_title
        body_p = soup.new_tag("p")
        strong = soup.new_tag("strong")
        link = soup.new_tag("a", href=video_url)
        link.string = "Watch Video"
        strong.append(link)
        body_p.append(strong)
        admonition.append(title_p)
        admonition.append(body_p)
        parent = iframe.parent
        # Only replace the immediate wrapping <div> too if the iframe is its
        # only real content - otherwise this would swallow unrelated sibling
        # content (e.g. a grid card, or the whole page's own wrapper div).
        if parent is not None and parent.name == "div" and len(list(parent.find_all(True))) == 1:
            parent.replace_with(admonition)
        else:
            iframe.replace_with(admonition)

    # Content tabs: pymdownx.blocks.tab renders each tab's label as an
    # inline <label> sibling inside a wrapping <div class="tabbed-labels">.
    # Pandoc's HTML reader merges adjacent inline-level siblings with no
    # block boundary between them into one Plain block - confirmed this
    # collapses every label in a tabbed-set into one unseparated run of
    # text, with no way to recover the boundary afterward in a Lua filter.
    # Rewriting each into its own <p> here, before Pandoc's reader ever
    # sees it, is the only point this can be fixed - see prodockit.pdf.lua's
    # tabbed-set Div() handler for the matching reconstruction.
    for radio in soup.select('input[type="radio"]'):
        radio.decompose()
    for label in soup.select("div.tabbed-labels label"):
        p = soup.new_tag("p")
        p["class"] = "prodockit-tab-label"
        p.string = label.get_text()
        label.replace_with(p)

    # Admonition icons: Zensical's own admonition HTML has no icon markup at
    # all - the website draws it via a CSS trick referencing a theme asset
    # URL that doesn't exist in a standalone PDF (confirmed directly - a
    # built admonition's title paragraph is just its plain text, nothing
    # else). Insert the configured, accent-coloured icon explicitly instead.
    if admonition_icon_config and icon_registry:
        from prodockit.pdf.icons import admonition_icon_svg

        for div in soup.select("div.admonition"):
            classes = div.get("class", [])
            adm_type = next((c for c in classes if c != "admonition"), None)
            admonition_title_p = div.find("p", class_="admonition-title")
            if adm_type and isinstance(admonition_title_p, Tag):
                svg_markup = admonition_icon_svg(adm_type, admonition_icon_config, icon_registry)
                if svg_markup:
                    # A raw inline <svg> confirmed not to survive Pandoc's
                    # HTML-to-HTML round trip through to WeasyPrint at all
                    # (tested directly, in isolation) - a base64 data: URI
                    # <img>, the same encoding used for regular images
                    # below, renders reliably instead.
                    b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("utf-8")
                    # Reuses a compiled stylesheet's own img.twemoji rule
                    # (see prodockit.pdf.css, sized for an inline icon) rather
                    # than a bare width/height attribute - a generic
                    # "img { max-width: 100% }" rule elsewhere in the same
                    # stylesheet otherwise overrides a plain attribute,
                    # scaling the icon up to fill the whole admonition width.
                    icon_img = soup.new_tag(
                        "img",
                        src=f"data:image/svg+xml;base64,{b64}",
                        **{"class": "twemoji"},
                    )
                    admonition_title_p.insert(0, " ")
                    admonition_title_p.insert(0, icon_img)

    # Any other inline icon/emoji shortcode (pymdownx.emoji renders these as
    # a raw inline <svg> inside a <span class="twemoji ...">, e.g. a grid
    # card's own title icon) - confirmed, the same way as admonition icons
    # above, that a raw inline <svg> doesn't survive Pandoc's HTML-to-HTML
    # round trip through to WeasyPrint at all. Converts every remaining
    # <svg> anywhere on the page to a base64 data: URI <img>, reusing the
    # same img.twemoji sizing rule.
    for svg in soup.find_all("svg"):
        b64 = base64.b64encode(str(svg).encode("utf-8")).decode("utf-8")
        icon_img = soup.new_tag(
            "img",
            src=f"data:image/svg+xml;base64,{b64}",
            **{"class": "twemoji"},
        )
        svg.replace_with(icon_img)

    # Footnotes: Zensical's own markdown pipeline (python-markdown's
    # footnote extension) renders these as a <sup id="fnref:N"><a
    # class="footnote-ref">N</a></sup> at the reference point, with every
    # footnote's own text collected into one <div class="footnote"><ol>
    # <li id="fn:N"><p>...</p></li></ol></div> at the *end* of the page -
    # never a Pandoc-native Note element (that only exists when Pandoc's
    # own *markdown* reader parses "[^1]" syntax directly; feeding Pandoc
    # pre-rendered HTML here means it just sees an ordinary <div>/<ol>/
    # <sup>, not a Note). Moves each footnote's text inline at its own
    # reference point instead, in a <span class="pdf-footnote"> a compiled
    # stylesheet's own float: footnote rule (see prodockit.pdf.css) can anchor
    # to the correct page - confirmed directly, without this the
    # footnote's own text rendered wherever the <div class="footnote">
    # happened to fall in normal document flow, often several pages after
    # its own reference, at regular body-text size.
    footnote_div = soup.find("div", class_="footnote")
    if isinstance(footnote_div, Tag):
        for li in footnote_div.select('li[id^="fn:"]'):
            ref = soup.find("sup", id=f'fnref:{li["id"][3:]}')
            if ref is None:
                continue
            backref = li.find("a", class_="footnote-backref")
            if isinstance(backref, Tag):
                backref.decompose()
            span = soup.new_tag("span", **{"class": "pdf-footnote"})
            for p in li.find_all("p", recursive=False):
                p.unwrap()
            for child in list(li.contents):
                span.append(child)
            ref.replace_with(span)
        footnote_div.decompose()

    # Mermaid diagrams: WeasyPrint has no JS engine to run Mermaid.js
    # client-side - pre-render each <pre class="mermaid">'s source to a
    # static image via the caller-supplied `render_mermaid` callback (see
    # prodockit.pdf.mermaid.render_mermaid_diagram for a ready-made one).
    if render_mermaid is not None:
        for pre in soup.select("pre.mermaid"):
            img_src = render_mermaid(pre.get_text())
            if img_src is not None:
                img = soup.new_tag("img", src=img_src, alt="Mermaid diagram")
                pre.replace_with(img)

    # Zensical rewrites every page-relative reference - not just <a href>
    # links to other pages, but an <img src> too - relative to this page's
    # own clean-URL *virtual* directory (see virtual_page_path()), matching
    # its use_directory_urls convention. Confirmed directly: a
    # <img src="../images/x.png"> here really does mean
    # "docs/starthere/images/x.png" (for a page at
    # "starthere/startediting.md"), not "docs/images/x.png" as a naive
    # relative-to-the-source-file resolution would assume.
    current_virtual_dir = virtual_page_path(current_docs_rel_path)
    virtual_base_dir = os.path.join(docs_dir, current_virtual_dir)

    # Images: base64-embed every local image reference directly into the
    # HTML, so the standalone compiled document doesn't depend on relative
    # file paths resolving correctly from wherever Pandoc happens to run.
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith("data:"):
            img["src"] = to_base64_data_uri(src, virtual_base_dir)

    # Cross-page links: a multi-page PDF concatenates every page into one
    # document, so a link like installtooling.md (fine on the website, a
    # separate page) has nothing to point at here - rewrite to the
    # deterministic in-document anchor from page_anchor_map instead (see
    # build_page_anchor_map()). By the time render() returns this page's
    # HTML, every such link (a regular markdown link, or a prodockit.refs/
    # prodockit.citations/prodockit.glossary cross-page link) already uses the
    # same clean-URL virtual-directory form.
    virtual_page_map = {virtual_page_path(key): anchor for key, anchor in page_anchor_map.items()}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target, _, frag = href.partition("#")
        if not target:
            continue
        joined = os.path.normpath(os.path.join(current_virtual_dir, target))
        resolved = joined.replace("\\", "/").rstrip("/")
        anchor = virtual_page_map.get(resolved)
        if anchor is not None:
            a["href"] = f"#{frag}" if frag else f"#{anchor}"

    # Repo file links: a relative link to a non-markdown repo file isn't
    # part of the concatenated PDF at all (unlike a page link above) -
    # resolved relative to wherever Pandoc happens to run, it's meaningless
    # (and reveals a local file path) to anyone else reading the PDF, so
    # rewrite it to the file's canonical GitHub/GitLab "blob" URL instead.
    # Unlike the clean-URL page links above, this one *is* just a direct
    # relative path from the source file's own directory - Zensical doesn't
    # clean-URL-rewrite links to non-page assets.
    current_dir = os.path.dirname(current_docs_rel_path)
    repo_url_lower = repo_url.lower()
    if "github.com" in repo_url_lower:
        blob_prefix: str | None = f"{repo_url}/blob/main/"
    elif "gitlab" in repo_url_lower:
        blob_prefix = f"{repo_url}/-/blob/main/"
    else:
        blob_prefix = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("http://", "https://", "mailto:", "#", "/")):
            continue
        if blob_prefix is None:
            a.unwrap()
            continue
        joined = os.path.normpath(os.path.join(docs_dir, current_dir, href))
        repo_rel_path = joined.replace("\\", "/")
        a["href"] = f"{blob_prefix}{repo_rel_path}"

    # Prepend-position figure-caption/table-caption ("/// figure-caption | <"
    # or "/// table-caption | <" in pymdownx.blocks.caption): Pandoc's Figure
    # AST node stores Caption and content as two separate, independently-
    # typed fields rather than as ordered children reflecting the original
    # DOM position, and Pandoc's own HTML writer always re-emits a Figure's
    # <figcaption> *after* its content when serializing back to HTML for
    # WeasyPrint - confirmed directly (isolated test: a <figcaption> placed
    # first in the source HTML still comes out last in Pandoc's own HTML
    # writer output), discarding "prepend" positioning entirely regardless
    # of input order. A Div's children, unlike a Figure's, ARE emitted in
    # original document order - so retag any figure whose <figcaption>
    # comes first to a <div> (preserving id/class) and unwrap the
    # <figcaption> itself (also confirmed: Pandoc's HTML reader treats a
    # bare <figcaption> not inside a <figure> as ordinary flow content),
    # leaving the caption as this element's first child block. A Lua
    # filter's Div() handler (see prodockit.pdf.lua) applies the same
    # "Figure "/"Table " + chapter-prefix numbering to this case that its
    # Figure() handler applies to the (unaffected) default append-position
    # case.
    caption_classes = ["prodockit-figure-caption", "prodockit-table-caption"]
    for figure in soup.find_all("figure", class_=caption_classes):
        first_child = figure.find(True, recursive=False)
        if first_child is not None and first_child.name == "figcaption":
            figure.name = "div"
            first_child.unwrap()

    # Pandoc's native Para AST node has no attribute field at all (unlike
    # Div/Header/CodeBlock/Table/Figure, which all carry one) - confirmed
    # directly: a <p id="..." class="...">, once read by Pandoc's HTML
    # reader, comes out the other end as a bare Para with both the id *and*
    # the class silently gone. This is exactly the shape every attr_list
    # citation/acronym/glossary definition (prodockit.citations/prodockit.glossary's
    # own convention) and a typical cover page's own title styling takes -
    # both would otherwise silently lose their id/styling with no error at
    # all. Retagging as a <div> (which Pandoc's reader does preserve
    # attributes on) fixes both at once.
    for p in soup.find_all("p"):
        classes = p.get("class") or []
        # prodockit-tab-label (see above) deliberately stays a <p>: a Lua
        # filter's tabbed-set Div() handler (see prodockit.pdf.lua) reads it
        # as a Plain/Para whose .content is a plain inline list, matching
        # Pandoc's own Para AST node - retagging it to a Div here too would
        # change its .content to a list of blocks instead, breaking that
        # handler.
        if "prodockit-tab-label" in classes:
            continue
        if p.get("id") or classes:
            p.name = "div"

    # Cover page: every heading here (there's usually just one, hidden) is
    # decorative, not a real chapter - unnumbered/unlisted/hidden from a Lua
    # filter's Header() counter (see prodockit.pdf.lua) and the table of
    # contents. Wrapped in a ".cover-page" class a compiled stylesheet
    # already styles against (see prodockit.pdf.css).
    if is_index:
        for heading in soup.find_all(HEADING_TAGS):
            classes = heading.get("class", [])
            for extra_class in ("hidden", "unnumbered", "unlisted"):
                if extra_class not in classes:
                    classes.append(extra_class)
            heading["class"] = classes
        cover_div = soup.new_tag("div")
        cover_div["class"] = "cover-page"
        for child in list(soup.contents):
            cover_div.append(child)
        soup.append(cover_div)

    # This page's own anchor (see build_page_anchor_map()): give the first
    # real heading that id directly, and flag it .appendix if this page is
    # one, for a Lua filter's Header() (see prodockit.pdf.lua) to letter
    # instead of number it.
    own_anchor = page_anchor_map.get(current_docs_rel_path)
    first_heading = soup.find(HEADING_TAGS)
    if own_anchor and isinstance(first_heading, Tag):
        first_heading["id"] = own_anchor
        if is_appendix:
            classes = list(first_heading.get("class", []))
            classes.append("appendix")
            first_heading["class"] = classes

    # recto_title (see docstring above): inserted directly *after* the real
    # heading, not before, so its own string-set (see prodockit.pdf.css) is
    # the *second* value set on this page, not the first - CSS string()'s
    # default policy means it only takes effect from the following page
    # onward, letting this page itself still show the heading's own full
    # title.
    if recto_title and isinstance(first_heading, Tag):
        override = soup.new_tag("div")
        override["class"] = "prodockit-recto-title"
        override.string = recto_title
        first_heading.insert_after(override)

    return str(soup)

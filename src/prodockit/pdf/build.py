# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""One-call PDF build: wires up html/lua/css into a real `pandoc` +
WeasyPrint invocation and writes a finished PDF file.

The rest of `prodockit.pdf` (`html.py`/`lua.py`/`css.py`/`icons.py`/
`mermaid.py`) is a set of focused building blocks you can call individually
if you need to change how they fit together. `build_pdf()` here is the
convenience path: hand it your already-rendered pages and where you want
the PDF written, and it does the rest - fixing up each page's HTML,
generating the Lua filter and CSS, concatenating everything, and running
`pandoc`/WeasyPrint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from prodockit.pdf.css import build_css
from prodockit.pdf.html import build_page_anchor_map, fix_up_page_html
from prodockit.pdf.index import (
    INDEX_CONTENT_ID,
    build_index_entries,
    extract_term_pages,
    mark_index_terms,
    render_index_content,
)
from prodockit.pdf.lua import build_lua_filter
from prodockit.pdf.rotate import rotate_landscape_pages


@dataclass
class Page:
    """One page to include in the PDF.

    `html` is this page's content already rendered to HTML by your own
    Markdown pipeline (e.g. Zensical's `zensical.markdown.render.render()`)
    - not yet fixed up for Pandoc; `build_pdf()` applies
    `prodockit.pdf.html.fix_up_page_html()` to it internally. `docs_rel_path`
    is this page's path relative to your docs directory (e.g.
    `"starthere/installtooling.md"`), used to resolve this page's own
    relative links/images and to generate its in-document anchor.
    `recto_title`, if given, overrides the running header's auto-detected
    chapter title from the next page onward (this page itself still shows
    the heading's own full title) - see `fix_up_page_html()`'s own
    docstring.
    """

    docs_rel_path: str
    html: str
    is_index: bool = False
    is_appendix: bool = False
    recto_title: str | None = None


class PdfBuildError(RuntimeError):
    """Raised when the underlying `pandoc` invocation fails. `stderr` (if
    captured) and `returncode` are attached for a caller that wants to
    inspect or log the failure, rather than just the formatted message."""

    def __init__(
        self, message: str, *, returncode: int | None = None, stderr: str | None = None
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def build_pdf(
    pages: list[Page],
    output_path: str,
    *,
    docs_dir: str = "docs",
    extra_css: str = "",
    repo_url: str = "",
    admonition_icon_config: dict[str, Any] | None = None,
    icon_registry: dict[str, str] | None = None,
    render_mermaid: Callable[[str], str | None] | None = None,
    main_font: str = "Inter",
    mono_font: str = "JetBrains Mono",
    copyright_text: str = "",
    site_name: str = "",
    page_size: str = "A4",
    margin_top: str = "2cm",
    margin_right: str = "2cm",
    margin_bottom: str = "2cm",
    margin_left: str = "2cm",
    double_sided: bool = False,
    margin_inner: str = "2cm",
    margin_outer: str = "2cm",
    header_footer_font_size: str = "10pt",
    header_footer_color: str = "#555555",
    header_footer_divider_color: str = "#e2e8f0",
    reference_style_global: bool = False,
    reference_spacing_european: str = "-0.8em",
    reference_indent_global: str = "1.27cm",
    reference_spacing_global: str = "2em",
    heading_numbering_enabled: bool = True,
    mathjax_available: bool = False,
    math_dir: str | None = None,
    tex2svg_script: str = "",
    include_table_of_contents: bool = True,
    table_of_contents_title: str = "Table of Contents",
    include_index: bool = False,
    index_title: str = "Index",
    work_dir: str | None = None,
    keep_work_dir: bool = False,
    pandoc_timeout: int | None = 1800,
) -> None:
    """Builds a complete PDF from `pages` and writes it to `output_path`
    (e.g. `"dist/report.pdf"`, `"build/output/handbook.pdf"` - any path,
    absolute or relative; parent directories are not created for you).

    Raises `PdfBuildError` if the underlying `pandoc` invocation fails
    (`pandoc` and a WeasyPrint install are both required on `PATH`/in the
    current Python environment - this function doesn't install either).

    **Content**

    `docs_dir` is your project's docs root (used to resolve each page's own
    relative image/link references - see `prodockit.pdf.html.fix_up_page_html`).
    `extra_css` is your own website stylesheet's content (e.g. your theme
    CSS plus any custom stylesheet), concatenated *before* the CSS this
    function generates, so its own `!important` rules can still override a
    website-only style that doesn't make sense in a paginated PDF. `repo_url`,
    `admonition_icon_config`, `icon_registry`, and `render_mermaid` are
    passed straight through to `fix_up_page_html()` for every page - see its
    own docs for what each does.

    **Typography and layout**

    `main_font`/`mono_font` are font family names (already installed/
    available to WeasyPrint - this function doesn't fetch fonts).
    `page_size` is any WeasyPrint-supported CSS page size (`"A4"`,
    `"Letter"`, ...). `margin_*`/`header_footer_*` are CSS length/colour
    values for the page margins and running header/footer. `copyright_text`/
    `site_name` appear in the running footer/header. `reference_style_global`
    and its `reference_*` spacing values control `.reference`/`.acronym`/
    `.glossary` paragraph spacing - see `prodockit.pdf.css.build_css` for what
    each style looks like.

    `double_sided` (default off) switches the whole document to a duplex-
    printing layout: header/footer content mirrors between left-hand
    (verso) and right-hand (recto) pages (the chapter title stays on the
    outer, fore-edge corner; `site_name` on the inner, spine-side corner),
    `margin_inner`/`margin_outer` replace `margin_left`/`margin_right`
    (swapping which physical side each applies to depending on verso/
    recto), every new numbered heading starts on its own recto page (a
    blank page is inserted if needed - see `prodockit.pdf.css`'s own module
    docstring for why this is plain CSS, not something computed here), and
    a `prodockit-table-rotated` landscape page's own rotation direction
    alternates by its final odd/even page position instead of always being
    the same direction (see `prodockit.pdf.rotate`) - the physical spine is
    on the opposite side for a verso vs. a recto page, so the rotation has
    to compensate to keep landscape content facing the same way regardless
    of which side of the spread it lands on. Off by default: everything
    above is unchanged from a single-sided build.

    **Numbering and math**

    `heading_numbering_enabled` turns chapter/appendix numbering on
    headings and captions on or off entirely. `mathjax_available`/
    `math_dir`/`tex2svg_script` enable TeX math pre-rendering - see
    `prodockit.pdf.lua.build_lua_filter` for what each does; leave
    `mathjax_available` False if your content has no math or you haven't
    set up a local MathJax/`tex2svg` install.

    **Table of contents**

    `include_table_of_contents` (default on) inserts an auto-generated
    Table of Contents, right after your first page if it's `is_index=True`,
    or at the very start otherwise - a page break always follows it, so
    your first real chapter still starts on its own page.
    `table_of_contents_title` is that page's own heading text.

    **Back-of-book index**

    `include_index` (default off) generates a traditional back-of-book
    index - an alphabetised list of terms with the page number(s) they
    appear on - from every `\\index{Term}` marker (see `prodockit.index`)
    anywhere in your own content, and appends it (as its own
    `index_title`-headed page) at the
    very end of the document, after everything else. PDF-only by nature -
    there's no equivalent on a live website, where readers use browser/
    Ctrl-F search instead - see `prodockit.pdf.index`'s own module
    docstring for why this needs (and is the only feature in this package
    that needs) a genuine two-pass build: an index term's own page number
    can only be known after WeasyPrint has already laid the PDF out once.
    Requires the optional `pymupdf` dependency (`pip install
    prodockit[index]`) - only imported (and so only required) if
    `include_index` is actually on. A no-op, single-pass build as before
    if no page anywhere uses the `.index` marker at all, even with
    `include_index` on.

    **Sideways tables**

    Wrap a table (plus its own caption) in `<div class="prodockit-table-rotated">`
    to print it sideways, on its own landscape-sized page(s), spanning
    multiple pages with a repeated heading row exactly like any other
    table - see `prodockit.pdf.css`'s own module docstring for why this
    isn't a CSS `transform`, and `prodockit.pdf.rotate` for the `/Rotate`
    post-processing step (always run, a no-op if no page needs it) that
    applies the actual anticlockwise rotation once WeasyPrint has finished
    laying the page out.

    **Working files**

    `pandoc` needs a few intermediate files on disk (the concatenated HTML,
    the generated Lua filter, the compiled CSS) - written under `work_dir`
    if given, or a fresh temporary directory otherwise. `keep_work_dir`
    leaves those files in place afterwards (only meaningful with an explicit
    `work_dir` - a temporary directory is always cleaned up regardless, and
    can't usefully be inspected afterwards) - handy for debugging exactly
    what Pandoc/WeasyPrint received, e.g. when the generated PDF looks wrong
    but the build didn't fail outright.

    `pandoc_timeout` (default 1800 seconds/30 minutes - generous for any
    real document, however large) bounds each `pandoc`/WeasyPrint
    invocation, raising `PdfBuildError` instead of hanging indefinitely
    on a pathological CSS layout or similar. Pass `None` to disable the
    timeout entirely for an exceptionally large build that genuinely
    needs longer.
    """
    use_temp_dir = work_dir is None
    resolved_work_dir: str = (
        tempfile.mkdtemp(prefix="prodockit-pdf-") if work_dir is None else work_dir
    )
    os.makedirs(resolved_work_dir, exist_ok=True)

    try:
        page_anchor_map = build_page_anchor_map([page.docs_rel_path for page in pages])

        fixed_html_parts = []
        for page in pages:
            fixed_html_parts.append(
                fix_up_page_html(
                    page.html,
                    current_docs_rel_path=page.docs_rel_path,
                    docs_dir=docs_dir,
                    page_anchor_map=page_anchor_map,
                    is_index=page.is_index,
                    is_appendix=page.is_appendix,
                    recto_title=page.recto_title,
                    repo_url=repo_url,
                    admonition_icon_config=admonition_icon_config,
                    icon_registry=icon_registry,
                    render_mermaid=render_mermaid,
                )
            )

        if include_table_of_contents:
            # A Lua filter's own Pandoc() handler (see prodockit.pdf.lua)
            # inserts the real, auto-generated Table of Contents right
            # after a heading literally titled `table_of_contents_title` -
            # this is that heading, unnumbered/unlisted like a cover page's
            # own heading, with a page break after it so the first real
            # chapter still starts on its own page. Raw HTML, not run
            # through fix_up_page_html() - it's not a real page with its
            # own links/images/anchor to fix up.
            toc_trigger_html = (
                f'<h1 class="unnumbered unlisted">{table_of_contents_title}</h1>'
                '<div class="page-break"></div>'
            )
            insert_at = 1 if pages and pages[0].is_index else 0
            fixed_html_parts.insert(insert_at, toc_trigger_html)

        body_html = "\n\n".join(fixed_html_parts)

        # See prodockit.pdf.index's own module docstring for why this needs
        # a real two-pass build - a marker's own page number can only be
        # known once WeasyPrint has already laid the whole document out.
        # index_terms stays empty (no second pass at all) if include_index
        # is on but nothing anywhere actually used the \index{Term} marker -
        # nothing to index, so no reason to pay for a second pandoc/
        # WeasyPrint invocation.
        index_terms: list[str] = []
        index_code_flags: list[bool] = []
        if include_index:
            body_html, index_terms, index_code_flags = mark_index_terms(body_html)
            if index_terms:
                # Always last, after every real page (including any
                # appendices) - the standard back-of-book position, and
                # the only one where this section's own content growing
                # or shrinking can't retroactively shift the page numbers
                # already recorded for every earlier marker.
                body_html += (
                    '<div class="page-break"></div>'
                    f'<h1 class="unnumbered unlisted">{index_title}</h1>'
                    f'<div id="{INDEX_CONTENT_ID}"></div>'
                )

        concatenated_html_path = os.path.join(resolved_work_dir, "_prodockit_pdf_compiled.html")

        def write_concatenated_html(body: str) -> None:
            with open(concatenated_html_path, "w", encoding="utf-8") as f:
                f.write("<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body>\n")
                f.write(body)
                f.write("\n</body></html>")

        write_concatenated_html(body_html)

        lua_filter_path = os.path.join(resolved_work_dir, "_prodockit_pdf_filter.lua")
        with open(lua_filter_path, "w", encoding="utf-8") as f:
            f.write(
                build_lua_filter(
                    heading_numbering_enabled=heading_numbering_enabled,
                    mathjax_available=mathjax_available,
                    math_dir=math_dir or resolved_work_dir,
                    tex2svg_script=tex2svg_script,
                )
            )

        css = build_css(
            main_font=main_font,
            mono_font=mono_font,
            copyright_text=copyright_text,
            site_name=site_name,
            page_size=page_size,
            margin_top=margin_top,
            margin_right=margin_right,
            margin_bottom=margin_bottom,
            margin_left=margin_left,
            double_sided=double_sided,
            margin_inner=margin_inner,
            margin_outer=margin_outer,
            header_footer_font_size=header_footer_font_size,
            header_footer_color=header_footer_color,
            header_footer_divider_color=header_footer_divider_color,
            reference_style_global=reference_style_global,
            reference_spacing_european=reference_spacing_european,
            reference_indent_global=reference_indent_global,
            reference_spacing_global=reference_spacing_global,
        )
        compiled_css_path = os.path.join(resolved_work_dir, "_prodockit_pdf_compiled.css")
        with open(compiled_css_path, "w", encoding="utf-8") as f:
            f.write(extra_css + "\n\n" + css)

        cmd = [
            "pandoc",
            concatenated_html_path,
            "-o", output_path,
            "--pdf-engine=weasyprint",
            "--pdf-engine-opt=-q",
            "--mathjax",
            f"--lua-filter={lua_filter_path}",
            "-f", "html",
            "--resource-path=.",
            f"--resource-path={docs_dir}",
            f"--css={compiled_css_path}",
        ]
        def run_pandoc(pass_label: str) -> None:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=pandoc_timeout
                )
            except subprocess.TimeoutExpired as exc:
                raise PdfBuildError(
                    f"pandoc timed out after {pandoc_timeout}s building "
                    f"{output_path!r} ({pass_label})"
                ) from exc
            if result.returncode != 0:
                raise PdfBuildError(
                    f"pandoc exited with status {result.returncode} "
                    f"building {output_path!r} ({pass_label})",
                    returncode=result.returncode,
                    stderr=result.stderr,
                )

        run_pandoc("first pass" if index_terms else "only pass")

        if index_terms:
            # output_path is this first pass's own finished PDF at this
            # point - exactly what extract_term_pages() needs to inspect.
            occurrence_pages = extract_term_pages(output_path, len(index_terms))
            entries = build_index_entries(index_terms, occurrence_pages, index_code_flags)
            index_content_html = render_index_content(entries)
            body_html = body_html.replace(
                f'<div id="{INDEX_CONTENT_ID}"></div>',
                f'<div id="{INDEX_CONTENT_ID}">{index_content_html}</div>',
            )
            write_concatenated_html(body_html)
            run_pandoc("second pass")

        rotate_landscape_pages(output_path, double_sided=double_sided)
    finally:
        if use_temp_dir or not keep_work_dir:
            shutil.rmtree(resolved_work_dir, ignore_errors=True)

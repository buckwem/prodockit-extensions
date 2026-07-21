# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Drives a full PDF build entirely from `zensical.toml`, for a project
that doesn't want to write any Python at all - see `prodockit.pdf.cli` for the
command-line tool built on top of this.

`build_pdf_from_zensical_config()` reads your project's nav, docs
directory, and PDF-specific settings (all under the same `[project.extra]`
table your other Zensical settings live in), renders every nav page
through Zensical's own Markdown pipeline, and calls
`prodockit.pdf.build.build_pdf()` with everything wired up: icon/Mermaid/
MathJax auto-detection included, so a typical project needs zero
additional configuration beyond what it likely already has.
"""

from __future__ import annotations

import base64
import os
import re
import shutil

from prodockit.pdf.build import Page, build_pdf
from prodockit.pdf.icons import build_icon_registry, discover_icon_dirs
from prodockit.pdf.mermaid import render_mermaid_diagram
from prodockit.pdf.release import get_latest_release_tag
from prodockit.pdf.source_bundle import build_source_bundle
from prodockit.settings import flatten_nav, heading_numbering_enabled, reference_style_values
from prodockit.zensical_macros import _compute_site_word_count, _get_repo_url

# Front matter flag marking a page for letter-based numbering ("A", "A.1",
# ...) - same default name as prodockit.headings' own `appendix_attr` option,
# so a project already using continuous numbering doesn't need a second,
# differently-named flag for the PDF.
APPENDIX_FRONT_MATTER_KEY = "is_appendix"

# Front matter key overriding a page's own running header text - see
# `fix_up_page_html()`'s own docstring in prodockit.pdf.html.
RECTO_TITLE_FRONT_MATTER_KEY = "recto_title"


def _inline_css_urls(css_text: str, css_dir: str) -> str:
    """Rewrites every relative `url(...)` reference in `css_text` (e.g. a
    `background-image` or a `.md-logo img { content: url(...) }` swap) into
    a base64 `data:` URI resolved against `css_dir`, leaving anything
    already a `data:`/`http(s):`/fragment (`#...`) URL, or a path that
    doesn't resolve to a real file, untouched.

    `build_pdf()`'s compiled CSS lives in its own temporary work directory,
    not `css_dir` - a relative reference in a project's own `extra_css`
    that resolves fine on the live website (relative to that stylesheet's
    own path) would otherwise point nowhere once compiled there, silently
    breaking e.g. a light/dark logo swap or a header background image."""

    def url_replacer(match: re.Match[str]) -> str:
        quote, ref = match.group(1), match.group(2)
        if ref.startswith(("data:", "http://", "https://", "#")):
            return match.group(0)
        asset_path = os.path.abspath(os.path.join(css_dir, ref))
        if not os.path.isfile(asset_path):
            return match.group(0)
        ext = os.path.splitext(asset_path)[1].lower().strip(".")
        mime_type = {"svg": "image/svg+xml", "jpg": "image/jpeg"}.get(ext, f"image/{ext}")
        with open(asset_path, "rb") as f:
            b64_payload = base64.b64encode(f.read()).decode("utf-8")
        return f"url({quote}data:{mime_type};base64,{b64_payload}{quote})"

    return re.sub(r'url\((["\']?)([^)"\']+)\1\)', url_replacer, css_text)


def _find_mmdc_bin(configured: str | None) -> str | None:
    """Resolves a usable `mmdc` (mermaid-cli) binary path: an explicit
    `configured` path if given and it exists, else whatever `mmdc` is found
    on `PATH`, else a couple of common local-install locations, else None
    (Mermaid diagrams are then left unrendered rather than failing the
    whole build).

    A relative `configured` path resolves against the current working
    directory, not wherever the `zensical.toml` it came from lives - fine
    for the common case of running `prodockit pdf` from the project root
    (the same directory both `configured` and `config_path` are typically
    relative to), but a `-f`/`--config-file` pointing at a project in a
    different directory needs an absolute `pdf_mmdc_bin` instead.
    """
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("mmdc")
    if found:
        return found
    for candidate in (
        os.path.join("tools", "mermaid", "node_modules", ".bin", "mmdc"),
        os.path.join("node_modules", ".bin", "mmdc"),
    ):
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def _find_tex2svg_script(configured: str | None) -> str | None:
    """Resolves a usable `tex2svg`-style Node script path for TeX math
    pre-rendering: an explicit `configured` path if given and it exists,
    else a common local-install location, else None (math formulas are
    then left as literal, unrendered text rather than failing the whole
    build). Same CWD-relative caveat for a relative `configured` path as
    `_find_mmdc_bin` above."""
    if configured and os.path.exists(configured):
        return os.path.abspath(configured)
    candidate = os.path.join("tools", "mathjax", "tex2svg.js")
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    return None


def build_pdf_from_zensical_config(
    config_path: str = "zensical.toml", *, markdown_file: str | None = None
) -> str:
    """Builds a PDF entirely from `config_path` (a Zensical config file)
    and returns the path it was written to.

    If `markdown_file` is given (a path relative to `project.docs_dir`),
    the PDF is built from just that one file instead of `project.nav` -
    everything else (fonts, page size, margins, `heading_numbering`, and so
    on) still comes from `config_path` exactly as it would for a full
    nav-driven build. `pdf_output` still overrides the output path if set;
    otherwise it defaults to `markdown_file`'s own name (with a `.pdf`
    extension) inside `docs_dir`, rather than `site_documentation.pdf`.

    Reads (all optional except `nav` when `markdown_file` isn't given, with
    defaults matching a typical Zensical project):

    - `project.nav` - which pages to include, in order (ignored if
      `markdown_file` is given).
    - `project.docs_dir` (default `"docs"`).
    - `project.site_name`, `project.copyright`, `project.repo_url`.
    - `project.theme.font.text`/`.code` - main/monospace font.
    - `project.theme.icon.admonition` - per-admonition-type icon shortcodes,
      if you've customised them (used to give admonitions an icon in the
      PDF the same way your website already shows one).
    - Under `project.extra`: `pdf_output` (default
      `"<docs_dir>/site_documentation.pdf"`), `pdf_page_size`,
      `pdf_margin_{top,right,bottom,left}`, `pdf_double_sided` (default
      `false`) and its own `pdf_margin_{inner,outer}` (replace
      `pdf_margin_{left,right}` when set - see `build_pdf()`'s own
      `double_sided` docs), `pdf_header_footer_{font_size,color,divider_color}`,
      `heading_numbering` (default `true`), `reference_style` (`"european"`
      - the default - or `"global"`), `reference_spacing_european`,
      `reference_indent_global`, `reference_spacing_global`,
      `pdf_mmdc_bin` and `pdf_tex2svg_script` (both auto-detected if unset -
      see `_find_mmdc_bin`/`_find_tex2svg_script` - Mermaid diagrams/math
      formulas are simply left unrendered if neither is found, rather than
      failing the build), `pdf_math_dir`, `pdf_include_table_of_contents`
      (default `true`), `pdf_table_of_contents_title`, `pdf_include_index`
      (default `false` - a back-of-book index from every `\\index{Term}`
      marker (see `prodockit.index`) anywhere in your content; see `build_pdf()`'s own
      `include_index` docs for why this needs a real two-pass build, and
      `prodockit.pdf.index` for the module behind it), `pdf_index_title`,
      `pdf_source_bundle` (default `false` - see `prodockit.pdf.source_bundle`
      for what this builds and why it's a separate PDF rather than part of
      the one above; only runs for a full, nav-driven build, never for a
      `markdown_file`-scoped one).
    - `project.extra_css` - your site's own stylesheet(s) (the same setting
      Zensical itself reads to style the live website), passed through as
      `build_pdf()`'s own `extra_css` - so a project-specific `@media print`
      rule (e.g. hiding a website-only "Download PDF" link/button) applies
      in the PDF too, since WeasyPrint always renders in print mode. Any
      relative `url(...)` reference in it (e.g. a light/dark logo swap or
      a header background image) is resolved and base64-embedded before
      being passed through, since the compiled CSS `build_pdf()` writes
      lives in its own temporary directory, not wherever your stylesheet
      does.

    A page's own front matter `is_appendix: true` flag gives it letter-
    based numbering, matching `prodockit.headings`' own `appendix_attr`
    default. A page's own front matter `recto_title: "Short Title"`
    overrides that page's running header text - see `fix_up_page_html()`'s
    own docstring in `prodockit.pdf.html`.

    **Cover page markers**: for a full, nav-driven build (never a
    `markdown_file`-scoped one) whose first page is `nav`'s own index
    page, any of these literal strings in that page's markdown are
    substituted with a real value once its HTML exists - no configuration
    needed beyond writing the marker itself:

    - `{WORDCOUNT}` - the site-wide word count (see
      `prodockit.zensical_macros._compute_site_word_count()` - the exact
      same value a `{{ word_count }}` website macro would show), so a
      submission's PDF cover page and its live website page never
      disagree.
    - `{REPOURL}` - the git-detected repo URL (see
      `prodockit.zensical_macros._get_repo_url()`).
    - `{RELEASE}` - the latest published GitHub/GitLab release tag (see
      `prodockit.pdf.release.get_latest_release_tag()`) - the whole line
      containing this marker is dropped instead if there isn't one (most
      projects never publish a release at all).
    - `{{ site_name }}` - this function never evaluates Jinja, so the
      exact same literal text a website macro variable uses substitutes
      directly here too.
    """
    import zensical.config as zensical_config
    from zensical.markdown.render import render as zensical_render

    config = zensical_config.parse_config(config_path)
    extra = config.get("extra") or {}
    theme = config.get("theme") or {}
    font = theme.get("font") or {}
    admonition_icon_config = (theme.get("icon") or {}).get("admonition") or {}

    docs_dir = config.get("docs_dir") or "docs"
    if markdown_file:
        nav_pages = [{"url": markdown_file}]
    else:
        nav_pages = flatten_nav(config.get("nav") or [])
        if not nav_pages:
            raise ValueError(f"No pages found in {config_path}'s nav - nothing to build")

    icon_registry = build_icon_registry(discover_icon_dirs(docs_dir))

    extra_css = ""
    for css_rel_path in config.get("extra_css") or []:
        full_css_path = os.path.join(docs_dir, css_rel_path)
        with open(full_css_path, encoding="utf-8") as f:
            extra_css += _inline_css_urls(f.read(), os.path.dirname(full_css_path)) + "\n"

    mmdc_bin = _find_mmdc_bin(extra.get("pdf_mmdc_bin"))
    mermaid_state = {"count": 0}
    render_mermaid = None
    if mmdc_bin:
        mermaid_dir = os.path.join(docs_dir, ".prodockit-pdf-mermaid")

        def render_mermaid(source: str) -> str | None:
            mermaid_state["count"] += 1
            return render_mermaid_diagram(source, mmdc_bin, mermaid_dir, mermaid_state["count"])

    tex2svg_script = _find_tex2svg_script(extra.get("pdf_tex2svg_script"))
    math_dir = extra.get("pdf_math_dir")
    if math_dir:
        # build_lua_filter()'s math_dir "must already exist or be creatable
        # by the caller" - only relevant here for an explicitly configured
        # directory; the default (build_pdf()'s own work_dir) already
        # exists by the time the Lua filter needs it.
        os.makedirs(math_dir, exist_ok=True)

    page_objects = []
    for nav_page in nav_pages:
        docs_rel_path = nav_page["url"]
        full_path = os.path.join(docs_dir, docs_rel_path)
        with open(full_path, encoding="utf-8") as f:
            raw_content = f.read()
        result = zensical_render(raw_content, docs_rel_path, docs_rel_path)
        page_objects.append(
            Page(
                docs_rel_path=docs_rel_path,
                html=result["content"],
                is_index=bool(nav_page.get("is_index")),
                is_appendix=bool(result["meta"].get(APPENDIX_FRONT_MATTER_KEY, False)),
                recto_title=result["meta"].get(RECTO_TITLE_FRONT_MATTER_KEY) or None,
            )
        )

    # Cover-page markers (see this function's own docs below) - a
    # nav-driven build's own cover page (its first page, if flagged
    # is_index) can use {WORDCOUNT}/{REPOURL}/{RELEASE}/{{ site_name }}
    # literally in its markdown, substituted here once the page's real
    # HTML exists. Skipped for a single markdown_file build - there's no
    # "cover page" to speak of, just whichever one page was requested.
    if not markdown_file and page_objects and page_objects[0].is_index and len(page_objects) > 1:
        cover = page_objects[0]
        cover_html = cover.html
        if "{WORDCOUNT}" in cover_html:
            cover_html = cover_html.replace("{WORDCOUNT}", _compute_site_word_count(config))
        if "{REPOURL}" in cover_html or "{RELEASE}" in cover_html:
            # Computed from the local git remote (like the website's own
            # {{ repo_url }} - see _get_repo_url()), not this function's
            # own repo_url (config.get("repo_url"), passed to build_pdf()
            # below): in practice they usually match, but they're not the
            # same mechanism.
            git_repo_url = _get_repo_url()
        if "{REPOURL}" in cover_html:
            cover_html = cover_html.replace("{REPOURL}", git_repo_url)
        if "{RELEASE}" in cover_html:
            # Unlike {WORDCOUNT}/{REPOURL}, which are always locally
            # computable, most projects will never have a published
            # release - an empty result drops the whole line rather than
            # leaving a bare "Release: " label behind.
            release_tag = get_latest_release_tag(git_repo_url)
            if release_tag:
                cover_html = cover_html.replace("{RELEASE}", release_tag)
            else:
                cover_html = re.sub(r"^.*\{RELEASE\}.*\n?", "", cover_html, flags=re.MULTILINE)
        if "{{ site_name }}" in cover_html:
            # prodockit.pdf never evaluates Jinja, so the exact same
            # literal "{{ site_name }}" text used for the website's macro
            # variable can just be substituted directly here too - one
            # line of markdown works for both outputs, no separate marker.
            cover_html = cover_html.replace("{{ site_name }}", config.get("site_name") or "")
        cover.html = cover_html

    if extra.get("pdf_output"):
        output_path = str(extra["pdf_output"])
    elif markdown_file:
        stem = os.path.splitext(os.path.basename(markdown_file))[0]
        output_path = os.path.join(docs_dir, f"{stem}.pdf")
    else:
        output_path = os.path.join(docs_dir, "site_documentation.pdf")
    (
        reference_style,
        reference_spacing_european,
        reference_indent_global,
        reference_spacing_global,
    ) = reference_style_values(extra)

    build_pdf(
        page_objects,
        output_path,
        docs_dir=docs_dir,
        extra_css=extra_css,
        repo_url=config.get("repo_url") or "",
        admonition_icon_config=admonition_icon_config,
        icon_registry=icon_registry,
        render_mermaid=render_mermaid,
        main_font=font.get("text") or "Inter",
        mono_font=font.get("code") or "JetBrains Mono",
        copyright_text=config.get("copyright") or "",
        site_name=config.get("site_name") or "",
        page_size=extra.get("pdf_page_size") or "A4",
        margin_top=extra.get("pdf_margin_top") or "2cm",
        margin_right=extra.get("pdf_margin_right") or "2cm",
        margin_bottom=extra.get("pdf_margin_bottom") or "2cm",
        margin_left=extra.get("pdf_margin_left") or "2cm",
        double_sided=bool(extra.get("pdf_double_sided", False)),
        margin_inner=extra.get("pdf_margin_inner") or "2cm",
        margin_outer=extra.get("pdf_margin_outer") or "2cm",
        header_footer_font_size=extra.get("pdf_header_footer_font_size") or "10pt",
        header_footer_color=extra.get("pdf_header_footer_color") or "#555555",
        header_footer_divider_color=extra.get("pdf_header_footer_divider_color") or "#e2e8f0",
        reference_style_global=reference_style == "global",
        reference_spacing_european=reference_spacing_european,
        reference_indent_global=reference_indent_global,
        reference_spacing_global=reference_spacing_global,
        heading_numbering_enabled=heading_numbering_enabled(extra),
        mathjax_available=tex2svg_script is not None,
        math_dir=math_dir,
        tex2svg_script=tex2svg_script or "",
        include_table_of_contents=bool(extra.get("pdf_include_table_of_contents", True)),
        table_of_contents_title=extra.get("pdf_table_of_contents_title") or "Table of Contents",
        include_index=bool(extra.get("pdf_include_index", False)),
        index_title=extra.get("pdf_index_title") or "Index",
    )

    if not markdown_file and bool(extra.get("pdf_source_bundle", False)):
        build_source_bundle(
            "source_bundle.pdf",
            root=os.path.dirname(os.path.abspath(config_path)),
            report_name=config.get("site_name") or "",
            page_size=extra.get("pdf_page_size") or "A4",
        )

    return output_path

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Drives a full PDF build entirely from `zensical.toml`, for a project
that doesn't want to write any Python at all - see `zendoc.pdf.cli` for the
command-line tool built on top of this.

`build_pdf_from_zensical_config()` reads your project's nav, docs
directory, and PDF-specific settings (all under the same `[project.extra]`
table your other Zensical settings live in), renders every nav page
through Zensical's own Markdown pipeline, and calls
`zendoc.pdf.build.build_pdf()` with everything wired up: icon/Mermaid/
MathJax auto-detection included, so a typical project needs zero
additional configuration beyond what it likely already has.
"""

from __future__ import annotations

import os
import shutil

from zendoc.pdf.build import Page, build_pdf
from zendoc.pdf.icons import build_icon_registry, discover_icon_dirs
from zendoc.pdf.mermaid import render_mermaid_diagram
from zendoc.settings import flatten_nav, heading_numbering_enabled, reference_style_values

# Front matter flag marking a page for letter-based numbering ("A", "A.1",
# ...) - same default name as zendoc.headings' own `appendix_attr` option,
# so a project already using continuous numbering doesn't need a second,
# differently-named flag for the PDF.
APPENDIX_FRONT_MATTER_KEY = "is_appendix"


def _find_mmdc_bin(configured: str | None) -> str | None:
    """Resolves a usable `mmdc` (mermaid-cli) binary path: an explicit
    `configured` path if given and it exists, else whatever `mmdc` is found
    on `PATH`, else a couple of common local-install locations, else None
    (Mermaid diagrams are then left unrendered rather than failing the
    whole build)."""
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
    build)."""
    if configured and os.path.exists(configured):
        return os.path.abspath(configured)
    candidate = os.path.join("tools", "mathjax", "tex2svg.js")
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    return None


def build_pdf_from_zensical_config(config_path: str = "zensical.toml") -> str:
    """Builds a PDF entirely from `config_path` (a Zensical config file)
    and returns the path it was written to.

    Reads (all optional except `nav`, with defaults matching a typical
    Zensical project):

    - `project.nav` - which pages to include, in order.
    - `project.docs_dir` (default `"docs"`).
    - `project.site_name`, `project.copyright`, `project.repo_url`.
    - `project.theme.font.text`/`.code` - main/monospace font.
    - `project.theme.icon.admonition` - per-admonition-type icon shortcodes,
      if you've customised them (used to give admonitions an icon in the
      PDF the same way your website already shows one).
    - Under `project.extra`: `pdf_output` (default
      `"<docs_dir>/site_documentation.pdf"`), `pdf_page_size`,
      `pdf_margin_{top,right,bottom,left}`,
      `pdf_header_footer_{font_size,color,divider_color}`,
      `heading_numbering` (default `true`), `reference_style` (`"european"`
      - the default - or `"global"`), `reference_spacing_european`,
      `reference_indent_global`, `reference_spacing_global`,
      `pdf_mmdc_bin` and `pdf_tex2svg_script` (both auto-detected if unset -
      see `_find_mmdc_bin`/`_find_tex2svg_script` - Mermaid diagrams/math
      formulas are simply left unrendered if neither is found, rather than
      failing the build), `pdf_math_dir`, `pdf_include_table_of_contents`
      (default `true`), `pdf_table_of_contents_title`.

    A page's own front matter `is_appendix: true` flag gives it letter-
    based numbering, matching `zendoc.headings`' own `appendix_attr`
    default.
    """
    import zensical.config as zensical_config
    from zensical.markdown.render import render as zensical_render

    config = zensical_config.parse_config(config_path)
    extra = config.get("extra") or {}
    theme = config.get("theme") or {}
    font = theme.get("font") or {}
    admonition_icon_config = (theme.get("icon") or {}).get("admonition") or {}

    docs_dir = config.get("docs_dir") or "docs"
    nav_pages = flatten_nav(config.get("nav") or [])
    if not nav_pages:
        raise ValueError(f"No pages found in {config_path}'s nav - nothing to build")

    icon_registry = build_icon_registry(discover_icon_dirs(docs_dir))

    mmdc_bin = _find_mmdc_bin(extra.get("pdf_mmdc_bin"))
    mermaid_state = {"count": 0}
    render_mermaid = None
    if mmdc_bin:
        mermaid_dir = os.path.join(docs_dir, ".zendoc-pdf-mermaid")

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
        with open(full_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
        result = zensical_render(raw_content, docs_rel_path, docs_rel_path)
        page_objects.append(
            Page(
                docs_rel_path=docs_rel_path,
                html=result["content"],
                is_index=bool(nav_page.get("is_index")),
                is_appendix=bool(result["meta"].get(APPENDIX_FRONT_MATTER_KEY, False)),
            )
        )

    output_path = extra.get("pdf_output") or os.path.join(docs_dir, "site_documentation.pdf")
    reference_style, reference_spacing_european, reference_indent_global, reference_spacing_global = (
        reference_style_values(extra)
    )

    build_pdf(
        page_objects,
        output_path,
        docs_dir=docs_dir,
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
    )
    return output_path

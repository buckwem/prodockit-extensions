# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.pdf: build a standalone PDF from Zensical-rendered HTML via
Pandoc and WeasyPrint.

Zensical's own Markdown pipeline (and the prodockit.headings/refs/citations/
glossary extensions built for it) targets *websites* - Pandoc, not
Python-Markdown, does the actual HTML-to-PDF conversion, and it has no
awareness of Zensical/pymdownx-specific markup at all. This package collects
the workarounds a Pandoc/WeasyPrint-based PDF pipeline consuming
Zensical-rendered HTML needs.

For most projects, :func:`build_pdf` is the only thing you need - hand it
your already-rendered pages and where you want the PDF written:

    from prodockit.pdf import Page, build_pdf

    build_pdf(
        [Page(docs_rel_path="index.md", html=rendered_index_html, is_index=True),
         Page(docs_rel_path="chapter1.md", html=rendered_chapter1_html)],
        "dist/report.pdf",
    )

The individual pieces it's built from are also importable directly, if you
need more control over how they fit together: HTML fixups for Pandoc's
reader/writer quirks (:mod:`prodockit.pdf.html`), the Lua filter for
chapter-prefix numbering and caption ordering (:mod:`prodockit.pdf.lua`), the
CSS a compiled PDF needs that a live website doesn't (:mod:`prodockit.pdf.css`),
and standalone helpers for Mermaid pre-rendering (:mod:`prodockit.pdf.mermaid`)
and admonition icons (:mod:`prodockit.pdf.icons`).

:mod:`prodockit.pdf.source_bundle` is unrelated to the rest of this package -
it bundles a git repository's own source files (not Zensical/Markdown content
at all) into a separate PDF, skipping Pandoc entirely since there's no
Markdown involved.

No published API stability contract yet - see prodockit-extensions#7.
"""

from prodockit.pdf.build import Page, PdfBuildError, build_pdf

__all__ = ["Page", "PdfBuildError", "build_pdf"]

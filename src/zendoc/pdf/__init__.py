# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc.pdf: helpers for building a standalone PDF from Zensical-rendered
HTML via Pandoc and WeasyPrint.

Zensical's own Markdown pipeline (and the zendoc.headings/refs/citations/
glossary extensions built for it) targets *websites* - Pandoc, not
Python-Markdown, does the actual HTML-to-PDF conversion, and it has no
awareness of Zensical/pymdownx-specific markup at all. This package collects
the workarounds a Pandoc/WeasyPrint-based PDF pipeline consuming
Zensical-rendered HTML needs: fixing up HTML Pandoc's reader/writer would
otherwise mishandle (:mod:`zendoc.pdf.html`), a Lua filter for chapter-prefix
numbering and caption ordering (:mod:`zendoc.pdf.lua`), the CSS a compiled
PDF needs that a live website doesn't (:mod:`zendoc.pdf.css`), and
standalone helpers for Mermaid pre-rendering (:mod:`zendoc.pdf.mermaid`) and
admonition icons (:mod:`zendoc.pdf.icons`).

No published API contract yet - see zendoc-extension#7. Import whatever's
needed directly, the same way as the rest of this package.
"""

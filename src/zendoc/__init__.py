# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc: a family of independent Python-Markdown extensions for section
cross-references and bibliography/citation handling, in the spirit of
pymdown-extensions - each is its own extension, enabled separately:

- ``zendoc.headings`` - heading ids and hierarchical section numbers.
- ``zendoc.refs`` - ``\\ref{id}`` section cross-references.
- ``zendoc.citations`` - define a source once, cite it by key anywhere with
  ``\\cite{id}``.
- ``zendoc.glossary`` - define a term once, insert it by id anywhere with
  ``\\gls{id}``.

Built for use with Zensical (https://zensical.org/) - enable an extension in
`zensical.toml` the same way as a built-in or pymdownx one. Zensical's
per-page rendering context is detected automatically where it's useful (see
zendoc.headings'/zendoc.citations'/zendoc.glossary's cross-page registry
sharing).

Also includes ``zendoc.pdf``, a family of plain functions (not a
Python-Markdown extension - there's no ``markdown.extensions`` entry point
for it) for building a standalone PDF from Zensical-rendered HTML via Pandoc
and WeasyPrint: HTML fixups for Pandoc's own reader/writer quirks, a Lua
filter, and the compiled CSS a PDF needs on top of a project's own website
stylesheet.

See https://buckwem.github.io/zendoc-extension/ for documentation.
"""

__version__ = "0.5.0"

__all__ = ["__version__"]

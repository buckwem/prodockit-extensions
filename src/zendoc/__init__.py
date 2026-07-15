# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc: a family of extensions for Zensical (https://zensical.org/) -
the pieces professional and academic documentation commonly needs that
Zensical doesn't provide out of the box, each usable independently:

- ``zendoc.headings`` - heading ids and hierarchical section numbers.
- ``zendoc.refs`` - ``\\ref{id}`` section cross-references.
- ``zendoc.citations`` - define a source once, cite it by key anywhere with
  ``\\cite{id}``.
- ``zendoc.glossary`` - define a term once, insert it by id anywhere with
  ``\\gls{id}``.
- ``zendoc.pdf`` - a Pandoc/WeasyPrint pipeline for building a standalone
  PDF from Zensical-rendered HTML, the kind of downloadable, submittable
  document professional/academic reports typically need alongside the
  website itself.

``zendoc.headings``/``zendoc.refs``/``zendoc.citations``/``zendoc.glossary``
are Python-Markdown extensions, in the spirit of pymdown-extensions - enable
one in `zensical.toml` the same way as a built-in or pymdownx extension.
Zensical's per-page rendering context is detected automatically where it's
useful (see their own cross-page registry sharing). ``zendoc.pdf`` is a
family of plain functions instead (there's no ``markdown.extensions`` entry
point for it - a PDF build pipeline isn't a Markdown syntax extension):
HTML fixups for Pandoc's own reader/writer quirks, a Lua filter, and the
compiled CSS a PDF needs on top of a project's own website stylesheet.

See https://buckwem.github.io/zendoc-extension/ for documentation.
"""

__version__ = "0.7.0"

__all__ = ["__version__"]

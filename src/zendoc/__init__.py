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
- ``zendoc.pdf`` - build a standalone PDF from your Zensical site via
  Pandoc and WeasyPrint, the kind of downloadable, submittable document
  professional/academic reports typically need alongside the website
  itself. Run ``zendoc pdf`` from your project root - no Python required,
  it reads the same ``zensical.toml`` your site already has.
- ``zendoc.zensical_macros`` - Jinja variables/macros for Zensical's own
  macros plugin: a site-wide word count, the git-detected repository URL,
  chapter/appendix numbering that continues across pages, and reference/
  acronym/glossary spacing that matches ``zendoc.pdf``'s own PDF output.

``zendoc.headings``/``zendoc.refs``/``zendoc.citations``/``zendoc.glossary``
are Python-Markdown extensions, in the spirit of pymdown-extensions - enable
one in `zensical.toml` the same way as a built-in or pymdownx extension.
Zensical's per-page rendering context is detected automatically where it's
useful (see their own cross-page registry sharing). ``zendoc.pdf`` is a
command-line tool instead (there's no ``markdown.extensions`` entry point
for it - a PDF build pipeline isn't a Markdown syntax extension).
``zendoc.zensical_macros`` is a plain ``define_env()`` module for Zensical's
macros plugin's own ``modules`` config, not a Markdown extension either.

See https://buckwem.github.io/zendoc-extensions/ for documentation.
"""

__version__ = "0.10.0"

__all__ = ["__version__"]

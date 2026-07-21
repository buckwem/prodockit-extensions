# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit: a family of extensions for Zensical (https://zensical.org/) -
the pieces professional and academic documentation commonly needs that
Zensical doesn't provide out of the box, each usable independently:

- ``prodockit.headings`` - heading ids and hierarchical section numbers.
- ``prodockit.refs`` - ``\\ref{id}`` section cross-references.
- ``prodockit.citations`` - define a source once, cite it by key anywhere with
  ``\\cite{id}``.
- ``prodockit.glossary`` - define a term once, insert it by id anywhere with
  ``\\gls{id}``.
- ``prodockit.tables`` - percentage or fixed column widths on a table, via a
  ``width`` attribute already attachable to a header cell with ``attr_list``.
- ``prodockit.bibliography`` - an alternative to ``prodockit.citations``: define
  sources in a BibTeX/BibLaTeX ``.bib`` file instead of by hand, and format
  ``\\cite{id}``/the reference list in any Citation Style Language (CSL)
  style (APA, IEEE, Harvard, ...) via Pandoc's own ``--citeproc`` - requires
  `pandoc` on ``PATH`` even without a PDF build.
- ``prodockit.index`` - mark a term inline with ``\\index{Term}`` for a
  traditional, PDF-only back-of-book index (see ``prodockit.pdf``'s own
  ``pdf_include_index`` below) - with hierarchical sub-entries and
  code-styled terms.
- ``prodockit.pdf`` - build a standalone PDF from your Zensical site via
  Pandoc and WeasyPrint, the kind of downloadable, submittable document
  professional/academic reports typically need alongside the website
  itself. Run ``prodockit pdf`` from your project root - no Python required,
  it reads the same ``zensical.toml`` your site already has.
- ``prodockit.zensical_macros`` - Jinja variables/macros for Zensical's own
  macros plugin: a site-wide word count, the git-detected repository URL,
  chapter/appendix numbering that continues across pages, and reference/
  acronym/glossary spacing that matches ``prodockit.pdf``'s own PDF output.

``prodockit.headings``/``prodockit.refs``/``prodockit.citations``/``prodockit.glossary``/
``prodockit.tables``/``prodockit.bibliography``/``prodockit.index`` are Python-Markdown
extensions, in the spirit of pymdown-extensions - enable
one in `zensical.toml` the same way as a built-in or pymdownx extension.
Zensical's per-page rendering context is detected automatically where it's
useful (see their own cross-page registry sharing). ``prodockit.pdf`` is a
command-line tool instead (there's no ``markdown.extensions`` entry point
for it - a PDF build pipeline isn't a Markdown syntax extension).
``prodockit.zensical_macros`` is a plain ``define_env()`` module for Zensical's
macros plugin's own ``modules`` config, not a Markdown extension either.

See https://buckwem.github.io/prodockit-extensions/ for documentation.
"""

__version__ = "0.6.8"

__all__ = ["__version__"]

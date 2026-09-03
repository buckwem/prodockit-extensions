# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit: a family of extensions for Zensical (https://zensical.org/) -
the pieces professional and academic documentation commonly needs that
Zensical doesn't provide out of the box, each usable independently:

- ``prodockit.headings`` - heading ids and hierarchical section numbers.
- ``prodockit.refs`` - ``\\ref{id}`` cross-references, resolving to a
  section's number and name or a captioned figure or table's label, and
  ``\\autoref{id}``, which additionally carries the target's page number in
  the PDF.
- ``prodockit.citations`` - define a source once, cite it by key anywhere with
  ``\\citeref{id}``.
- ``prodockit.glossary`` - define a term once, insert it by id anywhere with
  ``\\gls{id}``.
- ``prodockit.tables`` - column widths, dense tables, headers of more than one
  row, merged cells and rotated headings, all through an attribute already
  attachable to a cell with ``attr_list``.
- ``prodockit.bibliography`` - an alternative to ``prodockit.citations``: define
  sources in a BibTeX/BibLaTeX ``.bib`` file instead of by hand, and format
  ``\\cite{id}``/the reference list in any Citation Style Language (CSL)
  style (APA, IEEE, Harvard, ...) via Pandoc's own ``--citeproc`` - requires
  `pandoc` on ``PATH`` even without a PDF build.
- ``prodockit.index`` - mark a term inline with ``\\index{Term}`` for a
  traditional, PDF-only back-of-book index (see ``prodockit.pdf``'s own
  the extension's ``include`` option) - with hierarchical sub-entries and
  code-styled terms.
- ``prodockit.steps`` - numbered steps a reader works through in order,
  written as ``/// steps`` with a ``//// step | Title`` for each one. A
  step holds paragraphs, commands or a table, and ``start`` continues a
  procedure split across sections - written into the HTML in both the
  spellings a browser and WeasyPrint each read, since they disagree.
- ``prodockit.tree`` - a directory listing that looks like one: indentation is
  the structure, and the icons come from the project's own set.
- ``prodockit.pdf`` - build a standalone PDF from your Zensical site via
  Pandoc and WeasyPrint, the kind of downloadable, submittable document
  professional/academic reports typically need alongside the website
  itself. Run ``prodockit pdf`` from your project root - no Python required,
  it reads the same ``zensical.toml`` your site already has.
  ``prodockit source-bundle`` builds a separate PDF of your Markdown
  content and config, one file per page, into ``docs_dir`` - for a
  submission needing the underlying source alongside the rendered
  document, without paying for both PDFs on every build.
- ``prodockit.revision_dates`` - add per-page last-update dates to a completed
  Zensical website from complete Git history, or file modification
  times where no Git history exists. Run ``prodockit update-dates`` after the
  site's normal build command; it changes generated HTML, not source files.
- ``prodockit.bootstrap`` - set a new machine up from scratch, as twenty-three
  stages that can each be checked and repaired individually rather than a
  long sequence of instructions followed once and hoped over. Run
  ``prodockit bootstrap`` to report what is set up, ``--dry-run`` to see
  the exact commands, ``--apply`` to do it. Surrey's GitLab, gitlab.com
  and github.com for now.
- ``prodockit.adopt`` - add the standard prodockit authoring components to an
  existing Zensical repository without configuring Git, SSH or an editor.
  Mermaid diagrams and mathematical notation are independent opt-in stages,
  so a project using neither is not handed either Node toolchain. Run
  ``prodockit adopt`` to assess, ``--dry-run`` to preview and ``--apply`` to
  change local project files.
- ``prodockit.zensical_macros`` - Jinja variables/macros for Zensical's own
  macros plugin: a site-wide word count, the git-detected repository URL,
  the successfully applied template release, chapter/appendix numbering that continues across
  pages, and reference/acronym/glossary spacing that matches
  ``prodockit.pdf``'s own PDF output.
- ``prodockit.sync_repo`` - keep ``repo_url``/``repo_name``/brand icon/
  ``edit_uri``/``site_url`` and your README's badge row matching the git
  remote a checkout actually uses, so forking or mirroring a project
  between GitHub, GitLab and Bitbucket doesn't leave stale links, a wrong
  canonical URL, or badges for somebody else's repository behind. Run
  ``prodockit sync-repo`` from your project root.
- ``prodockit.diagnostics`` - inspect the active Python, commands,
  dependencies, ``zensical.toml`` inputs, configured renderers, pins, shared
  files, Git repository and template state without changing any of them. Run
  ``prodockit diag`` for a concise offline report, adding ``--verbose``,
  ``--online`` or ``--json`` when needed.
- ``prodockit.pins`` - find every place a build-input version is declared
  across a project (``pyproject.toml``, GitHub Actions workflows,
  ``.gitlab-ci.yml``, requirements/constraints files) and move them
  together, keeping each site's own operator so a library floor stays a
  floor and a build pin stays exact. Handles runner labels
  (``runs-on: ubuntu-24.04``), container tags (``image: python:3.14``) and
  ``<PACKAGE>_VERSION`` CI variables (``PANDOC_VERSION: "3.10.1"``) as well
  as pip specifiers - pandoc is managed by default alongside Zensical and
  WeasyPrint. Run ``prodockit pins`` from your project root.
- ``prodockit.init_tools`` - scaffold the Node tooling ``prodockit.pdf``
  needs to pre-render Mermaid diagrams and TeX maths into the PDF (neither
  can be rendered client-side there, since WeasyPrint has no JS engine).
  Run ``prodockit init-tools`` from your project root; a project using
  neither feature needs none of it.
- ``prodockit.template_sync`` - bring a project back into step with the
  template it came from, updating the template's own files and leaving the
  writing alone. Run ``prodockit template-sync`` from your project root;
  it reports by default and only writes with ``--apply``.
- ``prodockit.testing`` - pytest fixtures pointing at your project's own
  built site and PDF, plus checks for the failure modes every prodockit
  project shares (chiefly diagrams and maths reaching the PDF unrendered).
  ``pip install prodockit[testing]``; nothing else in prodockit imports it.

``prodockit.headings``/``prodockit.refs``/``prodockit.citations``/``prodockit.glossary``/
``prodockit.tables``/``prodockit.bibliography``/``prodockit.index``/``prodockit.steps``/
``prodockit.tree``
are Python-Markdown
extensions, in the spirit of pymdown-extensions - enable
one in `zensical.toml` the same way as a built-in or pymdownx extension.
Zensical's per-page rendering context is detected automatically where it's
useful (see their own cross-page registry sharing). ``prodockit.pdf`` is a
command-line tool instead (there's no ``markdown.extensions`` entry point
for it - a PDF build pipeline isn't a Markdown syntax extension).
``prodockit.zensical_macros`` is a plain ``define_env()`` module for Zensical's
macros plugin's own ``modules`` config, not a Markdown extension either, and
``prodockit.sync_repo``, ``prodockit.diagnostics`` and
``prodockit.template_sync`` are command-line tools (``prodockit sync-repo``,
``prodockit diag``, ``prodockit template-sync``) with a plain Python API
alongside them.

See https://prodockit.org/ for documentation.
"""

__version__ = "0.56.0"

__all__ = ["__version__"]

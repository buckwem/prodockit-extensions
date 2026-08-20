# Overview

prodockit adds the document features that professional and academic
[Zensical](https://zensical.org/) projects commonly need: numbered sections,
cross-references, citations, glossaries, richer tables, and a printable PDF.
Install one Python package, then enable only the parts your project uses.

If you want to see it working before reading the reference pages, follow
[Build your first site](getting-started.md). It starts with a new Zensical
project and ends at a live local preview.

## Choose what you need

### Authoring extensions

These are standard Python-Markdown extensions configured in `zensical.toml`:

| Extension | Use it for |
| --- | --- |
| [`prodockit.headings`](extensions/headings.md) | Numbered headings |
| [`prodockit.refs`](extensions/refs.md) | Cross-references to headings, figures, and tables |
| [`prodockit.citations`](extensions/citations.md) | A small, Markdown-defined reference list |
| [`prodockit.glossary`](extensions/glossary.md) | Acronyms and glossary terms |
| [`prodockit.tables`](extensions/tables.md) | Widths, merged cells, dense tables, and richer headers |
| [`prodockit.tree`](extensions/tree.md) | Readable directory trees |
| [`prodockit.steps`](extensions/steps.md) | Procedures presented as numbered steps |
| [`prodockit.bibliography`](extensions/bibliography.md) | BibTeX/BibLaTeX citations formatted with CSL |
| [`prodockit.index`](extensions/index-terms.md) | A PDF-only back-of-book index |

Every extension is independent. Start with one; add another when the document
needs it.

### Publishing and project tools

prodockit also provides commands and integrations rather than Markdown syntax:

| Feature | Use it for |
| --- | --- |
| [`prodockit pdf`](pdf.md) | Build a standalone PDF from the same navigation as the site |
| [`prodockit source-bundle`](pdf.md#bundling-source-into-a-pdf) | Package the underlying Markdown and configuration as a PDF |
| [`prodockit.zensical_macros`](macros.md) | Word counts, repository data, and document-wide numbering in templates |
| [`prodockit.testing`](devcons/testing.md) | Check the built website and PDF with pytest |
| [Project commands](command-line.md) | Set up tooling and keep repositories, pins, and templates current |

The [command-line map](command-line.md) says which commands change files and
which only report. The detailed reference stays in the section where each
command is used.

## Project status

prodockit is early but functional. All nine extensions, the PDF and source
bundle builders, website macros, testing support, and project-management
commands are implemented and tested. It currently targets Python 3.10–3.13;
see [Installation](installation.md) for external tools and
[Release Notes](about/changelog.md) for changes between versions.

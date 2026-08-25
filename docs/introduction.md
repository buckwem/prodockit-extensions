---
icon: lucide/signpost
---

{{ heading_counter_reset(page) }}

# Overview

This section is for anyone new to prodockit. It explains what the package
adds to Zensical, how to install it, and how to build a first local site before
you choose authoring or publishing features.

prodockit adds the document features that professional and academic
\index{Zensical} projects ([Zensical website](https://zensical.org/)) commonly need: numbered sections,
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
| [Maintain prodockit](project-maintenance.md) | Maintain the package repository, build pins, automation, and releases |

Go to the [Authoring reference](authoring.md) when you want to add document
features. Go to [Publish a document](publishing.md) when you are ready to use
the template, build a PDF, or publish with continuous integration. The
[command-line reference](command-line.md) says which commands change files and
which only report.

## Project status

prodockit is early but functional. All nine extensions, the PDF and source
bundle builders, website macros, testing support, and project-management
commands are implemented and tested. See
[Support and compatibility](about/support.md) for maturity, PyMdown Blocks and
other required versions, platform coverage, and known constraints. Read the
[release notes](about/changelog.md) before upgrading.

## Support prodockit

prodockit is free and open-source software. If it helps your work and you
would like to support its continued development, you can buy the maintainer a
coffee. Your contribution helps fund the software and online services used to
develop, test, and publish prodockit, as well as the time spent maintaining the
project and developing new features.

[Buy me a coffee](https://buymeacoffee.com/buckwem){ .md-button .md-button--primary target="_blank" rel="noopener" }

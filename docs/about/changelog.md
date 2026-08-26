---
icon: lucide/history
pdf_include: false
---

{{ heading_counter_reset(page) }}

# Release notes

This website page records the current capability baseline and short,
user-relevant changes made from now on. It is deliberately not included in
the PDF: Git commits, tags, pull requests, and
[GitHub Releases](https://github.com/buckwem/prodockit-extensions/releases)
are the complete historical record.

Read the Unreleased section when it is present, then every release between
the version a project uses and the version it will install. An entry is needed
only when it adds or changes behaviour that matters to a user, or requires an
upgrade action. Defect-by-defect history belongs in GitHub issues and pull
requests rather than here.

## Implemented functionality

- **Authoring:** Markdown extensions provide numbered headings, references,
  citations, glossaries, bibliographies, tables, numbered steps, directory
  trees, captions, acronyms, and a generated index.
- **Website integration:** Zensical macros, shared styles, configurable
  heading numbering, and optional Mermaid and MathJax support integrate the
  components into an existing or template-based documentation website.
- **PDF output:** `prodockit pdf` performs a clean Zensical build and creates a
  styled PDF with navigation-order chapters, cross-page links, figures,
  tables, references, running headers and footers, and an optional index.
- **Project setup:** `prodockit adopt` adds selected components to an existing
  Zensical or MkDocs project; `pdkboot` automates a complete template-based
  environment on supported macOS, Windows, and Ubuntu systems.
- **Project maintenance:** template sync, repository metadata sync, version
  pin checks, shared-file checks, source bundles, and built-output tests help
  keep projects reproducible and publishable.
- **Publishing:** the maintained template supplies reviewed GitHub Pages and
  GitLab Pages workflows for the website and PDF.

## 0.47.0 (2026-08-26)

- Added `pdf_include: false` page front matter for website pages that should
  be omitted from the complete PDF; an explicit single-page build can still
  include them.
- Replaced the historical change transcript with a concise capability summary
  and user-facing updates. GitHub retains the full record.
- Macro rendering errors now stop the documentation build instead of allowing
  a page containing broken macro output to be published.
- Pull requests now run a smaller risk-selected test set; pushes to `main`
  retain the complete supported-Python and installed-wheel matrices.

## 0.46.0 (2026-08-25)

- Added Python 3.14 project pins and compatibility checks.
- Added wheel-owned shared website styles and checks that downstream copies
  remain identical.
- Made the documented Zensical build output the standard PDF input.
- Added adoption of prodockit components into existing documentation sites.
- Expanded resumable machine setup and installed-wheel acceptance across
  supported operating systems and processor architectures.
- Improved template synchronisation and package-version guidance for document
  authors.

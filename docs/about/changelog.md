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
- **PDF output:** `prodockit pdf` consumes a completed Zensical website and
  creates a styled PDF with chapters, cross-page links, figures, tables,
  references, headers, footers, and an optional index.
- **Project setup:** `prodockit adopt` adds selected components to an existing
  Zensical or MkDocs project; `pdkboot` automates a complete template-based
  environment on supported macOS, Windows, and Ubuntu systems.
- **Project maintenance:** template sync, repository metadata sync, version
  pin checks, shared-file checks, source bundles, and built-output tests help
  keep projects reproducible and publishable.
- **Publishing:** the maintained template supplies reviewed GitHub Pages and
  GitLab Pages workflows for the website and PDF.

## 0.50.0 (2026-08-29)

- Added `prodockit config` diagnostics and reusable project-integrity checks for configuration mistakes, missing project files, disabled extensions and unresolved build inputs.
- Changed generated MathJax website assets to be restored from the pinned npm installation when needed rather than stored in a project repository.
- Made numbered figure captions follow the rendered image width on websites and in PDFs, including percentage, full-width and height-constrained images.

## 0.49.1 (2026-08-28)

- Changed `prodockit pdf` to consume and validate a prior strict Zensical build, then atomically add the finished PDF to the published site.

## 0.49.0 (2026-08-27)

- Added `prodockit update-dates` to add UTC per-page dates to completed site HTML and PDF footers without modifying source Markdown or calling the site builder. It uses Git history by default and file modification times for non-Git or untracked pages, or for every page with `--modification-dates`.

## 0.48.1 (2026-08-26)

- Added consent-gated Google Analytics to `prodockit.org`; analytics remains
  disabled until a visitor explicitly accepts it.
- Made optional Mermaid and maths adoption deterministic and faster by
  supplying canonical npm lockfiles, using `npm ci`, and reusing the package
  cache in installed-wheel CI. Custom Node manifests remain author-owned and
  continue to use `npm install` when they have no matching lockfile.
- Made the shared home-page hero more compact by top-aligning its content,
  reducing the illustration, and allowing the footer to follow the content
  instead of forcing the hero to fill the viewport.

## 0.48.0 (2026-08-26)

- Separated managed website and PDF styles into `pdk.css` and `pdk-pdf.css`,
  leaving `extra.css` and `print.css` for document-specific overrides.
- Added managed-file protection to template synchronisation and shared-file
  checks so local edits to Prodockit styles are reported before replacement.
- Moved PDF contents-page presentation into the stylesheet cascade, allowing
  a document's `print.css` to customise it without changing renderer code.

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

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
  Zensical or MkDocs project; `prodockit bootstrap` automates a complete template-based
  environment on supported macOS, Windows, and Ubuntu systems.
- **Project maintenance:** template sync, repository metadata sync, version
  pin checks, shared-file checks, source bundles, and built-output tests help
  keep projects reproducible and publishable.
- **Publishing:** the maintained template supplies reviewed GitHub Pages and
  GitLab Pages workflows for the website and PDF.

## Unreleased

- Made `template-sync --apply` create its review branch and GitLab merge request,
  while aligning build-input declarations and refreshing declared shared files.

## 0.51.1 (2026-08-29)

- Made `template-sync` fetch the released template selected for the project's
  host instead of silently using a nearby checkout. Surrey projects use the
  Surrey GitLab template and other supported projects use the canonical
  GitHub template; a local checkout now requires explicit `--template-path`.

## 0.51.0 (2026-08-29)

- Promoted the tested machine and template setup workflow to the public
  `prodockit bootstrap` command, also available as `pdk boot`. The preview
  `pdkboot` executable has been removed; existing `.pdkboot.toml`
  configuration files remain valid.
- Improved Bootstrap progress and failure messages, prerequisite ordering,
  repository handling, and verification of the exact published Pages site.
- Expanded adoption to preserve both string and mapping extension
  configurations, configure tree icons, and install shared diagram styles
  without copying the Prodockit website's own branding.
- Made generated table-caption anchors local to each page so captions in
  different Markdown files remain distinct.

## 0.50.1 (2026-08-29)

- Made website figure captions use the rendered figure width instead of the theme's narrower default caption measure.

## 0.50.0 (2026-08-29)

- Added `prodockit config` diagnostics and reusable project-integrity checks for configuration mistakes, missing project files, disabled extensions and unresolved build inputs.
- Changed generated MathJax website assets to be restored from the pinned npm installation when needed rather than stored in a project repository.
- Made numbered figure captions follow the rendered image width on websites and in PDFs, including percentage, full-width and height-constrained images.

## 0.49.1 (2026-08-28)

- Changed `prodockit pdf` to consume and validate a prior strict Zensical build, then atomically add the finished PDF to the published site.

## 0.49.0 (2026-08-27)

- Added `prodockit update-dates` to add UTC per-page dates to completed site HTML and PDF footers without modifying source Markdown or calling the site builder. It uses Git history by default and file modification times for non-Git or untracked pages, or for every page with `--modification-dates`.

## 0.48.1 (2026-08-26)

- Added consent-gated Google Analytics to `prodockit.org`; analytics remains disabled until a visitor explicitly accepts it.
- Made optional Mermaid and maths adoption deterministic and faster with canonical npm lockfiles and reusable CI caches. Custom Node manifests remain author-owned.
- Made the shared home-page hero more compact so the footer follows its content instead of being pushed below a full viewport.

## 0.48.0 (2026-08-26)

- Separated managed website and PDF styles into `pdk.css` and `pdk-pdf.css`,
  leaving `extra.css` and `print.css` for document-specific overrides.
- Added managed-file protection to template synchronisation and shared-file
  checks so local edits to Prodockit styles are reported before replacement.
- Moved PDF contents-page presentation into the stylesheet cascade, allowing
  a document's `print.css` to customise it without changing renderer code.

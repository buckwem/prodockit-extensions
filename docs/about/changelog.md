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
- **Project setup:** `prodockit adopt` adds components to an existing Zensical or
  MkDocs project; `prodockit bootstrap` automates a complete template environment.
- **Project maintenance:** read-only environment/project diagnostics, template
  sync, repository metadata sync, version pin checks, shared-file checks,
  source bundles, and built-output tests keep projects reproducible.
- **Publishing:** the maintained template supplies reviewed GitHub Pages and
  GitLab Pages workflows for the website and PDF.

## 0.55.0 (2026-09-02)

- Added `{% raw %}{{ applied_release }}{% endraw %}` so a template-derived site and PDF can show
  the last `prodockit-template` release successfully applied, independently
  of the student's own repository tags. Bootstrap records the initial release
  and `template-sync --apply` advances it only with a successful update.
- Replaced Prodockit's duplicate `site_name` and `release` variables with
  Zensical's native `{% raw %}{{ config.site_name }}{% endraw %}` and
  `{% raw %}{{ git.short_tag }}{% endraw %}` values.
- Made `prodockit pdf` stop with actionable guidance when it detects a stale
  or mismatched Python environment, before rendering can produce misleading
  failures or incomplete output.

## 0.54.1 (2026-09-01)

- Made Bootstrap retry transient package-service failures, including Snapcraft
  HTTP 408 responses, and made the native release tests validate, cache, and
  switch between compatible sources for immutable downloads.
- Made Adoption without Mermaid or maths agree with project diagnostics: unused
  Zensical Markdown defaults no longer require the optional PDF renderers.
- Made Adoption, Bootstrap, and project diagnostics exercise Mermaid rendering
  and MathJax module loading instead of accepting incomplete npm installations
  because their shim, script, or package directory exists. Browser diagnostics
  now execute Chrome/Chromium, and index diagnostics verify PyMuPDF can import.

## 0.54.0 (2026-09-01)

- Added read-only `pdk diag` environment and project health reports, with
  verbose, online, stable JSON, and author remediation for every check.
- Kept paired captioned PDF images centred at their authored width.

## 0.53.0 (2026-08-31)

- Kept `.web-only` images hidden inside captioned PDF figures, preventing paired website and PDF diagram variants from both appearing in the PDF.
- Added top, middle, and bottom vertical alignment for individual table cells,
  with top alignment as the website and PDF default.

## 0.52.0 (2026-08-31)

- Made Adoption write valid YAML callbacks, repair legacy callback strings,
  and recommend strict builds using the project's discovered configuration file.
- Extended table widths to promoted header rows and grouped column headers,
  distributing grouped widths according to their columns' content.
- Simplified the canonical analytics consent dialog and made accepting optional
  analytics reliably enable measurement.

## 0.51.4 (2026-08-30)

- Made Bootstrap safely upgrade unsupported prerequisites and resume after
  inconclusive installers; made Adoption refresh its version floor and managed `pdk.css`.

## 0.51.3 (2026-08-30)

- Added Bootstrap acceptance coverage for Surrey GitLab and public GitHub, using new
  and existing repositories across supported operating-system and processor combinations.

## 0.51.2 (2026-08-30)

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

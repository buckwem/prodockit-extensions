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

## Unreleased

- Preserved Zensical's syntax-token markup through the Pandoc conversion so
  highlighted code blocks in PDFs use its light-theme palette, with darker
  name text for print contrast, without losing line breaks or guessing the
  source language.
- Changed PDF code from a fixed point size to Zensical's relative `0.85em`
  scale, so code follows changes to the surrounding text size, increased its
  character weight to medium for print clarity, and reduced its background
  from about 13% to 4% shading. Inline code is optically aligned with body text.
- Gave complete website content-tab groups a persistent table-style border and
  theme-aware hover shadow, 3% selected-tab shading and balanced content
  spacing, and made PDF tab panels use subtler 5%/1% header and content shading
  with matching rounded outside corners. Copy-to-clipboard controls are now
  visible before hover as well.
- Made live-provider Bootstrap controls require an exact destination
  confirmation before entering a credential-bearing environment. Provider
  observations and prerequisite downloads now share bounded transient-failure
  handling, retain prior failure evidence, and reconcile ambiguous GitHub
  mutations without blindly repeating writes.
- Aligned annotated-tag snapshots across the GitHub live-provider controller
  and candidate, allowed a deliberately removed Surrey test project to be
  recreated from historical retained state, and preserved the candidate's
  original failure reason after trusted cleanup. The shared candidate boundary
  now also recognises Bootstrap's narrowly constrained renderer-floor and
  shared-file repair commands without allowing arbitrary package installation.
- Changed `prodockit pins` so every standard interactive suggestion uses the
  complete software combination tested by the installed Prodockit release,
  including Zensical, WeasyPrint, Markdown, PyMdown Extensions, Pandoc, and
  Python. Newer PyPI releases remain visible and can still be selected
  explicitly with typed input or `--latest`; accepting the defaults restores a
  project to the supported combination even offline.
- Made `pdk diag` warn when declared tool versions do not match that supported
  combination and direct the author to `pdk pins`. Diagnostics reports this as
  manual remediation and does not offer it as a `pdk diag --fix` action.

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

## 0.58.0 (2026-09-04)

- Made Adopt's installed-wheel checks tolerate one classified transient npm or
  Mermaid failure without hiding deterministic regressions. Mermaid health
  probes now use the PDF renderer's browser sandbox settings and a less brittle
  timeout, failed checks retain a structured report, and repeated scenarios no
  longer reinstall identical renderer combinations unnecessarily.
- Added a repair-disposition registry and read-only `pdk diag --dry-run`
  preview. It lists every bounded repair option, warning, affected path,
  recovery boundary, and command that could be used without choosing or
  executing one. Independent project repairs prefer Adoption and the existing
  focused Prodockit commands; no diagnostic fix depends on
  `prodockit-template`. Diagnostic JSON schema version 2 exposes the same
  policy and unselected choices for automation.
- Added the generic diagnostic repair transaction and adapted stale
  distribution metadata to it. Interactive `pdk diag --fix` now prints its
  complete plan, repeats warnings, and requires an exact default-No confirmation
  for each supported mutation. Confirmed actions receive an atomic recovery
  manifest with hashes; verification failures roll back, redirected input is
  refused, and JSON mode keeps prompts off stdout.
- Added Stage 3 diagnostic repairs for individually declared shared files and
  inconsistent pins. Shared files can be reviewed, created, or restored from
  the installed release; pins can only align to an already detected bounded
  version. Each decision remains separate from its exact-`y` confirmation,
  uses the existing typed service, is atomically written and verified, and is
  independently recoverable without consulting a template. Repair output now
  uses bootstrap's phase boundaries, stage headings, and warning/failure colours.
- Added Stage 4 locked renderer recovery. With explicit `--online` and two
  default-No decisions, diagnostics can rebuild project-local Mermaid or
  MathJax dependencies using immutable `npm ci`, regenerate MathJax website
  assets, verify a real render, and roll back on failure. Custom paths,
  partial or unpinned manifests, author lifecycle scripts, and symlinks are
  refused.
- Added Stage 5 narrowly lossless `zensical.toml` repairs for uniquely
  suggested Prodockit spellings, obsolete index settings, extensions proved
  necessary by author syntax, and recognized existing Prodockit assets. Each
  edit preserves unrelated formatting and comments, verifies the parsed
  result, and remains independent of `prodockit-template`.
- Completed Stage 6 with Ubuntu, Windows, and macOS diagnostic-repair
  acceptance coverage for fully repairable, mixed, and ambiguous projects;
  renderer rollback and MathJax regeneration tests; UTF-8, CRLF, and paths
  containing spaces; and complete author, recovery, JSON compatibility, and
  template-sync preflight guidance.

## 0.57.0 (2026-09-03)

- Added an explicit `pdk diag --fix` repair for unambiguous stale Prodockit
  and Zensical distribution metadata in the active virtual environment. The
  repair quarantines recoverable entries, refuses ambiguous or external
  environments, and makes `template-sync --apply` stop with targeted guidance
  when metadata must be repaired first.
- Made `template-sync --apply` copy the template's complete managed dependency
  pins non-interactively, preserving version operators and extras so an
  adopted project receives the same reviewed toolchain as the template.

## 0.56.0 (2026-09-03)

- Made `template-sync` repair missing or outdated stylesheet and JavaScript
  configuration while preserving author additions, seed absent author-owned
  assets without replacing existing content, and refresh managed PDK styles.
  `pdk diag` now reports local CSS and JavaScript omitted from `zensical.toml`.

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

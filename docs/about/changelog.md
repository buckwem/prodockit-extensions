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

## 0.61.4 (2026-09-08)

- Made Adopt fetch, validate and cache the configured standard Harvard CSL file
  when it is missing, reuse a validated cached copy offline, preserve existing
  citation styles, and give explicit guidance for author-owned custom styles.
- Made Adopt and Diagnostics install Mermaid CLI with its required Puppeteer
  peer dependency on current Node.js and npm releases, including npm 11, and
  added the required Tailwind peer entry to the packaged lockfile.

## 0.61.3 (2026-09-08)

- Moved Bootstrap's preserved template history into a dedicated sibling
  `.pdk-template-backups` directory, so hidden recovery data no longer competes
  with the project during PowerShell path completion. Interrupted runs still
  recognise recovery directories created by older releases.
- Made Adopt identify a missing project-local environment even when another
  virtual environment is active, and report missing Node.js or npm before a
  selected Mermaid or MathJax activity can leave installation half-finished.
- Standardised lifecycle output on phases containing activities, while the
  installation guides use stages containing steps.
- Reorganised installation guidance around four distinct routes, adding a
  complete manual-build route and a troubleshooting guide for common setup,
  environment, download, renderer, and repository problems.

## 0.61.2 (2026-09-07)

- Made Diagnostics stop after detecting that another virtual environment is
  active, avoiding misleading renderer and dependency failures from the wrong
  Python. Its correction now gives the activation command for macOS, Ubuntu,
  or Windows and asks the reader to rerun the complete report.
- Made Diagnostics and Adopt reject a directory that contains project
  repositories rather than being a project itself. The error names the child
  repositories so a reader can change into the intended project directory.
- Consolidated the Bootstrap and template setup guidance, moved the Windows
  terminal restart into the point where it is needed, and added a guided route
  for starting with Zensical before adopting Prodockit, configuring PDF and
  source-bundle outputs, and running the first checks.
- Recorded successful current-release Bootstrap and existing-repository tests
  for Surrey GitLab on Windows, Ubuntu, and macOS.

## 0.61.1 (2026-09-06)

- Made Bootstrap install and verify Pandoc 3.10.1 inside each project's virtual
  environment on macOS, Windows, and Ubuntu. A different system or Homebrew
  Pandoc can remain installed without changing local or published output.
- Added environment safeguards across lifecycle commands: Diagnostics and
  Template Sync reject a project's inactive `.venv`; Adopt rejects a different
  active environment and warns when no virtual environment is active; Pins
  warns when its tested defaults come from another environment.
- Made Template Sync recover Windows installer environment changes where
  possible and display a prominent terminal-restart instruction when a fresh
  PowerShell is required. Bootstrap now presents the same post-install restart
  and project-environment checks.
- Prevented Git's normal LF-to-CRLF checkout conversion from being reported as
  managed stylesheet drift while retaining detection of real content changes.
- Clarified operating-system installation commands and the two Bootstrap
  activations: the setup environment in the parent directory, followed by the
  repository's own environment before Diagnostics and Template Sync.

## 0.61.0 (2026-09-06)

- Added `template-sync --review-all` to select every protected template file
  for one interactive review. Each full diff now offers `overwrite`, `new`, or
  `skip`, with `skip` as the safe default; targeted `--force FILE-PATH` remains
  available for single-file reviews.
- Renamed the diagnostics repair action to `pdk diag --apply` and its selector
  to `--apply-check` for consistency with the other lifecycle commands. The
  previous `--fix` and `--fix-check` spellings remain hidden compatibility
  aliases.
- Added consistent short forms for common command modes: `-a` for `--apply`,
  `-n` for `--dry-run`, `-v` for `--verbose`, and `-o` for `--online` wherever
  the corresponding long option is available. `-h` opens help for the main
  command and every subcommand. Specialised and higher-risk options remain
  long-only.
- Made Template Sync fetch the public GitHub template over HTTPS, including for
  GitLab-hosted projects, so students do not need a GitHub account, SSH key, or
  interactive GitHub host-key decision to check for an update.
- Changed command warnings from yellow to the colour-blind-safe amber
  `#E69F00`, retaining explicit warning labels so redirected and monochrome
  output carries the same meaning.
- Added task-oriented lifecycle guidance and a top-level command reference for
  Bootstrap, Adopt, Diagnostics, Pins, Template Sync, PDF and the supporting
  commands. Each reference identifies its working directory, wrong-directory
  result, options, effects, and related commands.
- Added a shared guide to reading phase-and-stage output, with labelled,
  theme-aware figures placed beside the relevant task steps and command output
  sections. The figures can be selected to enlarge through Zensical's native
  GLightbox integration and retain numbered captions in website and PDF output.

## 0.60.4 (2026-09-06)

- Made Template Sync highlight actionable changes in purple and warnings in
  yellow, while keeping its diagnostic log plain text. Adopt stage file names
  are now displayed relative to the project root.
- Changed `template-sync --force FILE-PATH` into an interactive review: it
  shows the complete diff and asks whether to overwrite the project file or
  save the incoming template copy as `FILE-PATH.new`, with `.new` as the safe
  default.
- Corrected Windows Pango selection on ARM64 hosts running x64 Python. Both
  Bootstrap and Diagnostics now select and verify native libraries from the
  Python executable's PE architecture, and Bootstrap cannot accept an
  unrelated `pango-view` from another MSYS2 environment.
- Prevented online diagnostics from displaying an interactive SSH host-key
  prompt while checking for template updates; the public GitHub template is
  queried over HTTPS and any remaining SSH probe is strictly non-interactive.
- Made Adopt retry replacement of `pandoc.exe` when Windows briefly retains a
  file handle during a supported-version upgrade or downgrade.
- Made Bootstrap reuse an existing valid MSYS2 installation before asking
  WinGet to install it, avoiding installer failures when only Pango is missing.

## 0.60.3 (2026-09-05)

- Preserved an existing project's choice between bibliography-backed and
  inline citation definitions during Adopt and Template Sync instead of
  enabling both implementations.
- Separated the saved component choices from standard authoring configuration
  in Adopt plans. Diagnostics and Template Sync now identify a missing
  `.prodockit-components.toml` directly and name only the extensions or shared
  website inputs that actually need attention.

## 0.60.2 (2026-09-05)

- Prevented the Adopt-readiness diagnostic from treating a valid CI
  `setup-python` environment without `VIRTUAL_ENV` as an Adopt integration
  failure. Interpreter validity remains covered by the dedicated environment
  checks; readiness now compares only the project integration stages shared
  with Template Sync.

## 0.60.1 (2026-09-05)

- Preserved established Mermaid and maths selections when an older project has
  no `.prodockit-components.toml`. Adopt now labels choices inferred from the
  Zensical configuration and saves the project-owned record on apply, while
  diagnostics and Template Sync use the same resolution.
- Made Diagnostics detect a project `.venv` containing launchers from
  different Python installations before package symptoms obscure the cause.
  On macOS and Linux, `pdk diag --apply` can explicitly archive and rebuild the
  environment from project requirements; Adopt refuses to mutate a mixed
  environment first. Diagnostic recovery directories are ignored by Git.
- Made `pdk diag` reuse Adopt's own local readiness assessment, so missing
  supported-toolchain declarations or standard authoring integration are
  reported before `template-sync` reports the same prerequisite work.
- Clarified that unresolved edited template files stop a normal
  `template-sync --apply` without writing anything; only the explicit
  `--local-only` review route writes adjacent `.new` copies.

## 0.60.0 (2026-09-05)

- Made Bootstrap fall back from exhausted transient VS Code Marketplace
  failures to exact reviewed Open VSX extension releases. Fallback archives
  are identity/version/licence checked and cached by extension, release and
  platform, with the selected source and cache result shown in apply output.
- Added architecture-aware Windows Pango integrity checks and conditional
  repair for Bootstrap and `pdk diag --apply`. ARM64 uses CLANGARM64 and x64 uses
  UCRT64; both verify the expected DLL, pacman package, persistent and current
  environment, and a fresh-process native-library load without a restart.
- Reorganised the installation guide around a single Python and virtual-
  environment preparation path, with benefit-led guidance for choosing
  installation routes, authoring features and lifecycle tools.
- Made Bootstrap record Mermaid and maths component choices so `pdk adopt` can
  later repair the selected toolchain without asking for initial configuration.
  Diagnostics now identifies when a different project's virtual environment is
  active, runs Mermaid browser checks explicitly headless, and accepts a
  successful render with Mermaid's bundled browser without requiring a separate
  Chrome or Chromium installation.
- Made Bootstrap configure the VS Code `code` command automatically on macOS by
  adding the application-owned command directory to the user's shell profile.
  Existing working commands and profile content are preserved, and the change
  is idempotent across reruns.

## 0.59.0 (2026-09-05)

- Raised the supported Zensical floor to 0.0.59 after comparing the generated
  Extensions website and PDF with the previous supported release.

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
- Changed `prodockit pins` so every standard interactive suggestion uses the
  complete software combination tested by the installed Prodockit release,
  including Zensical, WeasyPrint, Markdown, PyMdown Extensions, Pandoc, and
  Python. Newer PyPI releases remain visible and can still be selected
  explicitly with typed input or `--latest`; accepting the defaults restores a
  project to the supported combination even offline.
- Made `pdk diag` warn when declared tool versions do not match that supported
  combination and direct the author to `pdk pins`. Diagnostics reports this as
  manual remediation and does not offer it as a `pdk diag --apply` action.
- Made `prodockit adopt` install, upgrade or downgrade its active Python
  packages and project-local Pandoc to the exact combination carried by the
  installed release. Adopt now aligns complete project declarations without a
  template dependency, blocks safely under the wrong Python before mutation,
  exposes commands and files in `--dry-run`, verifies the result, and supports
  bounded retries, configured mirrors, validated caches and explicit offline
  operation. Separate six-platform installed-wheel jobs exercise genuine
  upgrades from unmodified previous PyPI packages and Pandoc, plus genuine
  Pandoc downgrades from the adjacent newer release. The harness never changes
  installed metadata or substitutes fixture code. Existing managed Python
  packages are replaced directly without re-resolving unchanged dependencies,
  avoiding unavailable optional transitive wheels such as Brotli on Windows
  ARM64; genuinely missing packages retain normal dependency resolution.
- Made Bootstrap refresh managed shared files from the running candidate
  release rather than allowing an older template environment to restore stale
  copies during first-time setup.
- Made `prodockit template-sync --apply` align the active environment to the
  exact Prodockit release paired with the selected template, continue safely
  in a fresh process, and run Adopt before changing template files. Package and
  Adopt changes have separate default-No confirmations; explicit flags support
  deliberately unattended and offline runs, and failed prerequisites leave the
  template update untouched and resumable.

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
  Zensical project, including one that retains a compatible MkDocs configuration
  filename; `prodockit bootstrap` automates a complete template environment.
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
  distribution metadata to it. Interactive `pdk diag --apply` now prints its
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

- Added an explicit `pdk diag --apply` repair for unambiguous stale Prodockit
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

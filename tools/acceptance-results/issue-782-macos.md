# Issue 782: installed-wheel acceptance checkpoint

Date: 2026-09-09. Platform: macOS 26.6.2 ARM64, Python 3.14.7.
Branch: `codex/issue-782-complete-adopt`.

## Scope and limitations

Built an isolated candidate wheel (version 0.61.6) from this branch and
verified that the disposable environments imported its installed package,
not the checkout or the older editable installation. The wheel includes the
template version-floor fix described below.

This Mac already has native libraries, fonts, Node and a browser. These results
are **not** evidence of clean-machine native provisioning, Windows 11 or Ubuntu
acceptance. No existing author project was used as a mutable fixture.

## Results

- Local regression suite: 2,921 passed, 11 skipped, 17 deselected. Ruff checks,
  formatting checks and `git diff --check` pass for this checkpoint.
- The original five installed-wheel scenarios pass: TOML core, YAML core,
  TOML Mermaid, YAML maths, and TOML both. They check dry-run immutability,
  existing site output preservation, installation and repeat-apply stability.
- Strengthened checks use strict website builds and run Diagnostics, PDF and
  source-bundle commands. Core and both-renderer projects pass the applicable
  diagnostics and generate PDFs with valid PDF headers. This does not yet
  establish visual correctness of every authoring feature.
- Diagnostics warnings for intentionally absent optional renderers and a
  non-Git fixture are explicitly allowed; unrelated warnings are rejected.
- Both genuine upgrade and downgrade scenarios fail after aligning their
  top-level versions because required Python dependencies remain missing.
- Source-bundle generation fails in both strengthened scenarios because the
  disposable projects are not Git repositories.

## Fixed during testing

The template settings fetch accepted only an exact `prodockit==VERSION`
declaration. The actual template uses `prodockit>=0.61.6`, so even a clean
preview failed. Accept a compatible minimum declaration as well as the existing
exact-version form, while rejecting a newer template requirement. Regression
tests exercise both forms at the same immutable template revision.

## Blockers found in the first run

1. **Python dependency repair:** the real upgrade/downgrade fixtures install
   genuine distributions with `--no-deps`. Adopt checks top-level versions but
   leaves missing `cssselect2` and other WeasyPrint dependencies unresolved.
   Native PDF assessment misclassifies the resulting `ModuleNotFoundError` as
   a native-library problem and runs Homebrew repair, which cannot fix it.
   Repair the relevant Python dependency graph and distinguish Python import
   failures from native loader failures before invoking OS installers.
2. **Source bundle without Git:** `pdk source-bundle` invokes `git ls-files`
   and fails outside a repository. The documented clean-site route and issue
   782 exclude requiring Git. Provide a safe non-Git input-discovery route;
   do not mask this acceptance failure by initialising the fixture as a repo.
3. **Missing package managers:** code inspection confirms Node/native PDF plans
   block when Homebrew or winget is absent. Automatic trusted provisioning
   remains unimplemented and must not be described as merely untested.
4. **Native acceptance:** clean-machine runtime installation, permissions,
   current/future PATH and restart/resume still need real Windows 11, Ubuntu
   and macOS coverage. Existing mocked tests and pre-provisioned runners do
   not satisfy this requirement.
5. **Full acceptance matrix:** renderer upgrade/downgrade, representative
   authoring output, interrupted installs, offline inputs, and all remaining
   issue 782 cases still need reconciliation. Issues 783/784 track related
   Bootstrap recovery/font-verification concerns; they do not waive issue
   782's acceptance requirements.

## Reproduction

Build the candidate with `python -m build --wheel`, then run:

```sh
python tools/adopt_acceptance.py --wheel dist --scenario all --report acceptance.json
python tools/adopt_toolchain_acceptance.py --wheel dist --scenario upgrade --report upgrade.json --keep-on-failure
python tools/adopt_toolchain_acceptance.py --wheel dist --scenario downgrade --report downgrade.json --keep-on-failure
```

The strengthened first command now intentionally exposes the source-bundle
failure rather than reporting the older, website-only success as full acceptance.
Failed temporary fixtures are retained by the harness for diagnosis.

Local reports from this checkpoint are `/private/tmp/prodockit-782-acceptance.json`,
`/private/tmp/prodockit-782-upgrade.json`,
`/private/tmp/prodockit-782-downgrade.json`, and
`/private/tmp/prodockit-782-renderer-deliverables.json`. They are disposable
machine-local evidence, not required repository inputs.

## Follow-up: dependency repair and standalone source bundles

The dependency assessment now walks required installed-package dependencies,
including explicitly requested dependency extras, and plans a resolving repair
even when the top-level version already matches. After a version change it
checks again for newly introduced dependencies before writing declarations.
Missing Python imports no longer trigger native-library installation.

Standalone documentation projects now generate source bundles without Git.
The filesystem path honours local/nested ignore rules with `pathspec`, does
not follow symlinks, and excludes hidden and generated-tooling directories.
The existing Git-based selection remains unchanged for repositories.

All five **strengthened** installed-wheel scenarios now pass, including strict
site builds, applicable diagnostics, PDF and source-bundle generation, and
repeat-apply stability. Reports: `/private/tmp/prodockit-782-deliverables-retest.json`.

The real upgrade and downgrade scenarios also pass, including repair of missing
transitive dependencies and offline Pandoc cache recovery. Their harnesses now
default to a per-run download cache rather than sharing a checkout cache;
an explicitly configured cache remains supported. Report:
`/private/tmp/prodockit-782-upgrade-isolated.json` and
`/private/tmp/prodockit-782-downgrade-isolated.json`.

The missing-package-manager provisioning and full native platform/matrix gaps
listed above remain open. Passing these pre-provisioned-Mac checks does not
close issue 782.

Follow-up regression result: **2,925 passed, 11 skipped, 17 deselected**.
Strict documentation build, focused Ruff checks, changed-source mypy checks,
and whitespace validation also pass.

## Follow-up: Windows package-manager provisioning

Node and native-PDF plans now prepend current-user App Installer registration
and, if needed, Microsoft's stable WinGet repair/install workflow. They use
the existing bounded installer execution and PATH refresh. The script verifies
WinGet before later runtime commands and does not change execution policy,
install for all users, or request a preview release.

Planning/integration tests cover manager reuse, offline refusal, missing
PowerShell, and installation ordering for both consumers. Native Windows
execution remains untested on this Mac. The macOS gap remains explicit:
Homebrew's supported prerequisite includes Xcode Command Line Tools, outside
the agreed runtime-only installation boundary. No development tools are
silently installed to bypass that constraint.

WinGet checkpoint: **2,934 passed, 11 skipped, 17 deselected**. Strict
documentation build, lint, formatting and changed-source type checks pass.

## Agreed prerequisite exception and default-choice coverage

The user has approved **manual Homebrew installation** on macOS. It is now
an agreed prerequisite, not an unmet automatic-provisioning requirement.
When absent, Adopt points to brew.sh, asks the author to complete the installer's
shell setup, reopen the terminal, activate the project environment, and rerun
Adopt. Native runtime packages remain Adopt's responsibility afterwards.
Windows WinGet provisioning remains automatic and still needs native acceptance.

A new `toml-default` installed-wheel scenario passes no component-selection
flags. It requires both renderers to remain off, verifies that neither renderer
directory is created, and exercises the full build/diagnostics/PDF/source-bundle
and second-apply checks. The cross-platform installed-wheel workflow includes
this scenario on every runner.

The real installed-wheel `toml-default` scenario passes on this Mac, including
strict build, applicable diagnostics, both PDF commands and repeat apply.
Report: `/private/tmp/prodockit-782-default-acceptance.json`. The 65 focused
acceptance/manager/CI regression tests, lint and strict documentation build
also pass. The last full-suite result remains the 2,934-test checkpoint above.

## Follow-up: real authoring and older-project acceptance

The fresh default-choice scenario also passes with authored steps, a directory
tree and a table caption added after the existing-content preservation check.
Acceptance requires the expected generated classes and rejects raw block
directives. The content is included in the subsequent PDF and source bundle.
Report: `/private/tmp/prodockit-782-authoring-acceptance.json`.

A genuine project first adopted with published Prodockit 0.47.0 successfully
upgrades to the candidate 0.61.6 and passes the strengthened deliverable checks.
Report: `/private/tmp/prodockit-782-old-project-upgrade.json`.

The native-upgrade harness is further strengthened to remove only its own
disposable component-choice file, run the candidate without renderer flags,
and require automatic inference and alignment of actual installed Mermaid and
MathJax versions to the candidate's packaged specification. It records both
before/after renderer versions rather than relying on top-level Python pins.

The inferred upgrade scenario passes on this Mac. It detects both renderers
without saved choices or flags and downgrades the actual Mermaid CLI from
11.17.0 to the candidate's packaged 11.16.0; MathJax remains at the required
3.2.2. Authoring, diagnostics, both PDF commands and repeat apply pass.
Report: `/private/tmp/prodockit-782-inferred-upgrade.json`.

Latest full regression result: **2,937 passed, 11 skipped, 17 deselected**.
Changed harnesses and tests also pass lint, formatting and whitespace checks.

## Follow-up: installer cleanup and template preservation

Installer execution now reports elapsed progress and stops its owned process
group/tree on timeout or interruption. A real POSIX test confirms a child is
stopped before writing its delayed output. Windows tree cleanup has mocked
coverage only. Detached/elevated processes remain a reason not to retry timed-out
installers automatically. Completed npm failures discard incomplete node_modules
even after the final failed attempt, retaining manifests and author files.

Full regression result: **2,945 passed, 11 skipped, 17 deselected**. A subsequently
added template asset preservation/repeat regression also passes separately.
Lint and whitespace checks pass.

The rebuilt wheel passes the real `toml-both` acceptance scenario on this
pre-provisioned macOS ARM64 host: Mermaid and MathJax, strict site build,
diagnostics, PDF, source bundle and repeat apply.
Report: `/private/tmp/prodockit-782-clean-retry-acceptance.json`.

File operations were also exercised twice on a disposable tracked-file copy of
the local prodockit-template checkout (paired Prodockit 0.61.6). No original
files were deleted. Template/author assets and toolchain declarations were
unchanged. Four renderer manifest/lock files were aligned with backups and six
configuration defaults added. Mermaid remained 11.16.0 and MathJax 3.2.2.
The second file-alignment pass was byte-identical. This was not a full
template-sync-to-Adopt installation test.

Open risk: Adopt's managed-file alignment targets its installed release, so an
older installed Prodockit can still replace files supplied by a newer template.
These results do not establish a cross-version no-downgrade guarantee or native
Windows/Ubuntu acceptance.

## Follow-up: reject an older Adopt before project mutation

Assessment and direct activity application now check the project's managed
Prodockit declarations. A newer exact pin, minimum requirement or toolchain
manifest stops Adopt with upgrade guidance before file/runtime changes. The
previous test expecting a newer Prodockit floor to be lowered was replaced.
Same/older project declarations still permit alignment to the installed release;
dependency upgrade/downgrade behavior is unchanged. This protection relies on
the project retaining its managed version declarations, not file provenance.

Regression result: **2,951 passed, 11 skipped, 17 deselected**. Lint, formatting
and whitespace checks pass. The rebuilt wheel's real `toml-default` acceptance
scenario passes site, diagnostics, authored content, PDF/source bundle and
repeat-apply checks on pre-provisioned macOS ARM64.
Report: `/private/tmp/prodockit-782-release-guard-acceptance.json`.

The rebuilt wheel also passes real dependency downgrade acceptance after the
release guard: Pandoc 3.10.2 becomes 3.10.1 while compatible Python packages
remain unchanged, verified by code fingerprints. Offline cache recovery passes.
Report: `/private/tmp/prodockit-782-guard-downgrade.json`.

User-facing message findings and the proposed normal/verbose output contract
are recorded in `issue-782-message-review.md`. No message redesign has yet been
implemented. Native Windows/Ubuntu and clean-machine acceptance remain open.

## Follow-up: real template project acceptance

The disposable-copy harness initially assumed `site/` for every project. The
template uses `public/`, so the baseline build succeeded but the harness failed
to locate it. It now reads the configured output directory through the installed
candidate, excludes that output from source-mutation checks, and rejects output
paths equal to or outside the disposable project. Configurable/nested directory
and unsafe-path regression tests were added.

The next run detected generated site differences: the fresh environment had
installed Zensical 0.0.60 from the template's `>=0.0.59` requirement, while Adopt
aligned it to the candidate's supported 0.0.59. The homepage diff consisted of
the generator version and bundled CSS/JS references. This is dependency
alignment, not evidence of deleted author assets. Existing-project preservation
tests now align the baseline build engine first, matching the built-in fixture
policy; actual upgrade/downgrade behavior is covered separately.

Harness, toolchain acceptance and CI-scope regressions: **64 passed**. Lint,
formatting and whitespace checks pass. Original template checkout remains clean.

The aligned-baseline real template-copy acceptance passes: unchanged dry-run,
11 planned file changes, generated-site preservation, diagnostics, PDF and
source bundle, and byte-stable second apply. Both renderers were selected.
The harness also verified the original source snapshot was unchanged.
Report: `/private/tmp/prodockit-782-template-full-acceptance-aligned.json`.
This tests the local template checkout, not a fresh live template-sync transaction.

## Follow-up: installed-package message acceptance

The wheel rebuilt after message commit `03d14c5` passes both `toml-default` and
`toml-both` acceptance on pre-provisioned macOS ARM64. Checks include strict site
build, source preservation, diagnostics, PDF/source bundle, and stable repeat
apply. The default scenario also checks authored steps/tree/table-caption output.
Report: `/private/tmp/prodockit-782-message-acceptance.json`.

A separate fresh installed-wheel fixture declares `prodockit>=999.0.0` and runs
Adopt apply offline with a local template configuration, in normal and verbose
modes. Both return a nonzero exit status, show the prominent blocker, required
release and next action, omit approval prompts/ANSI escapes in captured output,
and preserve every project file. Template snapshot details appear only with
verbose. Report: `/private/tmp/prodockit-782-installed-blocker-report.json`.
The first version of that test fixture omitted Click/dependencies and failed
before command startup; the corrected fixture installs the wheel's dependencies.

These tests do not establish native Windows/Ubuntu or clean-machine runtime
provisioning acceptance. The remaining message refinements are listed in the
message review; no additional runtime behavior changed in this testing pass.

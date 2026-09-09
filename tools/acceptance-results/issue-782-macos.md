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

## Confirmed remaining blockers

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

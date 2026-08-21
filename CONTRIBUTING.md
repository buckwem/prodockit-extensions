<!--
# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT
-->

# Contributing

Thanks for improving prodockit. This guide is for changes to the Python
package, tests, automation, or technical documentation in this repository.

If you are using prodockit to write a document, follow the
[prodockit User Guide](https://buckwem.github.io/prodockit-userguide/). For
more detail about this repository, use the
[development and code map](docs/devcons/development.md). Maintainer operations
and package releases have separate guides:

- [Maintain prodockit](docs/project-maintenance.md)
- [Build and release](docs/devcons/releasing.md)

## Before you start

Search the [existing issues](https://github.com/buckwem/prodockit-extensions/issues)
before starting. For anything beyond a small correction such as a typo or
broken link, open an issue so the intended behaviour and scope can be agreed
before implementation.

Create a focused branch from current `main`. Keep unrelated local work out of
the change and do not edit directly on `main`.

## Create a development environment

Fork the repository on GitHub, then clone your fork and create an editable
environment:

```bash
git clone https://github.com/YOUR-USERNAME/prodockit-extensions.git
cd prodockit-extensions
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate the environment before running commands. Calling `.venv/bin/python`
without activating it is not equivalent for the PDF tests: Pandoc looks up the
`weasyprint` executable on `PATH`.

### Install the external PDF tools

The editable Python install does not supply the complete PDF toolchain:

- Install [Pandoc](https://pandoc.org/installing.html). Bibliography tests use
  its real `--citeproc` implementation, and PDF tests invoke it directly.
- Install WeasyPrint with `python -m pip install weasyprint`.
- Install WeasyPrint's native Pango libraries as described in
  [PDF requirements](docs/pdf.md#pdf-requirements). On macOS, run
  `brew install pango`.
- Mermaid and TeX rendering in this repository's complete documentation PDF
  also needs the existing Node tool directories under `tools/` and Chrome or
  Chromium. The [PDF guide](docs/pdf.md#mermaid-diagrams-and-tex-maths)
  explains that path.

Tests that need an unavailable external tool are skipped or deselected
where practical. A complete local verification requires the real tools.

### Configure the macOS library path

On Apple Silicon macOS, export Homebrew's library path in the same terminal
that will run pytest or build the PDF:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

Use `/usr/local/lib` on an Intel Mac. Without this variable, many PDF tests can
fail with `cannot load library 'libgobject-2.0-0'` even though
`brew install pango` completed. Check the environment before treating a group
of identical renderer failures as a code regression.

## Make the change

Add or update tests with the implementation. A regression test should fail
for the old behaviour and pass after the fix. Keep public documentation,
command help, configuration examples, and release notes aligned when a public
surface changes.

Preview documentation while editing:

```bash
zensical serve
```

Generated output is evidence to inspect, not a substitute for reviewing the
source diff. Preserve unrelated work in the checkout.

## Run the source gates

Run these from the repository root with the development environment active:

```bash
ruff check .
mypy src
prodockit pins --check --offline
pytest
zensical build --clean --strict
git diff --check
```

The ordinary `pytest` run excludes tests marked `built`; those inspect this
repository's generated site and PDF and are run separately below.

## Verify documentation and PDF changes

For a documentation or PDF change, build in publication order. The PDF comes
first because the Zensical build copies it into the site:

```bash
prodockit pdf
zensical build --clean --strict
python -m pytest tests/test_built_docs.py -m built -v
```

Open the finished website and PDF when layout or rendering can change. Check
representative pages, diagrams, tables, code blocks, links, the PDF outline,
and the generated back-of-book index where relevant. A successful command
does not prove the output is visually correct.

## Open the pull request

Review `git diff` and `git status --short`, then commit only the intended
source changes. Push the branch and open a pull request against `main`.

In the pull request:

- explain what changed and why;
- list the exact checks and manual inspections completed;
- reference the issue with `Fixes #123` when the pull request resolves it;
- call out platform-specific or external-tool coverage that was not run.

`main` is protected. Merge only after the required GitHub Actions checks pass
and review is complete.

## Report bugs and request features

Use the repository's
[issue templates](https://github.com/buckwem/prodockit-extensions/issues/new/choose).
Include the prodockit, Python, Zensical, and operating-system versions, the
command that failed, its complete error, and a minimal reproducer where
possible. For rendering problems, include the affected source and an image or
small output artifact that shows the result.

## Licence

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE.md).

<!--
# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT
-->

# Contributing

Thanks for your interest in improving prodockit. This guide covers contributing to the library itself - fixing bugs, adding a feature, or improving the documentation. If you're using prodockit to build your own site (via [prodockit-template](https://github.com/buckwem/prodockit-template) or otherwise), you don't need any of this: just follow the [prodockit User Guide](https://buckwem.github.io/prodockit-userguide/).

## Before you start

For anything beyond a small fix (typos, broken links), please open an issue first to discuss the change. This avoids duplicated effort and lets us agree on the approach before you spend time on an implementation.

## Getting set up

1. Fork the repository and clone your fork.
2. Install the package in editable mode with its dev dependencies: `pip install -e ".[dev]"`.
3. `prodockit.bibliography`'s own tests need a real [Pandoc](https://pandoc.org/installing.html) install (`brew install pandoc`, or see its own install instructions) - its citation/bibliography formatting is delegated entirely to `pandoc --citeproc`, so a fake stand-in wouldn't actually test anything meaningful. Tests needing it are skipped automatically if `pandoc` isn't on `PATH`.
4. Preview this project's own documentation site locally: `zensical serve`.

## Making a change

1. Create a branch off `main` for your change.
2. Make your change and verify it locally:
   - Run the test suite: `pytest`.
   - Run the linter and type checker: `ruff check .` and `mypy src`.
   - Docs changes: `zensical build --clean --strict` - catches a broken internal link/anchor before it ships.
   - If your change affects `prodockit.pdf`, also build a real PDF (`prodockit pdf` from a project using this library, or via the library's own test fixtures) and check the output - test coverage here still leans on real `pandoc`/`weasyprint` runs for anything visual.
3. Open a pull request against `main`. `main` is protected, so all changes - including from maintainers - go through a PR.
4. Reference the issue your PR addresses (e.g. `Fixes #123`) where applicable.

## Reporting bugs and requesting features

Please use the issue templates when opening an issue - they help make sure we get the information needed to act on it.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).

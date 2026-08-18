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
5. **Activate the virtual environment before running the tests**, rather than
   calling `.venv/bin/python` directly. `prodockit.pdf` runs `pandoc
   --pdf-engine=weasyprint`, and pandoc looks `weasyprint` up on `PATH` - so an
   unactivated venv gives `'weasyprint' not found` and about a dozen PDF tests
   fail, with pandoc exiting 47 and saying nothing about `PATH`.
6. **On macOS, also set `DYLD_FALLBACK_LIBRARY_PATH`.** WeasyPrint loads
   Homebrew's `libgobject`/`pango` through `ctypes`, which does not search
   `/opt/homebrew/lib`:

   ```bash
   export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
   ```

   Without it the failure is `cannot load library 'libgobject-2.0-0'`, and it
   reads like a missing package when the libraries are all present. Set it in
   the shell you run `pytest` from: macOS strips `DYLD_*` when spawning some
   binaries, so exporting it inside a script that then calls pytest is not
   always enough.

## Making a change

1. Create a branch off `main` for your change.
2. Make your change and verify it locally:
   - Run the test suite: `pytest`. A dozen PDF failures usually means the
     venv is not activated or `DYLD_FALLBACK_LIBRARY_PATH` is unset - see
     "Getting set up" above, and check the environment before the code.
   - Run the linter and type checker: `ruff check .` and `mypy src`.
   - Docs changes: `zensical build --clean --strict` - catches a broken internal link/anchor before it ships.
   - If your change affects `prodockit.pdf`, also build a real PDF (`prodockit pdf` from a project using this library, or via the library's own test fixtures) and check the output - test coverage here still leans on real `pandoc`/`weasyprint` runs for anything visual.
3. Open a pull request against `main`. `main` is protected, so all changes - including from maintainers - go through a PR.
4. Reference the issue your PR addresses (e.g. `Fixes #123`) where applicable.

## Reporting bugs and requesting features

Please use the issue templates when opening an issue - they help make sure we get the information needed to act on it.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).

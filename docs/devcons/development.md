---
icon: lucide/code
---

{{ heading_counter_reset(page) }}

# Development and code map

This page is for contributors changing prodockit's Python package, tests, or
documentation. Installing prodockit from PyPI is covered under Get started;
this editable installation creates a \index{development environment} that
keeps the checkout connected to the environment.

## Create a development environment

Clone the repository and install it in editable mode inside a dedicated virtual
environment:

```bash
git clone https://github.com/buckwem/prodockit-extensions
cd prodockit-extensions
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. The editable install
provides `prodockit`, `pdk`, and Zensical while importing package code directly
from `src/`.

!!! note "On macOS, expose Homebrew's Pango libraries"

    WeasyPrint's Python package still needs the native libraries installed by
    `brew install pango`. Export
    \index{macOS!`DYLD_FALLBACK_LIBRARY_PATH`} in the same terminal before
    running the PDF-backed tests:

    ```bash
    export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
    ```

    `brew --prefix` selects the correct Homebrew location on both Apple
    Silicon and Intel Macs and the rest preserves any fallback path already
    set.

    Without it, tests that import or invoke WeasyPrint fail with
    `cannot load library 'libgobject-2.0-0'`, even when Pango is installed.
    This is an environment problem rather than a regression in the PDF feature
    named by the failing test.

Run the ordinary contributor gates before opening a pull request:

```bash
ruff check .
mypy src
prodockit pins --check --offline
pytest
zensical build --clean --strict
```

## Find the code

This \index{source code map} shows where each public feature is implemented.

/// tree
src/
  prodockit/
    cli.py - public commands and aliases
    settings.py - extension configuration helpers
    headings.py - heading ids and numbering
    refs.py - heading, figure, and table references
    citations.py - Markdown-defined citations
    glossary.py - acronyms and glossary terms
    bibliography.py - Pandoc citeproc integration
    tables.py - table layout attributes
    tree.py - directory-tree block
    steps.py - numbered-steps block
    index.py - inline index markers
    shared_files.py - packaged managed styles and shared-file checks
    template_sync.py - template updates and managed-style safeguards
    pdf/ - PDF build and source-bundle pipeline
    bootstrap/ - machine setup stages and host model
    testing/ - pytest plugin, fixtures, and output checks
tests/ - unit, integration, documentation, and built-output tests
docs/ - public guides and contributor internals
tools/ - Mermaid and MathJax tooling used by PDF builds
pyproject.toml - package metadata, dependencies, and extension entry points
zensical.toml - this documentation site's configuration
///

### Stylesheet delivery code map {: #stylesheet-delivery-code-map }

Managed styles cross the documentation, package, maintenance commands, and
renderers. Use
\ref{tab-devcons-development-stylesheet-delivery-code-map} when changing that
contract:

| Path {: width="38%" } | Responsibility |
|---|---|
| `docs/stylesheets/pdk.css` | Canonical website and shared PDF component defaults |
| `docs/stylesheets/pdk-pdf.css` | Canonical PDF-only presentation defaults |
| `docs/stylesheets/extra.css` and `print.css` | This site's author-owned overrides; never packaged as shared files |
| `pyproject.toml` | `force-include` mappings that place the two managed files under `prodockit/assets/` in a wheel |
| `src/prodockit/shared_files.py` | Finite resource inventory used by `pins` and `shared-files` |
| `src/prodockit/template_sync.py` | Detection and preservation of locally edited managed stylesheets |
| `src/prodockit/pdf/config.py` | Website and PDF stylesheet loading order used by PDF builds |
| `tests/test_shared_files.py` and `tests/test_shared_file_wheel.py` | Source, manifest, installed-wheel, and byte-for-byte delivery checks |
| `tests/test_template_sync.py` | Managed-style warning and preservation behaviour |
| `tests/test_pdf_config.py` and `tests/test_site_consistency.py` | Cascade order and reference-site configuration |
/// table-caption | <
    attrs: {id: tab-devcons-development-stylesheet-delivery-code-map}

Stylesheet delivery code map
///

The author-facing ownership and override rules are in [Stylesheets](../stylesheets.md);
the contributor release obligations are in [Extension integration](extension-internals.md#maintain-the-stylesheet-contract).

Each Markdown extension is registered in `pyproject.toml`. A new public
extension normally needs its module, entry point, tests, Authoring reference
page, navigation entry, README inventory entry, and release note.

## Call maintenance logic from Python

CLI commands should remain thin wrappers around functions that return useful
state. For example, `prodockit sync-repo` calls `sync_repo_metadata()`:

```python
from prodockit.sync_repo import sync_repo_metadata

result = sync_repo_metadata(check=True)
if result.changed:
    print("out of date:", ", ".join(result.changes))
```

The function returns changes and notes instead of printing them, which keeps
it usable from tests and other tooling. The CLI owns terminal formatting and
exit status.

## Keep the pytest plugin lightweight

The `prodockit.testing` pytest plugin is discovered in every environment where
prodockit is installed, including unrelated test suites. It therefore avoids
heavy imports at module import time. PyMuPDF, Beautiful Soup, and Zensical are
loaded only inside fixtures that need them, and a missing `zensical.toml`
affects the requested fixture rather than test collection.

When adding a fixture, preserve session scope where possible, prefix its name
with `prodockit_`, resolve paths from pytest's root directory, and avoid work
until a test requests it.

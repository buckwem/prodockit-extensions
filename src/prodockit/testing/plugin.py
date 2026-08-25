# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""A pytest plugin giving a prodockit project fixtures for its own *built*
output - the site directory and the PDF - so each one doesn't rewrite the
same loading, config-reading and PDF-opening boilerplate.

These test artifacts that already exist on disk; they never build anything.
Run `prodockit pdf` and `zensical build` first.

Registered through the `pytest11` entry point, which means it is imported
into **every** pytest run in an environment where prodockit is installed,
including projects that have nothing to do with it. So:

- Nothing heavy is imported at module scope. `pymupdf` and `beautifulsoup4`
  are imported inside the fixtures that need them, and a project that never
  touches those fixtures never pays for them - nor breaks if they aren't
  installed.
- Every fixture is prefixed `prodockit_`, so it can't collide with a name a
  project already uses in its own `conftest.py`.
- A missing `zensical.toml` fails the individual fixture, not collection.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


def _load_toml(path: Path) -> dict[str, Any]:
    """Parses a TOML file, using the standard library where it exists.

    `tomllib` is 3.11+, and this package supports 3.10. The fallback import
    is deliberately *inside* this function rather than at module scope:
    pytest loads this plugin into every test run in any environment where
    prodockit is installed, so an ImportError up there would take down
    unrelated projects' test suites on 3.10 rather than just failing the
    fixtures that actually need it.
    """
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - exercised only on 3.10
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            pytest.skip(
                "reading the Zensical config on Python 3.10 needs tomli - "
                "`pip install prodockit[testing]`"
            )
    with open(path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)
    return data


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "prodockit_config_file",
        help=(
            "Zensical config file the prodockit_* fixtures read, relative to the pytest rootdir."
        ),
        default="zensical.toml",
    )
    parser.addini(
        "prodockit_pdf",
        help=(
            "Built PDF the prodockit_pdf fixture opens, relative to the "
            "rootdir. Defaults to the config's own pdf_output, or "
            "<docs_dir>/site_documentation.pdf."
        ),
        default="",
    )


@dataclass(frozen=True)
class ProdockitPaths:
    """Where this project's inputs and built outputs actually live."""

    root: Path
    config_file: Path
    docs_dir: Path
    site_dir: Path
    pdf: Path


@pytest.fixture(scope="session")
def prodockit_paths(pytestconfig: pytest.Config) -> ProdockitPaths:
    """Resolves docs/site/PDF locations from the Zensical config, rather
    than assuming any particular layout - `site_dir` in particular is
    `site` by default but commonly set to `public`, and the PDF's name
    follows `pdf_output` when set."""
    root = Path(str(pytestconfig.rootpath))
    config_file = root / str(pytestconfig.getini("prodockit_config_file"))
    if not config_file.is_file():
        pytest.fail(
            f"{config_file} not found - the prodockit_* fixtures read your "
            "Zensical config. Set the `prodockit_config_file` ini option if "
            "it lives elsewhere."
        )

    raw = _load_toml(config_file)
    project = raw.get("project", {}) or {}
    extra = project.get("extra", {}) or {}

    docs_dir = root / (project.get("docs_dir") or "docs")
    site_dir = root / (project.get("site_dir") or "site")

    configured_pdf = str(pytestconfig.getini("prodockit_pdf") or "")
    if configured_pdf:
        pdf = root / configured_pdf
    elif extra.get("pdf_output"):
        pdf = root / str(extra["pdf_output"])
    else:
        pdf = docs_dir / "site_documentation.pdf"

    return ProdockitPaths(
        root=root, config_file=config_file, docs_dir=docs_dir, site_dir=site_dir, pdf=pdf
    )


@pytest.fixture(scope="session")
def prodockit_config(prodockit_paths: ProdockitPaths) -> dict[str, Any]:
    """The Zensical config as plain parsed TOML."""
    return _load_toml(prodockit_paths.config_file)


@pytest.fixture(scope="session")
def prodockit_resolved_config(prodockit_paths: ProdockitPaths) -> dict[str, Any]:
    """Prodockit's normalized config compatibility mapping.

    Navigation entries carry ``url``/``is_index``/``children`` and
    ``mdx_configs`` contains extension options. Use ``prodockit_config`` when
    the source file's raw structure is what a test needs.
    """
    from prodockit.project_config import load_project_config

    return load_project_config(prodockit_paths.config_file).as_resolved_mapping()


@pytest.fixture(scope="session")
def prodockit_nav_pages(prodockit_resolved_config: dict[str, Any]) -> list[str]:
    """Every nav markdown file, docs_dir-relative, in nav order - the same
    order `prodockit.pdf` and the numbering macros walk."""
    from prodockit.settings import flatten_nav

    return [page["url"] for page in flatten_nav(prodockit_resolved_config.get("nav") or [])]


@pytest.fixture(scope="session")
def prodockit_pdf(prodockit_paths: ProdockitPaths):  # type: ignore[no-untyped-def]
    """The built PDF, opened with pymupdf. Yields a `pymupdf.Document`."""
    try:
        import pymupdf
    except ModuleNotFoundError:  # pragma: no cover - depends on the environment
        pytest.skip("pymupdf not installed - `pip install prodockit[testing]`")

    if not prodockit_paths.pdf.exists():
        pytest.fail(
            f"{prodockit_paths.pdf} not found - run `prodockit pdf` before "
            "these tests; they check built output rather than building it."
        )
    # pymupdf ships a py.typed marker but its members are effectively
    # untyped - the ignores below are for that gap, the same way
    # prodockit.pdf.index handles it.
    doc = pymupdf.open(prodockit_paths.pdf)  # type: ignore[no-untyped-call]
    if doc.page_count == 0:
        doc.close()  # type: ignore[no-untyped-call]
        pytest.fail(f"{prodockit_paths.pdf} opened but has no pages")
    yield doc
    doc.close()  # type: ignore[no-untyped-call]


@pytest.fixture(scope="session")
def prodockit_pdf_page_texts(prodockit_pdf: Any) -> list[str]:
    """The PDF's text, one string per page, in page order."""
    return [page.get_text() for page in prodockit_pdf]


@pytest.fixture(scope="session")
def prodockit_site_dir(prodockit_paths: ProdockitPaths) -> Path:
    """The built site directory."""
    if (
        not prodockit_paths.site_dir.is_dir()
        or not (prodockit_paths.site_dir / "index.html").is_file()
    ):
        pytest.fail(
            f"{prodockit_paths.site_dir} is missing or has no index.html - run "
            "`zensical build` before these tests."
        )
    return prodockit_paths.site_dir


@pytest.fixture(scope="session")
def prodockit_site_html_files(prodockit_site_dir: Path) -> list[Path]:
    """Every built HTML page, sorted."""
    return sorted(prodockit_site_dir.rglob("*.html"))


@pytest.fixture(scope="session")
def prodockit_soup_for():  # type: ignore[no-untyped-def]
    """Factory: `prodockit_soup_for(path)` parses one built HTML file."""
    from bs4 import BeautifulSoup

    def _soup(html_path: Path) -> Any:
        return BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")

    return _soup

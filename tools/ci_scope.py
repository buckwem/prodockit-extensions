# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Choose the expensive CI scopes needed by a set of changed files.

Pull requests use this small, repository-owned classifier instead of running
every installed-wheel matrix for documentation-only changes.  Pushes to
``main`` pass ``--all`` and retain the complete compatibility backstop.

The rules are deliberately conservative.  Shared command, configuration,
packaging and asset code selects both installed-wheel suites; a missed run is
more expensive than an unnecessary one.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Scope:
    """The PR checks selected by a collection of repository paths."""

    python_compat: bool
    adopt: bool
    pdf: bool

    @property
    def python_matrix(self) -> tuple[str, ...]:
        """Test the supported-version boundaries when Python can change."""

        return ("3.10", "3.14") if self.python_compat else ("3.14",)


_SHARED_INSTALLED_WHEEL_FILES = {
    "pyproject.toml",
    "docs/stylesheets/extra.css",
    "src/prodockit/__init__.py",
    "src/prodockit/__main__.py",
    "src/prodockit/cli.py",
    "src/prodockit/project_config.py",
    "src/prodockit/shared_files.py",
    "src/prodockit/util.py",
    "tools/ci_scope.py",
}

_ADOPT_FILES = {
    ".github/workflows/adopt-install.yml",
    "src/prodockit/_zensical_defaults.py",
    "src/prodockit/adopt.py",
    "src/prodockit/init_tools.py",
    "src/prodockit/mathjax.py",
    "tools/adopt_acceptance.py",
}

_PDF_FILES = {
    ".github/workflows/pdf-built-site-wheel.yml",
    "tools/check_shared_file_wheel.py",
    "tools/pdf_from_site_acceptance.py",
}

# The built-site renderer deliberately consumes the HTML these extensions
# produce.  Their integration belongs in the installed-wheel acceptance even
# though their implementation is outside prodockit.pdf itself.  In particular,
# headings and refs own the cross-file forward-reference behaviour fixed in
# #512.
_PDF_RENDERED_EXTENSION_FILES = {
    "src/prodockit/_markdown_toc.py",
    "src/prodockit/_zensical.py",
    "src/prodockit/_zensical_page_context.py",
    "src/prodockit/headings.py",
    "src/prodockit/refs.py",
    "src/prodockit/steps.py",
    "src/prodockit/tables.py",
    "src/prodockit/tree.py",
}

_ADOPT_TEST_PREFIXES = (
    "tests/test_adopt",
    "tests/test_init_tools",
    "tests/test_mathjax",
    "tests/test_shared_file",
)

_PDF_TEST_PREFIXES = (
    "tests/test_headings",
    "tests/test_markdown_toc",
    "tests/test_pdf_",
    "tests/test_refs",
    "tests/test_shared_file",
    "tests/test_steps",
    "tests/test_tables",
    "tests/test_tree",
    "tests/test_zensical_integration",
    "tests/test_zensical_page_context",
)


def _normalise(path: str) -> str:
    """Return a repository-relative POSIX path from Git's line output."""

    return PurePosixPath(path.strip().replace("\\", "/")).as_posix()


def classify(paths: list[str] | tuple[str, ...]) -> Scope:
    """Return the conservative CI scope for *paths*."""

    changed = {_normalise(path) for path in paths if path.strip()}

    python_compat = any(
        path.startswith(("src/", "tests/", "tools/"))
        or path.startswith(".github/workflows/ci")
        or path == "pyproject.toml"
        or path.startswith("requirements")
        for path in changed
    )

    shared = bool(changed & _SHARED_INSTALLED_WHEEL_FILES)
    adopt = shared or bool(changed & _ADOPT_FILES) or any(
        path.startswith(_ADOPT_TEST_PREFIXES) for path in changed
    )
    pdf = (
        shared
        or bool(changed & _PDF_FILES)
        or bool(changed & _PDF_RENDERED_EXTENSION_FILES)
        or any(path.startswith("src/prodockit/pdf/") for path in changed)
        or any(path.startswith(_PDF_TEST_PREFIXES) for path in changed)
    )
    return Scope(python_compat=python_compat, adopt=adopt, pdf=pdf)


def all_scope() -> Scope:
    """Return the comprehensive post-merge scope."""

    return Scope(python_compat=True, adopt=True, pdf=True)


def output_lines(scope: Scope, *, main: bool = False) -> tuple[str, ...]:
    """Format values for ``GITHUB_OUTPUT``."""

    versions = ("3.10", "3.11", "3.12", "3.13", "3.14") if main else scope.python_matrix
    return (
        f"python-matrix={json.dumps(versions, separators=(',', ':'))}",
        f"adopt={'true' if scope.adopt else 'false'}",
        f"pdf={'true' if scope.pdf else 'false'}",
    )


def main(argv: list[str] | None = None) -> int:
    """Read changed paths on stdin and emit GitHub job outputs."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all",
        action="store_true",
        help="select every scope and the complete Python matrix",
    )
    args = parser.parse_args(argv)
    scope = all_scope() if args.all else classify(tuple(sys.stdin.read().splitlines()))
    print("\n".join(output_lines(scope, main=args.all)))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by workflows
    raise SystemExit(main())

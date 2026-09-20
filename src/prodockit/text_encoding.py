# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Shared UTF-8 validation for author-owned project text inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        ".cache",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".prodockit-adopt-backups",
        "__pycache__",
        "node_modules",
        "site",
        "public",
    }
)
CONFIG_FILENAMES = (
    "zensical.toml",
    "zensical.yml",
    "zensical.yaml",
    "mkdocs.yml",
    "mkdocs.yaml",
)
_ROOT_FILES = (
    "pyproject.toml",
    ".python-version",
    ".gitlab-ci.yml",
    ".github/docs-single-page-pdfs.toml",
)
_REQUIREMENT_FILES = (
    "requirements.txt",
    "pdf-requirements.txt",
    "requirements/docs.txt",
    "docs/requirements.txt",
)
_RENDERER_FILES = tuple(
    f"tools/{renderer}/{name}"
    for renderer in ("mathjax",)
    for name in ("package.json", "package-lock.json")
)
_MAX_PROBLEMS_PER_FILE = 100


@dataclass(frozen=True)
class TextEncodingProblem:
    """One unreadable file or malformed UTF-8 byte sequence."""

    path: Path
    message: str
    line: int | None = None
    column: int | None = None
    offset: int | None = None

    def location(self, root: Path) -> str:
        """Return a portable project-relative location."""
        try:
            displayed = str(self.path.relative_to(root))
        except ValueError:
            displayed = str(self.path)
        if self.line is not None:
            displayed += f":{self.line}"
            if self.column is not None:
                displayed += f":{self.column}"
        return displayed


def _included(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return not path.is_symlink() and not (_EXCLUDED_PARTS & set(relative.parts))


def project_text_files(root: Path, config_path: Path, docs_dir: Path) -> tuple[Path, ...]:
    """Inventory Markdown and recognized project configuration inputs."""
    root = root.resolve()
    candidates: set[Path] = {config_path.resolve()}
    candidates.update(root / name for name in CONFIG_FILENAMES)
    candidates.update(root / name for name in _ROOT_FILES)
    candidates.update(root / name for name in _REQUIREMENT_FILES)
    candidates.update(root / name for name in _RENDERER_FILES)
    candidates.update(root.glob(".prodockit-*.toml"))
    candidates.update(root.glob("requirements*.txt"))
    candidates.update((root / "requirements").glob("**/*.txt"))
    candidates.update((root / ".github" / "workflows").glob("**/*.yml"))
    candidates.update((root / ".github" / "workflows").glob("**/*.yaml"))
    candidates.update((root / ".gitlab").glob("**/*.yml"))
    candidates.update((root / ".gitlab").glob("**/*.yaml"))
    if docs_dir.is_dir() and _included(docs_dir, root):
        candidates.update(docs_dir.rglob("*.md"))
    return tuple(sorted(path for path in candidates if path.is_file() and _included(path, root)))


def inspect_utf8_file(path: Path) -> tuple[TextEncodingProblem, ...]:
    """Return every malformed UTF-8 span in one file, with bounded output."""
    try:
        data = path.read_bytes()
    except OSError as error:
        return (TextEncodingProblem(path, f"cannot read file: {error}"),)

    problems: list[TextEncodingProblem] = []
    cursor = 0
    omitted = 0
    while cursor < len(data):
        try:
            data[cursor:].decode("utf-8", errors="strict")
            break
        except UnicodeDecodeError as error:
            start = cursor + error.start
            end = max(cursor + error.end, start + 1)
            if len(problems) < _MAX_PROBLEMS_PER_FILE:
                line = data.count(b"\n", 0, start) + 1
                line_start = data.rfind(b"\n", 0, start) + 1
                problems.append(
                    TextEncodingProblem(
                        path,
                        "invalid UTF-8 byte sequence",
                        line,
                        start - line_start + 1,
                        start,
                    )
                )
            else:
                omitted += 1
            cursor = end
    if omitted:
        problems.append(
            TextEncodingProblem(path, f"{omitted} additional invalid UTF-8 sequence(s) omitted")
        )
    return tuple(problems)


def inspect_project_text_encoding(
    root: Path, config_path: Path, docs_dir: Path
) -> tuple[TextEncodingProblem, ...]:
    """Validate all recognized project text inputs without changing them."""
    return tuple(
        problem
        for path in project_text_files(root, config_path, docs_dir)
        for problem in inspect_utf8_file(path)
    )

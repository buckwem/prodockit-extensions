"""Syntax guards for TOML and YAML edits; never execute YAML constructors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml  # type: ignore[import-untyped, unused-ignore]

from prodockit import toml_integrity


def validate(source: str, path: Path, error_type: Callable[[str], Exception] = ValueError) -> None:
    if path.suffix.lower() == ".toml":
        toml_integrity.validate(source, path, error_type)
        return
    if path.suffix.lower() not in {".yml", ".yaml"}:
        return
    try:
        # Compose nodes rather than constructing values: Markdown Python tags,
        # GitLab !reference and GitHub expressions are data, never executed.
        list(yaml.compose_all(source, Loader=yaml.SafeLoader))
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None) or getattr(error, "context_mark", None)
        line = mark.line + 1 if mark else source.count("\n") + 1
        column = mark.column + 1 if mark else 1
        raise error_type(
            f"{path}: line {line}, column {column}: invalid YAML. "
            "Correct the syntax at this location, then rerun the same command. "
            "This file has not been changed; earlier completed activities are retained. "
            "The parser reports the first error; check again after correcting it."
        ) from error


def check(path: Path, error_type: Callable[[str], Exception] = ValueError) -> None:
    if path.suffix.lower() not in {".toml", ".yml", ".yaml"} or not path.exists():
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise error_type(
            f"Cannot read configuration file {path}; correct it before retrying."
        ) from error
    validate(source, path, error_type)


def before_write(
    path: Path, content: str | bytes, error_type: Callable[[str], Exception] = ValueError
) -> None:
    if path.suffix.lower() not in {".toml", ".yml", ".yaml"}:
        return
    check(path, error_type)
    try:
        source = content.decode("utf-8") if isinstance(content, bytes) else content
    except UnicodeError as error:
        raise error_type(
            f"Proposed configuration for {path} is not UTF-8; no write performed."
        ) from error
    validate(source, path, error_type)


def check_project(root: Path, error_type: Callable[[str], Exception] = ValueError) -> None:
    """Check project configuration and CI inputs, not environments or caches."""
    paths = set(root.glob("*.toml"))
    for pattern in (
        "*.yml",
        "*.yaml",
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".gitlab/**/*.yml",
        ".gitlab/**/*.yaml",
    ):
        paths.update(root.glob(pattern))
    for path in sorted(paths):
        check(path, error_type)

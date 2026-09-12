"""Independent TOML validation before planning edits and before replacing files."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib


def validate(source: str, path: Path, error_type: Callable[[str], Exception] = ValueError) -> None:
    """Report the first syntax error without echoing potentially private values."""
    try:
        tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        location = re.search(r"\(at line (\d+), column (\d+)\)", str(error))
        line = getattr(error, "lineno", None)
        column = getattr(error, "colno", None)
        if line is None:
            line = int(location[1]) if location else source.count("\n") + 1
            column = int(location[2]) if location else len(source.rsplit("\n", 1)[-1]) + 1
        raise error_type(
            f"{path}: line {line}, column {column}: invalid TOML. "
            "Correct the syntax at this location, then rerun the same command. "
            "This file has not been changed; earlier completed activities are retained. "
            "The parser reports the first error; check again after correcting it."
        ) from error


def check(path: Path, error_type: Callable[[str], Exception] = ValueError) -> None:
    """Validate an existing TOML file before any editing or replacement begins."""
    if path.suffix.lower() != ".toml" or not path.exists():
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise error_type(f"Cannot read TOML file {path}; correct it before retrying.") from error
    validate(source, path, error_type)


def before_write(
    path: Path, content: str | bytes, error_type: Callable[[str], Exception] = ValueError
) -> None:
    """Check both old and proposed contents, including generated manifests."""
    if path.suffix.lower() != ".toml":
        return
    check(path, error_type)
    try:
        source = content.decode("utf-8") if isinstance(content, bytes) else content
    except UnicodeError as error:
        raise error_type(f"Proposed TOML for {path} is not UTF-8; no write performed.") from error
    validate(source, path, error_type)


def check_project(root: Path, error_type: Callable[[str], Exception] = ValueError) -> None:
    """Preflight root TOML inputs before an Adopt activity can mutate anything."""
    for path in sorted(root.glob("*.toml")):
        check(path, error_type)

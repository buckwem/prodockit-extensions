# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Architecture guard for Python-Markdown representation dependencies."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "prodockit"


def _reads_named_toc_processor(path: Path) -> bool:
    """Whether *path* directly reads ``*.treeprocessors['toc']``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if not isinstance(value, ast.Attribute) or value.attr != "treeprocessors":
            continue
        key = node.slice
        if isinstance(key, ast.Constant) and key.value == "toc":
            return True
    return False


def test_toc_processor_representation_is_confined_to_its_adapter() -> None:
    actual = {
        path.relative_to(SOURCE).as_posix()
        for path in SOURCE.rglob("*.py")
        if _reads_named_toc_processor(path)
    }

    assert actual == {"_markdown_toc.py"}, (
        "Python-Markdown's registered TOC processor representation must stay "
        "inside _markdown_toc.py; feature extensions should call toc_slugging()."
    )

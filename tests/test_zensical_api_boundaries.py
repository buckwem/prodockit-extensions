# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Architecture guard for undocumented Zensical Python dependencies.

Issue #561 removes this inventory one entry at a time. Keeping the exact
current set here prevents a new internal import arriving elsewhere while the
migration is in progress. The PDF entries remain only for the hidden legacy
renderer now that the public command consumes Zensical's built output.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "prodockit"

# Prodockit deliberately uses Zensical's documented CLI rather than its Python
# package, including for version lookup.  A normal extension name in a config
# string is not an API dependency and is therefore outside this AST scan; a
# string literal passed to ``importlib.import_module`` is an import and is
# inventoried below.
PROHIBITED_ZENSICAL_MODULE_PREFIXES = ("zensical",)

# Transitional inventory.  Every removal must shrink this mapping in the same
# change; every addition fails the test and requires an explicit design review.
EXPECTED_PRODUCTION_IMPORTS = {
    "_zensical_page_context.py": {"zensical.extensions.context"},
    "pdf/config.py": {"zensical.config", "zensical.markdown.render"},
}


def _undocumented_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    direct_import_module_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "importlib"
        for alias in node.names
        if alias.name == "import_module"
    }
    importlib_module_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "importlib"
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = (node.module,)
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and (
                (isinstance(node.func, ast.Name) and node.func.id in direct_import_module_names)
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in importlib_module_names
                )
            )
        ):
            names = (node.args[0].value,)
        else:
            continue
        for name in names:
            if name.startswith(PROHIBITED_ZENSICAL_MODULE_PREFIXES):
                found.add(name)
    return found


def test_undocumented_zensical_production_imports_match_the_shrinking_inventory() -> None:
    actual = {
        path.relative_to(SOURCE).as_posix(): imports
        for path in SOURCE.rglob("*.py")
        if (imports := _undocumented_imports(path))
    }

    assert actual == EXPECTED_PRODUCTION_IMPORTS, (
        "Undocumented Zensical imports changed. Issue #561 requires this "
        "inventory to shrink as legacy integrations are retired; "
        "do not add a new internal dependency to make another change work."
    )

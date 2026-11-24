# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Allow standalone styling calls while native Zensical owns macro rendering."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from prodockit.portable import PortableError

EXTENSION = "zensical.extensions.macros"
MODULE_FILENAME = "macros.py"
HEADING_NAMES = {"heading_counter_reset", "pdk_heading_counter_reset"}
_STYLE_NAMES = {
    "reference_style", "acronym_style", "glossary_style",
    "pdk_reference_style", "pdk_acronym_style", "pdk_glossary_style", "pdk_festive",
}
_TAG = re.compile(
    r"\{%[ \t]*raw[ \t]*%\}.*?\{%[ \t]*endraw[ \t]*%\}|(?P<unsupported>\{[{%#])",
    re.DOTALL,
)
_CALL = re.compile(
    r"\{\{[ \t]*(?P<name>[a-z_]+)[ \t]*\([ \t]*(?P<argument>page)?[ \t]*\)"
    r"[ \t]*\}\}[ \t]*$"
)


def capture_module(
    root: Path, options: dict[str, object], files: dict[Path, bytes]
) -> Path:
    """Capture a local module that only re-exports the standard Prodockit macros."""
    name = options.get("module_name", "main")
    if (
        not isinstance(name, str)
        or not name.isidentifier()
        or set(options) - {"module_name", "on_error_fail", "on_undefined", "verbose"}
    ):
        raise PortableError("portable macros require a local Prodockit macro module")
    module = root / f"{name}.py"
    if module.is_symlink() or not module.is_file():
        raise PortableError(f"portable macros require a local module: {module.name}")
    data = module.read_bytes()
    try:
        body = ast.parse(data, filename=str(module)).body
    except SyntaxError as error:
        raise PortableError(f"invalid macro module: {module.name}: {error.msg}") from error
    if (
        body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if (
        len(body) != 1
        or not isinstance(imports := body[0], ast.ImportFrom)
        or imports.level != 0
        or imports.module != "prodockit.zensical_macros"
        or len(imports.names) != 1
        or imports.names[0].name != "define_env"
        or imports.names[0].asname not in {None, "define_env"}
    ):
        raise PortableError(
            f"{module.name}: portable macros currently require a plain define_env re-export"
        )
    files[module] = data
    return module


def styling_calls(source: str, body: str, first_line: int) -> dict[int, str]:
    """Recognise complete styling lines and refuse content-generating templates."""
    calls: dict[int, str] = {}
    for match in _TAG.finditer(body):
        start = match.start()
        if match["unsupported"] is None:
            continue
        end = body.find("\n", start)
        end = len(body) if end == -1 else end
        call = _CALL.fullmatch(body, start, end)
        if (start == 0 or body[start - 1] == "\n") and call is not None:
            name, argument = call["name"], call["argument"]
            if (name in HEADING_NAMES and argument == "page") or (
                name in _STYLE_NAMES and argument is None
            ):
                calls[start] = name
                continue
        line = first_line + body.count("\n", 0, start)
        raise PortableError(f"{source}:{line}: unsupported template in portable macros")
    return calls

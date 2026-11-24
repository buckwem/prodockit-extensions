# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Allow standalone styling calls while native Zensical owns macro rendering."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import DebugUndefined, StrictUndefined, TemplateError, Undefined, nodes
from jinja2.sandbox import SandboxedEnvironment

from prodockit.portable import PortableError

EXTENSION = "zensical.extensions.macros"
MODULE_FILENAME = "macros.py"
HEADING_NAMES = {"heading_counter_reset", "pdk_heading_counter_reset"}
_STYLE_NAMES = {
    "reference_style", "acronym_style", "glossary_style",
    "pdk_reference_style", "pdk_acronym_style", "pdk_glossary_style", "pdk_festive",
}
_RAW = r"\{%[ \t]*raw[ \t]*%\}.*?\{%[ \t]*endraw[ \t]*%\}"
_TAG = re.compile(_RAW + r"|(?P<unsupported>\{[{%#])", re.DOTALL)
_QUOTED = r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\x22"""
_TAG_BODY = rf"""(?:{_QUOTED}|[^'"])*?"""
_BLOCK = re.compile(
    _RAW + rf"|\{{#.*?#\}}|\{{\{{{_TAG_BODY}\}}\}}"
    rf"|(?P<block>\{{%{_TAG_BODY}%\}}|\{{%)",
    re.DOTALL,
)
_BRANCH = re.compile(
    r"\{%\s*(?P<kind>if|elif|else|endif)(?P<condition>\s.*?)?%\}", re.DOTALL
)
_EXPRESSIONS = (
    nodes.Name, nodes.Const, nodes.Getattr, nodes.Getitem, nodes.And, nodes.Or, nodes.Not,
    nodes.Compare, nodes.Operand, nodes.Tuple, nodes.List, nodes.Dict, nodes.Pair,
    nodes.Neg, nodes.Pos, nodes.Test,
)
_RENDER_VARIABLES = {
    "config", "page", "git", "environment", "files", "navigation", "plugin",
    "filters", "filters_builtin", "macros", "context", "now", "macros_info",
    "reference_style", "word_count", "repo_url", "applied_release",
    "pdk_word_count", "pdk_repo_url", "pdk_applied_release",
} | HEADING_NAMES | _STYLE_NAMES

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


_UNDEFINED = {"keep": DebugUndefined, "silent": Undefined, "strict": StrictUndefined}


class _MetadataLoader(yaml.SafeLoader):
    """Read front matter using the native renderer's plain-scalar conventions."""


_MetadataLoader.yaml_implicit_resolvers = {}


def _decimal_metadata_integer(loader: _MetadataLoader, node: yaml.ScalarNode) -> int:
    value = loader.construct_scalar(node)
    return int(value, 0 if value.startswith(("0x", "0o")) else 10)


_MetadataLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), ["t", "f"],
)
_MetadataLoader.add_implicit_resolver(
    "tag:yaml.org,2002:null", re.compile(r"^(?:null|~)?$"), ["n", "~", ""],
)
_MetadataLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^(?:[+-]?[0-9]+|0x[0-9a-fA-F]+|0o[0-7]+)$"),
    list("0123456789+-"),
)
_MetadataLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"),
    list("0123456789+-."),
)
_MetadataLoader.add_constructor("tag:yaml.org,2002:int", _decimal_metadata_integer)


@dataclass(frozen=True)
class ConditionalContext:
    extra: Mapping[str, Any]
    undefined: str = "keep"

    @classmethod
    def from_config(
        cls, project: dict[str, Any], extensions: dict[str, dict[str, Any]]
    ) -> ConditionalContext:
        return cls(
            project.get("extra") or {},
            extensions.get(EXTENSION, {}).get("on_undefined", "keep"),
        )


@dataclass
class _Branch:
    parent_active: bool
    matched: bool
    location: str
    has_else: bool = False


def _evaluate(
    environment: SandboxedEnvironment,
    expression: str,
    variables: dict[str, Any],
    *,
    active: bool,
    location: str,
) -> bool:
    try:
        statement, = environment.parse("{% if " + expression + " %}{% endif %}").body
        if not isinstance(statement, nodes.If) or (
            statement.body or statement.elif_ or statement.else_
        ):
            raise PortableError(f"{location}: unsupported conditional expression")
        test = statement.test
        for node in (test, *test.find_all(nodes.Node)):
            if not isinstance(node, _EXPRESSIONS) or (
                isinstance(node, nodes.Test) and node.name not in {"defined", "undefined"}
            ):
                raise PortableError(f"{location}: unsupported conditional expression")
            if active and isinstance(node, nodes.Name) and node.name not in variables and (
                node.name in _RENDER_VARIABLES or node.name in environment.globals
            ):
                raise PortableError(
                    f"{location}: conditional needs render-time variable {node.name!r}"
                )
        return active and bool(
            environment.compile_expression(expression, undefined_to_none=False)(**variables)
        )
    except (TemplateError, ValueError, TypeError) as error:
        raise PortableError(f"{location}: cannot evaluate portable conditional: {error}") from error


def conditional_removals(
    body: str,
    context: ConditionalContext,
    front_matter: str,
    location: Callable[[int], str],
) -> list[tuple[int, int]]:
    """Select captured-data branches without executing template code or the macro module."""
    gaps: list[tuple[int, int]] = []
    branches: list[_Branch] = []
    cursor = 0
    active = True
    environment = None
    extra = context.extra
    variables = {"extra": extra, **extra}
    variables.pop("reference_style", None)  # The native module installs the legacy callable.
    for match in _BLOCK.finditer(body):
        block = match["block"]
        if block is None:
            continue
        here = location(match.start())
        tag = _BRANCH.fullmatch(block)
        if tag is None:
            raise PortableError(f"{here}: unsupported template in portable macros")
        kind = tag["kind"]
        condition = (tag["condition"] or "").strip()
        if bool(condition) != (kind in {"if", "elif"}):
            raise PortableError(f"{here}: invalid portable conditional tag")
        if environment is None:
            try:
                meta = yaml.load(front_matter, Loader=_MetadataLoader) or {}
            except (ValueError, TypeError, yaml.YAMLError) as error:
                raise PortableError(f"{here}: cannot read conditional metadata: {error}") from error
            if not isinstance(meta, dict):
                raise PortableError(f"{here}: conditional metadata must be a mapping")
            variables.update(meta)
            if meta.get("include_yaml") or meta.get("render_macros") is False:
                raise PortableError(
                    f"{here}: portable conditionals require captured macro variables"
                )
            undefined = _UNDEFINED.get(context.undefined)
            if undefined is None:
                raise PortableError(f"{here}: unknown macro undefined policy")
            environment = SandboxedEnvironment(undefined=undefined)
            try:
                environment.parse(body)
            except TemplateError as error:
                starts = [0, *(match.end() for match in re.finditer("\n", body))]
                line = getattr(error, "lineno", 1) or 1
                where = location(starts[min(line, len(starts)) - 1])
                raise PortableError(f"{where}: invalid macro template: {error}") from error

        start = match.start() if active else cursor
        gaps.append((start, match.end()))
        cursor = match.end()
        if kind == "if":
            selected = _evaluate(environment, condition, variables, active=active, location=here)
            branches.append(_Branch(active, selected, here))
            active = selected
        else:
            if not branches:
                raise PortableError(f"{here}: unexpected {kind} without an open if")
            branch = branches[-1]
            if kind == "endif":
                active = branches.pop().parent_active
                continue
            if branch.has_else:
                raise PortableError(f"{here}: unexpected {kind} after else")
            eligible = branch.parent_active and not branch.matched
            active = eligible if kind == "else" else _evaluate(
                environment, condition, variables, active=eligible, location=here
            )
            branch.has_else = kind == "else"
            branch.matched |= active
    if branches:
        raise PortableError(f"{branches[-1].location}: unclosed portable conditional")
    return gaps


def styling_calls(body: str, location: Callable[[int], str]) -> dict[int, str]:
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
        raise PortableError(f"{location(start)}: unsupported template in portable macros")
    return calls

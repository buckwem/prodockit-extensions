# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Adopt prodockit in an existing Zensical or MkDocs project.

This is deliberately project-scoped.  ``prodockit bootstrap`` prepares a machine and a
repository; adoption starts after that boundary, with an author who already
has Git, SSH, an editor and an existing documentation site.  It therefore
changes only files below the project root and never commits or pushes them.

The module contains the file operations separately from Click presentation so
they can be tested without a terminal or network access.  Mermaid and maths
are independent capabilities: neither is selected by default and neither
toolchain is written into a project which did not ask for it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]

from prodockit import __version__
from prodockit._zensical_defaults import DOCUMENTED_MARKDOWN_DEFAULTS
from prodockit.init_tools import COMPONENT_FILES, init_tools
from prodockit.mathjax import MathJaxError, install_mathjax
from prodockit.shared_files import resource_bytes

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


MANIFEST = ".prodockit-components.toml"
STYLESHEET = Path("docs/stylesheets/pdk.css")
CONFIG_NAMES = (
    "zensical.toml",
    "zensical.yml",
    "zensical.yaml",
    "mkdocs.yml",
    "mkdocs.yaml",
)
REQUIREMENT_CANDIDATES = (
    Path("requirements.txt"),
    Path("requirements/docs.txt"),
    Path("docs/requirements.txt"),
)

# These are the Python-only authoring additions.  They are safe to enable in
# a project which does not use their syntax: no Node renderer or external
# command is started merely because the extension is present.
CORE_EXTENSIONS = (
    "prodockit.headings",
    "prodockit.refs",
    "prodockit.citations",
    "prodockit.glossary",
    "prodockit.bibliography",
    "prodockit.tables",
    "prodockit.steps",
    "prodockit.tree",
    "prodockit.index",
)

# Directory trees emit these documented Zensical icon shortcodes by default.
# An explicit Markdown extension collection replaces Zensical's implicit
# defaults, so adoption must materialise the compatible renderer alongside
# prodockit.tree rather than leave the shortcodes visible in the output.
TREE_ICON_EXTENSION = "pymdownx.emoji"
TREE_ICON_SETTINGS = DOCUMENTED_MARKDOWN_DEFAULTS[TREE_ICON_EXTENSION]

MERMAID_FENCE = (
    '{ name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" }'
)


class AdoptError(Exception):
    """An existing project cannot safely be adopted as it stands."""


@dataclass(frozen=True)
class AdoptOptions:
    mermaid: bool = False
    maths: bool = False


@dataclass(frozen=True)
class Step:
    id: str
    phase: str
    summary: str
    status: str
    detail: str
    selected: bool = True

    @property
    def needs_work(self) -> bool:
        return self.selected and self.status not in {"ok", "wait"}


def load_manifest(root: Path) -> AdoptOptions:
    path = root / MANIFEST
    if not path.is_file():
        return AdoptOptions()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AdoptError(f"could not read {path}: {error}") from error
    components = data.get("components", {})
    return AdoptOptions(
        mermaid=bool(components.get("mermaid", False)),
        maths=bool(components.get("maths", False)),
    )


def write_manifest(root: Path, options: AdoptOptions) -> Path:
    path = root / MANIFEST
    source = (
        "# Selected by `prodockit adopt`; safe to commit.\n"
        "schema = 1\n\n"
        "[components]\n"
        f"mermaid = {str(options.mermaid).lower()}\n"
        f"maths = {str(options.maths).lower()}\n"
    )
    path.write_text(source, encoding="utf-8")
    return path


class _MarkdownConfigLoader(yaml.SafeLoader):  # type: ignore[misc, unused-ignore]
    """Safe YAML loader which treats MkDocs' Python-name tags as text.

    ``pymdownx.superfences`` commonly uses ``!!python/name:...`` for a
    formatter. Constructing arbitrary Python objects from a project file would
    be inappropriate here; the suffix is enough for configuration inventory.
    """


def _python_name(
    _loader: _MarkdownConfigLoader,
    suffix: str,
    _node: yaml.Node,
) -> str:
    return suffix


_MarkdownConfigLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/name:",
    _python_name,
)


def _python_object(
    loader: _MarkdownConfigLoader,
    _suffix: str,
    node: yaml.Node,
) -> Any:
    """Inventory a tagged value without importing or calling its target."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_MarkdownConfigLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/object/apply:",
    _python_object,
)


def _config(root: Path) -> tuple[Path, str, dict[str, Any]]:
    path = next((root / name for name in CONFIG_NAMES if (root / name).is_file()), None)
    if path is None:
        raise AdoptError(
            "no Zensical or MkDocs configuration is here. Run this command from "
            "the directory containing zensical.toml, zensical.yml, zensical.yaml, "
            "mkdocs.yml or mkdocs.yaml."
        )
    try:
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".toml":
            parsed = tomllib.loads(source)
        else:
            parsed = yaml.load(source, Loader=_MarkdownConfigLoader)
    except (OSError, tomllib.TOMLDecodeError, yaml.YAMLError) as error:
        raise AdoptError(f"could not read {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise AdoptError(f"{path} does not contain a configuration mapping")
    if path.suffix == ".toml" and not isinstance(parsed.get("project"), dict):
        raise AdoptError(f"{path} has no [project] table")
    return path, source, parsed


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _requirements_path(root: Path) -> Path:
    return next(
        (root / relative for relative in REQUIREMENT_CANDIDATES if (root / relative).is_file()),
        root / REQUIREMENT_CANDIDATES[0],
    )


def _requirement_ok(root: Path) -> bool:
    path = _requirements_path(root)
    if not path.is_file():
        return False
    return bool(
        re.search(
            r"(?im)^\s*prodockit(?:\[[^]]+\])?\s*>=\s*\S+",
            path.read_text(encoding="utf-8"),
        )
    )


def ensure_requirement(root: Path) -> Path:
    """Record a floor in the site's requirements file, never an exact package pin."""
    path = _requirements_path(root)
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    pattern = re.compile(
        r"(?im)^(?P<lead>\s*)prodockit(?:\[[^]]+\])?\s*"
        r"(?:==|>=|~=|<=|>|<)\s*[^\s#]+(?P<tail>\s*(?:#.*)?)$"
    )
    replacement = rf"\g<lead>prodockit>={__version__}\g<tail>"
    if pattern.search(current):
        updated = pattern.sub(replacement, current, count=1)
    else:
        lead = "" if not current or current.endswith("\n") else "\n"
        updated = f"{current}{lead}prodockit>={__version__}\n"
    path.write_text(updated, encoding="utf-8")
    return path


def _extensions(parsed: dict[str, Any]) -> dict[str, Any]:
    project = parsed.get("project", parsed)
    value = project.get("markdown_extensions", {}) if isinstance(project, dict) else {}
    if isinstance(value, dict):
        return value
    configured: dict[str, Any] = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                configured[item] = {}
            elif isinstance(item, dict):
                configured.update(item)
    return configured


def _serializable_default(value: Any) -> Any:
    """Turn Zensical's callable defaults into config-file values."""
    if callable(value):
        return f"{value.__module__}.{value.__name__}"
    if isinstance(value, Mapping):
        return {str(key): _serializable_default(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serializable_default(item) for item in value]
    return value


def _toml_value(value: Any) -> str:
    """Render the small TOML value vocabulary used by Zensical's defaults."""
    value = _serializable_default(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        body = ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items())
        return "{ " + body + " }"
    raise AdoptError(f"cannot preserve Zensical's Markdown default value {value!r}")


def _seed_toml_markdown_defaults(source: str) -> str:
    """Materialise defaults which an explicit extension table would replace."""
    chunks: list[str] = []
    for name, settings in DOCUMENTED_MARKDOWN_DEFAULTS.items():
        if not isinstance(settings, Mapping):  # pragma: no cover - upstream contract guard
            raise AdoptError(f"Zensical's Markdown default for {name} is not a mapping")
        lines = [f'[project.markdown_extensions."{name}"]']
        lines.extend(f"{key} = {_toml_value(value)}" for key, value in settings.items())
        chunks.append("\n".join(lines))
    lead = "" if source.endswith("\n") else "\n"
    return f"{source}{lead}\n" + "\n".join(chunks) + "\n"


def _seed_yaml_markdown_defaults(source: str) -> str:
    """Materialise Zensical defaults before adding entries to YAML config."""
    defaults = {
        name: _serializable_default(settings) or None
        for name, settings in DOCUMENTED_MARKDOWN_DEFAULTS.items()
    }
    rendered = yaml.safe_dump(
        {"markdown_extensions": defaults},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    lead = "" if source.endswith("\n") else "\n"
    return f"{source}{lead}\n{rendered}"


def _docs_dir(parsed: dict[str, Any]) -> Path:
    project = parsed.get("project", parsed)
    configured = project.get("docs_dir", "docs") if isinstance(project, dict) else "docs"
    path = Path(str(configured))
    if path.is_absolute() or ".." in path.parts:
        raise AdoptError("docs_dir must stay inside the project directory")
    return path


def _stylesheet_path(root: Path, parsed: dict[str, Any]) -> Path:
    return root / _docs_dir(parsed) / "stylesheets" / "pdk.css"


def _core_ok(parsed: dict[str, Any]) -> bool:
    configured = _extensions(parsed)
    return all(name in configured for name in CORE_EXTENSIONS) and _tree_icons_ok(parsed)


def _tree_icons_ok(parsed: dict[str, Any]) -> bool:
    configured = _extensions(parsed)
    settings = configured.get(TREE_ICON_EXTENSION)
    return isinstance(settings, Mapping) and all(key in settings for key in TREE_ICON_SETTINGS)


def _style_ok(root: Path, parsed: dict[str, Any]) -> bool:
    project = parsed.get("project", parsed)
    extra_css = project.get("extra_css", []) if isinstance(project, dict) else []
    return _stylesheet_path(root, parsed).is_file() and "stylesheets/pdk.css" in extra_css


def _section(source: str, table: str) -> tuple[int, int] | None:
    match = re.search(rf"(?m)^\[{re.escape(table)}\]\s*$", source)
    if match is None:
        return None
    following = re.search(r"(?m)^\[", source[match.end() :])
    end = match.end() + following.start() if following else len(source)
    return match.start(), end


def _append_tables(source: str, tables: tuple[str, ...]) -> str:
    missing = [table for table in tables if _section(source, table) is None]
    if not missing:
        return source
    lead = "" if source.endswith("\n") else "\n"
    return source + lead + "\n" + "\n".join(f"[{table}]" for table in missing) + "\n"


def _matching_bracket(source: str, start: int) -> int:
    depth = 0
    quote = ""
    escaped = False
    for position in range(start, len(source)):
        char = source[position]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return position
    raise AdoptError("could not find the end of a TOML array")


def _add_array_value(
    source: str,
    table: str,
    key: str,
    rendered: str,
    *,
    prepend: bool = False,
) -> str:
    located = _section(source, table)
    if located is None:
        source = _append_tables(source, (table,))
        located = _section(source, table)
    assert located is not None
    start, end = located
    region = source[start:end]
    assignment = re.search(rf"(?m)^{re.escape(key)}\s*=\s*\[", region)
    if assignment is None:
        header_end = source.find("\n", start) + 1
        return source[:header_end] + f"{key} = [\n  {rendered},\n]\n" + source[header_end:]
    array_start = start + assignment.end() - 1
    array_end = _matching_bracket(source, array_start)
    if rendered in source[array_start : array_end + 1]:
        return source
    if prepend:
        addition = f"\n  {rendered},"
        return source[: array_start + 1] + addition + source[array_start + 1 :]
    body = source[array_start + 1 : array_end]
    separator = "" if not body.strip() or body.rstrip().endswith(",") else ","
    addition = f"{separator}\n  {rendered},\n"
    return source[:array_end] + addition + source[array_end:]


def _set_table_bool(source: str, table: str, key: str, value: bool) -> str:
    located = _section(source, table)
    if located is None:
        source = _append_tables(source, (table,))
        located = _section(source, table)
    assert located is not None
    start, end = located
    region = source[start:end]
    rendered = str(value).lower()
    assignment = re.search(rf"(?m)^{re.escape(key)}\s*=\s*(?:true|false)[ \t]*$", region)
    if assignment:
        absolute_start = start + assignment.start()
        absolute_end = start + assignment.end()
        return source[:absolute_start] + f"{key} = {rendered}" + source[absolute_end:]
    header_end = source.find("\n", start) + 1
    return source[:header_end] + f"{key} = {rendered}\n" + source[header_end:]


def _add_table_string(source: str, table: str, key: str, value: str) -> str:
    """Add a missing string setting without replacing existing table data."""
    located = _section(source, table)
    if located is None:
        source = _append_tables(source, (table,))
        located = _section(source, table)
    assert located is not None
    start, end = located
    if re.search(rf"(?m)^{re.escape(key)}\s*=", source[start:end]):
        return source
    header_end = source.find("\n", start) + 1
    return source[:header_end] + f"{key} = {_toml_value(value)}\n" + source[header_end:]


def _set_array_extension(source: str, name: str, setting: str) -> str:
    """Configure an extension stored in ``project.markdown_extensions``.

    Zensical's TOML syntax accepts an array containing strings and inline
    tables.  A string has no settings, so replace it with the equivalent
    inline table when Mermaid or maths needs one.  Refuse an unfamiliar
    preconfigured inline table rather than risk discarding project settings.
    """
    located = _section(source, "project")
    assert located is not None
    start, end = located
    assignment = re.search(r"(?m)^markdown_extensions\s*=\s*\[", source[start:end])
    assert assignment is not None
    array_start = start + assignment.end() - 1
    array_end = _matching_bracket(source, array_start)
    region = source[array_start : array_end + 1]
    simple = re.search(
        rf"(?P<quote>[\"']){re.escape(name)}(?P=quote)(?![ \t]*=)", region
    )
    rendered = f'{{ "{name}" = {{ {setting} }} }}'
    if simple is not None:
        absolute_start = array_start + simple.start()
        absolute_end = array_start + simple.end()
        return source[:absolute_start] + rendered + source[absolute_end:]
    if name in region:
        raise AdoptError(
            f"the configured {name} inline table cannot be updated safely; "
            "add the required setting yourself and rerun"
        )
    return _add_array_value(source, "project", "markdown_extensions", rendered)


def _ensure_toml_tree_icons(
    source: str,
    parsed: dict[str, Any],
    *,
    extension_array: bool,
) -> str:
    """Materialise the icon renderer required by prodockit.tree."""
    configured = _extensions(parsed)
    existing = configured.get(TREE_ICON_EXTENSION)

    if extension_array:
        if _tree_icons_ok(parsed):
            return source
        setting = ", ".join(
            f"{key} = {_toml_value(value)}" for key, value in TREE_ICON_SETTINGS.items()
        )
        return _set_array_extension(source, TREE_ICON_EXTENSION, setting)

    table = f'project.markdown_extensions."{TREE_ICON_EXTENSION}"'
    for key, value in TREE_ICON_SETTINGS.items():
        if not isinstance(existing, Mapping) or key not in existing:
            source = _add_table_string(source, table, key, str(value))
    return source


def _planned_zensical_config(root: Path, options: AdoptOptions) -> tuple[Path, str]:
    """Return the validated configuration update without writing it."""
    path, source, _parsed = _config(root)
    if path.suffix != ".toml":
        return path, _planned_yaml_config(path, source, _parsed, options)
    project = _parsed["project"]
    if "markdown_extensions" not in project:
        source = _seed_toml_markdown_defaults(source)
        _parsed = tomllib.loads(source)
        project = _parsed["project"]
    extension_array = isinstance(project.get("markdown_extensions"), list)
    if extension_array:
        configured = _extensions(_parsed)
        for name in CORE_EXTENSIONS:
            if name not in configured:
                source = _add_array_value(source, "project", "markdown_extensions", f'"{name}"')
    else:
        source = _append_tables(
            source,
            tuple(f'project.markdown_extensions."{name}"' for name in CORE_EXTENSIONS),
        )
    source = _ensure_toml_tree_icons(
        source,
        _parsed,
        extension_array=extension_array,
    )
    source = _add_array_value(
        source,
        "project",
        "extra_css",
        '"stylesheets/pdk.css"',
        prepend=True,
    )
    if options.mermaid:
        if extension_array:
            existing = _extensions(_parsed).get("pymdownx.superfences")
            fences = existing.get("custom_fences", []) if isinstance(existing, dict) else []
            if not any(isinstance(item, dict) and item.get("name") == "mermaid" for item in fences):
                source = _set_array_extension(
                    source,
                    "pymdownx.superfences",
                    f"custom_fences = [{MERMAID_FENCE}]",
                )
        else:
            source = _add_array_value(
                source,
                "project.markdown_extensions.pymdownx.superfences",
                "custom_fences",
                MERMAID_FENCE,
            )
    if options.maths:
        if extension_array:
            existing = _extensions(_parsed).get("pymdownx.arithmatex")
            if not isinstance(existing, dict) or existing.get("generic") is not True:
                source = _set_array_extension(source, "pymdownx.arithmatex", "generic = true")
        else:
            source = _set_table_bool(
                source,
                "project.markdown_extensions.pymdownx.arithmatex",
                "generic",
                True,
            )
        source = _add_array_value(
            source,
            "project",
            "extra_javascript",
            '"javascripts/mathjax.js"',
        )
        source = _add_array_value(
            source,
            "project",
            "extra_javascript",
            '"javascripts/vendor/mathjax/tex-svg-full.js"',
        )
    try:
        tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:  # pragma: no cover - defensive transaction guard
        raise AdoptError(f"the planned {path.name} would be invalid: {error}") from error
    return path, source


def ensure_zensical_config(root: Path, options: AdoptOptions) -> Path:
    path, source = _planned_zensical_config(root, options)
    path.write_text(source, encoding="utf-8")
    return path


def _yaml_block(source: str, key: str) -> tuple[int, int] | None:
    match = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(?:#.*)?$", source)
    if match is None:
        return None
    following = re.search(r"(?m)^[A-Za-z_][\w.-]*:", source[match.end() :])
    end = match.end() + following.start() if following else len(source)
    return match.start(), end


def _yaml_list_indent(source: str, located: tuple[int, int], default: str = "  ") -> str:
    start, end = located
    # YAML permits a sequence to be indented at the same level as its key.
    # Preserve that style: mixing a newly indented item with existing
    # indentless items makes an otherwise valid configuration invalid.
    item = re.search(r"(?m)^(?P<indent>[ \t]*)- ", source[start:end])
    return item.group("indent") if item else default


def _yaml_extension_layout(source: str, located: tuple[int, int]) -> tuple[str, str]:
    """Return the collection style and top-level item indentation.

    MkDocs accepts ``markdown_extensions`` as either a sequence or a mapping.
    The mapping form is useful when most extensions have settings, and is used
    by FastAPI.  Look only at the first non-comment child so nested sequences
    in extension settings cannot be mistaken for the outer collection.
    """
    start, end = located
    header_end = source.find("\n", start, end)
    if header_end == -1:
        return "sequence", "  "
    for line in source[header_end + 1 : end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"(?P<indent>[ \t]*)(?P<body>.*)", line)
        assert match is not None
        body = match.group("body")
        return ("sequence" if body.startswith("- ") else "mapping"), match.group("indent")
    return "sequence", "  "


def _yaml_add_top_list_value(
    source: str,
    key: str,
    rendered: str,
    *,
    prepend: bool = False,
) -> str:
    located = _yaml_block(source, key)
    if located is None:
        inline = re.search(rf"(?m)^{re.escape(key)}:[ \t]*\[(?P<body>[^\]\n]*)\][ \t]*$", source)
        if inline:
            if rendered.strip("\"'") in inline.group("body"):
                return source
            body = inline.group("body")
            if prepend:
                insert = inline.start("body")
                separator = ", " if body.strip() else ""
                return source[:insert] + rendered + separator + source[insert:]
            insert = inline.start("body") + len(body)
            separator = ", " if body.strip() else ""
            return source[:insert] + separator + rendered + source[insert:]
        if re.search(rf"(?m)^{re.escape(key)}:", source):
            raise AdoptError(
                f"{key} uses a YAML form prodockit cannot update safely; "
                "write it as a block or inline list and rerun"
            )
        lead = "" if source.endswith("\n") else "\n"
        return f"{source}{lead}\n{key}:\n  - {rendered}\n"
    start, end = located
    region = source[start:end]
    if rendered.strip("\"'") in region:
        return source
    header_end = source.find("\n", start) + 1
    if header_end <= 0:
        header_end = end
    indent = _yaml_list_indent(source, located)
    return source[:header_end] + f"{indent}- {rendered}\n" + source[header_end:]


def _yaml_add_extension(source: str, name: str, lines: tuple[str, ...] = ()) -> str:
    configured = _yaml_block(source, "markdown_extensions")
    style, indent = _yaml_extension_layout(source, configured) if configured else ("sequence", "  ")
    if style == "mapping":
        entry = f"{indent}{name}:"
        if lines:
            entry += "\n" + "\n".join(f"{indent}  {line}" for line in lines) + "\n"
        else:
            entry += " null\n"
    else:
        entry = f"{indent}- {name}"
        if lines:
            entry += ":\n" + "\n".join(f"{indent}    {line}" for line in lines) + "\n"
        else:
            entry += "\n"
    if configured is None:
        if re.search(r"(?m)^markdown_extensions:", source):
            raise AdoptError(
                "markdown_extensions uses an inline or unusual YAML form. "
                "Change it to the normal indented list before running adoption."
            )
        lead = "" if source.endswith("\n") else "\n"
        return f"{source}{lead}\nmarkdown_extensions:\n{entry}"
    start, end = configured
    region = source[start:end]
    prefix = "- " if style == "sequence" else ""
    pattern = re.compile(
        rf"(?m)^{re.escape(indent + prefix + name)}(?P<colon>:)?"
        r"(?P<value>[ \t]*(?:null|~|\{\})?)[ \t]*$"
    )
    match = pattern.search(region)
    if match is not None:
        if not lines:
            return source
        absolute_start = start + match.start()
        absolute_end = start + match.end()
        if match.group("colon") and (
            style == "sequence" or match.group("value").strip() not in {"null", "~"}
        ):
            # A configured copy may carry project-specific settings. Do not
            # replace it; targeted helpers below add only required keys.
            return source
        return source[:absolute_start] + entry.rstrip("\n") + source[absolute_end:]
    if re.search(rf"(?m)^{re.escape(indent + prefix + name)}(?:[ \t]*:|[ \t]*$)", region):
        raise AdoptError(
            f"{name} uses a YAML form prodockit cannot update safely; "
            "write it as an indented mapping and rerun"
        )
    return source[:end] + entry + source[end:]


def _yaml_extension_item(source: str, name: str) -> tuple[int, int] | None:
    block = _yaml_block(source, "markdown_extensions")
    if block is None:
        return None
    start, end = block
    style, indent = _yaml_extension_layout(source, block)
    prefix = "- " if style == "sequence" else ""
    header = re.escape(indent + prefix + name)
    if style == "sequence":
        pattern = rf"(?m)^{header}(?::[ \t]*(?:null|~|\{{\}})?)?[ \t]*$"
    else:
        pattern = rf"(?m)^{header}:[ \t]*(?:null|~|\{{\}})?[ \t]*$"
    match = re.search(pattern, source[start:end])
    if match is None:
        return None
    item_start = start + match.start()
    if style == "sequence":
        following_pattern = rf"(?m)^{re.escape(indent)}- "
    else:
        following_pattern = rf"(?m)^{re.escape(indent)}[^ \t#\n][^:\n]*:"
    following = re.search(following_pattern, source[start + match.end() : end])
    item_end = start + match.end() + following.start() if following else end
    return item_start, item_end


def _yaml_ensure_arithmatex(source: str) -> str:
    source = _yaml_add_extension(source, "pymdownx.arithmatex", ("generic: true",))
    item = _yaml_extension_item(source, "pymdownx.arithmatex")
    assert item is not None
    start, end = item
    region = source[start:end]
    generic = re.search(r"(?m)^[ \t]+generic:[ \t]*(?:true|false)[ \t]*$", region)
    if generic:
        absolute_start = start + generic.start()
        absolute_end = start + generic.end()
        indent_match = re.match(r"[ \t]+", generic.group())
        assert indent_match is not None
        indent = indent_match.group()
        return source[:absolute_start] + f"{indent}generic: true" + source[absolute_end:]
    header_end = source.find("\n", start) + 1
    item_indent_match = re.match(r"[ \t]*", source[start:])
    assert item_indent_match is not None
    item_indent = item_indent_match.group()
    block = _yaml_block(source, "markdown_extensions")
    assert block is not None
    style, _indent = _yaml_extension_layout(source, block)
    setting_indent = item_indent + ("    " if style == "sequence" else "  ")
    return source[:header_end] + f"{setting_indent}generic: true\n" + source[header_end:]


def _yaml_add_extension_string(source: str, name: str, key: str, value: str) -> str:
    """Add one missing string setting to a normal indented extension item."""
    item = _yaml_extension_item(source, name)
    if item is None:
        raise AdoptError(
            f"{name} uses a YAML form prodockit cannot update safely; "
            "write it as an indented mapping and rerun"
        )
    start, end = item
    if re.search(rf"(?m)^[ \t]+{re.escape(key)}:[ \t]*", source[start:end]):
        return source
    header_end = source.find("\n", start) + 1
    item_indent_match = re.match(r"[ \t]*", source[start:])
    assert item_indent_match is not None
    block = _yaml_block(source, "markdown_extensions")
    assert block is not None
    style, _indent = _yaml_extension_layout(source, block)
    setting_indent = item_indent_match.group() + ("    " if style == "sequence" else "  ")
    return source[:header_end] + f"{setting_indent}{key}: {value}\n" + source[header_end:]


def _yaml_ensure_tree_icons(source: str, parsed: dict[str, Any]) -> str:
    """Materialise the icon renderer required by prodockit.tree."""
    configured = _extensions(parsed)
    existing = configured.get(TREE_ICON_EXTENSION)
    if not isinstance(existing, Mapping) and TREE_ICON_EXTENSION in configured:
        raise AdoptError(
            f"the configured {TREE_ICON_EXTENSION} settings must be an indented mapping"
        )

    lines = tuple(f"{key}: {value}" for key, value in TREE_ICON_SETTINGS.items())
    source = _yaml_add_extension(source, TREE_ICON_EXTENSION, lines)
    for key, value in TREE_ICON_SETTINGS.items():
        if not isinstance(existing, Mapping) or key not in existing:
            source = _yaml_add_extension_string(source, TREE_ICON_EXTENSION, key, str(value))
    return source


def _yaml_ensure_mermaid(source: str) -> str:
    configured = _yaml_block(source, "markdown_extensions")
    existing_region = source[configured[0] : configured[1]] if configured else ""
    if "name: mermaid" in existing_region:
        return source
    source = _yaml_add_extension(source, "pymdownx.superfences")
    block = _yaml_block(source, "markdown_extensions")
    if block is None:  # pragma: no cover - _yaml_add_extension creates it
        raise AdoptError("could not locate markdown_extensions after adding superfences")
    style, indent = _yaml_extension_layout(source, block)
    header = re.escape(indent + ("- " if style == "sequence" else "") + "pymdownx.superfences")
    if style == "sequence":
        pattern = re.compile(
            rf"(?m)^(?P<header>{header})(?::[ \t]*(?:null|~|\{{\}})?)?[ \t]*$"
        )
    else:
        pattern = re.compile(
            rf"(?m)^(?P<header>{header}):[ \t]*(?:null|~|\{{\}})?[ \t]*$"
        )
    block_start, block_end = block
    region, _replacements = pattern.subn(
        r"\g<header>:", source[block_start:block_end], count=1
    )
    source = source[:block_start] + region + source[block_end:]
    item = _yaml_extension_item(source, "pymdownx.superfences")
    if item is None:
        raise AdoptError(
            "pymdownx.superfences uses a YAML form prodockit cannot update safely; "
            "write it as an indented mapping and rerun"
        )
    start, end = item
    region = source[start:end]
    item_indent_match = re.match(r"[ \t]*", source[start:])
    assert item_indent_match is not None
    item_indent = item_indent_match.group()
    block = _yaml_block(source, "markdown_extensions")
    assert block is not None
    style, _indent = _yaml_extension_layout(source, block)
    setting_indent = item_indent + ("    " if style == "sequence" else "  ")
    custom = re.search(rf"(?m)^{re.escape(setting_indent)}custom_fences:[ \t]*$", region)
    fence = (
        f"{setting_indent}  - name: mermaid\n"
        f"{setting_indent}    class: mermaid\n"
        f"{setting_indent}    format: "
        "!!python/name:pymdownx.superfences.fence_code_format\n"
    )
    if custom:
        insert = start + custom.end()
        return source[:insert] + "\n" + fence.rstrip("\n") + source[insert:]
    header_end = source.find("\n", start) + 1
    return source[:header_end] + f"{setting_indent}custom_fences:\n" + fence + source[header_end:]


def _planned_yaml_config(
    path: Path,
    source: str,
    parsed: dict[str, Any],
    options: AdoptOptions,
) -> str:
    if "markdown_extensions" not in parsed:
        source = _seed_yaml_markdown_defaults(source)
        parsed = yaml.load(source, Loader=_MarkdownConfigLoader)
    configured = _extensions(parsed)
    for name in CORE_EXTENSIONS:
        if name not in configured:
            source = _yaml_add_extension(source, name)
    source = _yaml_ensure_tree_icons(source, parsed)
    source = _yaml_add_top_list_value(
        source,
        "extra_css",
        "stylesheets/pdk.css",
        prepend=True,
    )
    if options.mermaid:
        source = _yaml_ensure_mermaid(source)
    if options.maths:
        source = _yaml_ensure_arithmatex(source)
        source = _yaml_add_top_list_value(source, "extra_javascript", "javascripts/mathjax.js")
        source = _yaml_add_top_list_value(
            source,
            "extra_javascript",
            "javascripts/vendor/mathjax/tex-svg-full.js",
        )
    try:
        yaml.load(source, Loader=_MarkdownConfigLoader)
    except yaml.YAMLError as error:  # pragma: no cover - defensive transaction guard
        raise AdoptError(f"the planned {path.name} would be invalid: {error}") from error
    return source


def ensure_stylesheet(root: Path) -> Path:
    _config_path, _source, parsed = _config(root)
    path = _stylesheet_path(root, parsed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resource_bytes("pdk.css"))
    return path


def _tool_files_ok(root: Path, component: str) -> bool:
    return all((root / "tools" / component / name).is_file() for name in COMPONENT_FILES[component])


def _tool_installed(root: Path, component: str) -> bool:
    if not _tool_files_ok(root, component):
        return False
    if component == "mermaid":
        bin_dir = root / "tools" / component / "node_modules" / ".bin"
        return (bin_dir / "mmdc").is_file() or (bin_dir / "mmdc.cmd").is_file()
    return (
        root / "tools" / "mathjax" / "node_modules" / "mathjax-full" / "es5" / "tex-svg-full.js"
    ).is_file() and (root / "docs" / "javascripts" / "mathjax.js").is_file()


def ensure_tools(root: Path, options: AdoptOptions) -> list[Path]:
    components = tuple(
        name
        for name, selected in (("mermaid", options.mermaid), ("mathjax", options.maths))
        if selected
    )
    if not components:
        return []
    result = init_tools(root / "tools", components=components)
    ignore = root / ".gitignore"
    current = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    additions = [f"tools/{name}/node_modules/" for name in components]
    missing = [line for line in additions if line not in current.splitlines()]
    if missing:
        lead = "" if not current or current.endswith("\n") else "\n"
        ignore.write_text(
            f"{current}{lead}\n# Installed by `prodockit adopt`\n" + "\n".join(missing) + "\n",
            encoding="utf-8",
        )
    return [*result.written, *([ignore] if missing else [])]


def install_tool(root: Path, component: str) -> list[Path]:
    """Install one selected Node renderer after writing its scaffold."""
    if component not in COMPONENT_FILES:
        raise AdoptError(f"unknown optional renderer: {component}")
    npm = shutil.which("npm")
    if npm is None:
        raise AdoptError(
            f"{component} was selected but npm is not available. Install Node.js, "
            "then rerun `prodockit adopt --apply`; no editor or Git setup is required."
        )
    options = AdoptOptions(mermaid=component == "mermaid", maths=component == "mathjax")
    written = ensure_tools(root, options)
    # On Windows npm is a command shim named npm.cmd. Passing the path found
    # by shutil avoids depending on PATHEXT handling inside subprocess.
    tool_root = root / "tools" / component
    # New scaffolds contain prodockit's canonical lockfile, so npm can reuse
    # its download cache without resolving the dependency graph again.  Keep
    # the fallback for a project whose author supplied a custom package.json
    # without a matching lockfile; init_tools deliberately does not pair that
    # manifest with prodockit's unrelated lock.
    command = [
        npm,
        "ci" if (tool_root / "package-lock.json").is_file() else "install",
        "--no-audit",
        "--no-fund",
        "--prefer-offline",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=tool_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AdoptError(f"could not install {component}: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AdoptError(f"npm could not install {component}: {detail}")
    lock = root / "tools" / component / "package-lock.json"
    if lock.is_file() and lock not in written:
        written.append(lock)
    if component == "mathjax":
        try:
            installed = install_mathjax(root)
        except MathJaxError as error:  # pragma: no cover - npm success without its declared package
            raise AdoptError(str(error)) from error
        written.extend((installed.config, installed.bundle))
    return written


def assess(root: Path, options: AdoptOptions) -> list[Step]:
    try:
        config_path, _source, parsed = _config(root)
        config_status = ("ok", f"{config_path.name} is valid")
    except AdoptError as error:
        return [Step("project", "Assess", "Existing documentation project", "wrong", str(error))]

    config_error = ""
    try:
        _planned_zensical_config(root, options)
    except AdoptError as error:
        config_error = str(error)

    requirement = _requirements_path(root)
    requirement_detail = (
        f"{requirement.name} records a prodockit version floor"
        if _requirement_ok(root)
        else f"add prodockit>={__version__} to {requirement.name}"
    )
    configured = _extensions(parsed)
    missing = [name for name in CORE_EXTENSIONS if name not in configured]
    style_path = _stylesheet_path(root, parsed)
    core_ok = (
        not config_error
        and not missing
        and _tree_icons_ok(parsed)
        and _style_ok(root, parsed)
        and style_path.is_file()
    )
    core_detail = (
        config_error
        or (
            "all standard extensions and the shared stylesheet are configured"
            if core_ok
            else "add the standard extensions and shared website styles"
        )
    )
    mermaid_ok = _tool_installed(root, "mermaid") and "pymdownx.superfences" in configured
    maths_ok = _tool_installed(root, "mathjax") and "pymdownx.arithmatex" in configured
    ready_to_build = (
        _requirement_ok(root)
        and core_ok
        and (not options.mermaid or mermaid_ok)
        and (not options.maths or maths_ok)
    )
    return [
        Step(
            "project",
            "Assess",
            "Existing documentation project",
            config_status[0],
            config_status[1],
        ),
        Step(
            "environment",
            "Assess",
            "Active project environment",
            "ok" if _in_venv() else "wrong",
            (
                f"using {sys.prefix}"
                if _in_venv()
                else "activate the project's virtual environment first"
            ),
        ),
        Step(
            "dependency",
            "Integrate",
            "Prodockit dependency",
            "ok" if _requirement_ok(root) else "missing",
            requirement_detail,
        ),
        Step(
            "core",
            "Integrate",
            "Standard authoring components",
            "wrong" if config_error else ("ok" if core_ok else "missing"),
            core_detail,
        ),
        Step(
            "mermaid",
            "Optional renderers",
            "Mermaid diagrams",
            "ok" if mermaid_ok else "missing",
            "selected" if options.mermaid else "not selected; Node.js is not needed for Mermaid",
            selected=options.mermaid,
        ),
        Step(
            "maths",
            "Optional renderers",
            "Mathematical notation",
            "ok" if maths_ok else "missing",
            "selected" if options.maths else "not selected; MathJax is not installed",
            selected=options.maths,
        ),
        Step(
            "verify",
            "Verify",
            "Ready for local build",
            "ok" if ready_to_build else "wait",
            (
                "selected components are configured; run zensical build --clean to verify the site"
                if ready_to_build
                else "apply the selected integration stages before running zensical build --clean"
            ),
        ),
    ]


def apply_step(root: Path, options: AdoptOptions, step_id: str) -> list[Path]:
    if step_id == "dependency":
        return [ensure_requirement(root)]
    if step_id == "core":
        return [
            ensure_zensical_config(root, options),
            ensure_stylesheet(root),
            write_manifest(root, options),
        ]
    if step_id == "mermaid":
        return [
            ensure_zensical_config(root, options),
            write_manifest(root, options),
            *install_tool(root, "mermaid"),
        ]
    if step_id == "maths":
        return [
            ensure_zensical_config(root, options),
            write_manifest(root, options),
            *install_tool(root, "mathjax"),
        ]
    return []


__all__ = [
    "CORE_EXTENSIONS",
    "MANIFEST",
    "STYLESHEET",
    "AdoptError",
    "AdoptOptions",
    "Step",
    "apply_step",
    "assess",
    "ensure_requirement",
    "ensure_stylesheet",
    "ensure_tools",
    "ensure_zensical_config",
    "install_tool",
    "load_manifest",
    "write_manifest",
]

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Adopt prodockit in an existing Zensical project.

This is deliberately project-scoped.  ``prodockit bootstrap`` prepares a machine and a
repository; adoption starts after that boundary, with an author who already
has Git, SSH, an editor and an existing documentation site. It changes the
active project environment and files below the project root, and never commits
or pushes them.

The module contains the file operations separately from Click presentation so
they can be tested without a terminal or network access.  Mermaid and maths
are independent capabilities: neither is selected by default and neither
toolchain is written into a project which did not ask for it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomlkit
import yaml  # type: ignore[import-untyped, unused-ignore]
from packaging.version import InvalidVersion, Version

from prodockit import __version__, adopt_renderers, adopt_settings, adopt_workflow
from prodockit import toolchain as supported_toolchain
from prodockit._zensical_defaults import DOCUMENTED_MARKDOWN_DEFAULTS
from prodockit.csl import (
    CSL_STYLE_URL,
    DEFAULT_CSL_STYLE,
    CslError,
)
from prodockit.csl import (
    cache_path as csl_cache_path,
)
from prodockit.csl import (
    install as install_csl,
)
from prodockit.init_tools import COMPONENT_FILES
from prodockit.mathjax import MathJaxError, install_mathjax
from prodockit.pins import TESTED_VERSIONS
from prodockit.renderer_health import probe_mathjax, probe_mermaid
from prodockit.renderer_resilience import DEFAULT_RETRY_DELAYS, RetryReporter, run_npm_with_retries
from prodockit.settings import EXTRA_SETTINGS
from prodockit.shared_files import resource_bytes, same_text_content

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


MANIFEST = ".prodockit-components.toml"
STYLESHEET = Path("docs/stylesheets/pdk.css")
MANAGED_STYLESHEETS = ("pdk.css", "pdk-pdf.css")
MANAGED_JAVASCRIPTS = ("pdk.js",)
USER_MANAGED_JAVASCRIPTS = {"extra.js": ""}
USER_MANAGED_STYLESHEETS = {
    "extra.css": "/* Add project-specific website and PDF styles below this line. */\n",
    "print.css": "/* Add project-specific PDF-only styles below this line. */\n",
}
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
    "prodockit.glossary",
    "prodockit.bibliography",
    "prodockit.tables",
    "prodockit.steps",
    "prodockit.tree",
    "prodockit.index",
    "pymdownx.blocks.caption",
)

CAPTION_TYPES = (
    {"name": "caption"},
    {"name": "figure-caption", "prefix": "{}.", "classes": "prodockit-figure-caption"},
    {"name": "table-caption", "prefix": "{}.", "classes": "prodockit-table-caption"},
)

# These extensions provide alternative citation-definition sources. The
# template uses bibliography files, while an existing project may deliberately
# define citations inline. Adopt must preserve that choice rather than enable
# both implementations simply to satisfy a generic core-components check.
CITATION_EXTENSIONS = (
    "prodockit.bibliography",
    "prodockit.citations",
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
    template_snapshot: adopt_settings.Snapshot | None = field(
        default=None, repr=False, compare=False
    )


@dataclass(frozen=True)
class AdoptChoiceResolution:
    """Component choices and the project-local evidence they came from."""

    options: AdoptOptions
    source: str
    saved: bool


@dataclass(frozen=True)
class Step:
    id: str
    phase: str
    summary: str
    status: str
    detail: str
    selected: bool = True
    commands: tuple[tuple[str, ...], ...] = ()
    files: tuple[Path, ...] = ()
    plan_lines: tuple[str, ...] = ()

    @property
    def needs_work(self) -> bool:
        return self.selected and self.status not in {"ok", "wait", "warn"}


def load_manifest(root: Path) -> AdoptOptions:
    path = root / MANIFEST
    if not path.is_file():
        return AdoptOptions()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AdoptError(f"could not read {path}: {error}") from error
    components = data.get("components", {})
    if not isinstance(components, dict) or any(
        not isinstance(components.get(name, False), bool) for name in ("mermaid", "maths")
    ):
        raise AdoptError(
            f"{path}: [components] mermaid and maths must be TOML true or false, not quoted text"
        )
    return AdoptOptions(
        mermaid=bool(components.get("mermaid", False)),
        maths=bool(components.get("maths", False)),
    )


def resolve_options(root: Path) -> AdoptChoiceResolution:
    """Resolve saved choices, installed renderers, then neutral defaults.

    A Zensical starter may contain Mermaid or MathJax-capable configuration
    without the author having selected either renderer for Prodockit. Only the
    project-owned manifest, ``adopt --configure``, or explicit command-line
    flags may opt in; existing project installations are also retained.
    Template projects ship the manifest with both enabled.
    """
    path = root / MANIFEST
    if path.is_file():
        return AdoptChoiceResolution(load_manifest(root), str(path), True)
    # Starter extension declarations describe capability, not installation.
    # A scaffold remains evidence even when an interrupted install has left
    # node_modules incomplete. Saved and explicit choices take precedence.
    detected = {}
    for option, component in (("mermaid", "mermaid"), ("maths", "mathjax")):
        directory = root / "tools" / component
        detected[option] = any(
            (directory / name).exists()
            for name in ("package.json", "package-lock.json", "node_modules")
        )
    options = AdoptOptions(mermaid=detected["mermaid"], maths=detected["maths"])
    return AdoptChoiceResolution(
        options,
        "detected project renderer installation" if any(detected.values()) else "defaults",
        False,
    )


def manifest_source(options: AdoptOptions) -> str:
    """Return the commit-safe record of an author's component choices."""
    document = tomlkit.document()
    document.add(tomlkit.comment("Selected by `prodockit adopt`; safe to commit."))
    document["schema"] = 1
    document["components"] = {"mermaid": options.mermaid, "maths": options.maths}
    return tomlkit.dumps(document)


def write_manifest(root: Path, options: AdoptOptions) -> Path:
    from prodockit.config_integrity import check_project

    check_project(root, AdoptError)
    path = root / MANIFEST
    _atomic_write(path, manifest_source(options).encode("utf-8"))
    return path


def _atomic_write(path: Path, content: bytes) -> None:
    """Replace one validated file without exposing a truncated intermediate.

    Keep identical files untouched on a rerun. This is per-file safety, not
    rollback of package installations or an entire adoption activity.
    """
    from prodockit.config_integrity import before_write

    before_write(path, content, AdoptError)
    destination = path.resolve()
    if destination.is_file() and destination.read_bytes() == content:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            shutil.copymode(destination, temporary)
        os.replace(temporary, destination)
    except OSError as error:
        raise AdoptError(
            f"could not safely update {path}: {error}; rerun Adopt to resume"
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class _MarkdownConfigLoader(yaml.SafeLoader):  # type: ignore[misc, unused-ignore]
    """Safe YAML loader which treats MkDocs' Python-name tags as text.

    ``pymdownx.superfences`` commonly uses ``!!python/name:...`` for a
    formatter. Constructing arbitrary Python objects from a project file would
    be inappropriate here; the suffix is enough for configuration inventory.
    """


class _PythonName(str):
    """A safely inventoried ``!!python/name`` reference from YAML."""


def _python_name(
    _loader: _MarkdownConfigLoader,
    suffix: str,
    _node: yaml.Node,
) -> str:
    return _PythonName(suffix)


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
            "no Zensical configuration is here. Run this command from "
            "the directory containing zensical.toml, zensical.yml, zensical.yaml, "
            "mkdocs.yml or mkdocs.yaml used as a Zensical configuration."
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


def _interpreter_problem(root: Path) -> str | None:
    """Refuse mutation when a project's .venv mixes Python launchers."""
    from prodockit.environment import project_environment_problem

    problem = project_environment_problem(root)
    if problem:
        return problem
    environment = root.resolve() / ".venv"
    if not environment.is_dir():
        return None
    try:
        from prodockit.diagnostics import _interpreter_consistency_check, same_path

        if not same_path(sys.prefix, str(environment)):
            return None
        check = _interpreter_consistency_check(root.resolve())
    except (OSError, RuntimeError, ValueError) as error:
        return f"could not verify the active Python launchers: {error}"
    if check.status == "pass":
        return None
    detail = "; ".join(check.details)
    return (
        f"{check.summary}: {detail}. Run `pdk diag --dry-run --apply-check "
        "environment.interpreters` before Adopt"
    )


def _requirements_path(root: Path) -> Path:
    return next(
        (root / relative for relative in REQUIREMENT_CANDIDATES if (root / relative).is_file()),
        root / REQUIREMENT_CANDIDATES[0],
    )


def _requirement_ok(root: Path) -> bool:
    path = _requirements_path(root)
    if not path.is_file():
        return False
    match = re.search(
        r"(?im)^\s*prodockit(?:\[[^]]+\])?\s*>=\s*([^\s;#]+)",
        path.read_text(encoding="utf-8"),
    )
    if match is None:
        return False
    try:
        return Version(match.group(1)) >= Version(__version__)
    except InvalidVersion:
        return False


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
        mapped: dict[str, Any] = {}
        for name, options in value.items():
            if name == "pymdownx" and isinstance(options, Mapping):
                for child, child_options in options.items():
                    if child == "blocks" and isinstance(child_options, Mapping):
                        for block, block_options in child_options.items():
                            mapped[f"pymdownx.blocks.{block}"] = block_options
                    else:
                        mapped[f"pymdownx.{child}"] = child_options
            elif name == "prodockit" and isinstance(options, Mapping):
                for child, child_options in options.items():
                    mapped[f"prodockit.{child}"] = child_options
            elif name == "zensical" and isinstance(options, Mapping):
                extensions = options.get("extensions")
                if isinstance(extensions, Mapping):
                    for child, child_options in extensions.items():
                        mapped[f"zensical.extensions.{child}"] = child_options
                else:
                    mapped[name] = options
            else:
                mapped[str(name)] = options
        return mapped
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
    from prodockit.adopt_toml import inline

    return inline(_serializable_default(value)).as_string()


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


def _stylesheet_dir(root: Path, parsed: dict[str, Any]) -> Path:
    return root / _docs_dir(parsed) / "stylesheets"


def _stylesheet_path(root: Path, parsed: dict[str, Any]) -> Path:
    """Return the original public pdk.css path for compatibility."""
    return _stylesheet_dir(root, parsed) / "pdk.css"


def _stylesheet_paths(root: Path, parsed: dict[str, Any]) -> dict[str, Path]:
    directory = _stylesheet_dir(root, parsed)
    return {name: directory / name for name in (*MANAGED_STYLESHEETS, *USER_MANAGED_STYLESHEETS)}


def _javascript_paths(root: Path, parsed: dict[str, Any]) -> dict[str, Path]:
    directory = root / _docs_dir(parsed) / "javascripts"
    return {name: directory / name for name in (*MANAGED_JAVASCRIPTS, *USER_MANAGED_JAVASCRIPTS)}


def _missing_core_extensions(parsed: dict[str, Any]) -> list[str]:
    configured = _extensions(parsed)
    missing = [name for name in CORE_EXTENSIONS if name not in configured]
    if any(name in configured for name in CITATION_EXTENSIONS):
        missing = [name for name in missing if name != "prodockit.bibliography"]
    return missing


def _core_ok(parsed: dict[str, Any]) -> bool:
    return not _missing_core_extensions(parsed) and _tree_icons_ok(parsed)


def _tree_icons_ok(parsed: dict[str, Any], *, require_python_names: bool = False) -> bool:
    configured = _extensions(parsed)
    settings = configured.get(TREE_ICON_EXTENSION)
    return isinstance(settings, Mapping) and all(
        key in settings and (not require_python_names or isinstance(settings[key], _PythonName))
        for key in TREE_ICON_SETTINGS
    )


def _style_ok(root: Path, parsed: dict[str, Any]) -> bool:
    project = parsed.get("project", parsed)
    extra_css = project.get("extra_css", []) if isinstance(project, dict) else []
    extra_javascript = project.get("extra_javascript", []) if isinstance(project, dict) else []
    extra = project.get("extra", {}) if isinstance(project, dict) else {}
    pdf_extra_css = extra.get("pdf_extra_css", []) if isinstance(extra, dict) else []
    styles = _stylesheet_paths(root, parsed)
    scripts = _javascript_paths(root, parsed)
    return (
        all(path.is_file() for path in (*styles.values(), *scripts.values()))
        and all(
            same_text_content(styles[name].read_bytes(), resource_bytes(name))
            for name in MANAGED_STYLESHEETS
        )
        and all(
            same_text_content(scripts[name].read_bytes(), resource_bytes(name))
            for name in MANAGED_JAVASCRIPTS
        )
        and all(
            _asset_is_configured(configured, values)
            for configured, values in (
                ("stylesheets/pdk.css", extra_css),
                ("stylesheets/extra.css", extra_css),
                ("stylesheets/pdk-pdf.css", pdf_extra_css),
                ("stylesheets/print.css", pdf_extra_css),
                ("javascripts/pdk.js", extra_javascript),
                ("javascripts/extra.js", extra_javascript),
            )
        )
    )


def _csl_activity(root: Path, parsed: dict[str, Any], *, offline: bool) -> Step:
    """Describe the configured bibliography style without guessing its source."""
    bibliography = _extensions(parsed).get("prodockit.bibliography")
    configured = bibliography.get("csl_style") if isinstance(bibliography, Mapping) else None
    if not configured:
        return Step(
            "csl",
            "Integrate",
            "Citation style",
            "ok",
            "no external citation style is configured",
        )

    relative = Path(str(configured))
    target = relative if relative.is_absolute() else root / relative
    if target.is_file():
        return Step(
            "csl",
            "Integrate",
            "Citation style",
            "ok",
            f"preserve the existing {configured}",
            files=(target,),
        )

    try:
        safe_relative = not relative.is_absolute() and target.resolve().is_relative_to(
            root.resolve()
        )
    except OSError:
        safe_relative = False
    if relative.name != DEFAULT_CSL_STYLE or not safe_relative:
        return Step(
            "csl",
            "Integrate",
            "Citation style",
            "wrong",
            f"{configured} is missing. Adopt does not know a trusted source for this custom "
            "style; download the intended CSL file to that configured path, then rerun Adopt",
            files=(target,),
        )

    source = f"the validated cache at {csl_cache_path()}" if offline else CSL_STYLE_URL
    return Step(
        "csl",
        "Integrate",
        "Citation style",
        "missing",
        f"install {configured} from {source}",
        files=(target,),
    )


def _asset_reference(value: object) -> str | None:
    """Return an asset path without browser cache keys or fragments."""
    if not isinstance(value, str):
        return None
    return re.split(r"[?#]", value, maxsplit=1)[0]


def _asset_is_configured(expected: str, values: object) -> bool:
    """Treat cache-versioned and plain references to one asset as equivalent."""
    if not isinstance(values, list):
        return False
    return any(_asset_reference(value) == expected for value in values)


def _text_contains_asset_reference(source: str, rendered: str) -> bool:
    expected = rendered.strip("\"'")
    return bool(
        re.search(
            rf"(?<![\w./-]){re.escape(expected)}(?:[?#][^\"'\s,\]]*)?"
            r"(?=[\"'\s,\]])",
            source,
        )
    )


def _planned_zensical_config(root: Path, options: AdoptOptions) -> tuple[Path, str]:
    """Plan with TOML Kit, then independently validate with tomllib."""
    path, source, parsed = _config(root)
    if path.suffix != ".toml":
        return path, _planned_yaml_config(path, source, parsed, options)
    from prodockit.adopt_toml import update

    try:
        planned = update(source, options)
        if options.template_snapshot is not None:
            planned = adopt_settings.review(
                root, planned, options.template_snapshot, original=source
            ).source
        tomllib.loads(planned)
    except (ValueError, TypeError) as error:
        raise AdoptError(f"could not safely update {path.name}: {error}") from error
    return path, planned


def ensure_zensical_config(root: Path, options: AdoptOptions) -> Path:
    _, original, _ = _config(root)
    path, source = _planned_zensical_config(root, options)
    reviewed = None
    if path.suffix == ".toml" and options.template_snapshot is not None:
        try:
            reviewed = adopt_settings.review(
                root, source, options.template_snapshot, original=original
            )
        except adopt_settings.SettingsError as error:
            raise AdoptError(str(error)) from error
        if options.template_snapshot.identity.startswith("github:"):
            _atomic_write(
                adopt_settings.cache_path(), adopt_settings.cache_content(options.template_snapshot)
            )
    _atomic_write(path, source.encode("utf-8"))
    if reviewed is not None and (reviewed.count or not (root / adopt_settings.LEDGER).exists()):
        # Only mark work processed after the valid configuration is in place.
        # If this write fails, generated comment markers make a retry safe.
        _atomic_write(root / adopt_settings.LEDGER, reviewed.ledger.encode("utf-8"))
    return path


def _missing_caption_types(parsed: dict[str, Any]) -> list[dict[str, str]]:
    settings = _extensions(parsed).get("pymdownx.blocks.caption", {})
    types = settings.get("types", []) if isinstance(settings, Mapping) else []
    if not isinstance(types, list):
        raise AdoptError("pymdownx.blocks.caption.types must be a list")
    existing = {item.get("name"): item for item in types if isinstance(item, Mapping)}
    missing = []
    for required in CAPTION_TYPES:
        current = existing.get(required["name"])
        if current is None:
            missing.append(required)
        elif any(current.get(key) != value for key, value in required.items()):
            raise AdoptError(
                f"caption type {required['name']} conflicts with Prodockit's required "
                "numbering/classes; preserve your custom type under a different name"
            )
    return missing


def _extra_defaults_missing(parsed: dict[str, Any]) -> dict[str, Any]:
    project = parsed.get("project", parsed)
    extra = project.get("extra", {})
    # Context-dependent paths and optional renderer settings remain inferred
    # at runtime. Existing author values always win.
    return {
        setting.key: setting.default
        for setting in EXTRA_SETTINGS
        if isinstance(setting.default, (str, bool)) and setting.key not in extra
    }


def _ensure_authoring_settings(source: str, parsed: dict[str, Any]) -> str:
    """Materialise reusable YAML settings; TOML uses adopt_toml."""
    captions = _missing_caption_types(parsed)
    source = _yaml_add_extension(source, "pymdownx.blocks.caption", ("types: []",))
    item = _yaml_extension_item(source, "pymdownx.blocks.caption")
    if captions:
        if item is None:
            raise AdoptError("caption settings use an unsupported YAML layout")
        start, end = item
        block = _yaml_block(source, "markdown_extensions")
        assert block is not None
        style, indent = _yaml_extension_layout(source, block)
        settings_indent = indent + ("    " if style == "sequence" else "  ")
        types = re.search(rf"(?m)^{re.escape(settings_indent)}types:[ \t]*$", source[start:end])
        empty_types = re.search(
            rf"(?m)^{re.escape(settings_indent)}types:[ \t]*\[\][ \t]*$", source[start:end]
        )
        if empty_types:
            pos = start + empty_types.start()
            stop = start + empty_types.end()
            addition = f"{settings_indent}types:" + "".join(
                f"\n{settings_indent}  - {json.dumps(t)}" for t in captions
            )
            source = source[:pos] + addition + source[stop:]
            captions = []
        elif types:
            pos = start + types.end()
            addition = "".join(f"\n{settings_indent}  - {json.dumps(t)}" for t in captions)
        else:
            if "types:" in source[start:end]:
                raise AdoptError("write caption types as a YAML block list before adopting")
            pos = source.find("\n", start)
            addition = f"\n{settings_indent}types:" + "".join(
                f"\n{settings_indent}  - {json.dumps(t)}" for t in captions
            )
        if captions:
            source = source[:pos] + addition + source[pos:]
    missing = _extra_defaults_missing(parsed)
    if missing:
        block = _yaml_block(source, "extra")
        if block is None:
            if re.search(r"(?m)^extra:", source):
                raise AdoptError("write extra as a YAML block mapping before adopting")
            source = source.rstrip() + "\n\nextra:\n"
            block = _yaml_block(source, "extra")
        assert block is not None
        pos = len(source[: block[1]].rstrip())
        addition = "".join(f"\n  {key}: {json.dumps(value)}" for key, value in missing.items())
        source = source[:pos] + addition + source[pos:]
    return source


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
    asset: bool = False,
) -> str:
    located = _yaml_block(source, key)
    if located is None:
        inline = re.search(rf"(?m)^{re.escape(key)}:[ \t]*\[(?P<body>[^\]\n]*)\][ \t]*$", source)
        if inline:
            if (asset and _text_contains_asset_reference(inline.group("body"), rendered)) or (
                not asset and rendered.strip("\"'") in inline.group("body")
            ):
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
    if (asset and _text_contains_asset_reference(region, rendered)) or (
        not asset and rendered.strip("\"'") in region
    ):
        return source
    header_end = source.find("\n", start) + 1
    if header_end <= 0:
        header_end = end
    indent = _yaml_list_indent(source, located)
    item = f"{indent}- {rendered}\n"
    if prepend:
        return source[:header_end] + item + source[header_end:]
    return source[:end] + item + source[end:]


def _yaml_add_nested_list_value(
    source: str,
    parent: str,
    key: str,
    rendered: str,
    *,
    prepend: bool = False,
    asset: bool = False,
) -> str:
    """Add an item to a list below one top-level YAML mapping."""
    parent_block = _yaml_block(source, parent)
    if parent_block is None:
        if re.search(rf"(?m)^{re.escape(parent)}:", source):
            raise AdoptError(
                f"{parent} uses a YAML form prodockit cannot update safely; "
                "write it as an indented mapping and rerun"
            )
        lead = "" if source.endswith("\n") else "\n"
        return f"{source}{lead}\n{parent}:\n  {key}:\n    - {rendered}\n"

    parent_start, parent_end = parent_block
    region = source[parent_start:parent_end]
    child = re.search(
        rf"(?m)^(?P<indent>[ \t]+){re.escape(key)}:[ \t]*(?P<inline>\[[^\]\n]*\])?[ \t]*$",
        region,
    )
    if child is None:
        if re.search(rf"(?m)^[ \t]+{re.escape(key)}:", region):
            raise AdoptError(
                f"{parent}.{key} uses a YAML form prodockit cannot update safely; "
                "write it as a block or inline list and rerun"
            )
        header_end = source.find("\n", parent_start, parent_end) + 1
        return source[:header_end] + f"  {key}:\n    - {rendered}\n" + source[header_end:]

    absolute_start = parent_start + child.start()
    absolute_end = parent_start + child.end()
    inline = child.group("inline")
    if inline is not None:
        body_start = parent_start + child.start("inline") + 1
        body_end = parent_start + child.end("inline") - 1
        body = source[body_start:body_end]
        if (asset and _text_contains_asset_reference(body, rendered)) or (
            not asset and rendered.strip("\"'") in body
        ):
            return source
        separator = ", " if body.strip() else ""
        if prepend:
            return source[:body_start] + rendered + separator + source[body_start:]
        return source[:body_end] + separator + rendered + source[body_end:]

    child_indent = child.group("indent")
    following = re.search(
        rf"(?m)^(?:[ \t]{{0,{len(child_indent)}}}\S|{re.escape(child_indent)}[^ \t-][^:]*:)",
        source[absolute_end:parent_end],
    )
    child_end = absolute_end + following.start() if following else parent_end
    child_region = source[absolute_start:child_end]
    if (asset and _text_contains_asset_reference(child_region, rendered)) or (
        not asset and rendered.strip("\"'") in child_region
    ):
        return source
    header_end = source.find("\n", absolute_start, child_end) + 1
    item = re.search(r"(?m)^(?P<indent>[ \t]*)- ", child_region)
    item_indent = item.group("indent") if item else child_indent + "  "
    if prepend:
        return source[:header_end] + f"{item_indent}- {rendered}\n" + source[header_end:]
    return source[:child_end] + f"{item_indent}- {rendered}\n" + source[child_end:]


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


def _yaml_ensure_extension_python_name(
    source: str,
    name: str,
    key: str,
    default: str,
) -> str:
    """Add or repair one callable extension setting without importing it."""
    item = _yaml_extension_item(source, name)
    if item is None:
        raise AdoptError(
            f"{name} uses a YAML form prodockit cannot update safely; "
            "write it as an indented mapping and rerun"
        )
    start, end = item
    pattern = re.compile(
        rf"(?m)^(?P<indent>[ \t]+){re.escape(key)}:[ \t]*"
        rf"(?P<value>[^#\n]*?)(?P<comment>[ \t]+#.*)?$"
    )
    match = pattern.search(source[start:end])
    if match is None:
        return _yaml_add_extension_string(
            source,
            name,
            key,
            f"!!python/name:{default}",
        )
    value = match.group("value").strip()
    if value.startswith("!!python/name:"):
        return source
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", value):
        raise AdoptError(
            f"the configured {name} {key} value cannot be updated safely; "
            "use a !!python/name: callable reference and rerun"
        )
    replacement = (
        f"{match.group('indent')}{key}: !!python/name:{value}{match.group('comment') or ''}"
    )
    absolute_start = start + match.start()
    absolute_end = start + match.end()
    return source[:absolute_start] + replacement + source[absolute_end:]


def _yaml_ensure_tree_icons(source: str, parsed: dict[str, Any]) -> str:
    """Materialise the icon renderer required by prodockit.tree."""
    configured = _extensions(parsed)
    existing = configured.get(TREE_ICON_EXTENSION)
    if not isinstance(existing, Mapping) and TREE_ICON_EXTENSION in configured:
        raise AdoptError(
            f"the configured {TREE_ICON_EXTENSION} settings must be an indented mapping"
        )

    lines = tuple(f"{key}: !!python/name:{value}" for key, value in TREE_ICON_SETTINGS.items())
    source = _yaml_add_extension(source, TREE_ICON_EXTENSION, lines)
    for key, value in TREE_ICON_SETTINGS.items():
        source = _yaml_ensure_extension_python_name(
            source,
            TREE_ICON_EXTENSION,
            key,
            str(value),
        )
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
        pattern = re.compile(rf"(?m)^(?P<header>{header})(?::[ \t]*(?:null|~|\{{\}})?)?[ \t]*$")
    else:
        pattern = re.compile(rf"(?m)^(?P<header>{header}):[ \t]*(?:null|~|\{{\}})?[ \t]*$")
    block_start, block_end = block
    region, _replacements = pattern.subn(r"\g<header>:", source[block_start:block_end], count=1)
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
    for name in _missing_core_extensions(parsed):
        source = _yaml_add_extension(source, name)
    source = _yaml_ensure_tree_icons(source, parsed)
    source = _ensure_authoring_settings(source, parsed)
    source = _yaml_add_top_list_value(
        source,
        "extra_css",
        "stylesheets/pdk.css",
        prepend=True,
        asset=True,
    )
    source = _yaml_add_top_list_value(
        source,
        "extra_css",
        "stylesheets/extra.css",
        asset=True,
    )
    source = _yaml_add_nested_list_value(
        source,
        "extra",
        "pdf_extra_css",
        "stylesheets/pdk-pdf.css",
        prepend=True,
        asset=True,
    )
    source = _yaml_add_nested_list_value(
        source,
        "extra",
        "pdf_extra_css",
        "stylesheets/print.css",
        asset=True,
    )
    if options.mermaid:
        source = _yaml_ensure_mermaid(source)
    if options.maths:
        source = _yaml_ensure_arithmatex(source)
        source = _yaml_add_top_list_value(
            source,
            "extra_javascript",
            "javascripts/vendor/mathjax/tex-svg-full.js",
            prepend=True,
            asset=True,
        )
        source = _yaml_add_top_list_value(
            source,
            "extra_javascript",
            "javascripts/mathjax.js",
            prepend=True,
            asset=True,
        )
    source = _yaml_add_top_list_value(
        source,
        "extra_javascript",
        "javascripts/pdk.js",
        prepend=True,
        asset=True,
    )
    source = _yaml_add_top_list_value(
        source,
        "extra_javascript",
        "javascripts/extra.js",
        asset=True,
    )
    try:
        yaml.load(source, Loader=_MarkdownConfigLoader)
    except yaml.YAMLError as error:  # pragma: no cover - defensive transaction guard
        raise AdoptError(f"the planned {path.name} would be invalid: {error}") from error
    return source


def ensure_stylesheets(root: Path) -> list[Path]:
    """Install managed styles and create missing user-managed styles."""
    _config_path, _source, parsed = _config(root)
    paths = _stylesheet_paths(root, parsed)
    paths["pdk.css"].parent.mkdir(parents=True, exist_ok=True)
    for name in MANAGED_STYLESHEETS:
        _atomic_write(paths[name], resource_bytes(name))
    for name, initial_content in USER_MANAGED_STYLESHEETS.items():
        if not paths[name].exists():
            _atomic_write(paths[name], initial_content.encode("utf-8"))
    return list(paths.values())


def ensure_javascripts(root: Path) -> list[Path]:
    """Install managed scripts and create missing user-managed scripts."""
    _config_path, _source, parsed = _config(root)
    paths = _javascript_paths(root, parsed)
    paths["pdk.js"].parent.mkdir(parents=True, exist_ok=True)
    for name in MANAGED_JAVASCRIPTS:
        _atomic_write(paths[name], resource_bytes(name))
    for name, initial_content in USER_MANAGED_JAVASCRIPTS.items():
        if not paths[name].exists():
            _atomic_write(paths[name], initial_content.encode("utf-8"))
        elif name == "extra.js" and same_text_content(
            paths[name].read_bytes(), resource_bytes("pdk.js")
        ):
            # Older templates put this exact stock behaviour in the author
            # extension point. Move it to managed pdk.js without erasing any
            # file that differs by more than normal line-ending conversion.
            _atomic_write(paths[name], initial_content.encode("utf-8"))
    return list(paths.values())


def ensure_stylesheet(root: Path) -> Path:
    """Install standard assets and return pdk.css for compatibility."""
    ensure_stylesheets(root)
    ensure_javascripts(root)
    return _stylesheet_path(root, _config(root)[2])


def _tool_files_ok(root: Path, component: str) -> bool:
    return all((root / "tools" / component / name).is_file() for name in COMPONENT_FILES[component])


def _mermaid_bin(root: Path) -> Path | None:
    bin_dir = root / "tools" / "mermaid" / "node_modules" / ".bin"
    names = ("mmdc.cmd", "mmdc") if sys.platform == "win32" else ("mmdc",)
    return next(
        (candidate for name in names if (candidate := bin_dir / name).is_file()),
        None,
    )


def _tool_health(
    root: Path,
    component: str,
    *,
    retry_reporter: RetryReporter | None = None,
) -> tuple[bool, str]:
    if not _tool_files_ok(root, component):
        return False, (
            "renderer scaffold is incomplete; restore release files, preserving existing "
            f"files under {adopt_renderers.BACKUPS}"
        )
    try:
        if adopt_renderers.changes(root, component):
            return False, (
                "align renderer files to this Prodockit release; existing files will be "
                f"backed up under {adopt_renderers.BACKUPS}"
            )
    except (OSError, ValueError) as error:
        return False, str(error)
    if component == "mermaid":
        binary = _mermaid_bin(root)
        if binary is None:
            return False, "mmdc executable is missing"
        probe = (
            probe_mermaid(binary, reporter=retry_reporter)
            if retry_reporter is not None
            else probe_mermaid(binary)
        )
        attempts = getattr(probe, "attempts", 1)
        recovered = f" after {attempts} attempts" if attempts > 1 else ""
        expected = adopt_renderers.expected_version(component)
        if probe.ok and probe.version != expected:
            return False, f"align Mermaid CLI {probe.version} to supported {expected}"
        return (
            (True, f"mmdc {probe.version or 'is available'}{recovered}")
            if probe.ok
            else (False, f"mmdc health check failed: {probe.error}")
        )
    docs = root / _docs_dir(_config(root)[2])
    installed = (
        root / "tools" / "mathjax" / "node_modules" / "mathjax-full" / "es5" / "tex-svg-full.js"
    ).is_file() and all(
        path.is_file()
        for path in (
            docs / "javascripts" / "mathjax.js",
            docs / "javascripts" / "vendor" / "mathjax" / "tex-svg-full.js",
            docs / "javascripts" / "vendor" / "mathjax" / "LICENSE",
        )
    )
    if not installed:
        return False, "MathJax inputs are incomplete"
    version = adopt_renderers.installed_version(root, component)
    expected = adopt_renderers.expected_version(component)
    if version != expected:
        return False, f"align MathJax {version or 'unknown version'} to supported {expected}"
    node = shutil.which("node")
    if node is None:
        return False, "node is unavailable for the MathJax renderer"
    probe = probe_mathjax(node, root / "tools" / "mathjax" / "tex2svg.js")
    return (
        (True, "MathJax can render an expression")
        if probe.ok
        else (False, f"MathJax health check failed: {probe.error}")
    )


LOCAL_IGNORE_PATTERNS = (
    ".venv/",
    "__pycache__/",
    "*.py[cod]",
    "/site/",
    "/public/",
    "/docs/site_documentation.pdf",
    "/docs/source_bundle.pdf",
    "/docs/.prodockit-pdf-mermaid/",
    "/.prodockit-adopt-backups/",
)


def _missing_local_ignores(root: Path) -> list[str]:
    path = root / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return [pattern for pattern in LOCAL_IGNORE_PATTERNS if pattern not in lines]


def ensure_local_ignores(root: Path) -> list[Path]:
    missing = _missing_local_ignores(root)
    if not missing:
        return []
    path = root / ".gitignore"
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    _atomic_write(
        path,
        (
            original
            + ("\n" if original and not original.endswith("\n") else "")
            + "\n# Local environments and generated output — added by prodockit adopt\n"
            + "\n".join(missing)
            + "\n"
        ).encode("utf-8"),
    )
    return [path]


def ensure_tools(root: Path, options: AdoptOptions) -> list[Path]:
    components = tuple(
        name
        for name, selected in (("mermaid", options.mermaid), ("mathjax", options.maths))
        if selected
    )
    if not components:
        return []
    written: list[Path] = []
    try:
        for component in components:
            written.extend(adopt_renderers.align(root, component, write=_atomic_write))
    except (OSError, ValueError) as error:
        raise AdoptError(f"cannot align renderer files: {error}") from error
    ignore = root / ".gitignore"
    current = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    additions = [f"tools/{name}/node_modules/" for name in components]
    additions.append("/.prodockit-adopt-backups/")
    missing = [line for line in additions if line not in current.splitlines()]
    if missing:
        lead = "" if not current or current.endswith("\n") else "\n"
        ignore.write_text(
            f"{current}{lead}\n# Installed by `prodockit adopt`\n" + "\n".join(missing) + "\n",
            encoding="utf-8",
        )
    return [*written, *([ignore] if missing else [])]


def install_tool(
    root: Path,
    component: str,
    *,
    retry_reporter: RetryReporter | None = None,
    offline: bool = False,
) -> list[Path]:
    """Install one selected Node renderer after writing its scaffold."""
    if component not in COMPONENT_FILES:
        raise AdoptError(f"unknown optional renderer: {component}")
    npm = shutil.which("npm")
    if npm is None:
        raise AdoptError(
            f"{component} was selected but npm is not available. "
            "Rerun `prodockit adopt --apply` and approve the Node.js and npm runtime activity."
        )
    options = AdoptOptions(mermaid=component == "mermaid", maths=component == "mathjax")
    environment = None
    if component == "mermaid":
        from prodockit import adopt_browser

        try:
            environment = adopt_browser.prepare(root, offline=offline, reporter=retry_reporter)
        except (OSError, subprocess.SubprocessError, supported_toolchain.ToolchainError) as error:
            raise AdoptError(str(error)) from error
    written = ensure_tools(root, options)
    # On Windows npm is a command shim named npm.cmd. Passing the path found
    # by shutil avoids depending on PATHEXT handling inside subprocess.
    tool_root = root / "tools" / component
    # Adopt aligns and backs up the manifest/lock pair before installing.
    # The packaged lock fixes both upgrades and downgrades to this release.
    command = [
        npm,
        "ci",
        *(
            ["--legacy-peer-deps"]
            if component == "mathjax" and (tool_root / "package-lock.json").is_file()
            else []
        ),
        "--no-audit",
        "--no-fund",
        "--offline" if offline else "--prefer-offline",
    ]
    try:
        npm_result = run_npm_with_retries(
            command,
            cwd=tool_root,
            timeout=600,
            reporter=retry_reporter,
            retry_delays=() if offline else DEFAULT_RETRY_DELAYS,
            environment=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AdoptError(f"could not install {component}: {error}") from error
    completed = npm_result.completed
    if completed.returncode != 0:
        detail = npm_result.failure_detail
        raise AdoptError(f"npm could not install {component}: {detail}")
    if component == "mermaid":
        try:
            adopt_browser.complete(root, offline=offline, reporter=retry_reporter)
        except (OSError, subprocess.SubprocessError, supported_toolchain.ToolchainError) as error:
            raise AdoptError(str(error)) from error
        binary = _mermaid_bin(root)
        probe = (
            (
                probe_mermaid(binary, reporter=retry_reporter)
                if retry_reporter is not None
                else probe_mermaid(binary)
            )
            if binary
            else None
        )
        if probe is None or not probe.ok:
            health_detail = (
                probe.error or "health probe failed" if probe else "mmdc executable is missing"
            )
            raise AdoptError(
                "npm completed but Mermaid CLI is unusable: "
                f"{health_detail}. Remove tools/mermaid/node_modules and rerun "
                "`prodockit adopt --apply --mermaid`."
            )
    if component == "mathjax":
        node = shutil.which("node")
        probe = probe_mathjax(node, tool_root / "tex2svg.js") if node else None
        if probe is None or not probe.ok:
            health_detail = probe.error or "health probe failed" if probe else "node is unavailable"
            raise AdoptError(
                "npm completed but MathJax is unusable: "
                f"{health_detail}. Remove tools/mathjax/node_modules and rerun "
                "`prodockit adopt --apply --maths`."
            )
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


def _check_project_release(root: Path) -> None:
    """Do not rewrite a newer project's managed files with an older release."""
    from prodockit.pins import discover

    state = discover(str(root), ("prodockit",))["prodockit"]
    for site in state.sites:
        if site.kind != "manifest" and site.op not in {"==", ">="}:
            continue
        try:
            newer = Version(site.version) > Version(__version__)
        except InvalidVersion:
            continue
        if newer:
            raise AdoptError(
                f"{site.path} declares Prodockit {site.version}, but this command uses "
                f"{__version__}. Activate the project's environment and install "
                f"Prodockit {site.version} or a compatible newer release before running Adopt. "
                "No project files or software have been changed."
            )


def assess(
    root: Path,
    options: AdoptOptions,
    *,
    retry_reporter: RetryReporter | None = None,
    offline: bool = False,
) -> list[Step]:
    try:
        from prodockit.config_integrity import check_project

        check_project(root, AdoptError)
        _check_project_release(root)
        config_path, _source, parsed = _config(root)
        config_status = ("ok", f"{config_path.name} is valid")
    except AdoptError as error:
        return [Step("project", "Assess", "Existing documentation project", "wrong", str(error))]

    config_error = ""
    review_pending = False
    try:
        _planned_zensical_config(root, options)
        if config_path.suffix == ".toml" and options.template_snapshot is not None:
            review_pending = bool(
                adopt_settings.review(
                    root, _source, options.template_snapshot, original=_source
                ).count
            )
    except adopt_settings.SettingsError as error:
        config_error = str(error)
    except AdoptError as error:
        config_error = str(error)

    toolchain = supported_toolchain.plan(root, offline=offline)
    from prodockit import adopt_pdf_runtime

    native = adopt_pdf_runtime.plan(offline=offline)
    configured = _extensions(parsed)
    missing = _missing_core_extensions(parsed)
    style_paths = _stylesheet_paths(root, parsed)
    javascript_paths = _javascript_paths(root, parsed)
    core_ok = (
        not config_error
        and not review_pending
        and not missing
        and not _missing_caption_types(parsed)
        and not _extra_defaults_missing(parsed)
        and _tree_icons_ok(
            parsed,
            require_python_names=config_path.suffix != ".toml",
        )
        and _style_ok(root, parsed)
        and not _missing_local_ignores(root)
        and adopt_workflow.plan(root) is None
    )
    core_problems: list[str] = []
    if _missing_local_ignores(root):
        core_problems.append("exclude local environments and generated output from Git")
    if adopt_workflow.plan(root) is not None:
        core_problems.append(
            "update a verified stock workflow or prepare separate CI files for manual review"
        )
    if review_pending:
        core_problems.append("review new template settings and record .prodockit-adopt.toml")
    if missing:
        core_problems.append("add standard extension(s): " + ", ".join(missing))
    if not config_error and _missing_caption_types(parsed):
        core_problems.append("configure figure and table caption types")
    if _extra_defaults_missing(parsed):
        core_problems.append("add missing Prodockit website and PDF defaults")
    if not _tree_icons_ok(
        parsed,
        require_python_names=config_path.suffix != ".toml",
    ):
        core_problems.append("configure pymdownx.emoji for prodockit.tree icons")
    project = parsed.get("project", parsed)
    extra_css = project.get("extra_css", []) if isinstance(project, dict) else []
    extra = project.get("extra", {}) if isinstance(project, dict) else {}
    pdf_extra_css = extra.get("pdf_extra_css", []) if isinstance(extra, dict) else []
    extra_javascript = project.get("extra_javascript", []) if isinstance(project, dict) else []
    for name in MANAGED_STYLESHEETS:
        style_path = style_paths[name]
        if not style_path.is_file():
            core_problems.append(f"add managed stylesheet {style_path.relative_to(root)}")
        elif not same_text_content(style_path.read_bytes(), resource_bytes(name)):
            core_problems.append(f"refresh managed stylesheet {style_path.relative_to(root)}")
    for name in USER_MANAGED_STYLESHEETS:
        style_path = style_paths[name]
        if not style_path.is_file():
            core_problems.append(f"add user-managed stylesheet {style_path.relative_to(root)}")
    for name in MANAGED_JAVASCRIPTS:
        javascript_path = javascript_paths[name]
        if not javascript_path.is_file():
            core_problems.append(f"add managed JavaScript {javascript_path.relative_to(root)}")
        elif not same_text_content(javascript_path.read_bytes(), resource_bytes(name)):
            core_problems.append(f"refresh managed JavaScript {javascript_path.relative_to(root)}")
    for name in USER_MANAGED_JAVASCRIPTS:
        javascript_path = javascript_paths[name]
        if not javascript_path.is_file():
            core_problems.append(f"add user-managed JavaScript {javascript_path.relative_to(root)}")
    registrations = (
        ("stylesheets/pdk.css", extra_css, "project.extra_css"),
        ("stylesheets/extra.css", extra_css, "project.extra_css"),
        ("stylesheets/pdk-pdf.css", pdf_extra_css, "project.extra.pdf_extra_css"),
        ("stylesheets/print.css", pdf_extra_css, "project.extra.pdf_extra_css"),
        ("javascripts/pdk.js", extra_javascript, "project.extra_javascript"),
        ("javascripts/extra.js", extra_javascript, "project.extra_javascript"),
    )
    for stylesheet, configured_styles, setting in registrations:
        if not _asset_is_configured(stylesheet, configured_styles):
            core_problems.append(f"register {stylesheet} in {setting}")
    core_detail = config_error or (
        "all standard extensions and managed and user styles and scripts are configured"
        if core_ok
        else "; ".join(core_problems)
    )
    choices_ok = (root / MANIFEST).is_file()
    choices_detail = (
        f"component choices are saved in {MANIFEST}"
        if choices_ok
        else f"save the selected component choices in {MANIFEST}"
    )
    csl = _csl_activity(root, parsed, offline=offline)
    mermaid_tool_ok, mermaid_detail = _tool_health(root, "mermaid", retry_reporter=retry_reporter)
    maths_tool_ok, maths_detail = _tool_health(root, "mathjax")
    mermaid_ok = mermaid_tool_ok and "pymdownx.superfences" in configured
    maths_ok = maths_tool_ok and "pymdownx.arithmatex" in configured
    from prodockit import adopt_node

    node = (
        adopt_node.plan(offline=offline)
        if options.mermaid or options.maths
        else adopt_node.NodePlan()
    )
    from prodockit import adopt_browser

    browser = (
        adopt_browser.plan(root, offline=offline)
        if options.mermaid
        else adopt_browser.BrowserPlan()
    )
    in_venv = _in_venv()
    project_environment_exists = (root.resolve() / ".venv").is_dir()
    interpreter_problem = _interpreter_problem(root) if in_venv else None
    environment_warning = in_venv and not project_environment_exists
    ready_to_build = (
        not interpreter_problem
        and not toolchain.blocked
        and not toolchain.needs_work
        and not native.needs_work
        and core_ok
        and csl.status == "ok"
        and choices_ok
        and not node.needs_work
        and not browser.blocked
        and (not options.mermaid or mermaid_ok)
        and (not options.maths or maths_ok)
    )
    command = _build_command(config_path)
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
            "wrong"
            if interpreter_problem
            else ("warn" if environment_warning or not in_venv else "ok"),
            (
                interpreter_problem
                or (
                    "No project-local .venv is set up. Adopt is using the active "
                    f"environment at {sys.prefix}; package changes will affect it. "
                    "Create and activate .venv first unless this is intentional."
                    if environment_warning
                    else (
                        f"using {sys.prefix}"
                        if in_venv
                        else "No virtual environment is active. Package changes will affect "
                        "the running Python installation; create and activate a virtual "
                        "environment first unless this is intentional."
                    )
                )
            ),
        ),
        Step(
            "dependency",
            "Integrate",
            "Supported toolchain",
            "wrong" if toolchain.blocked else ("missing" if toolchain.needs_work else "ok"),
            toolchain.detail,
            commands=toolchain.commands,
            files=toolchain.files,
            plan_lines=tuple(
                f"{action.action.upper()}: "
                f"{supported_toolchain.DISPLAY_NAMES[action.package]} "
                + (
                    f"{action.installed} → {action.supported}"
                    if action.action in {"upgrade", "downgrade", "align"}
                    else action.supported
                )
                for action in toolchain.actions
            )
            + tuple(
                f"READY: {supported_toolchain.DISPLAY_NAMES[package]} {TESTED_VERSIONS[package]}"
                for package in (*supported_toolchain.PYTHON_PACKAGES, "pandoc")
                if not toolchain.blocked
                and not any(action.package == package for action in toolchain.actions)
            )
            + (("CONFIGURE: Project version settings",) if toolchain.declaration_changes else ()),
        ),
        Step(
            "pdf-runtime",
            "Integrate",
            "Native PDF libraries and fonts",
            "wrong" if native.blocked else ("missing" if native.needs_work else "ok"),
            native.blocked or native.detail,
            commands=native.commands,
        ),
        Step(
            "core",
            "Integrate",
            "Standard authoring components",
            "wrong" if config_error else ("ok" if core_ok else "missing"),
            core_detail,
        ),
        csl,
        Step(
            "choices",
            "Integrate",
            "Component choices",
            "ok" if choices_ok else "missing",
            choices_detail,
        ),
        Step(
            "node",
            "Optional renderers",
            "Node.js and npm runtime",
            "wrong" if node.blocked else ("missing" if node.needs_work else "ok"),
            node.blocked
            or (
                "install or repair Node.js/npm using the system package manager; "
                "administrator approval may be required"
                if node.needs_work
                else "Node.js and npm meet the supported runtime requirements"
            ),
            commands=node.commands,
            selected=options.mermaid or options.maths,
        ),
        Step(
            "mermaid",
            "Optional renderers",
            "Mermaid diagrams",
            "wrong" if browser.blocked else ("ok" if mermaid_ok else "missing"),
            (
                f"selected; {browser.blocked or mermaid_detail}; {browser.detail}"
                if options.mermaid
                else "not selected; Node.js is not needed for Mermaid"
            ),
            selected=options.mermaid,
            commands=browser.commands,
            files=tuple(root / "tools" / "mermaid" / name for name in COMPONENT_FILES["mermaid"])
            if options.mermaid and not mermaid_ok
            else (),
        ),
        Step(
            "maths",
            "Optional renderers",
            "Mathematical notation",
            "ok" if maths_ok else "missing",
            (
                f"selected; {maths_detail}"
                if options.maths
                else "not selected for this run; existing files are left in place"
            ),
            selected=options.maths,
            files=tuple(root / "tools" / "mathjax" / name for name in COMPONENT_FILES["mathjax"])
            if options.maths and not maths_ok
            else (),
        ),
        Step(
            "verify",
            "Verify",
            "Ready for local build",
            "ok" if ready_to_build else "wait",
            (
                f"selected components are configured; run {command} to verify the site"
                if ready_to_build
                else f"apply the selected integration activities before running {command}"
            ),
        ),
    ]


def _build_command(config_path: Path) -> str:
    explicit = "" if config_path.name == "zensical.toml" else f" -f {config_path.name}"
    return f"zensical build{explicit} --clean --strict"


def build_command(root: Path) -> str:
    """Return the strict build command for the configuration below ``root``."""
    config_path = next(
        (root / name for name in CONFIG_NAMES if (root / name).is_file()),
        root / "zensical.toml",
    )
    return _build_command(config_path)


def apply_step(
    root: Path,
    options: AdoptOptions,
    step_id: str,
    *,
    retry_reporter: RetryReporter | None = None,
    offline: bool = False,
) -> list[Path]:
    from prodockit.config_integrity import check_project

    check_project(root, AdoptError)
    _check_project_release(root)
    if step_id == "pdf-runtime":
        from prodockit import adopt_pdf_runtime

        try:
            adopt_pdf_runtime.apply(root, offline=offline, reporter=retry_reporter)
        except (OSError, subprocess.SubprocessError, supported_toolchain.ToolchainError) as error:
            raise AdoptError(str(error)) from error
        return []
    if step_id in {"mermaid", "maths"}:
        from prodockit import adopt_node

        if adopt_node.plan(offline=offline).needs_work:
            raise AdoptError(
                "Complete the Node.js and npm runtime activity before installing renderers."
            )
    if step_id == "node":
        from prodockit import adopt_node

        try:
            adopt_node.apply(root, offline=offline, reporter=retry_reporter)
        except (OSError, subprocess.SubprocessError, supported_toolchain.ToolchainError) as error:
            raise AdoptError(str(error)) from error
        return []
    if step_id == "dependency":
        try:
            return supported_toolchain.apply(root, offline=offline, reporter=retry_reporter)
        except supported_toolchain.ToolchainError as error:
            raise AdoptError(str(error)) from error
    if step_id == "core":
        workflow_files = []
        for path, content in adopt_workflow.plans(root):
            _atomic_write(path, content.encode("utf-8"))
            workflow_files.append(path)
        return [
            ensure_zensical_config(root, options),
            *ensure_stylesheets(root),
            *ensure_javascripts(root),
            *ensure_local_ignores(root),
            *workflow_files,
        ]
    if step_id == "csl":
        activity = _csl_activity(root, _config(root)[2], offline=offline)
        if not activity.files:
            return []
        try:
            return [install_csl(activity.files[0], offline=offline)]
        except CslError as error:
            raise AdoptError(str(error)) from error
    if step_id == "choices":
        return [write_manifest(root, options)]
    if step_id == "mermaid":
        return [
            ensure_zensical_config(root, options),
            write_manifest(root, options),
            *install_tool(
                root,
                "mermaid",
                retry_reporter=retry_reporter,
                **({"offline": True} if offline else {}),
            ),
        ]
    if step_id == "maths":
        return [
            ensure_zensical_config(root, options),
            write_manifest(root, options),
            *install_tool(
                root,
                "mathjax",
                retry_reporter=retry_reporter,
                **({"offline": True} if offline else {}),
            ),
        ]
    return []


def apply(
    root: Path,
    options: AdoptOptions,
    *,
    retry_reporter: RetryReporter | None = None,
    offline: bool = False,
) -> list[Path]:
    """Apply every selected Adopt stage and verify the resulting plan.

    The public command owns per-stage prompts.  Template sync has already
    shown the same plan and obtained one separate, explicit permission for
    Adopt, so it calls this non-interactive orchestration rather than
    duplicating any installer or project-repair implementation.
    """

    initial = assess(root, options, retry_reporter=retry_reporter, offline=offline)
    blocked = [step for step in initial if step.selected and step.status == "wrong"]
    if blocked:
        raise AdoptError("; ".join(f"{step.summary}: {step.detail}" for step in blocked))

    written: list[Path] = []
    for original in initial:
        if not original.selected or original.id == "verify":
            continue
        current = next(
            step
            for step in assess(
                root,
                options,
                retry_reporter=retry_reporter,
                offline=offline,
            )
            if step.id == original.id
        )
        if current.status == "wrong":
            raise AdoptError(f"{current.summary}: {current.detail}")
        if current.needs_work:
            written.extend(
                apply_step(
                    root,
                    options,
                    current.id,
                    retry_reporter=retry_reporter,
                    offline=offline,
                )
            )

    final = assess(root, options, retry_reporter=retry_reporter, offline=offline)
    incomplete = [
        step
        for step in final
        if step.selected and (step.status not in {"ok", "warn"} or step.needs_work)
    ]
    if incomplete:
        raise AdoptError(
            "Adopt verification is incomplete: "
            + "; ".join(f"{step.summary}: {step.detail}" for step in incomplete)
        )
    return list(dict.fromkeys(written))


__all__ = [
    "CORE_EXTENSIONS",
    "MANIFEST",
    "STYLESHEET",
    "AdoptChoiceResolution",
    "AdoptError",
    "AdoptOptions",
    "Step",
    "apply",
    "apply_step",
    "assess",
    "ensure_requirement",
    "ensure_stylesheet",
    "ensure_tools",
    "ensure_zensical_config",
    "install_tool",
    "load_manifest",
    "manifest_source",
    "resolve_options",
    "write_manifest",
]

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Resolved, strict diagnostics for configuration owned by Prodockit."""

from __future__ import annotations

import difflib
import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from markdown.extensions import Extension

from prodockit.bibliography import BibliographyExtension
from prodockit.citations import CitationsExtension
from prodockit.glossary import GlossaryExtension
from prodockit.headings import HeadingsExtension
from prodockit.index import IndexExtension
from prodockit.project_config import ProjectConfig
from prodockit.project_integrity import inspect_project
from prodockit.refs import RefsExtension
from prodockit.settings import EXTRA_SETTINGS, SettingError, resolve_index_settings
from prodockit.steps import StepsExtension
from prodockit.tables import TablesExtension
from prodockit.tree import TreeExtension

EXTENSION_TYPES: dict[str, type[Extension]] = {
    "prodockit.headings": HeadingsExtension,
    "prodockit.refs": RefsExtension,
    "prodockit.citations": CitationsExtension,
    "prodockit.glossary": GlossaryExtension,
    "prodockit.bibliography": BibliographyExtension,
    "prodockit.tables": TablesExtension,
    "prodockit.steps": StepsExtension,
    "prodockit.tree": TreeExtension,
    "prodockit.index": IndexExtension,
}

OBSOLETE_EXTRA_SETTINGS = {
    "pdf_include_index": (
        'use include under [project.markdown_extensions."prodockit.index"]'
    ),
    "pdf_index_title": (
        'use title under [project.markdown_extensions."prodockit.index"]'
    ),
    "pdf_source_bundle": "run `prodockit source-bundle` explicitly",
}


@dataclass(frozen=True)
class ResolvedSetting:
    """A setting's effective value and where it came from."""

    group: str
    key: str
    value: object
    source: str


@dataclass(frozen=True)
class Diagnostic:
    """One configuration problem that must not be silently ignored."""

    path: str
    message: str


@dataclass(frozen=True)
class ConfigReport:
    """Resolved settings and strict Prodockit-owned diagnostics."""

    path: Path
    settings: tuple[ResolvedSetting, ...]
    diagnostics: tuple[Diagnostic, ...]
    index_enabled: bool
    index_title: str
    index_dependency_available: bool


def _extension_defaults(extension_type: type[Extension]) -> dict[str, Any]:
    return extension_type().getConfigs()


def _suggest(value: str, choices: list[str]) -> str:
    matches = difflib.get_close_matches(value, choices, n=1, cutoff=0.6)
    return f"; did you mean {matches[0]!r}?" if matches else ""


def index_support_available() -> bool:
    """Whether the optional package needed to generate an index can import."""
    try:
        importlib.import_module("pymupdf")
    except Exception:  # native-loader failures are not necessarily ImportError
        return False
    return True


def _display_default(config: ProjectConfig, key: str, default: object) -> object:
    if key == "pdf_output":
        return os.path.join(str(config.project.get("docs_dir") or "docs"), "site_documentation.pdf")
    if key == "pdf_source_bundle_output":
        return os.path.join(str(config.project.get("docs_dir") or "docs"), "source_bundle.pdf")
    if key == "pdf_copyright":
        return config.project.get("copyright") or ""
    if default is None:
        return "auto-detected"
    if default == ():
        return []
    return default


def inspect_config(config: ProjectConfig) -> ConfigReport:
    """Resolve and validate only configuration Prodockit owns."""
    settings: list[ResolvedSetting] = []
    diagnostics: list[Diagnostic] = []
    extra = config.extra
    known_extra = {setting.key for setting in EXTRA_SETTINGS}

    for setting in EXTRA_SETTINGS:
        explicit = setting.key in extra
        value = (
            extra[setting.key]
            if explicit
            else _display_default(config, setting.key, setting.default)
        )
        source = f"project.extra.{setting.key}" if explicit else "default"
        settings.append(ResolvedSetting(setting.group, setting.key, value, source))

    for key in extra:
        path = f"project.extra.{key}"
        if key in OBSOLETE_EXTRA_SETTINGS:
            diagnostics.append(
                Diagnostic(path, f"obsolete setting; {OBSOLETE_EXTRA_SETTINGS[key]}")
            )
        elif key not in known_extra and (
            key.startswith("pdf_")
            or key.startswith("reference_")
            or bool(difflib.get_close_matches(key, sorted(known_extra), n=1, cutoff=0.75))
        ):
            diagnostics.append(
                Diagnostic(path, "unknown Prodockit setting" + _suggest(key, sorted(known_extra)))
            )

    extension_names = sorted(EXTENSION_TYPES)
    for name, options in sorted(config.markdown_extensions.items()):
        if not name.startswith("prodockit."):
            continue
        if name not in EXTENSION_TYPES:
            diagnostics.append(
                Diagnostic(
                    f"project.markdown_extensions.{name}",
                    "unknown Prodockit extension" + _suggest(name, extension_names),
                )
            )
            continue
        defaults = _extension_defaults(EXTENSION_TYPES[name])
        for key, default in defaults.items():
            explicit = key in options
            settings.append(
                ResolvedSetting(
                    f"Extension {name}",
                    key,
                    options[key] if explicit else default,
                    f"{name}.{key}" if explicit else "default",
                )
            )
        for key in options:
            if key not in defaults:
                diagnostics.append(
                    Diagnostic(
                        f'project.markdown_extensions."{name}".{key}',
                        "unknown option" + _suggest(key, sorted(defaults)),
                    )
                )

    index_options = config.markdown_extensions.get("prodockit.index", {})
    index_defaults = _extension_defaults(IndexExtension)
    if "prodockit.index" not in config.markdown_extensions:
        for key, default in index_defaults.items():
            settings.append(ResolvedSetting("Extension prodockit.index", key, default, "default"))
    try:
        index_settings = resolve_index_settings(index_options)
    except SettingError as error:
        diagnostics.append(Diagnostic("prodockit.index", str(error)))
        index_settings = resolve_index_settings(None)
    index_enabled = index_settings.include
    index_title = index_settings.title
    available = index_support_available()
    if index_enabled and not available:
        diagnostics.append(
            Diagnostic(
                'project.markdown_extensions."prodockit.index".include',
                "index generation is enabled but optional support is missing; "
                "install `prodockit[index]`",
            )
        )

    diagnostics.extend(
        Diagnostic(problem.path, problem.message) for problem in inspect_project(config)
    )

    return ConfigReport(
        path=config.path,
        settings=tuple(settings),
        diagnostics=tuple(diagnostics),
        index_enabled=index_enabled,
        index_title=index_title,
        index_dependency_available=available,
    )

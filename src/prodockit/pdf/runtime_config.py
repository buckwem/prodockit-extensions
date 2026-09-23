# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Committed policy for Prodockit's project-local PDF runtime.

``pdk-pdf.toml`` says what a project wants.  Resolved versions, digests and
machine-specific paths deliberately live in :mod:`prodockit.pdf.runtime_store`
instead, beneath the derived ``.prodockit/cache/pdf`` directory.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prodockit.settings import PDF_EXTRA_SETTINGS, SettingError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

CONFIG_NAME = "pdk-pdf.toml"
SCHEMA_VERSION = 1
COMPONENTS = ("mathjax", "mermaid", "weasyprint", "pandoc", "fonts")
_RENDERERS = frozenset({"mathjax", "mermaid"})
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")


class PdfRuntimeConfigError(ValueError):
    """The committed PDF runtime policy is invalid."""


@dataclass(frozen=True)
class ComponentPolicy:
    """One component's requested channel/version and acquisition policy."""

    version: str
    location: str = "cache"
    preload: bool = False


@dataclass(frozen=True)
class ResolvedPdfSettings:
    """Effective PDF-only settings and the source selected for each one."""

    values: Mapping[str, object]
    sources: Mapping[str, str]
    legacy: tuple[str, ...]
    shadowed_legacy: tuple[str, ...]
    conflicting_legacy: tuple[str, ...]

    def value(self, key: str) -> Any:
        try:
            return self.values[key]
        except KeyError as error:
            raise PdfRuntimeConfigError(f"unknown PDF document setting {key!r}") from error

    def source_for(self, key: str) -> str:
        try:
            return self.sources[key]
        except KeyError as error:
            raise PdfRuntimeConfigError(f"unknown PDF document setting {key!r}") from error


@dataclass(frozen=True)
class PdfRuntimeConfig:
    """Validated policy together with the project boundary that owns it."""

    project_root: Path
    path: Path
    schema_version: int
    components: Mapping[str, ComponentPolicy]
    pdf_values: Mapping[str, object]
    pdf_sources: Mapping[str, str]
    pdf_explicit: frozenset[str]
    exists: bool

    def policy_for(self, component: str) -> ComponentPolicy:
        try:
            return self.components[component]
        except KeyError as error:
            raise PdfRuntimeConfigError(f"unknown PDF runtime component {component!r}") from error

    def resolve_pdf_settings(
        self, legacy_extra: Mapping[str, object] | None = None
    ) -> ResolvedPdfSettings:
        """Resolve PDF-only policy with per-setting legacy compatibility.

        An explicit value in ``pdk-pdf.toml`` wins.  A corresponding
        ``project.extra.pdf_*`` value is otherwise read as a deprecated
        fallback.  Missing values use the supported defaults without writing
        either configuration file.
        """

        legacy_extra = legacy_extra or {}
        values = dict(self.pdf_values)
        sources = dict(self.pdf_sources)
        legacy: list[str] = []
        shadowed: list[str] = []
        conflicts: list[str] = []
        for setting in PDF_EXTRA_SETTINGS:
            key = setting.key
            if key not in legacy_extra:
                continue
            if key in self.pdf_explicit:
                shadowed.append(key)
                if legacy_extra[key] != self.pdf_values[key]:
                    conflicts.append(key)
                continue
            try:
                setting.validate(legacy_extra[key])
            except SettingError as error:
                raise PdfRuntimeConfigError(str(error)) from error
            values[key] = legacy_extra[key]
            sources[key] = f"project.extra.{key} (deprecated fallback)"
            legacy.append(key)
        return ResolvedPdfSettings(
            values,
            sources,
            tuple(sorted(legacy)),
            tuple(sorted(shadowed)),
            tuple(sorted(conflicts)),
        )


_DEFAULTS: Mapping[str, ComponentPolicy] = {
    "mathjax": ComponentPolicy("latest"),
    "mermaid": ComponentPolicy("supported"),
    "weasyprint": ComponentPolicy("supported"),
    "pandoc": ComponentPolicy("supported"),
    "fonts": ComponentPolicy("supported"),
}

_PDF_DEFAULTS: Mapping[str, object] = {
    setting.key: ([] if setting.default == () else setting.default)
    for setting in PDF_EXTRA_SETTINGS
    if setting.key not in {"pdf_tex2svg_script", "pdf_math_dir"}
}

_PDF_TABLES: Mapping[str, Mapping[str, str]] = {
    "document": {
        "output": "pdf_output",
        "copyright": "pdf_copyright",
        "extra_css": "pdf_extra_css",
        "page_size": "pdf_page_size",
        "double_sided": "pdf_double_sided",
    },
    "margins": {
        "top": "pdf_margin_top",
        "right": "pdf_margin_right",
        "bottom": "pdf_margin_bottom",
        "left": "pdf_margin_left",
        "inner": "pdf_margin_inner",
        "outer": "pdf_margin_outer",
    },
    "header_footer": {
        "font_size": "pdf_header_footer_font_size",
        "color": "pdf_header_footer_color",
        "divider_color": "pdf_header_footer_divider_color",
    },
    "table_of_contents": {
        "include": "pdf_include_table_of_contents",
        "title": "pdf_table_of_contents_title",
    },
    "source_bundle": {"output": "pdf_source_bundle_output"},
}

PDF_SETTING_PATHS: Mapping[str, str] = {
    legacy_key: f"[{table_name}].{field}"
    for table_name, fields in _PDF_TABLES.items()
    for field, legacy_key in fields.items()
}

_PDF_SETTING_BY_KEY = {setting.key: setting for setting in PDF_EXTRA_SETTINGS}


def _pdf_settings(
    raw: Mapping[str, Any],
) -> tuple[dict[str, object], dict[str, str], frozenset[str]]:
    values = dict(_PDF_DEFAULTS)
    sources = dict.fromkeys(values, "default")
    explicit: set[str] = set()
    for table_name, fields in _PDF_TABLES.items():
        table = _table(raw.get(table_name, {}), field=f"[{table_name}]")
        unknown = sorted(set(table) - set(fields))
        if unknown:
            joined = ", ".join(unknown)
            raise PdfRuntimeConfigError(
                f"[{table_name}] has unknown setting(s): {joined}"
            )
        for field, legacy_key in fields.items():
            if field not in table:
                continue
            value = table[field]
            try:
                _PDF_SETTING_BY_KEY[legacy_key].validate(value)
            except SettingError as error:
                expected = str(error).split(" must be ", 1)[-1]
                raise PdfRuntimeConfigError(
                    f"[{table_name}].{field} must be {expected}"
                ) from error
            values[legacy_key] = value
            sources[legacy_key] = f"pdk-pdf.toml [{table_name}].{field}"
            explicit.add(legacy_key)
    return values, sources, frozenset(explicit)


def project_root_for(config_file: str | Path = "zensical.toml") -> Path:
    """Resolve the project boundary from the selected Zensical config path."""

    path = Path(config_file).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve().parent


def _table(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PdfRuntimeConfigError(f"{field} must be a TOML table")
    return value


def _component_policy(component: str, raw: object) -> ComponentPolicy:
    table = _table(raw, field=f"[{component}]")
    allowed = {"version", "location"}
    if component in _RENDERERS:
        allowed.add("preload")
    unknown = sorted(set(table) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise PdfRuntimeConfigError(f"[{component}] has unknown setting(s): {joined}")

    default = _DEFAULTS[component]
    version = table.get("version", default.version)
    if not isinstance(version, str) or not version.strip():
        raise PdfRuntimeConfigError(f"[{component}].version must be a non-empty string")
    version = version.strip()
    if version not in {"latest", "supported"} and not _VERSION.fullmatch(version):
        raise PdfRuntimeConfigError(
            f"[{component}].version must be 'latest', 'supported', or an exact version"
        )

    location = table.get("location", default.location)
    if location != "cache":
        raise PdfRuntimeConfigError(
            f"[{component}].location must be 'cache'; other locations are not yet supported"
        )

    preload = table.get("preload", default.preload)
    if not isinstance(preload, bool):
        raise PdfRuntimeConfigError(f"[{component}].preload must be true or false")
    return ComponentPolicy(version=version, location=location, preload=preload)


def load_pdf_runtime_config(config_file: str | Path = "zensical.toml") -> PdfRuntimeConfig:
    """Load ``pdk-pdf.toml`` beside ``config_file`` without creating it.

    A missing file is the normal path and returns the supported defaults.
    Unknown data is rejected so a misspelt security or version policy cannot
    be silently ignored.
    """

    root = project_root_for(config_file)
    path = root / CONFIG_NAME
    if not path.exists():
        values, sources, explicit = _pdf_settings({})
        return PdfRuntimeConfig(
            root,
            path,
            SCHEMA_VERSION,
            dict(_DEFAULTS),
            values,
            sources,
            explicit,
            False,
        )
    try:
        source = path.read_text(encoding="utf-8")
        raw = tomllib.loads(source)
    except OSError as error:
        raise PdfRuntimeConfigError(f"cannot read {path}: {error}") from error
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PdfRuntimeConfigError(f"cannot parse {path}: {error}") from error

    allowed = {"schema_version", *COMPONENTS, *_PDF_TABLES}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise PdfRuntimeConfigError(f"{path.name} has unknown top-level setting(s): {joined}")
    schema = raw.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise PdfRuntimeConfigError(
            f"{path.name} schema_version must be {SCHEMA_VERSION}, not {schema!r}"
        )

    components = {
        component: _component_policy(component, raw.get(component, {}))
        for component in COMPONENTS
    }
    values, sources, explicit = _pdf_settings(raw)
    return PdfRuntimeConfig(
        root,
        path,
        schema,
        components,
        values,
        sources,
        explicit,
        True,
    )


__all__ = [
    "COMPONENTS",
    "CONFIG_NAME",
    "PDF_SETTING_PATHS",
    "SCHEMA_VERSION",
    "ComponentPolicy",
    "PdfRuntimeConfig",
    "PdfRuntimeConfigError",
    "ResolvedPdfSettings",
    "load_pdf_runtime_config",
    "project_root_for",
]

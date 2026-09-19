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
class PdfRuntimeConfig:
    """Validated policy together with the project boundary that owns it."""

    project_root: Path
    path: Path
    schema_version: int
    components: Mapping[str, ComponentPolicy]
    exists: bool

    def policy_for(self, component: str) -> ComponentPolicy:
        try:
            return self.components[component]
        except KeyError as error:
            raise PdfRuntimeConfigError(f"unknown PDF runtime component {component!r}") from error


_DEFAULTS: Mapping[str, ComponentPolicy] = {
    "mathjax": ComponentPolicy("latest"),
    "mermaid": ComponentPolicy("supported"),
    "weasyprint": ComponentPolicy("supported"),
    "pandoc": ComponentPolicy("supported"),
    "fonts": ComponentPolicy("supported"),
}


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
        return PdfRuntimeConfig(root, path, SCHEMA_VERSION, dict(_DEFAULTS), False)
    try:
        source = path.read_text(encoding="utf-8")
        raw = tomllib.loads(source)
    except OSError as error:
        raise PdfRuntimeConfigError(f"cannot read {path}: {error}") from error
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PdfRuntimeConfigError(f"cannot parse {path}: {error}") from error

    allowed = {"schema_version", *COMPONENTS}
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
    return PdfRuntimeConfig(root, path, schema, components, True)


__all__ = [
    "COMPONENTS",
    "CONFIG_NAME",
    "SCHEMA_VERSION",
    "ComponentPolicy",
    "PdfRuntimeConfig",
    "PdfRuntimeConfigError",
    "load_pdf_runtime_config",
    "project_root_for",
]

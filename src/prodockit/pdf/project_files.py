# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Prepare project-owned PDF policy on first PDF use, not during adoption."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import tomlkit
import yaml

from prodockit.pdf.python_requirements import (
    REQUIREMENTS_NAME,
    STANDARD_REQUIREMENTS,
)
from prodockit.pdf.runtime_config import (
    PDF_SETTING_PATHS,
    SCHEMA_VERSION,
    load_pdf_runtime_config,
)
from prodockit.shared_files import resource_bytes

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib


class PdfProjectFilesError(ValueError):
    """Project PDF files cannot be migrated without losing author settings."""


_WEASYPRINT_LINE = re.compile(
    r"(?im)^[ \t]*weasyprint(?:\[[^]]+\])?[ \t]*"
    r"(?:(?:==|>=|~=|<=|!=|>|<)[ \t]*[^\s;#]+)?"
    r"(?:[ \t]*;[^#\n]*)?(?:[ \t]*(?:#.*)?)?(?:\n|$)"
)
_LEGACY_PANDOC_LINE = re.compile(r"(?im)^[ \t]*pandoc[ \t]*(?:#.*)?(?:\n|$)")


def _inline(value: Any) -> Any:
    if isinstance(value, dict):
        table = tomlkit.inline_table()
        for key, item in value.items():
            table[str(key)] = _inline(item)
        return table
    if isinstance(value, list):
        array = tomlkit.array()
        for item in value:
            array.append(_inline(item))
        return array
    return tomlkit.item(value)


def _update_pdf(source: str, legacy_extra: dict[str, Any]) -> str:
    """Preserve PDF policy and add the two PDF stylesheet references."""
    document = tomlkit.parse(source) if source else tomlkit.document()
    document["schema_version"] = SCHEMA_VERSION
    for key, path in PDF_SETTING_PATHS.items():
        if key not in legacy_extra:
            continue
        table_name, field = path.removeprefix("[").split("].", 1)
        if table_name not in document:
            document[table_name] = tomlkit.table()
        table = document[table_name]
        if field not in table:
            table[field] = _inline(legacy_extra[key])
    if "document" not in document:
        document["document"] = tomlkit.table()
    pdf_document = document["document"]
    if "extra_css" not in pdf_document:
        pdf_document["extra_css"] = tomlkit.array().multiline(True)
    values = pdf_document["extra_css"]
    if not isinstance(values, list):
        raise PdfProjectFilesError("pdk-pdf.toml [document].extra_css must be an array")
    for name in ("stylesheets/pdk-pdf.css", "stylesheets/print.css"):
        if name not in values:
            values.insert(0, name) if name.endswith("pdk-pdf.css") else values.append(name)
    output = tomlkit.dumps(document)
    tomllib.loads(output)
    return output


def _write(path: Path, content: bytes) -> None:
    """Replace one file atomically, without leaving a partial download or edit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_project_files(config_file: str | Path) -> tuple[Path, ...]:
    """Create and safely migrate the PDF policy files before preparing runtimes.

    All potential conflicts are checked before any project file is changed.
    A second invocation leaves the files untouched.
    """
    config = Path(config_file).resolve()
    root = config.parent
    original = config.read_text(encoding="utf-8")
    if config.suffix == ".toml":
        parsed = tomllib.loads(original)
    else:
        from prodockit.adopt import _MarkdownConfigLoader

        parsed = yaml.load(original, Loader=_MarkdownConfigLoader)
    if not isinstance(parsed, dict):
        raise PdfProjectFilesError(f"{config.name} must contain a configuration mapping")
    project: Any = parsed.get("project", parsed)
    legacy = project.get("extra", {}) if isinstance(project, dict) else {}
    if not isinstance(legacy, dict):
        legacy = {}

    # Reject malformed legacy settings before creating or changing files.
    load_pdf_runtime_config(config).resolve_pdf_settings(legacy)

    pdf_path = root / "pdk-pdf.toml"
    current_pdf = pdf_path.read_text(encoding="utf-8") if pdf_path.is_file() else ""
    if pdf_path.is_file():
        load_pdf_runtime_config(config)
    existing = tomllib.loads(current_pdf) if current_pdf else {}
    for old_key, target in PDF_SETTING_PATHS.items():
        if old_key not in legacy:
            continue
        table_name, field = target.removeprefix("[").split("].", 1)
        current = existing.get(table_name, {}).get(field)
        if current is not None and current != legacy[old_key]:
            raise PdfProjectFilesError(
                f"{old_key} conflicts with pdk-pdf.toml {target}; resolve the values "
                "before running pdk pdf"
            )
    planned_pdf = _update_pdf(current_pdf, legacy)
    if config.suffix == ".toml":
        planned_config = original
        for old_key in PDF_SETTING_PATHS:
            if old_key not in legacy:
                continue
            # Reparse after each deletion: TOML Kit's dotted-key index becomes
            # stale when two project.extra.pdf_* entries share one table.
            document = tomlkit.parse(planned_config)
            extra = document.get("project", document).get("extra", {})
            extra.pop(old_key, None)
            planned_config = tomlkit.dumps(document)
        tomllib.loads(planned_config)
    else:
        from prodockit.adopt import _yaml_remove_nested_keys

        planned_config = _yaml_remove_nested_keys(original, "extra", set(PDF_SETTING_PATHS))
        yaml.load(planned_config, Loader=_MarkdownConfigLoader)

    base_path = root / "requirements.txt"
    base_source = base_path.read_text(encoding="utf-8") if base_path.is_file() else ""
    pdf_requirements = root / REQUIREMENTS_NAME
    current_requirements = (
        pdf_requirements.read_text(encoding="utf-8") if pdf_requirements.is_file() else ""
    )
    planned_requirements = current_requirements or STANDARD_REQUIREMENTS
    base_match = _WEASYPRINT_LINE.search(base_source)
    pdf_match = _WEASYPRINT_LINE.search(planned_requirements)
    if base_match:
        declaration = base_match.group(0).strip()
        code, marker, comment = declaration.partition("#")
        if ";" not in code:
            code = code.rstrip() + '; sys_platform != "win32"'
        migrated = code.rstrip() + (f"  # {comment.strip()}" if marker else "")
        if pdf_requirements.is_file() and pdf_match and pdf_match.group(0).strip() != migrated:
            raise PdfProjectFilesError(
                "requirements.txt WeasyPrint conflicts with pdf-requirements.txt; "
                "resolve the declarations before running pdk pdf"
            )
        if pdf_match:
            planned_requirements = (
                planned_requirements[: pdf_match.start()]
                + migrated
                + "\n"
                + planned_requirements[pdf_match.end() :]
            )
        else:
            planned_requirements = planned_requirements.rstrip() + "\n" + migrated + "\n"
    planned_base = _LEGACY_PANDOC_LINE.sub("", _WEASYPRINT_LINE.sub("", base_source))

    # PDF CSS is a PDF asset. Never replace an author-customized file.
    docs_dir = Path(str(project.get("docs_dir", "docs")))
    style_dir = (root / docs_dir / "stylesheets").resolve()
    if not style_dir.is_relative_to(root):
        raise PdfProjectFilesError("docs_dir must remain inside the project")
    pdf_css = style_dir / "pdk-pdf.css"
    print_css = style_dir / "print.css"
    changes = (
        (pdf_path, current_pdf.encode("utf-8"), planned_pdf.encode("utf-8")),
        (
            pdf_requirements,
            current_requirements.encode("utf-8"),
            planned_requirements.encode("utf-8"),
        ),
        (config, original.encode("utf-8"), planned_config.encode("utf-8")),
        (base_path, base_source.encode("utf-8"), planned_base.encode("utf-8")),
    )
    written: list[Path] = []
    for path, current, planned in changes:
        if current != planned or (not path.exists() and path in {pdf_path, pdf_requirements}):
            _write(path, planned)
            written.append(path)
    if not pdf_css.exists():
        _write(pdf_css, resource_bytes("pdk-pdf.css"))
        written.append(pdf_css)
    if not print_css.exists():
        _write(print_css, b"")
        written.append(print_css)
    return tuple(written)


__all__ = ["PdfProjectFilesError", "prepare_project_files"]

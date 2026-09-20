# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Prepare PDF-only Python packages in the active project environment.

The committed ``pdf-requirements.txt`` is policy.  The derived manifest below
``.prodockit/cache/pdf/python`` records that the policy has already been
validated for one concrete virtual environment.  A warm PDF build therefore
does not invoke pip or contact a package index.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from prodockit.environment import project_environment_problem
from prodockit.toolchain import (
    ToolchainError,
    pip_install_requirements_command,
    run_install_command,
)
from prodockit.weasyprint_probe import (
    clear_probe_cache,
    pango_install_guidance,
    run_probe,
)

REQUIREMENTS_NAME = "pdf-requirements.txt"
WEASYPRINT_REQUIREMENT = 'weasyprint>=69.0; sys_platform != "win32"'
PYMUPDF_REQUIREMENT = "pymupdf>=1.24"
STANDARD_REQUIREMENTS = (
    "# Python packages used only when pdk pdf renders this project.\n"
    "# Prodockit installs and validates them on first PDF use.\n"
    f"{WEASYPRINT_REQUIREMENT}\n"
)
_ALLOWED_PACKAGES = frozenset({"weasyprint", "pymupdf"})
_SCHEMA = 1


class PdfPythonRequirementsError(RuntimeError):
    """PDF-only Python packages could not be safely prepared."""


@dataclass(frozen=True)
class PdfPythonPreparation:
    """Result of one cold or warm PDF Python dependency preparation."""

    path: Path
    cached: bool
    versions: dict[str, str]

    @property
    def version(self) -> str:
        return ", ".join(f"{name} {version}" for name, version in self.versions.items())


def requirements_path(project_root: Path) -> Path:
    return project_root / REQUIREMENTS_NAME


def cache_manifest_path(project_root: Path) -> Path:
    return project_root / ".prodockit" / "cache" / "pdf" / "python" / "manifest.json"


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else STANDARD_REQUIREMENTS
    except (OSError, UnicodeError) as error:
        raise PdfPythonRequirementsError(f"could not read {path}: {error}") from error


def _requirements(source: str, *, include_index: bool) -> tuple[Requirement, ...]:
    """Validate the narrow automatically-installed dependency boundary."""

    parsed: dict[str, Requirement] = {}
    for number, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(("-", "http:", "https:", "git+", ".", "/")):
            raise PdfPythonRequirementsError(
                f"{REQUIREMENTS_NAME}:{number} must contain a package requirement, "
                "not an option, include, URL, or local path"
            )
        try:
            requirement = Requirement(line)
        except InvalidRequirement as error:
            raise PdfPythonRequirementsError(
                f"{REQUIREMENTS_NAME}:{number} is not a valid requirement: {error}"
            ) from error
        name = str(canonicalize_name(requirement.name))
        if name not in _ALLOWED_PACKAGES:
            raise PdfPythonRequirementsError(
                f"{REQUIREMENTS_NAME}:{number} declares {requirement.name}; only PDF runtime "
                "packages weasyprint and pymupdf are allowed"
            )
        if name in parsed:
            raise PdfPythonRequirementsError(
                f"{REQUIREMENTS_NAME}:{number} duplicates the {requirement.name} requirement"
            )
        parsed[name] = requirement

    if sys.platform != "win32" and "weasyprint" not in parsed:
        raise PdfPythonRequirementsError(
            f"{REQUIREMENTS_NAME} must declare WeasyPrint on macOS and Linux"
        )
    if include_index and "pymupdf" not in parsed:
        parsed["pymupdf"] = Requirement(PYMUPDF_REQUIREMENT)

    active = []
    for name, requirement in parsed.items():
        if name == "weasyprint" and sys.platform == "win32":
            continue
        if name == "pymupdf" and not include_index:
            continue
        if requirement.marker is None or requirement.marker.evaluate():
            active.append(requirement)
    return tuple(active)


def _active_file_names(source: str) -> set[str]:
    """Return declarations pip will install from the validated policy file."""

    names: set[str] = set()
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            names.add(str(canonicalize_name(requirement.name)))
    return names


def _installed_versions(requirements: tuple[Requirement, ...]) -> dict[str, str] | None:
    versions: dict[str, str] = {}
    for requirement in requirements:
        name = canonicalize_name(requirement.name)
        try:
            version = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            return None
        if requirement.specifier and not requirement.specifier.contains(version, prereleases=True):
            return None
        versions[name] = version
    return versions


def _fresh_versions(requirements: tuple[Requirement, ...]) -> dict[str, str] | None:
    names = [requirement.name for requirement in requirements]
    script = (
        "import importlib.metadata, json, sys; "
        "print(json.dumps({name: importlib.metadata.version(name) for name in sys.argv[1:]}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, *names],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode:
        return None
    try:
        values = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    versions = {str(canonicalize_name(name)): str(values[name]) for name in names}
    if any(
        requirement.specifier
        and not requirement.specifier.contains(
            versions[canonicalize_name(requirement.name)], prereleases=True
        )
        for requirement in requirements
    ):
        return None
    return versions


def _environment_identity() -> dict[str, str]:
    return {
        "executable": str(Path(sys.executable).resolve()),
        "prefix": str(Path(sys.prefix).resolve()),
        "python": platform.python_version(),
        "implementation": platform.python_implementation().lower(),
        "system": platform.system().lower() or sys.platform,
        "architecture": platform.machine().lower() or "unknown",
    }


def _fingerprint(source: str, requirements: tuple[Requirement, ...]) -> str:
    payload = {
        "schema": _SCHEMA,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "requirements": [str(requirement) for requirement in requirements],
        "environment": _environment_identity(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _cached_versions(path: Path, fingerprint: str) -> dict[str, str] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if value.get("schema") != _SCHEMA or value.get("fingerprint") != fingerprint:
        return None
    versions = value.get("versions")
    return (
        {str(name): str(version) for name, version in versions.items()}
        if isinstance(versions, dict)
        else None
    )


def _write_manifest(path: Path, fingerprint: str, versions: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    source = json.dumps(
        {
            "schema": _SCHEMA,
            "fingerprint": fingerprint,
            "environment": _environment_identity(),
            "versions": versions,
        },
        indent=2,
        sort_keys=True,
    )
    try:
        temporary.write_text(source + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError as error:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise PdfPythonRequirementsError(
            f"could not record PDF dependency state: {error}"
        ) from error


def _probe(requirements: tuple[Requirement, ...]) -> None:
    names = {canonicalize_name(requirement.name) for requirement in requirements}
    if "weasyprint" in names:
        result = run_probe(render=False)
        if result.returncode or result.pending:
            detail = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            if any(
                marker in detail.lower()
                for marker in ("libgobject", "pango", "harfbuzz", "cannot load library")
            ):
                raise PdfPythonRequirementsError(
                    "WeasyPrint is installed but cannot load its required native libraries. "
                    f"{pango_install_guidance()} Then retry `pdk pdf`."
                )
            raise PdfPythonRequirementsError(
                "WeasyPrint is installed but cannot load its macOS or Linux native libraries"
                + (f": {detail}" if detail else "")
            )
    if "pymupdf" in names:
        completed = subprocess.run(
            [sys.executable, "-c", "import pymupdf; print(pymupdf.__version__)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise PdfPythonRequirementsError(
                "PyMuPDF is installed but cannot import" + (f": {detail}" if detail else "")
            )


def prepare_pdf_python_requirements(
    config_file: str | Path,
    *,
    include_index: bool = False,
) -> PdfPythonPreparation:
    """Install once, validate, and record the active project's PDF packages."""

    config = Path(config_file).expanduser().resolve()
    root = config.parent
    environment_problem = project_environment_problem(root)
    if environment_problem:
        raise PdfPythonRequirementsError(environment_problem)
    path = requirements_path(root)
    source = _read_source(path)
    requirements = _requirements(source, include_index=include_index)
    fingerprint = _fingerprint(source, requirements)
    manifest = cache_manifest_path(root)
    installed = _installed_versions(requirements)
    cached = _cached_versions(manifest, fingerprint)
    if installed is not None and cached == installed:
        return PdfPythonPreparation(manifest.parent, True, installed)

    if installed is None and requirements:
        file_argument = path if path.is_file() and sys.platform != "win32" else None
        file_names = _active_file_names(source) if file_argument is not None else set()
        extra = tuple(
            str(requirement)
            for requirement in requirements
            if canonicalize_name(requirement.name) not in file_names
        )
        command = pip_install_requirements_command(file_argument, extra)
        try:
            run_install_command(command, root=root)
        except ToolchainError as error:
            raise PdfPythonRequirementsError(str(error)) from error
        importlib.invalidate_caches()
        clear_probe_cache()
        installed = _fresh_versions(requirements)
        if installed is None:
            raise PdfPythonRequirementsError(
                "pip finished but the PDF Python requirements are still not satisfied"
            )

    installed = installed or {}
    _probe(requirements)
    _write_manifest(manifest, fingerprint, installed)
    return PdfPythonPreparation(manifest.parent, cached == installed, installed)


def pdf_python_requirements_prepared(
    config_file: str | Path,
    *,
    include_index: bool = False,
) -> bool:
    """Whether the current environment matches an established preparation."""

    config = Path(config_file).expanduser().resolve()
    source = _read_source(requirements_path(config.parent))
    requirements = _requirements(source, include_index=include_index)
    installed = _installed_versions(requirements)
    return bool(
        installed is not None
        and _cached_versions(
            cache_manifest_path(config.parent), _fingerprint(source, requirements)
        )
        == installed
    )


def pdf_python_requirements_established(
    config_file: str | Path,
    *,
    include_index: bool = False,
) -> bool:
    """Whether a manifest exists for the current policy and environment."""

    config = Path(config_file).expanduser().resolve()
    source = _read_source(requirements_path(config.parent))
    active = _requirements(source, include_index=include_index)
    return (
        _cached_versions(
            cache_manifest_path(config.parent), _fingerprint(source, active)
        )
        is not None
    )


def weasyprint_executable() -> str:
    """Use the console script beside the active interpreter when present."""

    name = "weasyprint.exe" if os.name == "nt" else "weasyprint"
    candidate = Path(sys.executable).with_name(name)
    return str(candidate) if candidate.is_file() else name


__all__ = [
    "REQUIREMENTS_NAME",
    "STANDARD_REQUIREMENTS",
    "PdfPythonPreparation",
    "PdfPythonRequirementsError",
    "cache_manifest_path",
    "pdf_python_requirements_established",
    "pdf_python_requirements_prepared",
    "prepare_pdf_python_requirements",
    "requirements_path",
    "weasyprint_executable",
]

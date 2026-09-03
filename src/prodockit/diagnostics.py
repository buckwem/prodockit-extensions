# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Composable diagnostics and explicitly requested, narrowly scoped repairs."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from packaging.version import InvalidVersion, Version

import prodockit
from prodockit.config_diagnostics import inspect_config
from prodockit.pins import DEFAULT_PACKAGES, discover, resolve_latest
from prodockit.project_config import ProjectConfig, ProjectConfigError, load_project_config
from prodockit.project_integrity import renderer_requirements
from prodockit.renderer_health import find_browser, probe_mathjax, probe_mermaid
from prodockit.shared_files import SharedFileError
from prodockit.shared_files import inspect as inspect_shared_files

Status = Literal["pass", "warn", "fail"]
NODE_AUDIT_LEVEL = "moderate"
REPAIRABLE_DISTRIBUTIONS = ("prodockit", "zensical")


@dataclass(frozen=True)
class DiagnosticResult:
    """One stable diagnostic check and the evidence behind its status."""

    id: str
    section: str
    status: Status
    summary: str
    details: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "section": self.section,
            "status": self.status,
            "summary": self.summary,
            "details": list(self.details),
            "data": self.data,
        }


@dataclass(frozen=True)
class DiagnosticReport:
    """The complete deterministic result returned by :func:`inspect`."""

    config_file: str
    project_root: str
    online: bool
    checks: tuple[DiagnosticResult, ...]

    @property
    def status(self) -> Status:
        statuses = {check.status for check in self.checks}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        return "pass"

    @property
    def counts(self) -> dict[str, int]:
        return {
            status: sum(check.status == status for check in self.checks)
            for status in ("pass", "warn", "fail")
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "prodockit_version": prodockit.__version__,
            "status": self.status,
            "config_file": self.config_file,
            "project_root": self.project_root,
            "online": self.online,
            "summary": self.counts,
            "checks": [check.as_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)


@dataclass(frozen=True)
class CommandInfo:
    """A command resolved from PATH and the version it reports."""

    name: str
    path: str | None
    version: str | None
    error: str | None = None


@dataclass(frozen=True)
class DistributionMetadataEntry:
    """One repair-relevant metadata path found in active site-packages."""

    distribution: str
    version: str | None
    path: Path
    valid: bool


@dataclass(frozen=True)
class MetadataRepairResult:
    """Outcome of the opt-in duplicate metadata repair."""

    status: Literal["not-needed", "repaired"]
    moved: tuple[str, ...] = ()
    quarantine: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "moved": list(self.moved),
            "quarantine": self.quarantine,
        }


class MetadataRepairError(RuntimeError):
    """The requested repair cannot be proved safe."""


def _normalise_path(value: str, *, platform: str | None = None) -> str:
    """Normalize native or Windows paths without requiring that they exist."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return ntpath.normcase(ntpath.normpath(value))
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


def same_path(left: str, right: str, *, platform: str | None = None) -> bool:
    """Cross-platform path equality used by environment diagnostics and tests."""
    return _normalise_path(left, platform=platform) == _normalise_path(right, platform=platform)


def command_in_environment(
    command: str,
    prefix: str,
    scripts: str,
    *,
    platform: str | None = None,
) -> bool:
    """Return whether a command belongs to the active Python environment.

    Resolve POSIX symlinks so pipx shims are accepted when they point into the
    active prefix. Windows launchers are compared lexically because resolving a
    Windows path is not meaningful on a non-Windows test host.
    """
    platform = sys.platform if platform is None else platform
    path_module = ntpath if platform == "win32" else os.path
    candidates = [command]
    if platform != "win32":
        candidates.append(str(Path(command).resolve()))
    normalised_prefix = _normalise_path(prefix, platform=platform)
    normalised_scripts = _normalise_path(scripts, platform=platform)
    for candidate in candidates:
        normalised = _normalise_path(candidate, platform=platform)
        if _normalise_path(path_module.dirname(candidate), platform=platform) == normalised_scripts:
            return True
        try:
            if path_module.commonpath((normalised, normalised_prefix)) == normalised_prefix:
                return True
        except ValueError:
            continue
    return False


def _display_path(value: str | Path, root: Path) -> str:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    try:
        relative = resolved.relative_to(root.resolve())
        return "." if not relative.parts else relative.as_posix()
    except ValueError:
        pass
    try:
        relative = resolved.relative_to(Path.home().resolve())
        return "~" if not relative.parts else f"~/{relative.as_posix()}"
    except (OSError, ValueError):
        return str(resolved)


def _sanitise_text(value: str, root: Path) -> str:
    """Make subprocess and metadata evidence safe to attach to support."""
    text = re.sub(r"(https?://)[^/@\s]+@", r"\1", value)
    replacements = ((str(root.resolve()), "."), (str(Path.home().resolve()), "~"))
    for original, replacement in replacements:
        if len(original) > 1:
            text = text.replace(original, replacement)
    return text


def _run(
    command: list[str], *, cwd: Path | None = None, timeout: float = 10.0
) -> subprocess.CompletedProcess[str]:
    """Run one read-only probe with consistent text decoding and no prompts."""
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=environment,
    )


def _first_version(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)+(?:[A-Za-z0-9.+-]*))", text)
    return match.group(1) if match else None


def _command(name: str) -> CommandInfo:
    path = shutil.which(name)
    if path is None:
        return CommandInfo(name, None, None, "not found on PATH")
    try:
        completed = _run([path, "--version"])
    except (OSError, subprocess.SubprocessError) as error:
        return CommandInfo(name, path, None, str(error))
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if completed.returncode:
        return CommandInfo(name, path, None, output or f"exited {completed.returncode}")
    version = _first_version(output)
    return CommandInfo(name, path, version, None if version else "reported no version")


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _normalise_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _metadata_filename(path: Path) -> tuple[str | None, str | None, bool]:
    """Return a repairable name/version hinted by a dist-info filename."""
    suffix = ".dist-info"
    if not path.name.casefold().endswith(suffix):
        return None, None, False
    stem = path.name[: -len(suffix)].casefold().replace("_", "-")
    for distribution in REPAIRABLE_DISTRIBUTIONS:
        ordinary = f"{distribution}-"
        remnant = f"~{distribution[1:]}-"
        if stem.startswith(ordinary):
            return distribution, stem[len(ordinary) :] or None, False
        if stem.startswith(remnant):
            return distribution, stem[len(remnant) :] or None, True
    return None, None, False


def _metadata_headers(path: Path) -> tuple[str | None, str | None]:
    try:
        source = (path / "METADATA").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, None
    name: str | None = None
    version: str | None = None
    for line in source.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        if key.casefold() == "name":
            name = value.strip() or None
        elif key.casefold() == "version":
            version = value.strip() or None
        if name is not None and version is not None:
            break
    return name, version


def _known_distribution_version(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        Version(value)
    except InvalidVersion:
        return None
    return value


def _repair_metadata_entries(site_packages: tuple[Path, ...]) -> list[DistributionMetadataEntry]:
    """Scan only direct children of the active environment's library roots."""
    entries: list[DistributionMetadataEntry] = []
    seen: set[Path] = set()
    for library in site_packages:
        try:
            children = tuple(library.iterdir())
        except OSError as error:
            raise MetadataRepairError(
                f"cannot inspect active site-packages {library}: {error}"
            ) from error
        for path in children:
            filename_name, filename_version, remnant = _metadata_filename(path)
            metadata_name, metadata_version = _metadata_headers(path)
            normalized = (
                _normalise_distribution_name(metadata_name) if metadata_name is not None else None
            )
            distribution = (
                normalized if normalized in REPAIRABLE_DISTRIBUTIONS else filename_name
            )
            if distribution is None:
                continue
            try:
                identity = path.resolve()
            except OSError:
                identity = path.absolute()
            if identity in seen:
                continue
            seen.add(identity)
            versions_disagree = bool(
                metadata_version and filename_version and metadata_version != filename_version
            )
            version = _known_distribution_version(
                None if versions_disagree else metadata_version or filename_version
            )
            entries.append(
                DistributionMetadataEntry(
                    distribution,
                    version,
                    path,
                    bool(
                        not remnant
                        and normalized == distribution
                        and metadata_version
                        and not versions_disagree
                    ),
                )
            )
    return entries


def _running_repair_versions() -> dict[str, str]:
    versions = {"prodockit": prodockit.__version__}
    zensical = _command("zensical")
    scripts = sysconfig.get_path("scripts")
    if (
        zensical.path is not None
        and zensical.version is not None
        and zensical.error is None
        and command_in_environment(zensical.path, sys.prefix, scripts)
    ):
        versions["zensical"] = zensical.version
    return versions


def _active_site_packages(prefix: Path) -> tuple[Path, ...]:
    paths = sysconfig.get_paths()
    libraries: list[Path] = []
    for key in ("purelib", "platlib"):
        value = paths.get(key)
        if not value:
            continue
        library = Path(value).resolve()
        try:
            library.relative_to(prefix)
        except ValueError as error:
            raise MetadataRepairError(
                f"active {key} path is outside the running environment: {library}"
            ) from error
        if library not in libraries:
            libraries.append(library)
    if not libraries:
        raise MetadataRepairError("the running environment has no site-packages directory")
    return tuple(libraries)


def distribution_metadata_problems() -> tuple[str, ...]:
    """Describe supported metadata ambiguity in the active virtualenv.

    System and externally managed installations remain the responsibility of
    their package manager. This preflight exists for workflows that must not
    continue with ambiguous Prodockit or Zensical versions.
    """
    prefix = Path(sys.prefix).resolve()
    if prefix == Path(sys.base_prefix).resolve():
        return ()
    entries = _repair_metadata_entries(_active_site_packages(prefix))
    problems: list[str] = []
    for distribution in REPAIRABLE_DISTRIBUTIONS:
        group = [entry for entry in entries if entry.distribution == distribution]
        if len(group) > 1 or any(not entry.valid for entry in group):
            found = ", ".join(
                f"{entry.path.name} ({entry.version or 'unknown version'})" for entry in group
            )
            problems.append(f"{distribution}: {found}")
    return tuple(problems)


def repair_distribution_metadata(
    root: Path,
    *,
    prefix: Path | None = None,
    base_prefix: Path | None = None,
    site_packages: tuple[Path, ...] | None = None,
    current_versions: dict[str, str] | None = None,
    timestamp: str | None = None,
) -> MetadataRepairResult:
    """Quarantine only provably stale Prodockit or Zensical metadata.

    Optional arguments make the filesystem safety rules directly testable;
    the CLI always uses the running interpreter's own environment.
    """
    active_prefix = (prefix or Path(sys.prefix)).resolve()
    running_base = (base_prefix or Path(sys.base_prefix)).resolve()
    if active_prefix == running_base:
        raise MetadataRepairError(
            "metadata repair is only available inside an active virtual environment; "
            "no system or externally managed Python files were changed"
        )
    declared = os.environ.get("VIRTUAL_ENV")
    if prefix is None and declared and not same_path(declared, str(active_prefix)):
        raise MetadataRepairError(
            "VIRTUAL_ENV does not match the Python running Prodockit; activate the intended "
            "environment before using `pdk diag --fix`"
        )

    libraries = site_packages or _active_site_packages(active_prefix)
    resolved_libraries: list[Path] = []
    for library in libraries:
        resolved = library.resolve()
        try:
            resolved.relative_to(active_prefix)
        except ValueError as error:
            raise MetadataRepairError(
                f"refusing metadata outside the active environment: {resolved}"
            ) from error
        if resolved not in resolved_libraries:
            resolved_libraries.append(resolved)
    entries = _repair_metadata_entries(tuple(resolved_libraries))
    versions = current_versions or _running_repair_versions()

    stale: list[DistributionMetadataEntry] = []
    ambiguous: list[str] = []
    affected: set[str] = set()
    for distribution in REPAIRABLE_DISTRIBUTIONS:
        group = [entry for entry in entries if entry.distribution == distribution]
        if len(group) <= 1 and all(entry.valid for entry in group):
            continue
        if not group:
            continue
        affected.add(distribution)
        current = versions.get(distribution)
        matching = [entry for entry in group if entry.valid and entry.version == current]
        obsolete = [
            entry for entry in group if entry.version is not None and entry.version != current
        ]
        if current is None or len(matching) != 1 or len(obsolete) != len(group) - 1:
            found = ", ".join(
                f"{entry.path.name} ({entry.version or 'unknown version'})" for entry in group
            )
            ambiguous.append(f"{distribution}: {found}")
        else:
            stale.extend(obsolete)
    if ambiguous:
        detail = "; ".join(ambiguous)
        raise MetadataRepairError(
            "cannot prove which metadata is stale: "
            f"{detail}. Rebuild the active virtual environment at {active_prefix}, "
            "reinstall the project requirements, then rerun `pdk diag`"
        )
    if not stale:
        return MetadataRepairResult("not-needed")

    moment = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    quarantine = active_prefix / ".prodockit-quarantine" / "distribution-metadata" / moment
    moved: list[tuple[DistributionMetadataEntry, Path]] = []
    try:
        for entry in stale:
            if entry.path.is_symlink():
                raise MetadataRepairError(f"refusing symlinked metadata: {entry.path}")
            library_index = resolved_libraries.index(entry.path.parent.resolve())
            destination = quarantine / f"site-{library_index}" / entry.path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry.path), str(destination))
            moved.append((entry, destination))

        importlib.invalidate_caches()
        remaining = _repair_metadata_entries(tuple(resolved_libraries))
        for distribution in affected:
            group = [entry for entry in remaining if entry.distribution == distribution]
            current = versions.get(distribution)
            if len(group) != 1 or not group[0].valid or group[0].version != current:
                raise MetadataRepairError(
                    f"verification still found ambiguous {distribution} metadata"
                )

        manifest = {
            "created": moment,
            "entries": [
                {
                    "distribution": entry.distribution,
                    "version": entry.version,
                    "original": str(entry.path),
                    "quarantined": str(destination),
                }
                for entry, destination in moved
            ],
        }
        (quarantine / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (MetadataRepairError, OSError) as error:
        for entry, destination in reversed(moved):
            if destination.exists() and not entry.path.exists():
                shutil.move(str(destination), str(entry.path))
        importlib.invalidate_caches()
        if isinstance(error, MetadataRepairError):
            raise
        raise MetadataRepairError(f"metadata repair failed and was rolled back: {error}") from error

    return MetadataRepairResult(
        "repaired",
        tuple(_display_path(entry.path, root) for entry, _destination in moved),
        _display_path(quarantine, root),
    )


def _environment_checks(root: Path) -> list[DiagnosticResult]:
    executable = _display_path(sys.executable, root)
    prefix = _display_path(sys.prefix, root)
    base_prefix = _display_path(sys.base_prefix, root)
    active = sys.prefix != sys.base_prefix
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks = [
        DiagnosticResult(
            "environment.python",
            "Environment and installation",
            "pass",
            f"Python {python_version}",
            (f"executable: {executable}", f"prefix: {prefix}", f"base prefix: {base_prefix}"),
            {
                "version": python_version,
                "executable": executable,
                "prefix": prefix,
                "base_prefix": base_prefix,
                "isolated_environment": active,
            },
        )
    ]

    declared = os.environ.get("VIRTUAL_ENV")
    if declared and not same_path(declared, sys.prefix):
        checks.append(
            DiagnosticResult(
                "environment.virtual-env",
                "Environment and installation",
                "fail",
                "VIRTUAL_ENV does not match the Python running Prodockit",
                (
                    f"VIRTUAL_ENV: {_display_path(declared, root)}",
                    f"running prefix: {prefix}",
                    "activate the intended environment or select its interpreter, "
                    "then reopen the shell",
                ),
                {"declared": _display_path(declared, root), "running_prefix": prefix},
            )
        )
    elif declared:
        checks.append(
            DiagnosticResult(
                "environment.virtual-env",
                "Environment and installation",
                "pass",
                "VIRTUAL_ENV matches the running interpreter",
                (f"VIRTUAL_ENV: {_display_path(declared, root)}",),
            )
        )
    else:
        checks.append(
            DiagnosticResult(
                "environment.virtual-env",
                "Environment and installation",
                "pass",
                "No VIRTUAL_ENV is declared",
                ("this is valid for pipx, Conda, system Python and clean CI installations",),
            )
        )
    return checks


def _installation_checks(root: Path) -> list[DiagnosticResult]:
    expected = {
        "pdk": prodockit.__version__,
        "prodockit": prodockit.__version__,
        "zensical": _distribution_version("zensical"),
    }
    commands = [_command(name) for name in expected]
    active_scripts = sysconfig.get_path("scripts")
    details: list[str] = []
    failures: list[str] = []
    for command in commands:
        location = _display_path(command.path, root) if command.path else "missing"
        reported = command.version or "unknown"
        details.append(f"{command.name}: {reported} at {location}")
        wanted = expected[command.name]
        if command.path is None or command.error:
            failures.append(f"{command.name}: {_sanitise_text(command.error or 'missing', root)}")
        elif wanted is None:
            failures.append(f"{command.name}: installed distribution metadata is missing")
        elif command.version != wanted:
            failures.append(
                f"{command.name}: command reports {command.version}, active Python loads {wanted}"
            )
        elif not command_in_environment(command.path, sys.prefix, active_scripts):
            failures.append(
                f"{command.name}: command resolves outside the active Python environment"
            )

    script_dir = _display_path(active_scripts, root)
    details.append(f"active scripts directory: {script_dir}")
    checks = [
        DiagnosticResult(
            "installation.commands",
            "Environment and installation",
            "fail" if failures else "pass",
            "Command locations and loaded distributions disagree"
            if failures
            else "Prodockit and Zensical commands match the active Python",
            tuple(details + failures),
            {
                "commands": [
                    {
                        "name": item.name,
                        "path": _display_path(item.path, root) if item.path else None,
                        "version": item.version,
                        "error": _sanitise_text(item.error, root) if item.error else None,
                    }
                    for item in commands
                ],
                "active_scripts_directory": script_dir,
            },
        )
    ]

    try:
        pip_check = _run([sys.executable, "-m", "pip", "check"], timeout=30)
        pip_text = _sanitise_text(
            "\n".join(
                part.strip() for part in (pip_check.stdout, pip_check.stderr) if part.strip()
            ),
            root,
        )
        checks.append(
            DiagnosticResult(
                "installation.dependencies",
                "Environment and installation",
                "pass" if pip_check.returncode == 0 else "fail",
                "Installed dependencies are compatible"
                if pip_check.returncode == 0
                else "Installed dependencies are incompatible or missing",
                tuple(pip_text.splitlines()),
                {"returncode": pip_check.returncode},
            )
        )
    except (OSError, subprocess.SubprocessError) as error:
        checks.append(
            DiagnosticResult(
                "installation.dependencies",
                "Environment and installation",
                "fail",
                "Could not run the active Python's pip check",
                (_sanitise_text(str(error), root),),
            )
        )

    locations: dict[str, set[str]] = {}
    invalid: list[str] = []
    for distribution in importlib.metadata.distributions():
        try:
            name = distribution.metadata["Name"]
            version = distribution.version
            if not name or not version:
                invalid.append(str(getattr(distribution, "_path", "unknown metadata")))
                continue
            normalized = _normalise_distribution_name(name)
            locations.setdefault(normalized, set()).add(
                str(getattr(distribution, "_path", distribution.locate_file("")))
            )
        except (KeyError, OSError, UnicodeError, ValueError) as error:
            invalid.append(str(error))
    duplicates = {name: sorted(paths) for name, paths in locations.items() if len(paths) > 1}
    metadata_details = [
        f"invalid metadata: {_sanitise_text(item, root)}" for item in sorted(invalid)
    ]
    metadata_details.extend(
        f"duplicate {name}: {', '.join(_display_path(path, root) for path in paths)}"
        for name, paths in sorted(duplicates.items())
    )
    repair_candidates = set(duplicates).intersection(REPAIRABLE_DISTRIBUTIONS)
    for item in invalid:
        repair_distribution, _version, _remnant = _metadata_filename(Path(item))
        if repair_distribution is not None:
            repair_candidates.add(repair_distribution)
    if repair_candidates:
        metadata_details.append(
            "run `pdk diag --fix` to quarantine stale Prodockit or Zensical metadata "
            "when exactly one entry matches the loaded package"
        )
    checks.append(
        DiagnosticResult(
            "installation.metadata",
            "Environment and installation",
            "warn" if metadata_details else "pass",
            "Duplicate or invalid distribution metadata found"
            if metadata_details
            else "Distribution metadata is readable and unique",
            tuple(metadata_details),
            {
                "invalid_count": len(invalid),
                "duplicate_names": sorted(duplicates),
                "fix_candidates": sorted(repair_candidates),
            },
        )
    )
    return checks


def _configuration_check(config_file: Path) -> tuple[ProjectConfig | None, DiagnosticResult]:
    try:
        config = load_project_config(config_file)
        report = inspect_config(config)
    except ProjectConfigError as error:
        return None, DiagnosticResult(
            "project.configuration",
            "Project configuration and inputs",
            "fail",
            "Project configuration could not be loaded",
            (str(error), "run `pdk config --check` for the detailed configuration report"),
        )
    details = tuple(f"{item.path}: {item.message}" for item in report.diagnostics)
    return config, DiagnosticResult(
        "project.configuration",
        "Project configuration and inputs",
        "fail" if details else "pass",
        f"Configuration has {len(details)} actionable problem(s)"
        if details
        else "Configuration and local project inputs pass",
        details + (("run `pdk config --check` for the complete report",) if details else ()),
        {"config_file": _display_path(report.path, config.root), "problem_count": len(details)},
    )


def _pin_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    states = discover(str(root), DEFAULT_PACKAGES)
    resolve_latest(states, offline=not online)
    inconsistent = [state for state in states.values() if not state.is_consistent]
    behind = [state for state in states.values() if state.is_behind]
    lookup_errors = [
        f"{state.package}: {state.latest_error}"
        for state in states.values()
        if online and state.on_pypi and state.latest is None and state.latest_error
    ]
    details = [f"{state.package}: {', '.join(state.versions)}" for state in inconsistent]
    details.extend(
        f"{state.package}: {state.current} -> {state.latest} available" for state in behind
    )
    details.extend(lookup_errors)
    status: Status = "fail" if inconsistent else ("warn" if behind or lookup_errors else "pass")
    summary = (
        f"{len(inconsistent)} package declaration(s) are inconsistent"
        if inconsistent
        else f"{len(behind)} package update(s) are available"
        if behind
        else "Package declarations are consistent"
    )
    checks = [
        DiagnosticResult(
            "dependencies.pins",
            "Dependency and managed-file consistency",
            status,
            summary,
            tuple(details),
            {
                "online": online,
                "inconsistent": [state.package for state in inconsistent],
                "updates": [state.package for state in behind],
            },
        )
    ]
    try:
        shared = list(inspect_shared_files(root))
        drift = [state for state in shared if state.status != "current"]
        checks.append(
            DiagnosticResult(
                "dependencies.shared-files",
                "Dependency and managed-file consistency",
                "fail" if drift else "pass",
                f"{len(drift)} managed shared file(s) have drifted"
                if drift
                else "Managed shared files match the installed release",
                tuple(f"{state.file.target}: {state.status}" for state in drift),
                {"declared": len(shared), "drifted": len(drift)},
            )
        )
    except SharedFileError as error:
        checks.append(
            DiagnosticResult(
                "dependencies.shared-files",
                "Dependency and managed-file consistency",
                "fail",
                "Managed shared files could not be inspected",
                (str(error),),
            )
        )
    return checks


def _project_tool(root: Path, configured: object, defaults: tuple[str, ...]) -> Path | None:
    if configured:
        candidate = Path(str(configured))
        candidate = candidate if candidate.is_absolute() else root / candidate
        return candidate if candidate.is_file() else None
    for default in defaults:
        candidate = root / default
        for spelling in (candidate, Path(f"{candidate}.cmd"), Path(f"{candidate}.exe")):
            if spelling.is_file():
                return spelling
    return None


def _tool_result(
    check_id: str,
    name: str,
    command: str,
    *,
    root: Path,
    required: bool,
) -> DiagnosticResult:
    info = _command(command)
    if info.path and not info.error:
        return DiagnosticResult(
            check_id,
            "Rendering toolchain",
            "pass",
            f"{name} {info.version or 'is available'}",
            (f"path: {_display_path(info.path, root)}",),
            {"required": required, "path": _display_path(info.path, root), "version": info.version},
        )
    return DiagnosticResult(
        check_id,
        "Rendering toolchain",
        "fail" if required else "warn",
        f"{name} is missing" + (" but required by this project" if required else " (optional)"),
        ((info.error or "not found"),),
        {"required": required, "path": None, "version": None},
    )


def _renderer_checks(config: ProjectConfig | None, root: Path) -> list[DiagnosticResult]:
    pdf_required = bool(
        config
        and any(
            config.extra.get(key)
            for key in ("pdf_output", "pdf_source_bundle_output", "pdf_extra_css")
        )
    )
    mermaid_required, maths_required = renderer_requirements(config) if config else (False, False)
    node_required = mermaid_required or maths_required
    checks = [_tool_result("renderer.pandoc", "Pandoc", "pandoc", root=root, required=pdf_required)]

    try:
        module = importlib.import_module("weasyprint")
        version = str(getattr(module, "__version__", "unknown"))
        checks.append(
            DiagnosticResult(
                "renderer.weasyprint",
                "Rendering toolchain",
                "pass",
                f"WeasyPrint {version} imports with its native libraries",
                (),
                {"required": pdf_required, "version": version},
            )
        )
    except Exception as error:  # native-loader failures are not ImportError
        checks.append(
            DiagnosticResult(
                "renderer.weasyprint",
                "Rendering toolchain",
                "fail" if pdf_required else "warn",
                "WeasyPrint cannot import"
                + (" but is required by this project" if pdf_required else " (optional)"),
                (f"{type(error).__name__}: {error}",),
                {"required": pdf_required},
            )
        )

    checks.extend(
        (
            _tool_result("renderer.node", "Node", "node", root=root, required=node_required),
            _tool_result("renderer.npm", "npm", "npm", root=root, required=node_required),
        )
    )

    mmdc = None
    tex2svg = None
    if config:
        mmdc = _project_tool(
            root,
            config.extra.get("pdf_mmdc_bin"),
            ("tools/mermaid/node_modules/.bin/mmdc", "node_modules/.bin/mmdc"),
        ) or (Path(found) if (found := shutil.which("mmdc")) else None)
        tex2svg = _project_tool(
            root,
            config.extra.get("pdf_tex2svg_script"),
            ("tools/mathjax/tex2svg.js",),
        )
    mmdc_probe = probe_mermaid(mmdc) if mmdc else None
    mmdc_ok = bool(mmdc_probe and mmdc_probe.ok)
    checks.append(
        DiagnosticResult(
            "renderer.mermaid",
            "Rendering toolchain",
            "pass" if mmdc_ok else ("fail" if mermaid_required else "warn"),
            "Mermaid CLI is available"
            if mmdc_ok
            else ("Mermaid CLI is unusable" if mmdc else "Mermaid CLI is missing")
            + (" but required by this project" if mermaid_required else " (optional)"),
            tuple(
                detail
                for detail in (
                    f"path: {_display_path(mmdc, root)}" if mmdc else None,
                    f"health probe: {mmdc_probe.error}"
                    if mmdc_probe and mmdc_probe.error
                    else None,
                )
                if detail
            ),
            {
                "required": mermaid_required,
                "path": _display_path(mmdc, root) if mmdc else None,
                "version": mmdc_probe.version if mmdc_probe else None,
                "error": mmdc_probe.error if mmdc_probe else None,
            },
        )
    )

    browser = find_browser()
    browser_version = None
    browser_error = None
    if browser:
        try:
            browser_result = _run([browser, "--version"])
            browser_output = "\n".join(
                part.strip()
                for part in (browser_result.stdout, browser_result.stderr)
                if part.strip()
            )
            if browser_result.returncode:
                browser_error = browser_output or f"exited {browser_result.returncode}"
            else:
                browser_version = _first_version(browser_output)
                if browser_version is None:
                    browser_error = "reported no version"
        except (OSError, subprocess.SubprocessError) as error:
            browser_error = str(error)
    browser_ok = bool(browser and not browser_error)
    browser_status: Status = (
        "pass" if browser_ok else ("fail" if browser and mermaid_required else "warn")
    )
    checks.append(
        DiagnosticResult(
            "renderer.browser",
            "Rendering toolchain",
            browser_status,
            "Browser executable can run"
            if browser_ok
            else (
                "Browser executable is unusable"
                if browser
                else "No explicit Chrome/Chromium executable found"
            )
            + (
                "; Mermaid CLI may use its bundled browser"
                if not browser and mermaid_required
                else " (optional)" if not mermaid_required else ""
            ),
            tuple(
                detail
                for detail in (
                    f"path: {_display_path(browser, root)}" if browser else None,
                    f"health probe: {browser_error}" if browser_error else None,
                )
                if detail
            ),
            {
                "required": mermaid_required,
                "path": _display_path(browser, root) if browser else None,
                "version": browser_version,
                "error": browser_error,
            },
        )
    )

    mathjax_modules = root / "tools" / "mathjax" / "node_modules" / "mathjax-full"
    node = shutil.which("node")
    mathjax_probe = probe_mathjax(node, tex2svg) if node and tex2svg else None
    mathjax_ok = bool(mathjax_modules.is_dir() and mathjax_probe and mathjax_probe.ok)
    math_details = []
    if tex2svg:
        math_details.append(f"script: {_display_path(tex2svg, root)}")
    if mathjax_modules.is_dir():
        math_details.append(f"inputs: {_display_path(mathjax_modules, root)}")
    if tex2svg and node is None:
        math_details.append("health probe: node is not found on PATH")
    elif mathjax_probe and mathjax_probe.error:
        math_details.append(f"health probe: {mathjax_probe.error}")
    checks.append(
        DiagnosticResult(
            "renderer.mathjax",
            "Rendering toolchain",
            "pass" if mathjax_ok else ("fail" if maths_required else "warn"),
            "MathJax can render an expression"
            if mathjax_ok
            else "MathJax PDF renderer is incomplete"
            + (" but required by this project" if maths_required else " (optional)"),
            tuple(math_details),
            {
                "required": maths_required,
                "script": _display_path(tex2svg, root) if tex2svg else None,
                "inputs": _display_path(mathjax_modules, root)
                if mathjax_modules.is_dir()
                else None,
                "error": (
                    mathjax_probe.error
                    if mathjax_probe
                    else "node is not found on PATH" if tex2svg else None
                ),
            },
        )
    )
    return checks


def _node_security_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    """Audit the Mermaid production graph only when network checks are requested."""
    tool_root = root / "tools" / "mermaid"
    lockfile = tool_root / "package-lock.json"
    if not lockfile.is_file():
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "pass",
                "Mermaid security audit is not applicable",
                ("tools/mermaid/package-lock.json is not present",),
                {"checked": False, "reason": "not-configured"},
            )
        ]
    if not online:
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "pass",
                "Mermaid security audit skipped in offline mode",
                ("run `pdk diag --online` to query the npm advisory service",),
                {"checked": False, "reason": "offline", "level": NODE_AUDIT_LEVEL},
            )
        ]
    npm = shutil.which("npm")
    if npm is None:
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "warn",
                "Mermaid security audit could not run because npm is missing",
                ("install npm, then rerun `pdk diag --online`",),
                {"checked": False, "reason": "npm-missing", "level": NODE_AUDIT_LEVEL},
            )
        ]
    command = [npm, "audit", "--omit=dev", f"--audit-level={NODE_AUDIT_LEVEL}", "--json"]
    completed = _run(command, cwd=tool_root, timeout=60)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    raw_counts = metadata.get("vulnerabilities", {}) if isinstance(metadata, dict) else {}
    counts = {
        severity: int(raw_counts.get(severity, 0)) if isinstance(raw_counts, dict) else 0
        for severity in ("low", "moderate", "high", "critical")
    }
    affected = sum(counts[severity] for severity in ("moderate", "high", "critical"))
    data = {
        "checked": True,
        "level": NODE_AUDIT_LEVEL,
        "vulnerabilities": counts,
    }
    if affected:
        details = (
            *(f"{severity}: {count}" for severity, count in counts.items() if count),
            "run `npm audit --omit=dev` in tools/mermaid for remediation detail",
        )
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "warn",
                f"Mermaid dependencies have {affected} moderate-or-higher advisories",
                details,
                data,
            )
        ]
    if completed.returncode:
        evidence = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"npm audit exited {completed.returncode}"
        )
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "warn",
                "Mermaid security audit was unavailable",
                (_sanitise_text(evidence, root),),
                {**data, "checked": False, "reason": "audit-error"},
            )
        ]
    return [
        DiagnosticResult(
            "renderer.mermaid-security",
            "Rendering toolchain",
            "pass",
            "Mermaid dependencies have no moderate-or-higher advisories",
            (),
            data,
        )
    ]


def _repository_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    git = shutil.which("git")
    if git is None:
        return [
            DiagnosticResult(
                "repository.git",
                "Repository and template maintenance",
                "warn",
                "Git is not available; repository macros and publishing metadata cannot be checked",
            )
        ]
    try:
        top = _run([git, "-C", str(root), "rev-parse", "--show-toplevel"])
    except (OSError, subprocess.SubprocessError) as error:
        return [
            DiagnosticResult(
                "repository.git",
                "Repository and template maintenance",
                "warn",
                "Git repository could not be inspected",
                (str(error),),
            )
        ]
    if top.returncode:
        return [
            DiagnosticResult(
                "repository.git",
                "Repository and template maintenance",
                "warn",
                "Project is not inside a Git repository",
                (top.stderr.strip(),) if top.stderr.strip() else (),
            )
        ]
    git_root = Path(top.stdout.strip()).resolve()
    remotes = _run([git, "-C", str(git_root), "remote", "-v"])
    remote_lines = tuple(
        dict.fromkeys(line for line in remotes.stdout.splitlines() if line.strip())
    )
    checks = [
        DiagnosticResult(
            "repository.git",
            "Repository and template maintenance",
            "pass",
            f"Git repository found at {_display_path(git_root, root)}",
            tuple(_sanitise_text(line, root) for line in remote_lines)
            or ("no remotes configured",),
            {
                "root": _display_path(git_root, root),
                "remotes": [_sanitise_text(line, root) for line in remote_lines],
            },
        )
    ]

    from prodockit.template_sync import (
        MANIFEST_FILE,
        STAMP_FILE,
        TemplateSyncError,
        load_manifest,
        read_template_stamp,
        resolve_template,
    )

    metadata_details: list[str] = []
    metadata_failures: list[str] = []
    manifest_path = root / MANIFEST_FILE
    if manifest_path.is_file():
        try:
            manifest = load_manifest(manifest_path.read_text(encoding="utf-8"))
            ownership_rules = sum(
                map(
                    len,
                    (
                        manifest.template_owns,
                        manifest.project_owns,
                        manifest.shared,
                        manifest.excluded,
                    ),
                )
            )
            metadata_details.append(f"{MANIFEST_FILE}: {ownership_rules} ownership rule(s)")
        except (OSError, UnicodeError, TemplateSyncError) as error:
            metadata_failures.append(str(error))
    try:
        stamp_record = read_template_stamp(root)
    except OSError as error:
        stamp_record = None
        metadata_failures.append(f"{STAMP_FILE}: {error}")
    stamp = stamp_record.revision if stamp_record else None
    applied_release = stamp_record.applied_release if stamp_record else None
    if stamp:
        metadata_details.append(f"{STAMP_FILE} revision: {stamp}")
        if applied_release:
            metadata_details.append(
                f"Successfully applied template release: {applied_release}"
            )
        else:
            metadata_details.append("Successfully applied template release: not recorded")
    elif (root / STAMP_FILE).exists():
        metadata_failures.append(f"{STAMP_FILE} is empty")
    checks.append(
        DiagnosticResult(
            "repository.template-metadata",
            "Repository and template maintenance",
            "fail" if metadata_failures else "pass",
            "Local template metadata is invalid"
            if metadata_failures
            else "Local template metadata is valid or not present",
            tuple(metadata_details + metadata_failures),
            {
                "stamp": stamp,
                "applied_release": applied_release,
                "manifest_present": manifest_path.is_file(),
            },
        )
    )

    if online and stamp:
        origin = None
        for line in remote_lines:
            fields = line.split()
            if len(fields) >= 2 and fields[0] == "origin" and fields[-1] == "(fetch)":
                origin = fields[1]
                break
        try:
            remote = resolve_template(origin)
            latest = _run([git, "ls-remote", remote, "HEAD"], timeout=15)
            head = (
                latest.stdout.split()[0]
                if latest.returncode == 0 and latest.stdout.split()
                else None
            )
            if head is None:
                raise TemplateSyncError(latest.stderr.strip() or "template host returned no HEAD")
            update = not head.startswith(stamp) and not stamp.startswith(head)
            checks.append(
                DiagnosticResult(
                    "repository.template-update",
                    "Repository and template maintenance",
                    "warn" if update else "pass",
                    "A newer template revision may be available"
                    if update
                    else "Recorded template revision matches the template HEAD",
                    (f"recorded: {stamp}", f"template HEAD: {head}"),
                    {
                        "recorded": stamp,
                        "latest": head,
                        "remote": _sanitise_text(remote, root),
                    },
                )
            )
        except (OSError, subprocess.SubprocessError, TemplateSyncError) as error:
            checks.append(
                DiagnosticResult(
                    "repository.template-update",
                    "Repository and template maintenance",
                    "warn",
                    "Online template comparison was unavailable",
                    (_sanitise_text(str(error), root),),
                )
            )
    return checks


def inspect(config_file: str | Path = "zensical.toml", *, online: bool = False) -> DiagnosticReport:
    """Inspect the active environment and project without changing either."""
    requested = Path(config_file).expanduser().resolve()
    root = requested.parent
    try:
        config, config_check = _configuration_check(requested)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
        config = None
        config_check = DiagnosticResult(
            "project.configuration",
            "Project configuration and inputs",
            "fail",
            "Project configuration could not be inspected",
            (_sanitise_text(str(error), root),),
        )
    if config is not None:
        root = config.root
    checks: list[DiagnosticResult] = []

    def collect(
        check_id: str,
        section: str,
        name: str,
        probe: Callable[[], list[DiagnosticResult]],
    ) -> None:
        try:
            checks.extend(probe())
        except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
            checks.append(
                DiagnosticResult(
                    check_id,
                    section,
                    "fail",
                    f"{name} could not be inspected",
                    (_sanitise_text(str(error), root),),
                )
            )

    collect(
        "environment.inspection",
        "Environment and installation",
        "The Python environment",
        lambda: _environment_checks(root),
    )
    collect(
        "installation.inspection",
        "Environment and installation",
        "The active installation",
        lambda: _installation_checks(root),
    )
    checks.append(config_check)
    collect(
        "dependencies.inspection",
        "Dependency and managed-file consistency",
        "Dependency and managed-file consistency",
        lambda: _pin_checks(root, online),
    )
    collect(
        "renderer.inspection",
        "Rendering toolchain",
        "The rendering toolchain",
        lambda: _renderer_checks(config, root),
    )
    collect(
        "renderer.security-inspection",
        "Rendering toolchain",
        "The Mermaid security audit",
        lambda: _node_security_checks(root, online),
    )
    collect(
        "repository.inspection",
        "Repository and template maintenance",
        "Repository and template metadata",
        lambda: _repository_checks(root, online),
    )
    return DiagnosticReport(
        config_file=_display_path(requested, root),
        project_root=_display_path(root, Path.cwd()),
        online=online,
        checks=tuple(checks),
    )


__all__ = [
    "CommandInfo",
    "DiagnosticReport",
    "DiagnosticResult",
    "command_in_environment",
    "inspect",
    "same_path",
]

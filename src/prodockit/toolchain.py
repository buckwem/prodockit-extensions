# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Align an adopted project's active tools with Prodockit's tested versions.

The tested-version manifest lives in :mod:`prodockit.pins`.  This module is
deliberately a consumer of that manifest: Adopt, Pins and Diagnostics must not
grow three subtly different answers to "which combination is supported?".
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from prodockit.installer_process import InstallerCleanupError, run_installer
from prodockit.pins import (
    DEFAULT_PACKAGES,
    TESTED_VERSIONS,
    PackageState,
    PinError,
    apply_version,
    discover,
)
from prodockit.renderer_resilience import (
    DEFAULT_RETRY_DELAYS,
    RetryReporter,
    failure_with_history,
    run_with_retries,
)

TOOLCHAIN_MANIFEST = ".prodockit-toolchain.toml"
WHEELHOUSE_ENV = "PDK_WHEELHOUSE"
PYPI_MIRROR_ENV = "PDK_PYPI_MIRROR"
DOWNLOAD_CACHE_ENV = "PDK_NATIVE_DOWNLOAD_CACHE"

PYTHON_PACKAGES = (
    "zensical",
    "prodockit",
    "markdown",
    "pymdown-extensions",
)
DISPLAY_NAMES: Mapping[str, str] = {
    "zensical": "Zensical",
    "weasyprint": "WeasyPrint",
    "prodockit": "Prodockit",
    "markdown": "Markdown",
    "pymdown-extensions": "PyMdown Extensions",
    "python": "Python",
}


class ToolchainError(RuntimeError):
    """The supported toolchain could not be planned, installed or verified."""


@dataclass(frozen=True)
class ToolAction:
    package: str
    installed: str | None
    supported: str
    action: str

    @property
    def description(self) -> str:
        name = DISPLAY_NAMES[self.package]
        if self.action == "install":
            return f"install {name} {self.supported}"
        if self.action == "repair":
            return f"repair {name} {self.supported} Python dependencies"
        return f"{self.action} {name} {self.installed} to {self.supported}"


@dataclass(frozen=True)
class ToolchainPlan:
    actions: tuple[ToolAction, ...]
    declaration_changes: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    files: tuple[Path, ...]
    blocked: str = ""
    offline: bool = False

    @property
    def needs_work(self) -> bool:
        return bool(self.actions or self.declaration_changes)

    @property
    def detail(self) -> str:
        if self.blocked:
            return self.blocked
        changes = [action.description for action in self.actions]
        if self.declaration_changes:
            changes.append("align version declarations in " + ", ".join(self.declaration_changes))
        return "; ".join(changes) if changes else "all installed tools and declarations match"


def _normalise_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None


def _action(package: str, installed: str | None) -> ToolAction | None:
    supported = TESTED_VERSIONS[package]
    if installed == supported:
        return None
    if installed is None:
        kind = "install"
    else:
        current = _normalise_version(installed)
        wanted = _normalise_version(supported)
        if current is None or wanted is None:
            kind = "align"
        else:
            kind = "upgrade" if current < wanted else "downgrade"
    return ToolAction(package, installed, supported, kind)


def installed_distribution_version(package: str) -> str | None:
    """Return a distribution version without importing the package itself."""

    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _fresh_distribution_versions(packages: Sequence[str]) -> dict[str, str | None]:
    """Read metadata in a new interpreter after pip has changed it."""

    script = """\
import importlib.metadata
import json
import sys

versions = {}
for name in sys.argv[1:]:
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        versions[name] = None
print(json.dumps(versions))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, *packages],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ToolchainError(f"could not verify installed package versions: {result.stderr}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ToolchainError(
            "installed package version verification returned invalid data"
        ) from error
    return {package: value.get(package) for package in packages}


def installed_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _requirements_path(root: Path) -> Path:
    candidates = (
        Path("requirements.txt"),
        Path("requirements/docs.txt"),
        Path("docs/requirements.txt"),
    )
    return next(
        (root / item for item in candidates if (root / item).is_file()),
        root / candidates[0],
    )


def _local_declarations(root: Path) -> dict[str, PackageState]:
    """Leave CI files to the baseline-verified workflow planner, not Pins."""
    states = discover(str(root))
    for state in states.values():
        state.sites = [
            site
            for site in state.sites
            if not (
                site.path.replace("\\", "/").startswith((".github/workflows/", ".gitlab/"))
                or site.path in {".gitlab-ci.yml", ".gitlab-ci.yaml"}
            )
        ]
    return states


def _declarations(root: Path) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    states = _local_declarations(root)
    changed: set[str] = set()
    for package in DEFAULT_PACKAGES:
        state = states[package]
        if not state.sites or any(site.version != TESTED_VERSIONS[package] for site in state.sites):
            changed.update(site.path for site in state.sites)
            if not state.sites:
                changed.add(TOOLCHAIN_MANIFEST)

    requirements = _requirements_path(root)
    source = requirements.read_text(encoding="utf-8") if requirements.is_file() else ""
    for package in PYTHON_PACKAGES:
        pattern = re.compile(rf"(?im)^\s*{re.escape(package)}(?:\[[^]]+\])?(?=\s*(?:[<>=~!;#]|$))")
        if pattern.search(source) is None:
            changed.add(requirements.relative_to(root).as_posix())
    if not (root / ".python-version").is_file():
        changed.add(".python-version")
    if not (root / TOOLCHAIN_MANIFEST).is_file():
        changed.add(TOOLCHAIN_MANIFEST)
    paths = tuple(root / relative for relative in sorted(changed))
    return tuple(sorted(changed)), paths


def pip_install_command(
    packages: Sequence[str],
    *,
    offline: bool = False,
    dependencies: bool = True,
) -> tuple[str, ...]:
    return pip_install_specifier_command(
        tuple(f"{package}=={TESTED_VERSIONS[package]}" for package in packages),
        offline=offline,
        dependencies=dependencies,
    )


def pip_install_specifier_command(
    specifiers: Sequence[str],
    *,
    offline: bool = False,
    dependencies: bool = True,
) -> tuple[str, ...]:
    """Build the resilient pip command for exact, caller-resolved specs.

    Adopt normally supplies names from :data:`TESTED_VERSIONS`. Template sync
    has one earlier prerequisite: it must install the exact Prodockit release
    paired with the incoming template before that release can plan Adopt. Keep
    both routes on the same interpreter, mirror, wheelhouse and retry policy.
    """
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--retries",
        "5",
        "--timeout",
        "30",
        "--prefer-binary",
        "--upgrade-strategy",
        "only-if-needed",
    ]
    if not dependencies:
        # These distributions are already installed, so their dependency set
        # has already been provisioned. Re-resolving it can make an otherwise
        # valid exact upgrade/downgrade impossible on platforms where an
        # optional transitive wheel is unavailable (notably Brotli on Windows
        # ARM64). Pip still installs the genuine requested distribution wheel.
        command.append("--no-deps")
    wheelhouse = os.environ.get(WHEELHOUSE_ENV, "").strip()
    mirror = os.environ.get(PYPI_MIRROR_ENV, "").strip()
    if offline:
        command.append("--no-index")
        if wheelhouse:
            command.extend(("--find-links", wheelhouse))
    elif mirror:
        # An explicitly configured institutional mirror is tried alongside
        # PyPI. Pip selects a compatible exact version from either source.
        command.extend(("--extra-index-url", mirror))
    command.extend(specifiers)
    return tuple(command)


def pip_install_requirements_command(
    requirements: Path | None,
    specifiers: Sequence[str] = (),
    *,
    offline: bool = False,
) -> tuple[str, ...]:
    """Build the shared resilient command for a requirements file plus extras."""

    command = list(pip_install_specifier_command((), offline=offline))
    if requirements is not None:
        command.extend(("-r", str(requirements)))
    command.extend(specifiers)
    return tuple(command)


def dependency_repairs(packages: Sequence[str]) -> tuple[str, ...]:
    """Check each installed runtime's dependency graph, excluding unused extras."""

    def broken(
        package: str, visited: set[tuple[str, frozenset[str]]], extras: frozenset[str] = frozenset()
    ) -> bool:
        name = canonicalize_name(package)
        key = (name, extras)
        if key in visited:
            return False
        visited.add(key)
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            return True
        for value in distribution.requires or ():
            requirement = Requirement(value)
            if requirement.marker and not any(
                requirement.marker.evaluate({"extra": extra}) for extra in ("", *extras)
            ):
                continue
            try:
                version = importlib.metadata.version(requirement.name)
            except importlib.metadata.PackageNotFoundError:
                return True
            if version not in requirement.specifier or broken(
                requirement.name, visited, frozenset(requirement.extras)
            ):
                return True
        return False

    return tuple(package for package in packages if broken(package, set()))


def plan(root: Path, *, offline: bool = False, fresh: bool = False) -> ToolchainPlan:
    python = installed_python_version()
    supported_python = TESTED_VERSIONS["python"]
    declaration_changes, files = _declarations(root)
    if python != supported_python:
        return ToolchainPlan(
            (),
            declaration_changes,
            (),
            files,
            blocked=(
                f"Python {python} is active, but this Prodockit release supports its tested "
                f"Python {supported_python} toolchain. No packages or project files will be "
                f"changed. Run `prodockit bootstrap` or create and activate a Python "
                f"{supported_python} virtual environment, then rerun `prodockit adopt`."
            ),
            offline=offline,
        )

    installed = (
        _fresh_distribution_versions(PYTHON_PACKAGES)
        if fresh
        else {package: installed_distribution_version(package) for package in PYTHON_PACKAGES}
    )
    actions = tuple(
        action
        for package in PYTHON_PACKAGES
        if (action := _action(package, installed[package])) is not None
    )
    repairs = dependency_repairs(tuple(p for p in PYTHON_PACKAGES if installed[p] is not None))
    actions += tuple(
        ToolAction(p, installed[p], TESTED_VERSIONS[p], "repair")
        for p in repairs
        if p in PYTHON_PACKAGES
        if not any(action.package == p for action in actions)
    )
    missing_packages = tuple(
        action.package
        for action in actions
        if action.package in PYTHON_PACKAGES
        and (action.installed is None or action.package in repairs)
    )
    installed_packages = tuple(
        action.package
        for action in actions
        if action.package in PYTHON_PACKAGES
        and action.installed is not None
        and action.package not in repairs
    )
    commands: list[tuple[str, ...]] = []
    if missing_packages:
        commands.append(pip_install_command(missing_packages, offline=offline))
    if installed_packages:
        commands.append(
            pip_install_command(
                installed_packages,
                offline=offline,
                dependencies=False,
            )
        )
    return ToolchainPlan(actions, declaration_changes, tuple(commands), files, offline=offline)


def _replace_requirement(source: str, package: str, version: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"(?im)^(?P<lead>\s*)(?P<name>{re.escape(package)})(?P<extras>\[[^]]+\])?"
        rf"(?P<space>\s*)(?:(?P<op>==|>=|~=|<=|!=|>|<)\s*(?P<version>[^\s;#]+))?"
        rf"(?P<tail>\s*(?:;[^#]*)?(?:#.*)?)$"
    )
    match = pattern.search(source)
    if match is None:
        lead = "" if not source or source.endswith("\n") else "\n"
        return f"{source}{lead}{package}=={version}\n", True
    operator = match.group("op") or "=="
    replacement = (
        f"{match.group('lead')}{match.group('name')}{match.group('extras') or ''}"
        f"{match.group('space')}{operator}{version}{match.group('tail')}"
    )
    if match.group(0) == replacement:
        return source, False
    return source[: match.start()] + replacement + source[match.end() :], True


def _manifest_source() -> str:
    lines = [
        "# Exact combination supported by the installed Prodockit release.",
        "# `prodockit adopt` and `prodockit pins` maintain this file.",
        "schema = 1",
        "",
        "[versions]",
    ]
    lines.extend(f'{package} = "{TESTED_VERSIONS[package]}"' for package in DEFAULT_PACKAGES)
    return "\n".join(lines) + "\n"


def write_declarations(root: Path) -> list[Path]:
    """Align existing sites, then add the canonical missing declarations."""

    from prodockit.config_integrity import before_write, check_project

    check_project(root, ToolchainError)
    written: set[Path] = set()
    states = _local_declarations(root)
    try:
        for package, state in states.items():
            differs = any(site.version != TESTED_VERSIONS[package] for site in state.sites)
            if (
                state.sites
                and differs
                and apply_version(str(root), state, TESTED_VERSIONS[package])
            ):
                written.update(root / site.path for site in state.sites)
    except PinError as error:
        raise ToolchainError(str(error)) from error

    requirements = _requirements_path(root)
    source = requirements.read_text(encoding="utf-8") if requirements.is_file() else ""
    updated = source
    for package in PYTHON_PACKAGES:
        updated, _changed = _replace_requirement(updated, package, TESTED_VERSIONS[package])
    if updated != source:
        requirements.parent.mkdir(parents=True, exist_ok=True)
        requirements.write_text(updated, encoding="utf-8")
        written.add(requirements)

    python_file = root / ".python-version"
    python_source = TESTED_VERSIONS["python"] + "\n"
    if not python_file.is_file() or python_file.read_text(encoding="utf-8") != python_source:
        python_file.write_text(python_source, encoding="utf-8")
        written.add(python_file)

    manifest = root / TOOLCHAIN_MANIFEST
    manifest_source = _manifest_source()
    if not manifest.is_file() or manifest.read_text(encoding="utf-8") != manifest_source:
        before_write(manifest, manifest_source, ToolchainError)
        manifest.write_text(manifest_source, encoding="utf-8")
        written.add(manifest)
    return sorted(written)


def _command_detail(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())


def _run_resilient(
    command: Sequence[str],
    *,
    root: Path,
    reporter: RetryReporter | None,
    offline: bool,
) -> None:
    def invoke() -> subprocess.CompletedProcess[str]:
        try:
            return run_installer(
                list(command),
                cwd=root,
                timeout=1800,
            )
        except InstallerCleanupError as error:
            raise ToolchainError(str(error)) from error

    result = run_with_retries(
        "toolchain installation",
        invoke,
        succeeded=lambda completed: completed.returncode == 0,
        failure_detail=_command_detail,
        retry_delays=() if offline else DEFAULT_RETRY_DELAYS,
        reporter=reporter,
    )
    if result.value.returncode:
        detail = failure_with_history(
            _command_detail(result.value), result.attempts, result.transient_failures
        )
        raise ToolchainError(f"toolchain command failed: {' '.join(command)}\n{detail}")


def run_install_command(
    command: Sequence[str],
    *,
    root: Path,
    reporter: RetryReporter | None = None,
    offline: bool = False,
) -> None:
    """Run one planned installer through the shared bounded retry path."""

    _run_resilient(command, root=root, reporter=reporter, offline=offline)


def apply(
    root: Path,
    *,
    offline: bool = False,
    reporter: RetryReporter | None = None,
) -> list[Path]:
    """Apply and verify a complete plan; declarations are committed last."""

    from prodockit.config_integrity import check_project

    check_project(root, ToolchainError)
    planned = plan(root, offline=offline)
    if planned.blocked:
        raise ToolchainError(planned.blocked)
    for command in planned.commands:
        _run_resilient(command, root=root, reporter=reporter, offline=offline)
        importlib.invalidate_caches()

    # A changed distribution may introduce dependencies absent from the old
    # metadata. Resolve those once, then verify rather than retry indefinitely.
    repairs = dependency_repairs(PYTHON_PACKAGES)
    if repairs:
        _run_resilient(
            pip_install_command(repairs, offline=offline),
            root=root,
            reporter=reporter,
            offline=offline,
        )
        importlib.invalidate_caches()

    # Verify installed state before changing the project's declarations. A
    # failed package/download step therefore cannot claim the project uses a
    # combination that was never actually reached.
    remaining = tuple(action for action in plan(root, offline=offline, fresh=True).actions)
    if remaining:
        raise ToolchainError(
            "installation finished but version verification failed: "
            + "; ".join(action.description for action in remaining)
        )
    written = write_declarations(root)
    verified = plan(root, offline=offline, fresh=True)
    if verified.blocked or verified.needs_work:
        raise ToolchainError(f"supported-toolchain verification is incomplete: {verified.detail}")
    return written


def _cache_root() -> Path:
    configured = os.environ.get(DOWNLOAD_CACHE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    platform_name: str = sys.platform
    if platform_name == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "prodockit" / "Cache" / "downloads"
    if platform_name == "darwin":
        return Path.home() / "Library" / "Caches" / "prodockit" / "downloads"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "prodockit" / "downloads"

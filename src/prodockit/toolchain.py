# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Align an adopted project's active tools with Prodockit's tested versions.

The tested-version manifest lives in :mod:`prodockit.pins`.  This module is
deliberately a consumer of that manifest: Adopt, Pins and Diagnostics must not
grow three subtly different answers to "which combination is supported?".
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from prodockit.pins import DEFAULT_PACKAGES, TESTED_VERSIONS, PinError, apply_version, discover
from prodockit.renderer_resilience import (
    DEFAULT_RETRY_DELAYS,
    RetryReporter,
    failure_with_history,
    run_with_retries,
)

TOOLCHAIN_MANIFEST = ".prodockit-toolchain.toml"
WHEELHOUSE_ENV = "PDK_WHEELHOUSE"
PYPI_MIRROR_ENV = "PDK_PYPI_MIRROR"
PANDOC_MIRROR_ENV = "PDK_PANDOC_MIRROR"
DOWNLOAD_CACHE_ENV = "PDK_NATIVE_DOWNLOAD_CACHE"

PYTHON_PACKAGES = (
    "zensical",
    "weasyprint",
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
    "pandoc": "Pandoc",
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


def _pandoc_version(output: str) -> str | None:
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    match = re.match(r"pandoc\s+([^\s]+)", first, re.IGNORECASE)
    return match.group(1) if match else None


def installed_pandoc_version() -> str | None:
    command = shutil.which("pandoc")
    if command is None:
        return None
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _pandoc_version(result.stdout) if result.returncode == 0 else None


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


def _declarations(root: Path) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    states = discover(str(root))
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


def pandoc_install_command(version: str, *, offline: bool = False) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "prodockit.toolchain",
        "install-pandoc",
        "--version",
        version,
        *(("--offline",) if offline else ()),
    )


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
    installed["pandoc"] = installed_pandoc_version()
    actions = tuple(
        action
        for package in (*PYTHON_PACKAGES, "pandoc")
        if (action := _action(package, installed[package])) is not None
    )
    missing_packages = tuple(
        action.package
        for action in actions
        if action.package in PYTHON_PACKAGES and action.installed is None
    )
    installed_packages = tuple(
        action.package
        for action in actions
        if action.package in PYTHON_PACKAGES and action.installed is not None
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
    if any(action.package == "pandoc" for action in actions):
        commands.append(pandoc_install_command(TESTED_VERSIONS["pandoc"], offline=offline))
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

    written: set[Path] = set()
    states = discover(str(root))
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
        return subprocess.run(
            list(command),
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )

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

    planned = plan(root, offline=offline)
    if planned.blocked:
        raise ToolchainError(planned.blocked)
    for command in planned.commands:
        _run_resilient(command, root=root, reporter=reporter, offline=offline)
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


def _pandoc_asset(version: str) -> str:
    machine = platform.machine().lower()
    platform_name: str = sys.platform
    if platform_name == "darwin":
        architectures = {
            "arm64": "arm64",
            "aarch64": "arm64",
            "x86_64": "x86_64",
            "amd64": "x86_64",
        }
        architecture = architectures.get(machine)
        if architecture is None:
            raise ToolchainError(f"Pandoc has no supported macOS archive for {machine}")
        return f"pandoc-{version}-{architecture}-macOS.zip"
    if platform_name.startswith("linux"):
        architectures = {
            "arm64": "arm64",
            "aarch64": "arm64",
            "x86_64": "amd64",
            "amd64": "amd64",
        }
        architecture = architectures.get(machine)
        if architecture is None:
            raise ToolchainError(f"Pandoc has no supported Linux archive for {machine}")
        return f"pandoc-{version}-linux-{architecture}.tar.gz"
    if platform_name == "win32":
        # Pandoc publishes x64 Windows binaries; Windows ARM64 runs them
        # under its supported x64 emulation layer.
        if machine not in {"arm64", "aarch64", "x86_64", "amd64"}:
            raise ToolchainError(f"Pandoc has no supported Windows archive for {machine}")
        return f"pandoc-{version}-windows-x86_64.zip"
    raise ToolchainError(f"Pandoc installation is not supported on {platform_name}")


def _pandoc_urls(version: str, asset: str) -> tuple[str, ...]:
    primary = f"https://github.com/jgm/pandoc/releases/download/{version}/{asset}"
    mirror = os.environ.get(PANDOC_MIRROR_ENV, "").strip()
    if not mirror:
        return (primary,)
    expanded = (
        mirror.format(version=version, asset=asset)
        if "{" in mirror
        else f"{mirror.rstrip('/')}/{version}/{asset}"
    )
    return (expanded, primary)


def _download(url: str, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "prodockit-adopt"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if not partial.stat().st_size:
            raise ToolchainError(f"downloaded an empty Pandoc archive from {url}")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def _validated_archive(path: Path) -> None:
    try:
        if path.name.endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                if not archive.infolist() or archive.testzip() is not None:
                    raise ToolchainError(f"Pandoc download failed ZIP validation: {path}")
        else:
            with tarfile.open(path) as archive:
                if next(iter(archive), None) is None:
                    raise ToolchainError(f"Pandoc download is an empty archive: {path}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise ToolchainError(f"Pandoc download failed archive validation: {error}") from error


def _download_pandoc(version: str, destination: Path, *, offline: bool) -> Path:
    asset = _pandoc_asset(version)
    cache = _cache_root() / asset
    destination.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file():
        try:
            _validated_archive(cache)
            shutil.copy2(cache, destination)
            return destination
        except (OSError, ToolchainError):
            cache.unlink(missing_ok=True)
    if offline:
        raise ToolchainError(
            f"offline mode needs a validated cached {asset}; expected it at {cache}"
        )
    failures: list[str] = []
    for url in _pandoc_urls(version, asset):
        for attempt, delay in enumerate((*DEFAULT_RETRY_DELAYS, 0.0), start=1):
            try:
                _download(url, destination)
                _validated_archive(destination)
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_name(cache.name + f".{os.getpid()}.part")
                shutil.copy2(destination, temporary)
                temporary.replace(cache)
                return destination
            except urllib.error.HTTPError as error:
                destination.unlink(missing_ok=True)
                failures.append(f"{url} attempt {attempt}: HTTP {error.code} {error.reason}")
                if error.code != 429 and not 500 <= error.code <= 599:
                    break
                if delay:
                    time.sleep(delay)
            except (OSError, ToolchainError, urllib.error.URLError) as error:
                destination.unlink(missing_ok=True)
                failures.append(f"{url} attempt {attempt}: {error}")
                if delay:
                    time.sleep(delay)
    raise ToolchainError("all Pandoc download sources failed: " + "; ".join(failures))


def _safe_member(name: str) -> bool:
    path = Path(name)
    return not path.is_absolute() and ".." not in path.parts


def _extract_pandoc(archive: Path, output: Path) -> Path:
    output.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                if not _safe_member(member.filename):
                    raise ToolchainError(f"unsafe path in Pandoc archive: {member.filename}")
            source.extractall(output)
    else:
        with tarfile.open(archive) as source:
            for tar_member in source.getmembers():
                if not _safe_member(tar_member.name):
                    raise ToolchainError(f"unsafe path in Pandoc archive: {tar_member.name}")
            source.extractall(output, filter="data")
    executable = "pandoc.exe" if sys.platform == "win32" else "pandoc"
    matches = [path for path in output.rglob(executable) if path.is_file()]
    if not matches:
        raise ToolchainError(f"Pandoc archive does not contain {executable}")
    return matches[0]


def install_pandoc(version: str, *, offline: bool = False) -> Path:
    """Install an exact Pandoc executable into the active environment."""

    scripts = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin")
    scripts.mkdir(parents=True, exist_ok=True)
    target = scripts / ("pandoc.exe" if sys.platform == "win32" else "pandoc")
    with tempfile.TemporaryDirectory(prefix="prodockit-pandoc-") as temporary:
        work = Path(temporary)
        archive = work / _pandoc_asset(version)
        _download_pandoc(version, archive, offline=offline)
        executable = _extract_pandoc(archive, work / "extract")
        staged = target.with_name(target.name + f".{os.getpid()}.tmp")
        shutil.copy2(executable, staged)
        if sys.platform != "win32":
            staged.chmod(staged.stat().st_mode | 0o755)
        staged.replace(target)
    result = subprocess.run(
        [str(target), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    observed = _pandoc_version(result.stdout) if result.returncode == 0 else None
    if observed != version:
        raise ToolchainError(
            "installed Pandoc verification failed: "
            f"expected {version}, found {observed or 'unreadable'}"
        )
    return target


def _main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prodockit internal toolchain installer")
    commands = parser.add_subparsers(dest="command", required=True)
    pandoc = commands.add_parser("install-pandoc")
    pandoc.add_argument("--version", required=True)
    pandoc.add_argument("--offline", action="store_true")
    options = parser.parse_args(arguments)
    if options.command == "install-pandoc":
        install_pandoc(options.version, offline=options.offline)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

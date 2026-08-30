# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Run the two Bootstrap upgrade routes against genuine old executables.

The fast wheel harness returns controlled version strings.  This release gate
instead downloads and executes real back-level distributions, lets Bootstrap
run its ordinary package-manager plans, and verifies the finished machine and
repository.  Git hosts remain local bare repositories: this test is about the
installed software, not somebody's GitHub or GitLab account.
"""

from __future__ import annotations

import argparse
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
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

try:
    from .bootstrap_native_install import (
        MACOS,
        UBUNTU,
        WINDOWS,
        NativeInstallError,
        _ensure_windows_winget,
        _is_arm64,
        _resolve_wheel,
        cleanup_ephemeral_runner,
    )
except ImportError:  # executed directly by the release workflow
    from bootstrap_native_install import (
        MACOS,
        UBUNTU,
        WINDOWS,
        NativeInstallError,
        _ensure_windows_winget,
        _is_arm64,
        _resolve_wheel,
        cleanup_ephemeral_runner,
    )

from prodockit.bootstrap import current_platform, refresh_windows_path
from prodockit.bootstrap.stages import (
    GIT_MIN_VERSION,
    NODE_MIN_VERSION,
    PANDOC_MIN_MAJOR,
    VSCODE_EXTENSION_MIN_VERSIONS,
    VSCODE_MIN_VERSION,
)

OLD_VSCODE = "1.80.2"
OLD_GIT = "2.27.0"
OLD_PANDOC = "2.19.2"
OLD_NODE = "18.20.0"

SCENARIOS = (
    ("surrey-existing-real-upgrade", "surrey", "existing"),
    ("github-new-real-upgrade", "github", "new"),
)

# The version immediately below each accepted floor.  These are real VSIX
# packages from the Marketplace, unpacked into the disposable test profile.
OLD_EXTENSIONS = {
    "ms-python.python": "2026.2.0",
    "zensical.zensical-studio": "0.2.11",
    # The 0.20/0.21 intermediary packages were withdrawn from Microsoft's
    # Marketplace; 0.19.2 is the newest still-downloadable release below
    # the supported floor.
    "tamasfe.even-better-toml": "0.19.2",
    "ltex-plus.vscode-ltex-plus": "15.7.0",
}


def _run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int = 1200,
) -> subprocess.CompletedProcess[str]:
    print("prepare:", " ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode:
        raise NativeInstallError(
            f"back-level preparation failed ({' '.join(command)}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def _download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"download: {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "prodockit-release-ci"})
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        destination.open("wb") as output,
    ):
        shutil.copyfileobj(response, output)
    if not destination.stat().st_size:
        raise NativeInstallError(f"download produced an empty file: {url}")
    return destination


def _extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        source.extractall(destination)


def _extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")


def _find(root: Path, names: tuple[str, ...]) -> Path:
    wanted = {name.lower() for name in names}
    found = [path for path in root.rglob("*") if path.name.lower() in wanted]
    if not found:
        raise NativeInstallError(f"none of {names!r} was found below {root}")
    return min(found, key=lambda path: len(path.parts))


def _build_old_git(source_root: Path, prefix: Path) -> Path:
    archive = _download(
        f"https://github.com/git/git/archive/refs/tags/v{OLD_GIT}.tar.gz",
        source_root / f"git-{OLD_GIT}.tar.gz",
    )
    extracted = source_root / "git-source"
    _extract_tar(archive, extracted)
    source = next(extracted.iterdir())
    make_options = [
        f"prefix={prefix}",
        "NO_GETTEXT=YesPlease",
        "NO_TCLTK=YesPlease",
        "NO_OPENSSL=YesPlease",
        "NO_CURL=YesPlease",
    ]
    _run(["make", "-j2", *make_options], cwd=source)
    _run(["make", *make_options, "install"], cwd=source)
    return prefix / "bin"


def _portable_unix_software(root: Path, recipe: str) -> list[Path]:
    """Download genuine old applications into one reusable prefix."""
    architecture = "arm64" if _is_arm64() else "x64"
    bins: list[Path] = []

    vscode = root / "vscode"
    if recipe == MACOS:
        archive = _download(
            f"https://update.code.visualstudio.com/{OLD_VSCODE}/darwin-{architecture}/stable",
            root / "vscode.zip",
        )
        _extract_zip(archive, vscode)
        vscode_bin = _find(vscode, ("code",)).parent
    else:
        archive = _download(
            f"https://update.code.visualstudio.com/{OLD_VSCODE}/linux-deb-{architecture}/stable",
            root / "vscode.deb",
        )
        _run(["dpkg-deb", "-x", str(archive), str(vscode)])
        vscode_bin = vscode / "usr" / "share" / "code" / "bin"
        if not (vscode_bin / "code").is_file():
            raise NativeInstallError(f"the old VS Code CLI was not found at {vscode_bin}")
    bins.append(vscode_bin)

    git_prefix = root / "git"
    bins.append(_build_old_git(root / "downloads", git_prefix))

    pandoc = root / "pandoc"
    if recipe == MACOS:
        archive = _download(
            f"https://github.com/jgm/pandoc/releases/download/{OLD_PANDOC}/"
            f"pandoc-{OLD_PANDOC}-macOS.zip",
            root / "pandoc.zip",
        )
        _extract_zip(archive, pandoc)
    else:
        release_arch = "arm64" if _is_arm64() else "amd64"
        archive = _download(
            f"https://github.com/jgm/pandoc/releases/download/{OLD_PANDOC}/"
            f"pandoc-{OLD_PANDOC}-linux-{release_arch}.tar.gz",
            root / "pandoc.tar.gz",
        )
        _extract_tar(archive, pandoc)
    bins.append(_find(pandoc, ("pandoc",)).parent)

    node = root / "node"
    node_os = "darwin" if recipe == MACOS else "linux"
    suffix = "tar.gz" if recipe == MACOS else "tar.xz"
    archive = _download(
        f"https://nodejs.org/dist/v{OLD_NODE}/"
        f"node-v{OLD_NODE}-{node_os}-{architecture}.{suffix}",
        root / f"node.{suffix}",
    )
    _extract_tar(archive, node)
    bins.append(_find(node, ("node",)).parent)
    return bins


def _winget_old(identifier: str, version: str) -> None:
    _run(
        [
            "winget",
            "install",
            "--id",
            identifier,
            "--version",
            version,
            "-e",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--silent",
            "--disable-interactivity",
        ]
    )


def _install_windows_old_software() -> None:
    _ensure_windows_winget()
    for identifier, version in (
        ("Microsoft.VisualStudioCode", OLD_VSCODE),
        ("Git.Git", OLD_GIT),
        ("JohnMacFarlane.Pandoc", OLD_PANDOC),
        ("OpenJS.NodeJS.LTS", OLD_NODE),
    ):
        _winget_old(identifier, version)
    refresh_windows_path()


def _marketplace_url(identifier: str, version: str) -> str:
    publisher, name = identifier.split(".", 1)
    return (
        "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
        f"{publisher}/vsextensions/{name}/{version}/vspackage"
    )


def _seed_old_extensions(cache: Path, home: Path) -> None:
    extensions = home / ".vscode" / "extensions"
    extensions.mkdir(parents=True, exist_ok=True)
    for identifier, version in OLD_EXTENSIONS.items():
        minimum = VSCODE_EXTENSION_MIN_VERSIONS[identifier]
        if _parts(version) >= _parts(minimum):
            raise NativeInstallError(
                f"the seeded {identifier} {version} is not older than {minimum}"
            )
        archive = cache / f"{identifier}-{version}.vsix"
        if not archive.is_file():
            _download(_marketplace_url(identifier, version), archive)
        destination = extensions / f"{identifier}-{version}"
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                if not member.filename.startswith("extension/") or member.is_dir():
                    continue
                relative = Path(member.filename).relative_to("extension")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, target.open("wb") as output:
                    shutil.copyfileobj(input_file, output)


def _version(command: list[str], environment: dict[str, str]) -> str:
    output = _run(command, environment=environment).stdout
    match = re.search(r"\d+(?:\.\d+)+", output)
    if match is None:
        raise NativeInstallError(f"could not read a version from {' '.join(command)}: {output}")
    return match.group(0)


def _parts(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _assert_backlevel(environment: dict[str, str]) -> dict[str, str]:
    code = "code.cmd" if os.name == "nt" else "code"
    found = {
        "vscode": _version([code, "--version"], environment),
        "git": _version(["git", "--version"], environment),
        "pandoc": _version(["pandoc", "--version"], environment),
        "node": _version(["node", "--version"], environment),
        "npm": _version(["npm.cmd" if os.name == "nt" else "npm", "--version"], environment),
    }
    limits = {
        "vscode": VSCODE_MIN_VERSION,
        "git": GIT_MIN_VERSION,
        "node": NODE_MIN_VERSION,
    }
    for name, minimum in limits.items():
        if _parts(found[name]) >= _parts(minimum):
            raise NativeInstallError(
                f"{name} was meant to be back-level, but {found[name]} >= {minimum}"
            )
    if int(found["pandoc"].split(".", 1)[0]) >= PANDOC_MIN_MAJOR:
        raise NativeInstallError(f"pandoc {found['pandoc']} is not a back-level major")
    return found


def _scenario_environment(
    *, recipe: str, portable_bins: list[Path], home: Path
) -> dict[str, str]:
    environment = dict(os.environ)
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    parts = [part for part in environment.get("PATH", "").split(os.pathsep) if part]
    old = [str(path) for path in portable_bins]
    if recipe == MACOS:
        brew = _run(["brew", "--prefix"]).stdout.strip()
        manager = str(Path(brew) / "bin")
        parts = [part for part in parts if part != manager and part not in old]
        parts = [manager, *old, *parts]
    elif recipe == UBUNTU:
        parts = [part for part in parts if part not in old]
        parts.extend(old)
    environment["PATH"] = os.pathsep.join(parts)
    environment["PYTHONUTF8"] = "1"
    environment.pop("PYTHONPATH", None)
    return environment


def run_native_upgrades(wheel: Path, report_path: Path) -> dict[str, Any]:
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        raise NativeInstallError(
            "real upgrade acceptance is restricted to disposable GitHub Actions runners"
        )
    recipe = current_platform()
    started = time.monotonic()
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="prodockit-bootstrap-upgrades-") as temporary:
        root = Path(temporary)
        software = root / "backlevel-software"
        extension_cache = root / "extensions"
        portable_bins: list[Path] = []
        cleanup_ephemeral_runner(recipe, Path.home())
        if recipe in {MACOS, UBUNTU}:
            portable_bins = _portable_unix_software(software, recipe)

        driver = Path(__file__).with_name("_bootstrap_acceptance_driver.py").resolve()
        for index, (name, host, route) in enumerate(SCENARIOS):
            if index:
                cleanup_ephemeral_runner(recipe, Path.home())
            if recipe == WINDOWS:
                _install_windows_old_software()
            scenario_root = root / name
            home = scenario_root / "home"
            home.mkdir(parents=True)
            _seed_old_extensions(extension_cache, home)
            environment = _scenario_environment(
                recipe=recipe, portable_bins=portable_bins, home=home
            )
            before = _assert_backlevel(environment)
            scenario_report = root / f"{name}.json"
            completed = _run(
                [
                    sys.executable,
                    str(driver),
                    "--root",
                    str(scenario_root),
                    "--host",
                    host,
                    "--route",
                    route,
                    "--real-software",
                    "--report",
                    str(scenario_report),
                ],
                environment=environment,
                timeout=5400,
            )
            report = json.loads(scenario_report.read_text(encoding="utf-8"))
            report["backlevel_versions"] = before
            report["output"] = completed.stdout.strip()
            reports.append(report)
            print(f"{name}: real upgrades passed", flush=True)

    result = {
        "passed": True,
        "prodockit_wheel": wheel.name,
        "platform": recipe,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "duration_seconds": round(time.monotonic() - started, 2),
        "scenarios": reports,
    }
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    architecture = parser.add_mutually_exclusive_group(required=True)
    architecture.add_argument("--require-x64", action="store_true")
    architecture.add_argument("--require-arm64", action="store_true")
    args = parser.parse_args()
    expected_arm64 = bool(args.require_arm64)
    if _is_arm64() != expected_arm64:
        expected = "arm64" if expected_arm64 else "x64"
        raise NativeInstallError(f"expected {expected}, found {platform.machine()}")
    wheel = _resolve_wheel(args.wheel)
    report = run_native_upgrades(wheel, args.report)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

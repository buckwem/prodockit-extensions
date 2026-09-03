# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise Bootstrap's real installers on a disposable release runner.

The ordinary installed-wheel acceptance suite is intentionally hermetic and
fast.  This release gate crosses the package-manager boundary instead: it
removes the relevant runner applications, executes the plans produced by the
installed candidate wheel, and verifies every resulting stage.  It leaves
operating-system shared libraries intact because removing one can dismantle
the hosted runner's desktop stack rather than model a user upgrade.

Cleanup is deliberately unavailable on a developer machine.  GitHub-hosted
runners are disposable; a person's workstation is not.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import prodockit
from prodockit.bootstrap import (
    STAGES,
    BootstrapConfig,
    CommandResult,
    SubprocessRunner,
    apply_stage,
    build_context,
    current_platform,
)
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS


class NativeInstallError(RuntimeError):
    """The release runner did not reach a verified Bootstrap state."""


def _run(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("cleanup:", " ".join(command), flush=True)
    result = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    if check and result.returncode:
        raise NativeInstallError(
            f"cleanup failed ({' '.join(command)}):\n{result.stdout}\n{result.stderr}"
        )
    return result


def _brew_remove(name: str, *, cask: bool = False) -> None:
    kind = "--cask" if cask else "--formula"
    if _run(["brew", "list", kind, name], check=False).returncode:
        return
    command = ["brew", "uninstall", "--force"]
    if cask:
        command.append("--cask")
    else:
        command.append("--ignore-dependencies")
    _run([*command, name])


def _apt_remove(name: str) -> None:
    found = _run(["dpkg-query", "-W", "-f=${Status}", name], check=False)
    if found.returncode or "install ok installed" not in found.stdout:
        return
    _run(
        [
            "sudo",
            "apt",
            "-o",
            "DPkg::Lock::Timeout=600",
            "remove",
            "-y",
            name,
        ]
    )


def _winget_remove(identifier: str) -> None:
    found = _run(
        ["winget", "list", "--id", identifier, "-e", "--source", "winget"],
        check=False,
    )
    if found.returncode:
        return
    _run(
        [
            "winget",
            "uninstall",
            "--id",
            identifier,
            "-e",
            "--source",
            "winget",
            "--silent",
            "--disable-interactivity",
            "--accept-source-agreements",
        ]
    )


def _remove_windows_registered_node(
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    """Remove runner-image Node registrations that WinGet cannot see."""
    script = (
        "$roots = @("  # machine x64, machine x86, and current user
        "'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'); "
        "$entries = Get-ItemProperty -Path $roots -ErrorAction SilentlyContinue | "
        "Where-Object { $_.DisplayName -like 'Node.js*' }; "
        "foreach ($entry in $entries) { "
        "if ($entry.UninstallString -match '\\{[0-9A-Fa-f-]+\\}') { "
        "$product = $Matches[0]; "
        "Write-Host \"Removing registered $($entry.DisplayName) $product\"; "
        "$process = Start-Process msiexec.exe -ArgumentList "
        "@('/x', $product, '/qn', '/norestart') -Wait -PassThru; "
        "if ($process.ExitCode -notin @(0, 1605, 1614, 3010)) { "
        "exit $process.ExitCode } } }; exit 0"
    )
    run(["powershell", "-NoProfile", "-Command", script])


def _ensure_windows_winget() -> None:
    """Prepare WinGet where a disposable Windows runner omits App Installer.

    This is runner preparation, not a simulated Bootstrap stage. The commands
    are Microsoft's documented Windows Sandbox recovery sequence; Bootstrap's
    own plans still perform every application installation afterwards.
    """

    if shutil.which("winget") is not None:
        return
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        raise NativeInstallError("WinGet installation requires PowerShell")
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$ProgressPreference = 'SilentlyContinue'; "
        "$headers = if ($env:GITHUB_TOKEN) { @{ "
        "Authorization = \"Bearer $env:GITHUB_TOKEN\"; "
        "'X-GitHub-Api-Version' = '2022-11-28' } } else { @{} }; "
        "$release = Invoke-RestMethod -Uri "
        "'https://api.github.com/repos/microsoft/winget-cli/releases/latest' "
        "-Headers $headers; "
        "$bundleAsset = $release.assets | Where-Object { "
        "$_.name -eq 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle' "
        "} | Select-Object -First 1; "
        "$dependencyAsset = $release.assets | Where-Object { "
        "$_.name -eq 'DesktopAppInstaller_Dependencies.zip' "
        "} | Select-Object -First 1; "
        "if (-not $bundleAsset -or -not $dependencyAsset) { "
        "throw 'The current WinGet release does not contain its signed installer assets' "
        "}; "
        "$root = Join-Path $env:RUNNER_TEMP 'prodockit-winget'; "
        "New-Item -ItemType Directory -Force -Path $root | Out-Null; "
        "$bundle = Join-Path $root $bundleAsset.name; "
        "$dependencyArchive = Join-Path $root $dependencyAsset.name; "
        "$dependencyRoot = Join-Path $root 'dependencies'; "
        "Invoke-WebRequest -Uri $bundleAsset.browser_download_url -OutFile $bundle; "
        "Invoke-WebRequest -Uri $dependencyAsset.browser_download_url "
        "-OutFile $dependencyArchive; "
        "Expand-Archive -LiteralPath $dependencyArchive "
        "-DestinationPath $dependencyRoot -Force; "
        "$architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { "
        "'arm64' } elseif ($env:PROCESSOR_ARCHITECTURE -eq 'AMD64') { "
        "'x64' } else { 'x86' }; "
        "$dependencyPath = Get-ChildItem "
        "-LiteralPath (Join-Path $dependencyRoot $architecture) "
        "-Filter '*.appx' | ForEach-Object { $_.FullName }; "
        "if (-not $dependencyPath) { "
        'throw "No WinGet dependencies were found for $architecture" }; '
        "Add-AppxPackage -Path $bundle -DependencyPath $dependencyPath "
        "-ForceApplicationShutdown"
    )
    _run([shell, "-NoProfile", "-Command", script])
    located = _run(
        [
            shell,
            "-NoProfile",
            "-Command",
            "(Get-Command winget.exe -ErrorAction Stop).Source",
        ]
    )
    executable = Path(located.stdout.strip())
    if not executable.is_file():
        raise NativeInstallError("WinGet repair completed but winget.exe was not found")
    os.environ["PATH"] = str(executable.parent) + os.pathsep + os.environ.get("PATH", "")


def _windows_msys_roots() -> tuple[Path, ...]:
    """Return absolute MSYS2 roots using Windows drive-root syntax.

    ``Path("C:") / "msys64"`` is drive-relative on Windows and renders as
    ``C:msys64`` rather than ``C:\\msys64``.  The native release cleanup then
    missed the runner's preinstalled Pango package, letting Bootstrap mistake
    stale files for a completed fresh installation.
    """

    system_drive = os.environ.get("SYSTEMDRIVE", "C:").rstrip("\\/") or "C:"
    values = [system_drive + r"\msys64"]
    for variable in ("LOCALAPPDATA", "PROGRAMFILES"):
        base = os.environ.get(variable, "").rstrip("\\/")
        if base:
            suffix = r"\Programs\msys64" if variable == "LOCALAPPDATA" else r"\msys64"
            values.append(base + suffix)
    return tuple(Path(value) for value in values)


def cleanup_ephemeral_runner(
    recipe: str,
    home: Path,
    *,
    preserve_msys2: bool = False,
) -> None:
    """Remove target tools, but only from a disposable GitHub runner."""

    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        raise NativeInstallError(
            "native installer cleanup is restricted to disposable GitHub Actions runners"
        )
    if recipe == MACOS:
        for package in ("visual-studio-code", "font-inter", "font-jetbrains-mono"):
            _brew_remove(package, cask=True)
        for package in ("git", "pandoc", "pango", "node"):
            _brew_remove(package)
        vscode_app = Path("/Applications/Visual Studio Code.app")
        if vscode_app.exists():
            _run(["sudo", "rm", "-rf", str(vscode_app)])
    elif recipe == UBUNTU:
        for package in (
            "code",
            "git",
            "git-man",
            "pandoc",
            "nodejs",
            "chromium-browser",
            "fonts-inter",
            "fonts-jetbrains-mono",
        ):
            _apt_remove(package)
    elif recipe == WINDOWS:
        _ensure_windows_winget()
        roots = _windows_msys_roots()
        packages = (
            "mingw-w64-ucrt-x86_64-pango",
            "mingw-w64-clang-aarch64-pango",
        )
        for root in roots:
            bash = root / "usr" / "bin" / "bash.exe"
            if bash.is_file():
                for package in packages:
                    _run(
                        [
                            str(bash),
                            "-lc",
                            f"pacman -Rdd --noconfirm {package} >/dev/null 2>&1 || true",
                        ],
                        check=False,
                    )
        identifiers = [
            "Microsoft.VisualStudioCode",
            "Git.Git",
            "JohnMacFarlane.Pandoc",
            "OpenJS.NodeJS.LTS",
            "MSYS2.MSYS2",
        ]
        # Removing MSYS2 after the first route can hang indefinitely on the
        # Windows ARM64 hosted image even after its package processes have
        # stopped.  The upgrade fixture removes both Pango architectures above,
        # so retaining the manager for its second route still exercises a real
        # Pango install and avoids spending 15 minutes in runner-only cleanup.
        if preserve_msys2:
            identifiers.remove("MSYS2.MSYS2")
        for identifier in identifiers:
            _winget_remove(identifier)
        # Hosted images sometimes register Node with Windows Installer but
        # not WinGet. Leaving that hidden product behind makes the subsequent
        # clean-install MSI fail with 1603 even after bounded retries.
        _remove_windows_registered_node(_run)
        # Hosted images can retain the MSYS2 directory and the per-user DLL
        # setting after the package registration is removed. Bootstrap then
        # sees an apparently usable Pango during an intermediate recheck and
        # skips the commands that configure the fresh installation. Native
        # release tests deliberately start from a genuinely clean machine.
        os.environ.pop("WEASYPRINT_DLL_DIRECTORIES", None)
        os.environ["PATH"] = os.pathsep.join(
            part
            for part in os.environ.get("PATH", "").split(os.pathsep)
            if "msys64\\ucrt64\\bin" not in part.lower()
            and "msys64\\clangarm64\\bin" not in part.lower()
        )
        _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::SetEnvironmentVariable("
                "'WEASYPRINT_DLL_DIRECTORIES', $null, 'User'); "
                "$path = [Environment]::GetEnvironmentVariable('Path', 'User'); "
                "$kept = @($path -split ';' | Where-Object { $_ -and $_ -notmatch "
                "'\\msys64\\(ucrt64|clangarm64)\\bin\\?$' }); "
                "[Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User')",
            ]
        )
    else:  # pragma: no cover - guarded by prodockit's platform resolver
        raise NativeInstallError(f"unsupported Bootstrap recipe: {recipe}")

    extensions = home / ".vscode" / "extensions"
    if extensions.exists():
        shutil.rmtree(extensions)


class AbsentPlanningRunner:
    """Force fresh-install plans while retaining architecture decisions."""

    def __init__(self, recipe: str) -> None:
        self.recipe = recipe

    def run(
        self,
        command: Sequence[str],
        cwd: str | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> CommandResult:
        del cwd, timeout, capture
        words = list(command)
        if words[:2] == ["dpkg", "--print-architecture"]:
            architecture = "arm64" if _is_arm64() else "amd64"
            return CommandResult(0, architecture + "\n")
        if words[:2] == ["brew", "--prefix"]:
            return CommandResult(0, "/opt/homebrew\n" if _is_arm64() else "/usr/local\n")
        if words and words[0] == sys.executable and "-c" in words:
            script = words[words.index("-c") + 1]
            if "int.from_bytes" in script:
                return CommandResult(0, "0xaa64\n" if _is_arm64() else "0x8664\n")
            return CommandResult(0)
        if words[:2] == ["fc-list", ":"]:
            return CommandResult(0, "")
        return CommandResult(127, stderr=f"planned as absent: {words[0] if words else ''}")


def _is_arm64() -> bool:
    return platform.machine().lower() in {"arm64", "aarch64"}


def _resolve_wheel(value: Path) -> Path:
    if value.is_file() and value.suffix == ".whl":
        return value.resolve()
    candidates = sorted(value.glob("prodockit-*.whl")) if value.is_dir() else []
    if len(candidates) != 1:
        raise NativeInstallError(
            f"expected one prodockit wheel in {value}, found {len(candidates)}"
        )
    return candidates[0].resolve()


def _seed_project(project: Path, wheel: Path) -> None:
    package = Path(prodockit.__file__).resolve().parent
    tools = package / "_tools_template"
    if not tools.is_dir():
        raise NativeInstallError(f"installed wheel has no tool templates at {tools}")
    project.mkdir(parents=True)
    shutil.copytree(tools, project / "tools")
    (project / "requirements.txt").write_text(
        f"zensical\nweasyprint\n{wheel.as_uri()}\n", encoding="utf-8"
    )


def _progress(state: str, number: int, total: int, command: list[str]) -> None:
    if state == "start":
        print(f"  command {number}/{total}: {' '.join(command)}", flush=True)


def run_native_install(wheel: Path, report_path: Path) -> dict[str, Any]:
    recipe = current_platform()
    home = Path.home()
    cleanup_ephemeral_runner(recipe, home)
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="prodockit-bootstrap-native-") as temporary:
        root = Path(temporary)
        project = root / "report-native-install"
        _seed_project(project, wheel)
        config = BootstrapConfig(
            full_name="Bootstrap Native CI",
            email="bootstrap-native@example.invalid",
            username="bootstrap-native",
            host="github.com",
            namespace="bootstrap-native",
            project_name=project.name,
            project_dir=str(project),
        )
        planning = build_context(
            config,
            runner=AbsentPlanningRunner(recipe),
            platform=recipe,
            home=home,
            exists=lambda _path: False,
            fetch=lambda *_args, **_kwargs: None,
            guided=True,
        )
        real = build_context(
            config,
            runner=SubprocessRunner(),
            platform=recipe,
            home=home,
            guided=True,
        )
        selected = {stage.id: stage for stage in STAGES}
        for stage_id in ("vscode", "git", "pandoc", "project-env", "node", "extensions"):
            stage = selected[stage_id]
            plan = stage.plan(planning)
            if not plan.commands:
                raise NativeInstallError(f"{stage_id} produced no real install commands")
            print(f"\nStage: {stage.summary}", flush=True)
            result = apply_stage(real, stage, plan, progress=_progress)
            record = {
                "id": stage_id,
                "commands": result.ran,
                "verified": result.verified.detail if result.verified else "",
                "ok": result.ok,
            }
            records.append(record)
            if not result.ok:
                failed = result.failed
                detail = result.verified.detail if result.verified else "verification did not run"
                output = "" if failed is None else f"\n{failed.stdout}\n{failed.stderr}"
                raise NativeInstallError(f"{stage_id} failed: {detail}{output}")

    report = {
        "prodockit": prodockit.__version__,
        "platform": recipe,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "duration_seconds": round(time.monotonic() - started, 2),
        "stages": records,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


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
    report = run_native_install(wheel, args.report)
    print(
        f"\nVerified real Bootstrap installs on {report['platform']} "
        f"{report['machine']} in {report['duration_seconds']}s."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

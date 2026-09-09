# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Runtime package-manager prerequisites, without development-tool setup."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS


@dataclass(frozen=True)
class ManagerPlan:
    commands: tuple[tuple[str, ...], ...] = ()
    blocked: str = ""


# Microsoft documents registration and Microsoft.WinGet.Client repair here:
# https://learn.microsoft.com/windows/package-manager/winget/
# Current-user scope avoids silently provisioning software for other accounts.
_WINGET_INSTALL = r"""
$ErrorActionPreference = 'Stop'
try {
    $family = 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe'
    Add-AppxPackage -RegisterByFamilyName -MainPackage $family -ErrorAction Stop
} catch {
    Write-Host 'App Installer registration needs repair.'
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Install-PackageProvider -Name NuGet -Scope CurrentUser -Force | Out-Null
    Install-Module -Name Microsoft.WinGet.Client -Scope CurrentUser -Repository PSGallery -Force |
        Out-Null
    Import-Module Microsoft.WinGet.Client
    Repair-WinGetPackageManager -Latest
}
$apps = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
$userPath = [string][Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $apps) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $apps), 'User')
}
$env:Path = $env:Path + ';' + $apps
& winget --version
if ($LASTEXITCODE -ne 0) {
    throw 'WinGet verification failed; reopen PowerShell and rerun pdk adopt --apply.'
}
""".strip()


def plan(platform: str, *, offline: bool = False) -> ManagerPlan:
    manager = {MACOS: "brew", UBUNTU: "apt", WINDOWS: "winget"}.get(platform)
    if manager is None:
        return ManagerPlan(blocked="Unsupported runtime package-manager platform")
    if shutil.which(manager):
        return ManagerPlan()
    if offline:
        return ManagerPlan(
            blocked=f"{manager} is missing; package-manager provisioning requires an online run"
        )
    if platform == WINDOWS:
        powershell = shutil.which("powershell")
        if not powershell:
            return ManagerPlan(
                blocked="Windows PowerShell is unavailable; cannot provision App Installer"
            )
        return ManagerPlan(
            ((powershell, "-NoProfile", "-NonInteractive", "-Command", _WINGET_INSTALL),)
        )
    if platform == MACOS:
        return ManagerPlan(
            blocked=(
                "Homebrew is unavailable. Its supported installer requires "
                "Xcode Command Line Tools, which are outside Adopt's runtime-only scope. "
                "No development tools were installed. "
                "Automatic installation without those prerequisites remains unsupported."
            )
        )
    return ManagerPlan(
        blocked="Ubuntu apt is unavailable; Adopt cannot safely replace "
        "the operating system package manager"
    )

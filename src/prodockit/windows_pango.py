# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Windows Pango evidence and bounded repair shared by bootstrap and diagnostics."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import asdict, dataclass

MSYS2_ROOTS = (
    r"$env:SystemDrive\msys64",
    r"$env:SystemDrive\msys2",
    r"$env:LOCALAPPDATA\Programs\msys64",
    r"$env:ProgramFiles\msys64",
    r"C:\tools\msys64",
)


@dataclass(frozen=True)
class PangoSpec:
    architecture: str
    environment: str
    package: str


@dataclass(frozen=True)
class WindowsPangoEvidence:
    architecture: str
    environment: str
    package: str
    root: str | None
    bin: str | None
    dll: str | None
    dll_exists: bool
    package_integrity: bool
    user_environment: str | None
    process_environment: str | None

    @property
    def environment_persisted(self) -> bool:
        return bool(self.bin and _same_path(self.user_environment, self.bin))

    @property
    def environment_current(self) -> bool:
        return bool(self.bin and _same_path(self.process_environment, self.bin))

    @property
    def healthy(self) -> bool:
        return (
            self.dll_exists
            and self.package_integrity
            and self.environment_persisted
            and self.environment_current
        )

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.update(
            environment_persisted=self.environment_persisted,
            environment_current=self.environment_current,
            healthy=self.healthy,
        )
        return value


def _same_path(left: str | None, right: str) -> bool:
    return bool(
        left
        and os.path.normcase(os.path.normpath(left))
        == os.path.normcase(os.path.normpath(right))
    )


def pango_spec(*, arm64: bool | None = None) -> PangoSpec:
    if arm64 is None:
        arm64 = platform.machine().casefold() in {"arm64", "aarch64"}
    if arm64:
        return PangoSpec("arm64", "clangarm64", "mingw-w64-clang-aarch64-pango")
    return PangoSpec("x64", "ucrt64", "mingw-w64-ucrt-x86_64-pango")


def probe_script(spec: PangoSpec) -> str:
    roots = ", ".join(f'"{root}"' for root in MSYS2_ROOTS)
    return (
        f"$roots = @({roots}); "
        '$root = $roots | Where-Object { Test-Path "$_\\usr\\bin\\bash.exe" } '
        "| Select-Object -First 1; "
        f"$msysEnv = '{spec.environment}'; $pkg = '{spec.package}'; "
        '$bin = if ($root) { Join-Path $root "$msysEnv\\bin" } else { $null }; '
        '$dll = if ($bin) { Join-Path $bin "libpango-1.0-0.dll" } else { $null }; '
        "$integrity = $false; "
        "if ($root) { "
        '& "$root\\usr\\bin\\bash.exe" -lc "pacman -Qkk $pkg" *> $null; '
        "$integrity = ($LASTEXITCODE -eq 0) }; "
        "$evidence = [ordered]@{ "
        f"architecture='{spec.architecture}'; environment=$msysEnv; package=$pkg; "
        "root=$root; bin=$bin; dll=$dll; dll_exists=[bool]($dll -and (Test-Path $dll)); "
        "package_integrity=$integrity; "
        "user_environment=[Environment]::GetEnvironmentVariable("
        "'WEASYPRINT_DLL_DIRECTORIES','User'); "
        "process_environment=$env:WEASYPRINT_DLL_DIRECTORIES }; "
        "$evidence | ConvertTo-Json -Compress"
    )


def repair_script(spec: PangoSpec) -> str:
    roots = ", ".join(f'"{root}"' for root in MSYS2_ROOTS)
    return (
        f"$roots = @({roots}); "
        '$root = $roots | Where-Object { Test-Path "$_\\usr\\bin\\bash.exe" } '
        "| Select-Object -First 1; "
        "if (-not $root) { Write-Error \"MSYS2 was not found. Looked in: "
        "$($roots -join ', ')\"; exit 1 }; "
        f"$msysEnv = '{spec.environment}'; $pkg = '{spec.package}'; "
        '$bin = Join-Path $root "$msysEnv\\bin"; '
        '$dll = Join-Path $bin "libpango-1.0-0.dll"; '
        '& "$root\\usr\\bin\\bash.exe" -lc "pacman -S --noconfirm --needed $pkg"; '
        "if ($LASTEXITCODE -ne 0) { throw 'Pango package installation failed' }; "
        '& "$root\\usr\\bin\\bash.exe" -lc "pacman -Qkk $pkg" *> $null; '
        "$integrity = ($LASTEXITCODE -eq 0); "
        "if (-not $integrity -or -not (Test-Path $dll)) { "
        '& "$root\\usr\\bin\\bash.exe" -lc "pacman -S --noconfirm $pkg"; '
        "if ($LASTEXITCODE -ne 0) { throw 'Pango package reinstall failed' }; "
        '& "$root\\usr\\bin\\bash.exe" -lc "pacman -Qkk $pkg" *> $null; '
        "$integrity = ($LASTEXITCODE -eq 0) }; "
        "if (-not $integrity) { throw 'Pango package integrity check failed after reinstall' }; "
        "if (-not (Test-Path $dll)) { throw \"Pango DLL is missing after reinstall: $dll\" }; "
        "$path = [Environment]::GetEnvironmentVariable('Path','User'); "
        '$entries = @($path -split ";" | Where-Object { $_ }); '
        'if ($path -notlike "*$bin*") { '
        "$path = (@($entries) + $bin) -join ';'; "
        "[Environment]::SetEnvironmentVariable('Path',$path,'User') }; "
        "[Environment]::SetEnvironmentVariable('WEASYPRINT_DLL_DIRECTORIES',$bin,'User'); "
        "$env:WEASYPRINT_DLL_DIRECTORIES = $bin; "
        '$env:Path = "$bin;$env:Path"; '
        'Write-Host "Verified $pkg and $dll; configured WEASYPRINT_DLL_DIRECTORIES=$bin"'
    )


def parse_evidence(output: str) -> WindowsPangoEvidence:
    try:
        value = json.loads(next(line for line in reversed(output.splitlines()) if line.strip()))
        return WindowsPangoEvidence(
            architecture=str(value["architecture"]),
            environment=str(value["environment"]),
            package=str(value["package"]),
            root=str(value["root"]) if value.get("root") else None,
            bin=str(value["bin"]) if value.get("bin") else None,
            dll=str(value["dll"]) if value.get("dll") else None,
            dll_exists=bool(value["dll_exists"]),
            package_integrity=bool(value["package_integrity"]),
            user_environment=(
                str(value["user_environment"]) if value.get("user_environment") else None
            ),
            process_environment=(
                str(value["process_environment"])
                if value.get("process_environment")
                else None
            ),
        )
    except (KeyError, StopIteration, TypeError, ValueError) as error:
        raise ValueError(f"Windows Pango probe returned invalid evidence: {error}") from error


def inspect_windows_pango(*, arm64: bool | None = None) -> WindowsPangoEvidence:
    spec = pango_spec(arm64=arm64)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", probe_script(spec)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if completed.returncode != 0:
        raise OSError(completed.stderr.strip() or "Windows Pango probe failed")
    return parse_evidence(completed.stdout)


__all__ = [
    "MSYS2_ROOTS",
    "PangoSpec",
    "WindowsPangoEvidence",
    "inspect_windows_pango",
    "pango_spec",
    "parse_evidence",
    "probe_script",
    "repair_script",
]

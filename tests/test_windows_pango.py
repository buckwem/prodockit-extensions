# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Windows Pango evidence and recovery for issue #722."""

from __future__ import annotations

import json

from prodockit.windows_pango import pango_spec, parse_evidence, probe_script, repair_script


def test_architecture_selects_the_matching_environment_and_package() -> None:
    arm = pango_spec(arm64=True)
    x64 = pango_spec(arm64=False)

    assert (arm.environment, arm.package) == (
        "clangarm64",
        "mingw-w64-clang-aarch64-pango",
    )
    assert (x64.environment, x64.package) == (
        "ucrt64",
        "mingw-w64-ucrt-x86_64-pango",
    )


def test_probe_distinguishes_dll_package_and_both_environment_scopes() -> None:
    script = probe_script(pango_spec(arm64=False))

    assert "libpango-1.0-0.dll" in script
    assert "pacman -Qkk" in script
    assert "'WEASYPRINT_DLL_DIRECTORIES','User'" in script
    assert "$env:WEASYPRINT_DLL_DIRECTORIES" in script


def test_repair_reinstalls_only_after_integrity_or_dll_failure() -> None:
    script = repair_script(pango_spec(arm64=True))

    assert "pacman -S --noconfirm --needed" in script
    assert "if (-not $integrity -or -not (Test-Path $dll))" in script
    assert "pacman -S --noconfirm $pkg" in script
    assert "integrity check failed after reinstall" in script
    assert "Pango DLL is missing after reinstall" in script


def test_evidence_requires_the_exact_persistent_and_current_directory() -> None:
    directory = r"C:\msys64\ucrt64\bin"
    evidence = parse_evidence(
        json.dumps(
            {
                "architecture": "x64",
                "environment": "ucrt64",
                "package": "mingw-w64-ucrt-x86_64-pango",
                "root": r"C:\msys64",
                "bin": directory,
                "dll": directory + r"\libpango-1.0-0.dll",
                "dll_exists": True,
                "package_integrity": True,
                "user_environment": directory,
                "process_environment": directory,
            }
        )
    )

    assert evidence.healthy
    assert evidence.as_dict()["healthy"] is True

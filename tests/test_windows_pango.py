# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Windows Pango evidence and recovery for issue #722."""

from __future__ import annotations

import json
import struct

from prodockit import windows_pango
from prodockit.windows_pango import (
    executable_architecture,
    pango_spec,
    parse_evidence,
    probe_script,
    repair_script,
)


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


def test_executable_architecture_uses_the_pe_machine_not_the_host(tmp_path) -> None:
    executable = tmp_path / "python.exe"
    image = bytearray(256)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 128)
    image[128:132] = b"PE\0\0"
    struct.pack_into("<H", image, 132, 0x8664)
    executable.write_bytes(image)

    assert executable_architecture(executable) == "x64"

    struct.pack_into("<H", image, 132, 0xAA64)
    executable.write_bytes(image)
    assert executable_architecture(executable) == "arm64"


def test_default_selection_uses_x64_python_on_an_arm64_host(
    tmp_path, monkeypatch
) -> None:
    executable = tmp_path / "python.exe"
    image = bytearray(256)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 128)
    image[128:132] = b"PE\0\0"
    struct.pack_into("<H", image, 132, 0x8664)
    executable.write_bytes(image)
    monkeypatch.setattr(windows_pango.sys, "executable", str(executable))
    monkeypatch.setattr(windows_pango.platform, "machine", lambda: "ARM64")

    selected = pango_spec()

    assert selected.architecture == "x64"
    assert selected.environment == "ucrt64"


def test_probe_distinguishes_dll_package_and_both_environment_scopes() -> None:
    script = probe_script(pango_spec(arm64=False))

    assert "libpango-1.0-0.dll" in script
    assert "pacman -Qkk" in script
    assert "'WEASYPRINT_DLL_DIRECTORIES','User'" in script
    assert "$env:WEASYPRINT_DLL_DIRECTORIES" in script


def test_repair_uses_shared_recovery_before_persisting_user_environment() -> None:
    script = repair_script(pango_spec(arm64=True))

    assert "-m prodockit.windows_msys2 --root $root" in script
    assert script.index("$LASTEXITCODE -ne 0") < script.index("SetEnvironmentVariable")
    assert "(@($bin) + $entries)" in script


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

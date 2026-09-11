# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise real Windows MSYS2 recovery with a synthetic trust failure.

The failing subprocess emits the regression's signature error without damaging
keys or caches. All subsequent key refreshes, upgrades and DLL loads are real.
Run only against the isolated CI installation, before building the wheel.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prodockit.windows_msys2 import Msys2Setup, SetupError
from prodockit.windows_pango import pango_spec

TRUST_COMMAND = "printf '%s\\n' 'error: MSYS2 signature is unknown trust (PGP signature)'; exit 1"


class InjectedTrustSetup(Msys2Setup):
    def __init__(self, root: Path, log: Path, *, persistent: bool) -> None:
        super().__init__(root, pango_spec(), log)
        self.persistent = persistent
        self.injected = False

    def run(self, phase: str, command: str) -> subprocess.CompletedProcess[str]:
        if phase == "full-upgrade" and (self.persistent or not self.injected):
            self.injected = True
            return super().run(phase, TRUST_COMMAND)
        return super().run(phase, command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("msys2-acceptance.json"))
    args = parser.parse_args()
    results: dict[str, object] = {"architecture": pango_spec().architecture, "status": "failed"}
    try:
        if platform.system() != "Windows":
            raise SetupError("Native acceptance requires Windows.")
        recovered = InjectedTrustSetup(args.root, Path("msys2-recovered.log"), persistent=False)
        directory = recovered.install()
        with getattr(os, "add_dll_directory")(str(directory)):  # noqa: B009 - Windows-only export
            getattr(ctypes, "WinDLL")(str(directory / "libpango-1.0-0.dll"))  # noqa: B009
        results["synthetic-trust-real-recovery"] = "passed"
        terminal = InjectedTrustSetup(args.root, Path("msys2-terminal.log"), persistent=True)
        try:
            terminal.install()
        except SetupError as error:
            # Infrastructure failures must not masquerade as expected exhaustion.
            if (
                terminal.trust_attempts != 2
                or error.phase != "full-upgrade"
                or error.category != "trust"
            ):
                raise
        else:
            raise SetupError("Persistent trust failure was incorrectly reported as success.")
        results["synthetic-persistent-trust-terminal"] = "passed"
        results["status"] = "passed"
        return 0
    except (OSError, SetupError) as error:
        results["error_type"] = type(error).__name__
        return 1
    finally:
        args.report.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

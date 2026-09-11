# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded, signature-preserving MSYS2 recovery, also runnable before wheel install.

Follow https://www.msys2.org/docs/updating/: refresh known keys, then install
msys2-keyring with signatures enabled and finish a full system upgrade.
Every subprocess goes through installer_process before another can start.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from prodockit.installer_process import InstallerCleanupError, run_installer
from prodockit.windows_pango import PangoSpec, executable_architecture, pango_spec


class SetupError(RuntimeError):
    """A terminal setup failure; never retry the enclosing installer."""

    def __init__(self, message: str, *, category: str = "permanent", phase: str = "") -> None:
        super().__init__(message)
        self.category = category
        self.phase = phase


def failure_category(output: str) -> str:
    text = output.casefold()
    # Permanent conditions take precedence over an incidental download error.
    for category, markers in (
        ("lock", ("unable to lock database", "failed to acquire lock", "database is locked")),
        (
            "architecture",
            ("invalid architecture", "not a valid win32 application", "bad exe format"),
        ),
        ("permanent", ("404", "403", "permission denied", "no space left", "ssl certificate")),
        ("trust", ("unknown trust", "pgp signature", "signature from", "required key missing")),
        (
            "download",
            (
                "failed retrieving file",
                "could not resolve host",
                "connection timed out",
                "connection reset",
                "operation too slow",
                "unexpected eof",
            ),
        ),
    ):
        if any(marker in text for marker in markers):
            return category
    return "permanent"


def sanitize(text: str) -> str:
    # Do not retain proxy credentials, signed query strings, or terminal controls.
    text = re.sub(r"https?://[^\s\"'<>]+", "[URL redacted]", text, flags=re.I)
    text = re.sub(
        r"(?i)\b(token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", text
    )
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)


class Msys2Setup:
    """One transaction with a shared recovery budget, not nested retries."""

    def __init__(self, root: Path, spec: PangoSpec, log: Path) -> None:
        self.root = root.resolve()
        self.spec = spec
        self.log = log
        self.trust_attempts = 0
        self.download_attempts = 0
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.message(
            f"Python={sys.version.split()[0]} architecture={spec.architecture} "
            f"environment={spec.environment} root={self.root} package={spec.package}"
        )

    def message(self, text: str, *, warning: bool = False) -> None:
        clean = sanitize(text)
        with self.log.open("a", encoding="utf-8") as stream:
            stream.write(clean + "\n")
        colour = "33" if warning else "36"
        if sys.stderr.isatty() and "NO_COLOR" not in os.environ:
            print(f"\033[{colour}m{clean}\033[0m", file=sys.stderr, flush=True)
        else:
            print(clean, file=sys.stderr, flush=True)

    def run(self, phase: str, command: str) -> subprocess.CompletedProcess[str]:
        self.message(
            f"phase={phase} trust-recovery={self.trust_attempts}/2 "
            f"download-recovery={self.download_attempts}/1"
        )
        env = dict(os.environ, LC_ALL="C", LANG="C", MSYSTEM=self.spec.environment.upper())
        try:
            result = run_installer(
                [str(self.root / "usr/bin/bash.exe"), "-lc", command],
                cwd=self.root,
                timeout=600,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired, InstallerCleanupError) as error:
            # A timeout or uncertain process ownership must never start a retry.
            self.message(
                f"phase={phase} stopped: {type(error).__name__}; no automatic retry", warning=True
            )
            raise SetupError(
                "Check for active installers before retrying; see the setup log."
            ) from error
        self.message(f"phase={phase} exit={result.returncode}\n{result.stdout}\n{result.stderr}")
        return result

    def cleanup_partial(self, output: str) -> None:
        """Remove only a named package partial; never databases, locks or whole caches."""
        cache = self.root / "var/cache/pacman/pkg"
        if cache.resolve() != cache or (self.root / "var/lib/pacman/db.lck").exists():
            return
        for name in set(
            re.findall(
                r"(?:^|[\s\"'])(?:/var/cache/pacman/pkg/)?"
                r"([\w+.-]+\.pkg\.tar\.(?:zst|xz)(?:\.part)?)(?=$|[\s\"':)])",
                output,
            )
        ):
            name = name if name.endswith(".part") else name + ".part"
            path = cache / name
            if path.is_symlink() or path.resolve().parent != cache.resolve():
                continue
            if path.is_file():
                path.unlink()
                self.message(f"Removed identified partial download: {name}", warning=True)

    def terminal(self, phase: str, category: str) -> None:
        advice = {
            "trust": (
                "Check the system clock and official MSYS2 keyring/update guidance. "
                "Signatures remain enabled."
            ),
            "download": "Check network, DNS and the configured MSYS2 mirror before retrying.",
            "lock": "Wait for the other package manager to finish. Do not delete db.lck.",
            "architecture": "Use the MSYS2 environment matching the Python executable.",
            "permanent": "Correct the reported package-manager error before retrying.",
        }[category]
        self.message(
            f"MSYS2 terminal failure category={category} phase={phase}. {advice}", warning=True
        )
        raise SetupError(advice, category=category, phase=phase)

    @staticmethod
    def core_restart(result: subprocess.CompletedProcess[str]) -> bool:
        output = (result.stdout + "\n" + result.stderr).casefold()
        return (
            "to complete this update all msys2 processes" in output
            and "will be closed" in output
            and "error:" not in output
        )

    def transaction(self, phase: str, command: str, *, core_restart: bool = False) -> None:
        while True:
            result = self.run(phase, command)
            if result.returncode == 0:
                return
            if core_restart and self.core_restart(result):
                self.message("Core upgrade closed its shell; a fresh full upgrade must succeed.")
                return
            output = result.stdout + "\n" + result.stderr
            category = failure_category(output)
            if category == "download" and self.download_attempts < 1:
                self.download_attempts += 1
                self.cleanup_partial(output)
                self.message(
                    "Retrying the failed download once after process shutdown.", warning=True
                )
                continue
            if category == "trust" and self.trust_attempts < 2:
                self.trust_attempts += 1
                if self.trust_attempts == 1:
                    self.message(
                        "Refreshing existing MSYS2 signing keys; signature checks remain enabled.",
                        warning=True,
                    )
                    refreshed = self.run("refresh-keys", "pacman-key --refresh-keys")
                    if refreshed.returncode != 0:
                        self.terminal(
                            "refresh-keys", failure_category(refreshed.stdout + refreshed.stderr)
                        )
                else:
                    self.message(
                        "Updating the signed MSYS2 keyring, then completing a full upgrade.",
                        warning=True,
                    )
                    # Recovery commands cannot recursively trigger recovery.
                    for repair_phase, repair in (
                        ("keyring", "pacman -Sy --noconfirm msys2-keyring"),
                        ("keyring-full-upgrade", "pacman -Syu --noconfirm"),
                        ("keyring-full-upgrade-final", "pacman -Syu --noconfirm"),
                    ):
                        repaired = self.run(repair_phase, repair)
                        if repair_phase == "keyring-full-upgrade" and self.core_restart(repaired):
                            continue
                        if repaired.returncode != 0:
                            self.terminal(
                                repair_phase, failure_category(repaired.stdout + repaired.stderr)
                            )
                continue
            self.terminal(phase, category)

    def install(self) -> Path:
        versions = self.run("versions", "bash --version; pacman --version")
        if versions.returncode:
            self.terminal("versions", "permanent")
        # MSYS2 supports full upgrades only. A second fresh shell completes core updates.
        self.transaction("full-upgrade", "pacman -Syu --noconfirm", core_restart=True)
        self.transaction("full-upgrade-final", "pacman -Syu --noconfirm")
        self.transaction("pango", f"pacman -S --noconfirm --needed {self.spec.package}")
        dll = self.root / self.spec.environment / "bin/libpango-1.0-0.dll"
        integrity = self.run("integrity", f"pacman -Qkk {self.spec.package}")
        if integrity.returncode or not dll.is_file():
            self.transaction("pango-reinstall", f"pacman -S --noconfirm {self.spec.package}")
            integrity = self.run("integrity-final", f"pacman -Qkk {self.spec.package}")
            if integrity.returncode or not dll.is_file():
                self.terminal("integrity-or-dll", "permanent")
        self.message(f"Verified Pango: {dll}")
        return dll.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    log = (
        args.log
        or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "prodockit/logs/msys2-setup.log"
    )
    try:
        setup = Msys2Setup(args.root, pango_spec(), log)
        if sys.platform == "win32" and executable_architecture() not in {"x64", "arm64"}:
            setup.terminal("python-architecture", "architecture")
        directory = setup.install()
        if os.environ.get("GITHUB_ENV"):
            with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
                stream.write(f"WEASYPRINT_DLL_DIRECTORIES={directory}\n")
        return 0
    except (OSError, SetupError) as error:
        print(f"MSYS2 setup failed: {sanitize(str(error))}. Log: {log}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

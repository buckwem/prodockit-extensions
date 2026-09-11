# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Fault-injected transactions exercise recovery without changing the host."""

import subprocess
from pathlib import Path

import pytest

from prodockit import windows_msys2 as native
from prodockit.installer_process import InstallerCleanupError
from prodockit.windows_pango import pango_spec

TRUST = 'error: signature from "Maintainer" is unknown trust (PGP signature)'


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "msys64"
    root.mkdir()
    return native.Msys2Setup(root, pango_spec(arm64=False), tmp_path / "setup.log")


def outcomes(monkeypatch, results):
    calls = []
    pending = iter(results)

    def run(command, **kwargs):
        calls.append(command[-1])
        value = next(pending)
        if isinstance(value, Exception):
            raise value
        code, output = value
        return subprocess.CompletedProcess(command, code, output, "")

    monkeypatch.setattr(native, "run_installer", run)
    return calls


def test_trust_recovers_after_refresh(monkeypatch, setup):
    calls = outcomes(monkeypatch, [(1, TRUST), (0, "refreshed"), (0, "")])
    setup.transaction("install", "pacman -S --needed pango")
    assert calls == [
        "pacman -S --needed pango",
        "pacman-key --refresh-keys",
        "pacman -S --needed pango",
    ]
    assert setup.trust_attempts == 1


def test_signed_keyring_recovery_completes_full_upgrade(monkeypatch, setup):
    calls = outcomes(
        monkeypatch, [(1, TRUST), (0, ""), (1, TRUST), (0, ""), (0, ""), (0, ""), (0, "")]
    )
    setup.transaction("install", "pacman -S --needed pango")
    assert calls[3:6] == [
        "pacman -Sy --noconfirm msys2-keyring",
        "pacman -Syu --noconfirm",
        "pacman -Syu --noconfirm",
    ]
    assert setup.trust_attempts == 2
    assert not any(
        marker in " ".join(calls)
        for marker in ("SigLevel", "--lsign", "--recv-keys", "--overwrite")
    )


def test_trust_exhaustion_is_terminal_and_logged(monkeypatch, setup):
    calls = outcomes(
        monkeypatch, [(1, TRUST), (0, ""), (1, TRUST), (0, ""), (0, ""), (0, ""), (1, TRUST)]
    )
    with pytest.raises(native.SetupError, match="Signatures remain enabled"):
        setup.transaction("install", "pacman -S pango")
    assert len(calls) == 7
    assert "category=trust" in setup.log.read_text()


def test_failed_signed_keyring_is_not_retried(monkeypatch, setup):
    calls = outcomes(monkeypatch, [(1, TRUST), (0, ""), (1, TRUST), (1, TRUST)])
    with pytest.raises(native.SetupError):
        setup.transaction("install", "pacman -S pango")
    assert len(calls) == 4


@pytest.mark.parametrize(
    "message,category",
    [
        ("unable to lock database: failed retrieving file", "lock"),
        ("package has invalid architecture", "architecture"),
        ("target not found: pango", "permanent"),
        ("SSL certificate problem", "permanent"),
    ],
)
def test_permanent_errors_never_retry(monkeypatch, setup, message, category):
    calls = outcomes(monkeypatch, [(1, message)])
    with pytest.raises(native.SetupError):
        setup.transaction("install", "pacman -S pango")
    assert len(calls) == 1
    assert f"category={category}" in setup.log.read_text()


@pytest.mark.parametrize(
    "error", [subprocess.TimeoutExpired("bash", 600), InstallerCleanupError("live children")]
)
def test_unverified_shutdown_never_retries(monkeypatch, setup, error):
    calls = outcomes(monkeypatch, [error])
    with pytest.raises(native.SetupError, match="active installers"):
        setup.transaction("install", "pacman -S pango")
    assert len(calls) == 1
    assert "no automatic retry" in setup.log.read_text()


def test_download_cleanup_preserves_unrelated_cache_and_user_files(monkeypatch, setup):
    cache = setup.root / "var/cache/pacman/pkg"
    cache.mkdir(parents=True)
    failed = cache / "pango-1.pkg.tar.zst.part"
    failed.write_text("partial")
    preserved = [
        cache / "other.pkg.tar.zst.part",
        cache / "pango-1.pkg.tar.zst",
        setup.root / "user.conf",
    ]
    for path in preserved:
        path.write_text("keep")
    calls = outcomes(
        monkeypatch, [(1, "failed retrieving file 'pango-1.pkg.tar.zst.part'"), (0, "")]
    )
    setup.transaction("install", "pacman -S pango")
    assert len(calls) == 2
    assert not failed.exists()
    assert all(path.read_text() == "keep" for path in preserved)


def test_cleanup_does_not_follow_symlinks(setup, tmp_path):
    cache = setup.root / "var/cache/pacman/pkg"
    cache.mkdir(parents=True)
    user = tmp_path / "user-data"
    user.write_text("keep")
    link = cache / "pango.pkg.tar.zst.part"
    try:
        link.symlink_to(user)
    except OSError:
        pytest.skip("host does not grant symlink creation")
    setup.cleanup_partial("failed retrieving file 'pango.pkg.tar.zst.part'")
    assert user.read_text() == "keep"
    assert link.is_symlink()


def test_network_budget_is_shared_between_transactions(monkeypatch, setup):
    calls = outcomes(
        monkeypatch, [(1, "failed retrieving file"), (0, ""), (1, "failed retrieving file")]
    )
    setup.transaction("upgrade", "pacman -Syu")
    with pytest.raises(native.SetupError):
        setup.transaction("install", "pacman -S pango")
    assert len(calls) == 3


@pytest.mark.parametrize("arm64", [False, True])
def test_install_verifies_matching_dll_and_reuses_warm_package(monkeypatch, tmp_path, arm64):
    root = tmp_path / "msys64"
    spec = pango_spec(arm64=arm64)
    dll = root / spec.environment / "bin/libpango-1.0-0.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"fixture")
    setup = native.Msys2Setup(root, spec, tmp_path / "setup.log")
    calls = outcomes(monkeypatch, [(0, "")] * 5)
    assert setup.install() == dll.parent
    assert calls[-2:] == [
        f"pacman -S --noconfirm --needed {spec.package}",
        f"pacman -Qkk {spec.package}",
    ]


def test_missing_dll_reinstall_cannot_report_success(monkeypatch, setup):
    calls = outcomes(monkeypatch, [(0, "")] * 7)
    with pytest.raises(native.SetupError):
        setup.install()
    assert len(calls) == 7
    assert "phase=integrity-or-dll" in setup.log.read_text()


def test_sanitized_log_contains_phase_exit_and_no_credentials(monkeypatch, setup):
    outcomes(
        monkeypatch, [(1, "error https://user:secret@example.com/path?token=abc password=123")]
    )
    with pytest.raises(native.SetupError):
        setup.transaction("install", "pacman -S pango")
    log = setup.log.read_text()
    assert "phase=install exit=1" in log
    assert "secret" not in log and "abc" not in log and "123" not in log


def test_ci_uses_shared_engine_before_build_with_no_action_owned_transactions():
    import yaml

    workflow = yaml.safe_load(Path(".github/workflows/adopt-install.yml").read_text())
    steps = workflow["jobs"]["template-sync"]["steps"]
    provision = next(step for step in steps if step.get("uses") == "msys2/setup-msys2@v2")
    assert provision["with"]["update"] is False
    assert "install" not in provision["with"]
    native_step = next(
        step for step in steps if "python -m prodockit.windows_msys2" in step.get("run", "")
    )
    build = next(step for step in steps if step.get("name") == "Build the candidate wheel")
    assert steps.index(native_step) < steps.index(build)
    assert "continue-on-error" not in native_step
    assert native_step["run"].count("python -m prodockit.windows_msys2") == 2


def test_core_restart_requires_successful_fresh_upgrade(monkeypatch, setup):
    calls = outcomes(
        monkeypatch,
        [
            (0, "versions"),
            (
                1,
                "To complete this update all MSYS2 processes including this terminal will be closed.",
            ),
            (1, "permanent failure"),
        ],
    )
    with pytest.raises(native.SetupError):
        setup.install()
    assert len(calls) == 3
    assert calls[-1] == "pacman -Syu --noconfirm"


def test_error_alongside_core_notice_is_not_ignored(monkeypatch, setup):
    calls = outcomes(
        monkeypatch,
        [(1, "To complete this update all MSYS2 processes will be closed. error: disk full")],
    )
    with pytest.raises(native.SetupError):
        setup.transaction("upgrade", "pacman -Syu", core_restart=True)
    assert len(calls) == 1


def test_cleanup_preserves_redirected_cache(setup, tmp_path):
    cache = setup.root / "var/cache/pacman/pkg"
    cache.parent.mkdir(parents=True)
    elsewhere = tmp_path / "shared-cache"
    elsewhere.mkdir()
    partial = elsewhere / "pango.pkg.tar.zst.part"
    partial.write_text("keep")
    try:
        cache.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("host does not grant symlink creation")
    setup.cleanup_partial("failed retrieving file 'pango.pkg.tar.zst.part'")
    assert partial.read_text() == "keep"


def test_bootstrap_does_not_restart_exhausted_shared_recovery():
    from prodockit.bootstrap import _safe_to_retry
    from prodockit.windows_pango import repair_script

    assert not _safe_to_retry(["powershell", "-Command", repair_script(pango_spec())])


@pytest.mark.parametrize(
    "message,category", [(TRUST, "trust"), ("pacman: unable to lock database", "lock")]
)
def test_bootstrap_reports_native_failure_category(message, category):
    from prodockit.bootstrap.model import WINDOWS, CommandResult
    from prodockit.bootstrap.recovery import recovery_advice

    advice = recovery_advice(
        "pandoc", WINDOWS, ["powershell"], CommandResult(1, "MSYS2 " + message)
    )
    assert advice.category == f"msys2-{category}"


def test_download_named_without_part_suffix_cleans_only_its_partial(setup):
    cache = setup.root / "var/cache/pacman/pkg"
    cache.mkdir(parents=True)
    archive = cache / "pango.pkg.tar.zst"
    archive.write_text("verified archive")
    partial = cache / (archive.name + ".part")
    partial.write_text("incomplete")
    setup.cleanup_partial("failed retrieving file 'pango.pkg.tar.zst' from mirror")
    assert archive.read_text() == "verified archive"
    assert not partial.exists()


def test_native_acceptance_never_counts_infrastructure_failure_as_expected(tmp_path, monkeypatch):
    import importlib
    import sys
    from contextlib import nullcontext

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    driver = importlib.import_module("windows_native_acceptance")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(driver.platform, "system", lambda: "Windows")
    monkeypatch.setattr(driver.os, "add_dll_directory", lambda path: nullcontext(), raising=False)
    monkeypatch.setattr(driver.ctypes, "WinDLL", lambda path: None, raising=False)
    monkeypatch.setattr(sys, "argv", ["acceptance", "--root", str(tmp_path)])

    def install(self):
        if self.persistent:
            self.trust_attempts = 2
            raise native.SetupError("network failed", category="download", phase="keyring")
        return tmp_path

    monkeypatch.setattr(driver.InjectedTrustSetup, "install", install)
    assert driver.main() == 1
    import json

    assert json.loads((tmp_path / "msys2-acceptance.json").read_text())["status"] == "failed"

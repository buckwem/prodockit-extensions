# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from prodockit import installer_process
from prodockit.installer_process import run_installer


@pytest.mark.parametrize(
    "python", ["/project/.venv/bin/python3.14", r"C:\project\.venv\Scripts\python.exe"]
)
def test_pip_progress_names_packages_not_python(python):
    label = installer_process._progress_label(
        [
            python,
            "-m",
            "pip",
            "install",
            "--retries",
            "5",
            "--index-url",
            "https://user:secret@example.test/simple",
            "zensical==0.0.59",
            "weasyprint==69.0",
        ]
    )
    assert label == "Installing project packages: zensical==0.0.59, weasyprint==69.0"
    assert "secret" not in label
    assert "python" not in label


def test_pip_progress_fallback_does_not_expose_urls():
    label = installer_process._progress_label(
        ["python", "-m", "pip", "install", "https://user:secret@example.test/pkg.whl"]
    )
    assert label == "Installing project packages in the active environment"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            ["bash", "-c", "private script"],
            "Preparing required system software and environment settings",
        ),
        (["brew", "install", "pango"], "Installing or updating PDF text-layout libraries"),
        (["brew", "install", "fontconfig"], "Installing or updating font detection tools"),
        (
            ["brew", "install", "--cask", "font-inter", "font-jetbrains-mono"],
            "Installing or updating Inter font, JetBrains Mono font",
        ),
        (["fc-cache", "-f"], "Refreshing the font list so PDF tools can find installed fonts"),
        (
            ["sudo", "-n", "-E", "apt-get", "install", "pango"],
            "Installing or updating required system software",
        ),
        ([r"C:\tools\npm.cmd", "ci"], "Installing project diagram or maths dependencies"),
        (
            ["node", "private/path/cli.js", "browsers", "install"],
            "Preparing the browser used to render diagrams",
        ),
        (["curl", "https://user:secret@example.test"], "Downloading required software"),
        (["unknown", "secret"], "Preparing required project tools"),
    ],
)
def test_progress_describes_work_without_raw_commands(command, expected):
    assert installer_process._progress_label(command) == expected


def test_homebrew_shell_wrapper_names_the_package():
    from prodockit.bootstrap.stages import _brew_upgrade_or_install

    assert installer_process._progress_label(_brew_upgrade_or_install("pango")) == (
        "Installing or updating PDF text-layout libraries"
    )


def test_real_installer_captures_output_and_exit_status(tmp_path):
    result = run_installer(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
        ],
        cwd=tmp_path,
        timeout=10,
    )
    assert result.returncode == 3
    assert result.stdout.strip() == "out"
    assert result.stderr.strip() == "err"


def test_real_installer_reports_elapsed_progress(tmp_path, capsys):
    run_installer(
        [sys.executable, "-c", "import time; time.sleep(0.2)"],
        cwd=tmp_path,
        timeout=10,
        progress_interval=0.05,
    )
    assert "Working:" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="POSIX owned-process-group acceptance")
def test_timeout_stops_descendant_before_it_can_write(tmp_path):
    marker = tmp_path / "survived"
    child = (
        "import time; from pathlib import Path; time.sleep(1.5); Path('survived').write_text('bad')"
    )
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(10)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_installer(
            [sys.executable, "-c", parent], cwd=tmp_path, timeout=0.5, progress_interval=0.1
        )
    time.sleep(1.6)
    assert not marker.exists()


def test_nonpositive_limits_rejected_before_launch(tmp_path):
    with pytest.raises(ValueError):
        run_installer(["never-run"], cwd=tmp_path, timeout=0)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group fixture")
def test_exited_parent_with_surviving_child_blocks_retry(tmp_path):
    from prodockit.renderer_resilience import run_with_retries

    calls = []
    child = "import time; time.sleep(10)"
    parent = (
        f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}]); sys.exit(1)"
    )

    def invoke():
        calls.append(True)
        return run_installer([sys.executable, "-c", parent], cwd=tmp_path, timeout=5)

    with pytest.raises(installer_process.InstallerCleanupError, match="child processes"):
        run_with_retries(
            "fixture",
            invoke,
            succeeded=lambda result: result.returncode == 0,
            failure_detail=lambda result: "ECONNRESET",
            retry_delays=(0, 0),
        )
    assert calls == [True]
    # A subsequent explicit invocation remains usable after owned-tree cleanup.
    assert (
        run_installer([sys.executable, "-c", "print('ok')"], cwd=tmp_path, timeout=5).returncode
        == 0
    )


@pytest.mark.parametrize("recovers", [True, False])
def test_child_shutdown_wait_is_bounded(monkeypatch, recovers):
    clock = [0.0]
    monkeypatch.setattr(installer_process.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        installer_process.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    monkeypatch.setattr(
        installer_process, "_descendants_remain", lambda pid, **kw: not recovers or clock[0] < 0.5
    )
    assert installer_process._wait_for_children(2345, grace=1) is recovers
    assert clock[0] == (0.5 if recovers else 1)


def test_child_shutdown_wait_does_not_hide_unknown_inventory(monkeypatch):
    def unknown(pid, **kwargs):
        raise installer_process.InstallerCleanupError("unverified")

    monkeypatch.setattr(installer_process, "_descendants_remain", unknown)
    with pytest.raises(installer_process.InstallerCleanupError, match="unverified"):
        installer_process._wait_for_children(2345, grace=1)


def test_cancellation_requests_cleanup_and_propagates(tmp_path, monkeypatch):
    stopped = []

    def interrupted(**kwargs):
        raise KeyboardInterrupt

    process = SimpleNamespace(pid=2345, wait=interrupted)
    monkeypatch.setattr(installer_process.subprocess, "Popen", lambda *args, **kw: process)
    monkeypatch.setattr(installer_process, "_stop", lambda value: stopped.append(value) or False)
    with pytest.raises(KeyboardInterrupt):
        run_installer(["fixture"], cwd=tmp_path, timeout=5)
    assert stopped == [process]


@pytest.mark.parametrize("output,returncode,expected", [("[]", 0, False), ("[1000]", 0, True)])
def test_windows_process_inventory(monkeypatch, output, returncode, expected):
    monkeypatch.setattr(installer_process, "_windows", lambda: True)
    monkeypatch.setattr(
        installer_process.subprocess,
        "run",
        lambda *args, **kw: SimpleNamespace(stdout=output, returncode=returncode),
    )
    assert installer_process._descendants_remain(2345) is expected


@pytest.mark.parametrize(
    "times,expected", [("[999]", False), ("[1000]", True), ("[999,1001]", True)]
)
def test_windows_pid_reuse_excludes_older_children(monkeypatch, times, expected):
    monkeypatch.setattr(installer_process, "_windows", lambda: True)
    monkeypatch.setattr(
        installer_process.subprocess,
        "run",
        lambda *args, **kw: SimpleNamespace(stdout=times, returncode=0),
    )
    assert installer_process._descendants_remain(2345, launched_at=1) is expected


@pytest.mark.parametrize("output,returncode", [("", 1), ('"unknown"', 0)])
def test_unverified_windows_inventory_blocks(monkeypatch, output, returncode):
    monkeypatch.setattr(installer_process, "_windows", lambda: True)
    monkeypatch.setattr(
        installer_process.subprocess,
        "run",
        lambda *args, **kw: SimpleNamespace(stdout=output, returncode=returncode),
    )
    with pytest.raises(installer_process.InstallerCleanupError, match="no automatic retry"):
        installer_process._descendants_remain(2345)


def test_bootstrap_install_uses_shared_capture_but_checks_do_not(tmp_path, monkeypatch):
    from prodockit.bootstrap import model

    calls = []

    def install(command, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 0, "done", "")

    monkeypatch.setattr(model, "run_installer", install)
    result = model.SubprocessRunner().run(
        ["fixture"], cwd=str(tmp_path), timeout=model.INSTALL_TIMEOUT_SECONDS
    )
    assert result.ok
    assert calls[0]["show_progress"] is False
    monkeypatch.setattr(
        model.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "", ""),
    )
    assert model.SubprocessRunner().run(["probe"]).ok
    assert len(calls) == 1


@pytest.mark.parametrize("status,verified", [(0, True), (1, False)])
def test_windows_cleanup_targets_owned_tree_and_reports_failure(monkeypatch, status, verified):
    commands = []
    waited = []
    killed = []
    monkeypatch.setattr(installer_process, "_windows", lambda: True)

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=status)

    monkeypatch.setattr(installer_process.subprocess, "run", run)
    process = SimpleNamespace(
        pid=12345, wait=lambda **kwargs: waited.append(True), kill=lambda: killed.append(True)
    )
    assert installer_process._stop(process) is verified
    assert commands == [["taskkill", "/PID", "12345", "/T", "/F"]]
    assert waited
    assert bool(killed) is (status != 0)

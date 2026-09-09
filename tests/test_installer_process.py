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

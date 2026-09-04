# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import csv
import io
import shutil
import zipfile
from pathlib import Path

import pytest

from tools import template_sync_acceptance as acceptance


def _candidate_wheel(root: Path, *, newline: str = "\n") -> Path:
    wheel = root / "prodockit-0.58.0-py3-none-any.whl"
    metadata = newline.join(
        ("Metadata-Version: 2.4", "Name: prodockit", "Version: 0.58.0", "")
    )
    package = f'__version__ = "0.58.0"{newline}'
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("prodockit/__init__.py", package)
        archive.writestr("prodockit-0.58.0.dist-info/METADATA", metadata)
        archive.writestr(
            "prodockit-0.58.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("prodockit-0.58.0.dist-info/RECORD", "")
    return wheel


def test_versioned_wheel_contains_real_code_and_coherent_new_metadata(tmp_path) -> None:
    candidate = _candidate_wheel(tmp_path)
    rewritten = acceptance.versioned_wheel(candidate, "0.57.999", tmp_path)

    assert acceptance.wheel_version(rewritten) == "0.57.999"
    with zipfile.ZipFile(rewritten) as archive:
        names = set(archive.namelist())
        assert "prodockit-0.57.999.dist-info/METADATA" in names
        assert "prodockit-0.58.0.dist-info/METADATA" not in names
        assert b'__version__ = "0.57.999"' in archive.read("prodockit/__init__.py")
        record = archive.read("prodockit-0.57.999.dist-info/RECORD").decode()
    rows = list(csv.reader(io.StringIO(record)))
    assert {row[0] for row in rows} == names
    assert next(row for row in rows if row[0].endswith("/RECORD"))[1:] == ["", ""]


def test_adjacent_versions_straddle_the_candidate() -> None:
    assert acceptance.adjacent_versions("0.58.0") == ("0.57.999", "0.58.1")


def test_versioned_wheel_rewrites_code_from_a_windows_checkout(tmp_path) -> None:
    candidate = _candidate_wheel(tmp_path, newline="\r\n")
    rewritten = acceptance.versioned_wheel(candidate, "0.57.999", tmp_path)

    with zipfile.ZipFile(rewritten) as archive:
        package = archive.read("prodockit/__init__.py")

    assert package == b'__version__ = "0.57.999"\r\n'


def test_remove_tree_retries_transient_windows_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    real_rmtree = shutil.rmtree

    def flaky_rmtree(path: Path, *, onerror: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("temporary checkout handle")
        real_rmtree(path, onerror=onerror)  # type: ignore[arg-type]

    monkeypatch.setattr(acceptance.shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(acceptance.time, "sleep", lambda _seconds: None)

    acceptance.remove_tree(tmp_path)

    assert calls == 2
    assert not tmp_path.exists()

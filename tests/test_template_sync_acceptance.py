# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from tools import template_sync_acceptance as acceptance


def _candidate_wheel(root: Path) -> Path:
    wheel = root / "prodockit-0.58.0-py3-none-any.whl"
    metadata = "Metadata-Version: 2.4\nName: prodockit\nVersion: 0.58.0\n"
    package = '__version__ = "0.58.0"\n'
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

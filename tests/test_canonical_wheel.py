# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Canonical candidate-wheel identity tests for the protected release gate."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
wheel_identity = importlib.import_module("canonical_wheel")


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def write_wheel(
    path: Path,
    *,
    order: tuple[str, ...] = ("module.py", "METADATA", "WHEEL"),
    timestamp: tuple[int, int, int, int, int, int] = (2026, 9, 1, 12, 0, 0),
    compression: int = zipfile.ZIP_DEFLATED,
    alter_record: str | None = None,
    module: bytes = b'__version__ = "0.54.0"\n',
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dist_info = "prodockit-0.54.0.dist-info"
    files = {
        "prodockit/__init__.py": module,
        f"{dist_info}/METADATA": b"Metadata-Version: 2.4\nName: prodockit\nVersion: 0.54.0\n\n",
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    aliases = {
        "module.py": "prodockit/__init__.py",
        "METADATA": f"{dist_info}/METADATA",
        "WHEEL": f"{dist_info}/WHEEL",
    }
    record_name = f"{dist_info}/RECORD"
    rows = [[name, _record_hash(data), str(len(data))] for name, data in sorted(files.items())]
    rows.append([record_name, "", ""])
    record = io.StringIO(newline="")
    csv.writer(record, lineterminator="\n").writerows(rows)
    record_data = record.getvalue().encode("utf-8")
    if alter_record == "hash":
        record_data = record_data.replace(b"sha256=", b"sha256=x", 1)
    elif alter_record == "missing":
        record_data = b"\n".join(record_data.splitlines()[1:]) + b"\n"

    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for short_name in order:
            name = aliases[short_name]
            info = zipfile.ZipInfo(name, date_time=timestamp)
            info.compress_type = compression
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
        info = zipfile.ZipInfo(record_name, date_time=timestamp)
        info.compress_type = compression
        info.external_attr = 0o100644 << 16
        archive.writestr(info, record_data)
    return path


def test_canonical_identity_ignores_zip_order_timestamp_and_compression(
    tmp_path: Path,
) -> None:
    wheel_name = "prodockit-0.54.0-py3-none-any.whl"
    first = write_wheel(tmp_path / "first" / wheel_name)
    second = write_wheel(
        tmp_path / "second" / wheel_name,
        order=("WHEEL", "module.py", "METADATA"),
        timestamp=(2026, 9, 2, 14, 30, 0),
        compression=zipfile.ZIP_STORED,
    )

    left = wheel_identity.inspect_wheel(first)
    right = wheel_identity.inspect_wheel(second)

    assert left.wheel_sha256 != right.wheel_sha256
    assert left.wheel_contents_sha256 == right.wheel_contents_sha256
    assert left.distribution == "prodockit"
    assert left.version == "0.54.0"
    assert left.file_count == 4


def test_canonical_identity_changes_with_file_content(tmp_path: Path) -> None:
    wheel_name = "prodockit-0.54.0-py3-none-any.whl"
    first = write_wheel(tmp_path / "first" / wheel_name)
    second = write_wheel(
        tmp_path / "second" / wheel_name,
        module=b'__version__ = "0.54.0"\nVALUE = 2\n',
    )

    left = wheel_identity.inspect_wheel(first)
    right = wheel_identity.inspect_wheel(second)

    assert left.wheel_contents_sha256 != right.wheel_contents_sha256


def test_unrecorded_member_is_rejected(tmp_path: Path) -> None:
    candidate = write_wheel(tmp_path / "prodockit-0.54.0-py3-none-any.whl")
    with zipfile.ZipFile(candidate, "a") as archive:
        archive.writestr("another.txt", b"different")

    with pytest.raises(wheel_identity.WheelIdentityError, match="RECORD omits"):
        wheel_identity.inspect_wheel(candidate)


@pytest.mark.parametrize("problem", ["hash", "missing"])
def test_record_must_match_every_member(tmp_path: Path, problem: str) -> None:
    candidate = write_wheel(tmp_path / "prodockit-0.54.0-py3-none-any.whl", alter_record=problem)

    with pytest.raises(wheel_identity.WheelIdentityError, match="wheel RECORD"):
        wheel_identity.inspect_wheel(candidate)


def test_cli_writes_the_closed_identity(tmp_path: Path) -> None:
    candidate = write_wheel(tmp_path / "prodockit-0.54.0-py3-none-any.whl")
    output = tmp_path / "identity.json"

    wheel_identity.main([str(candidate), "--output", str(output)])

    value = json.loads(output.read_text(encoding="utf-8"))
    assert set(value) == {
        "canonical_format",
        "distribution",
        "file_count",
        "filename",
        "schema",
        "size",
        "version",
        "wheel_contents_sha256",
        "wheel_sha256",
    }
    assert value["canonical_format"] == "prodockit-wheel-content-v1"

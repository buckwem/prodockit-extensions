# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tools import check_shared_file_wheel


def _wheel(path: Path, resource: str, content: bytes | None) -> Path:
    wheel = path / "prodockit-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        if content is not None:
            archive.writestr(resource, content)
    return wheel


def test_wheel_resource_must_match_the_canonical_file(tmp_path: Path) -> None:
    resource = "prodockit/assets/pdk.css"
    canonical = tmp_path / "pdk.css"
    canonical.write_bytes(b"canonical\n")
    wheel = _wheel(tmp_path, resource, b"canonical\n")

    check_shared_file_wheel.check(wheel, {resource: canonical})


@pytest.mark.parametrize("content", [None, b"older copy\n"])
def test_missing_or_different_wheel_resource_is_rejected(
    tmp_path: Path, content: bytes | None
) -> None:
    resource = "prodockit/assets/pdk-pdf.css"
    canonical = tmp_path / "pdk-pdf.css"
    canonical.write_bytes(b"canonical\n")
    wheel = _wheel(tmp_path, resource, content)

    with pytest.raises(ValueError):
        check_shared_file_wheel.check(wheel, {resource: canonical})


def test_single_wheel_directory_is_resolved(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, "prodockit/assets/pdk.css", b"content")

    assert check_shared_file_wheel.resolve_wheel(tmp_path) == wheel

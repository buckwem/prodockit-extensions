# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tools import check_shared_file_wheel


def _wheel(path: Path, content: bytes | None) -> Path:
    wheel = path / "prodockit-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        if content is not None:
            archive.writestr(check_shared_file_wheel.RESOURCE, content)
    return wheel


def test_wheel_resource_must_match_the_canonical_file(tmp_path: Path) -> None:
    canonical = tmp_path / "extra.css"
    canonical.write_bytes(b"canonical\n")
    wheel = _wheel(tmp_path, b"canonical\n")

    check_shared_file_wheel.check(wheel, canonical)


@pytest.mark.parametrize("content", [None, b"older copy\n"])
def test_missing_or_different_wheel_resource_is_rejected(
    tmp_path: Path, content: bytes | None
) -> None:
    canonical = tmp_path / "extra.css"
    canonical.write_bytes(b"canonical\n")
    wheel = _wheel(tmp_path, content)

    with pytest.raises(ValueError):
        check_shared_file_wheel.check(wheel, canonical)


def test_single_wheel_directory_is_resolved(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, b"content")

    assert check_shared_file_wheel.resolve_wheel(tmp_path) == wheel

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.pdf import runtime_download
from prodockit.pdf.runtime_store import RuntimeStoreError


def test_download_rejects_unapproved_hosts_before_opening(tmp_path: Path) -> None:
    with pytest.raises(RuntimeStoreError, match="unapproved"):
        runtime_download.download_release_asset(
            "https://example.invalid/tool.zip",
            tmp_path / "tool.zip",
            expected_bytes=1,
            label="fixture",
        )


def test_download_enforces_declared_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        def __init__(self) -> None:
            self.headers = {"Content-Length": "3"}

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://github.com/example/tool.zip"

        def read(self, _size: int) -> bytes:
            return b""

    monkeypatch.setattr(runtime_download, "_open_download", lambda *_args: Response())
    monkeypatch.setattr(runtime_download, "_DOWNLOAD_ATTEMPTS", 1)

    with pytest.raises(RuntimeStoreError, match="size changed"):
        runtime_download.download_release_asset(
            "https://github.com/example/tool.zip",
            tmp_path / "tool.zip",
            expected_bytes=4,
            label="fixture",
        )

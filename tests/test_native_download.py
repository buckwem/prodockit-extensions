# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import tarfile
import urllib.error
import zipfile
from pathlib import Path

import pytest

from tools import native_download


class Response(io.BytesIO):
    def __init__(
        self,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
        final_url: str = "https://cdn.example.invalid/fixture",
        declared_size: int | None = None,
        encoding: str = "",
    ) -> None:
        super().__init__(content)
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(content) if declared_size is None else declared_size),
            "Content-Encoding": encoding,
        }
        self.final_url = final_url

    def geturl(self) -> str:
        return self.final_url


def _zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("fixture/file.txt", "valid")
    return output.getvalue()


def _tar_bytes() -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        content = b"valid"
        member = tarfile.TarInfo("fixture/file.txt")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    return output.getvalue()


def _deb_bytes() -> bytes:
    content = b"fixture"
    header = (
        b"debian-binary/  "
        + b"0           "
        + b"0     "
        + b"0     "
        + b"100644  "
        + f"{len(content):<10}".encode()
        + b"`\n"
    )
    assert len(header) == 60
    return native_download.DEB_MAGIC + header + content + b"\n"


def _msi_bytes() -> bytes:
    return native_download.MSI_MAGIC + bytes(512 - len(native_download.MSI_MAGIC))


def test_invalid_first_zip_then_valid_response_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    valid = _zip_bytes()
    responses = iter((Response(b"not a zip"), Response(valid)))
    sleeps: list[float] = []

    destination = native_download.download(
        "https://example.invalid/vscode",
        tmp_path / "vscode.zip",
        opener=lambda *_args, **_kwargs: next(responses),
        sleep=sleeps.append,
    )

    assert destination.read_bytes() == valid
    assert sleeps == [1.0]
    assert not (tmp_path / "vscode.zip.part").exists()
    output = capsys.readouterr().out
    assert "bytes=9 attempt=1/3" in output
    assert "validation=DownloadValidationError: invalid ZIP archive" in output
    assert "attempt=2/3" in output


def test_invalid_payload_retry_exhaustion_is_bounded(tmp_path: Path) -> None:
    calls = 0

    def invalid(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return Response(b"still not a zip")

    with pytest.raises(native_download.DownloadError, match="after 3 attempts"):
        native_download.download(
            "https://example.invalid/vscode",
            tmp_path / "vscode.zip",
            opener=invalid,
            sleep=lambda _seconds: None,
        )

    assert calls == 3
    assert not (tmp_path / "vscode.zip").exists()
    assert not (tmp_path / "vscode.zip.part").exists()


def test_transient_http_failure_is_retried(tmp_path: Path) -> None:
    attempts = iter(
        (
            urllib.error.HTTPError(
                "https://example.invalid/fixture",
                503,
                "temporarily unavailable",
                {"Content-Type": "text/plain"},
                None,
            ),
            Response(_zip_bytes()),
        )
    )

    def open_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    result = native_download.download(
        "https://example.invalid/fixture",
        tmp_path / "fixture.vsix",
        opener=open_next,
        sleep=lambda _seconds: None,
    )

    assert result.is_file()


def test_transient_network_failure_is_retried(tmp_path: Path) -> None:
    attempts = iter(
        (
            urllib.error.URLError("connection reset"),
            Response(_zip_bytes()),
        )
    )

    def open_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    result = native_download.download(
        "https://example.invalid/fixture",
        tmp_path / "fixture.zip",
        opener=open_next,
        sleep=lambda _seconds: None,
    )

    assert result.is_file()


def test_permanent_http_failure_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def missing(request, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

    with pytest.raises(urllib.error.HTTPError) as raised:
        native_download.download(
            "https://example.invalid/withdrawn",
            tmp_path / "fixture.vsix",
            opener=missing,
            sleep=lambda _seconds: None,
        )

    assert raised.value.code == 404
    assert calls == 1


def test_truncated_payload_is_removed_before_retry(tmp_path: Path) -> None:
    valid = _zip_bytes()
    responses = iter(
        (
            Response(valid[:20], declared_size=200),
            Response(valid),
        )
    )

    result = native_download.download(
        "https://example.invalid/fixture",
        tmp_path / "fixture.zip",
        opener=lambda *_args, **_kwargs: next(responses),
        sleep=lambda _seconds: None,
    )

    assert result.read_bytes() == valid


@pytest.mark.parametrize(
    ("name", "content"),
    (
        ("fixture.zip", _zip_bytes()),
        ("fixture.vsix", _zip_bytes()),
        ("fixture.tar.gz", _tar_bytes()),
        ("fixture.deb", _deb_bytes()),
        ("fixture.msi", _msi_bytes()),
    ),
)
def test_supported_native_fixture_formats_are_validated(
    tmp_path: Path, name: str, content: bytes
) -> None:
    path = tmp_path / name
    path.write_bytes(content)
    native_download.validate_download(path)


def test_success_report_names_redirect_type_size_and_attempt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    native_download.download(
        "https://example.invalid/source",
        tmp_path / "fixture.zip",
        opener=lambda *_args, **_kwargs: Response(
            _zip_bytes(),
            content_type="application/zip",
            final_url="https://cdn.example.invalid/final.zip",
        ),
        sleep=lambda _seconds: None,
    )

    output = capsys.readouterr().out
    assert "source=https://example.invalid/source" in output
    assert "final=https://cdn.example.invalid/final.zip" in output
    assert "type=application/zip" in output
    assert "bytes=" in output
    assert "attempt=1/3" in output


def test_validated_download_is_restored_from_a_shared_cache(tmp_path: Path) -> None:
    content = _zip_bytes()
    cache = tmp_path / "cache"
    first = tmp_path / "first" / "fixture.zip"
    second = tmp_path / "second" / "fixture.zip"

    native_download.download(
        "https://primary.example.invalid/fixture",
        first,
        opener=lambda *_args, **_kwargs: Response(content),
        cache_dir=cache,
        cache_key="logical-fixture",
        sleep=lambda _seconds: None,
    )
    native_download.download(
        "https://mirror.example.invalid/fixture",
        second,
        opener=lambda *_args, **_kwargs: pytest.fail("cache miss"),
        cache_dir=cache,
        cache_key="logical-fixture",
        sleep=lambda _seconds: None,
    )

    assert second.read_bytes() == content
    assert len(list(cache.iterdir())) == 1


def test_invalid_cached_archive_is_discarded_and_replaced(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    destination = tmp_path / "fixture.zip"
    cached = native_download._cache_path(cache, "logical-fixture", destination)
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"invalid")

    native_download.download(
        "https://example.invalid/fixture",
        destination,
        opener=lambda *_args, **_kwargs: Response(_zip_bytes()),
        cache_dir=cache,
        cache_key="logical-fixture",
        sleep=lambda _seconds: None,
    )

    native_download.validate_download(cached)
    assert cached.read_bytes() == destination.read_bytes()


def test_expected_sha256_is_checked_before_caching(tmp_path: Path) -> None:
    content = _zip_bytes()
    expected = hashlib.sha256(content).hexdigest()

    result = native_download.download(
        "https://example.invalid/fixture",
        tmp_path / "fixture.zip",
        opener=lambda *_args, **_kwargs: Response(content),
        expected_sha256=expected,
        cache_dir=tmp_path / "cache",
        sleep=lambda _seconds: None,
    )

    assert result.is_file()


def test_cache_write_failure_does_not_discard_a_valid_download(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_cache(*_args: object, **_kwargs: object) -> None:
        raise OSError("cache volume unavailable")

    monkeypatch.setattr(native_download, "_store_cache", fail_cache)
    destination = native_download.download(
        "https://example.invalid/fixture",
        tmp_path / "fixture.zip",
        opener=lambda *_args, **_kwargs: Response(_zip_bytes()),
        cache_dir=tmp_path / "cache",
        sleep=lambda _seconds: None,
    )

    assert destination.is_file()
    assert "download cache write skipped" in capsys.readouterr().out


def test_cache_read_failure_falls_back_to_the_source(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "cache"
    destination = tmp_path / "fixture.zip"
    cached = native_download._cache_path(cache, "logical-fixture", destination)
    cached.parent.mkdir(parents=True)
    cached.write_bytes(_zip_bytes())
    real_copy = native_download.shutil.copy2
    calls = 0

    def fail_first_copy(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("cache volume unavailable")
        return real_copy(*args, **kwargs)

    monkeypatch.setattr(native_download.shutil, "copy2", fail_first_copy)
    result = native_download.download(
        "https://example.invalid/fixture",
        destination,
        opener=lambda *_args, **_kwargs: Response(_zip_bytes()),
        cache_dir=cache,
        cache_key="logical-fixture",
        sleep=lambda _seconds: None,
    )

    assert result.is_file()
    assert "download cache read skipped" in capsys.readouterr().out

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Citation-style downloads are validated, cached and installed atomically."""

from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import pytest

from prodockit import csl

VALID_CSL = b"""<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0">
  <info><title>Cite Them Right 12th edition - Harvard</title><id>test</id></info>
</style>
"""


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_online_install_validates_and_populates_the_cache(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache" / csl.DEFAULT_CSL_STYLE
    target = tmp_path / "project" / csl.DEFAULT_CSL_STYLE
    monkeypatch.setattr(csl, "cache_path", lambda: cache)
    monkeypatch.setattr(
        csl.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(VALID_CSL)
    )

    assert csl.install(target) == target
    assert target.read_bytes() == VALID_CSL
    assert cache.read_bytes() == VALID_CSL
    csl.validate(target)
    assert not list(target.parent.glob("*.part"))


def test_offline_install_uses_a_validated_cache(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache" / csl.DEFAULT_CSL_STYLE
    cache.parent.mkdir()
    cache.write_bytes(VALID_CSL)
    target = tmp_path / "project" / csl.DEFAULT_CSL_STYLE
    monkeypatch.setattr(csl, "cache_path", lambda: cache)

    csl.install(target, offline=True)

    assert target.read_bytes() == VALID_CSL


def test_offline_install_names_the_url_and_cache_when_the_asset_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    cache = tmp_path / "cache" / csl.DEFAULT_CSL_STYLE
    monkeypatch.setattr(csl, "cache_path", lambda: cache)

    with pytest.raises(csl.CslError) as caught:
        csl.install(tmp_path / "project" / csl.DEFAULT_CSL_STYLE, offline=True)

    assert csl.CSL_STYLE_URL in str(caught.value)
    assert str(cache) in str(caught.value)


def test_invalid_download_never_replaces_the_destination(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "project" / csl.DEFAULT_CSL_STYLE
    monkeypatch.setattr(csl, "cache_path", lambda: tmp_path / "cache" / csl.DEFAULT_CSL_STYLE)
    monkeypatch.setattr(
        csl.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"<html>not a CSL style</html>"),
    )

    with pytest.raises(csl.CslError, match="not a CSL style"):
        csl.install(target)

    assert not target.exists()
    assert not list(target.parent.glob("*.part"))


def test_existing_style_is_preserved_without_a_network_request(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / csl.DEFAULT_CSL_STYLE
    target.write_bytes(VALID_CSL)
    monkeypatch.setattr(
        csl.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail("existing files must not be downloaded again"),
    )

    csl.install(target)

    assert target.read_bytes() == VALID_CSL


@pytest.mark.parametrize(
    "content", [b"not XML", b"<html/>", b"", b'<style xmlns="http://purl.org/net/xbiblio/csl"/>']
)
def test_invalid_existing_style_is_preserved_and_rejected(
    tmp_path: Path, monkeypatch, content
) -> None:
    target = tmp_path / "custom.csl"
    target.write_bytes(content)
    monkeypatch.setattr(csl.urllib.request, "urlopen", lambda *a, **k: pytest.fail("no download"))
    with pytest.raises(csl.CslError, match="Existing file preserved"):
        csl.install(target)
    assert target.read_bytes() == content


@pytest.mark.parametrize("failure", [429, 503, TimeoutError(), ConnectionResetError()])
def test_transient_download_recovers(tmp_path: Path, monkeypatch, failure) -> None:
    target = tmp_path / "style.csl"
    cache = tmp_path / "cache" / "style.csl"
    monkeypatch.setattr(csl, "cache_path", lambda: cache)
    sleeps = []
    monkeypatch.setattr(csl.time, "sleep", sleeps.append)
    calls = []

    def download(request, **kwargs):
        calls.append(request)
        if len(calls) == 1:
            if isinstance(failure, int):
                raise urllib.error.HTTPError(request.full_url, failure, "failed", {}, None)
            raise failure
        assert not list(tmp_path.rglob("*.part"))
        return _Response(VALID_CSL)

    monkeypatch.setattr(csl.urllib.request, "urlopen", download)
    csl.install(target)
    assert len(calls) == 2
    assert sleeps == [1]
    assert target.read_bytes() == cache.read_bytes() == VALID_CSL


@pytest.mark.parametrize("status, attempts", [(404, 1), (503, 3)])
def test_failed_download_leaves_no_partial_files(
    tmp_path: Path, monkeypatch, status, attempts
) -> None:
    target = tmp_path / "style.csl"
    cache = tmp_path / "cache" / "style.csl"
    monkeypatch.setattr(csl, "cache_path", lambda: cache)
    monkeypatch.setattr(csl.time, "sleep", lambda _: None)
    calls = []

    def download(request, **kwargs):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, status, "failed", {}, None)

    monkeypatch.setattr(csl.urllib.request, "urlopen", download)
    with pytest.raises(csl.CslError, match=f"after {attempts} attempt"):
        csl.install(target)
    assert len(calls) == attempts
    assert not target.exists() and not cache.exists()
    assert not list(tmp_path.rglob("*.part"))


def test_existing_directory_is_not_accepted_as_a_style(tmp_path: Path) -> None:
    target = tmp_path / csl.DEFAULT_CSL_STYLE
    target.mkdir()

    with pytest.raises(csl.CslError, match="is not a file"):
        csl.install(target)


def test_interrupted_body_is_discarded_before_retry(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "style.csl"
    monkeypatch.setattr(csl, "cache_path", lambda: tmp_path / "cache" / "style.csl")
    monkeypatch.setattr(csl.time, "sleep", lambda _: None)

    class Interrupted(_Response):
        def read(self, size=-1):
            if self.tell():
                raise ConnectionResetError("connection lost during body")
            return super().read(8)

    calls = []

    def download(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            return Interrupted(VALID_CSL)
        assert not list(tmp_path.rglob("*.part"))
        return _Response(VALID_CSL)

    monkeypatch.setattr(csl.urllib.request, "urlopen", download)
    csl.install(target)
    assert len(calls) == 2
    assert target.read_bytes() == VALID_CSL

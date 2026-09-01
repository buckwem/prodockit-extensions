# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for the closed GitHub candidate fixture builder."""

from __future__ import annotations

import importlib
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
fixture_builder = importlib.import_module("bootstrap_live_provider_github_fixture")
state = importlib.import_module("live_provider_state")


def git(checkout: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(checkout), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def source_checkout(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / ".prodockit-template.toml").write_text("[template]\n", encoding="utf-8")
    git(source, "add", ".")
    git(source, "commit", "-m", "Fixture")
    git(source, "remote", "add", "origin", fixture_builder.PUBLIC_TEMPLATE)
    return source, git(source, "rev-parse", "HEAD")


def handoff(commit: str) -> state.ResetHandoff:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return state.ResetHandoff(
        schema=2,
        run_id=str(uuid.uuid4()),
        provider="github",
        project_id=1,
        path_with_namespace=state.GITHUB_PATH,
        repository_empty=True,
        deploy_key_id=2,
        deploy_key_fingerprint="SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        source_commit=commit,
        source_refs_digest="a" * 64,
        candidate_version="0.54.0",
        wheel_sha256="b" * 64,
        controller_commit="c" * 40,
        completed_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(minutes=30)).isoformat(),
        wheel_contents_sha256="d" * 64,
    )


def test_fixture_is_bound_to_clean_exact_public_source(tmp_path: Path) -> None:
    source, commit = source_checkout(tmp_path)

    fixture = fixture_builder.create_fixture(
        handoff=handoff(commit),
        source_checkout=source,
    )

    assert fixture.provider == "github"
    assert fixture.source_remote == fixture_builder.PUBLIC_TEMPLATE
    assert fixture.source_head == commit
    assert fixture.destination_remote == fixture_builder.DESTINATION_REMOTE


def test_fixture_refuses_wrong_commit_origin_and_dirty_source(tmp_path: Path) -> None:
    source, commit = source_checkout(tmp_path)

    with pytest.raises(fixture_builder.FixtureError, match="source commit"):
        fixture_builder.create_fixture(handoff=handoff("f" * 40), source_checkout=source)

    git(source, "remote", "set-url", "origin", "https://example.invalid/template.git")
    with pytest.raises(fixture_builder.FixtureError, match="unexpected origin"):
        fixture_builder.create_fixture(handoff=handoff(commit), source_checkout=source)

    git(source, "remote", "set-url", "origin", fixture_builder.PUBLIC_TEMPLATE)
    (source / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(fixture_builder.FixtureError, match="not clean"):
        fixture_builder.create_fixture(handoff=handoff(commit), source_checkout=source)

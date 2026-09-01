# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for the closed Surrey candidate fixture builder."""

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
builder = importlib.import_module("bootstrap_live_provider_surrey_fixture")
state = importlib.import_module("live_provider_state")

COMMIT = "1" * 40


def git(checkout: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(checkout), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def handoff(*, source_commit: str) -> state.ResetHandoff:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return state.ResetHandoff(
        schema=2,
        run_id=str(uuid.uuid4()),
        provider="surrey",
        project_id=404,
        path_with_namespace=state.SURREY_PATH,
        repository_empty=True,
        deploy_key_id=303,
        deploy_key_fingerprint=state.SURREY_DEPLOY_KEY_FINGERPRINT,
        source_commit=source_commit,
        source_refs_digest="b" * 64,
        candidate_version="0.54.0",
        wheel_sha256="a" * 64,
        controller_commit="c" * 40,
        completed_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(minutes=30)).isoformat(),
        wheel_contents_sha256="d" * 64,
    )


def source_checkout(tmp_path: Path) -> tuple[Path, str]:
    checkout = tmp_path / "template"
    checkout.mkdir()
    git(checkout, "init", "-b", "main")
    git(checkout, "config", "user.name", "Fixture")
    git(checkout, "config", "user.email", "fixture@example.invalid")
    (checkout / ".prodockit-template.toml").write_text("[template]\n", encoding="utf-8")
    git(checkout, "add", "-A")
    git(checkout, "commit", "-m", "Template")
    commit = git(checkout, "rev-parse", "HEAD")
    git(checkout, "remote", "add", "origin", builder.SURREY_SOURCE)
    return checkout, commit


def test_fixture_is_bound_to_clean_exact_surrey_source(tmp_path: Path) -> None:
    checkout, commit = source_checkout(tmp_path)

    fixture = builder.create_fixture(
        handoff=handoff(source_commit=commit),
        source_checkout=checkout,
    )

    assert fixture.provider == "surrey"
    assert fixture.source_remote == builder.SURREY_SOURCE
    assert fixture.destination_remote == builder.SURREY_DESTINATION
    assert len(fixture.template_marker_sha256) == 64


def test_fixture_rejects_another_source_origin(tmp_path: Path) -> None:
    checkout, commit = source_checkout(tmp_path)
    git(checkout, "remote", "set-url", "origin", "git@example.invalid:other/template.git")

    with pytest.raises(builder.FixtureError, match="unexpected origin"):
        builder.create_fixture(
            handoff=handoff(source_commit=commit),
            source_checkout=checkout,
        )


def test_fixture_rejects_a_dirty_source_clone(tmp_path: Path) -> None:
    checkout, commit = source_checkout(tmp_path)
    (checkout / "unreviewed.txt").write_text("change\n", encoding="utf-8")

    with pytest.raises(builder.FixtureError, match="not clean"):
        builder.create_fixture(
            handoff=handoff(source_commit=commit),
            source_checkout=checkout,
        )

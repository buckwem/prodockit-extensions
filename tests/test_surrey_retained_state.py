# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Closed provenance tests for Surrey retained state stored by GitHub Actions."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
helper = importlib.import_module("surrey_retained_state")
state = importlib.import_module("live_provider_state")

COMMIT = "a" * 40
NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)


def run(identifier: int, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": identifier,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "head_branch": "main",
        "head_sha": COMMIT,
        "path": helper.SURREY_WORKFLOW,
        "html_url": f"https://github.com/{helper.RELEASE_REPOSITORY}/actions/runs/{identifier}",
        "repository": {"full_name": helper.RELEASE_REPOSITORY},
    }
    value.update(updates)
    return value


def retained(*, sealed_at: datetime = NOW) -> state.RetainedState:
    return state.RetainedState(
        schema=1,
        provider="surrey",
        project_id=14888,
        path_with_namespace=state.SURREY_PATH,
        visibility="private",
        head="b" * 40,
        tree="c" * 40,
        refs={"refs/heads/main": "b" * 40},
        destination_deploy_key_enabled=False,
        source_refs_digest="d" * 64,
        candidate_version="0.55.0",
        wheel_sha256="e" * 64,
        sealed_at_utc=sealed_at.isoformat(),
    )


def write_artifact(tmp_path: Path, value: state.RetainedState, *, run_id: int) -> tuple[Path, Path]:
    state_path = tmp_path / "retained-state.json"
    envelope_path = tmp_path / "retained-state-envelope.json"
    state_path.write_text(json.dumps(value.document()), encoding="utf-8")
    envelope = helper.build_envelope(
        retained=value,
        run_id=run_id,
        run_attempt=1,
        release_commit=COMMIT,
    )
    envelope_path.write_text(json.dumps(envelope.document()), encoding="utf-8")
    return state_path, envelope_path


def test_prior_run_selection_uses_newest_exact_successful_run() -> None:
    pages = [
        {
            "workflow_runs": [
                run(20),
                run(21, conclusion="failure"),
                run(22, path=".github/workflows/another.yml"),
                run(23, head_branch="feature"),
            ]
        }
    ]

    assert helper.select_prior_run(pages, current_run_id=30) == 20
    assert helper.select_prior_run(pages, current_run_id=30, override_run_id=20) == 20
    assert helper.candidate_prior_runs(pages, current_run_id=30) == (20,)


def test_prior_run_selection_rejects_unsafe_override() -> None:
    with pytest.raises(helper.RetainedStateError, match="not one successful prior run"):
        helper.select_prior_run(
            [{"workflow_runs": [run(20, repository={"full_name": "other/repo"})]}],
            current_run_id=30,
            override_run_id=20,
        )


def test_first_run_can_have_no_prior_success() -> None:
    assert helper.select_prior_run([{"workflow_runs": []}], current_run_id=1) is None


def test_recovery_run_must_be_the_exact_unsuccessful_surrey_workflow() -> None:
    failed = run(42, conclusion="failure")
    helper.validate_recovery_run(failed, expected_run_id=42, expected_commit=COMMIT)

    with pytest.raises(helper.RetainedStateError, match="only for an unsuccessful"):
        helper.validate_recovery_run(run(42), expected_run_id=42, expected_commit=COMMIT)
    with pytest.raises(helper.RetainedStateError, match="unexpected path"):
        helper.validate_recovery_run(
            run(42, conclusion="failure", path=".github/workflows/another.yml"),
            expected_run_id=42,
            expected_commit=COMMIT,
        )


def test_retained_artifact_binds_state_to_exact_run(tmp_path: Path) -> None:
    value = retained()
    state_path, envelope_path = write_artifact(tmp_path, value, run_id=42)

    assert (
        helper.validate_retained_artifact(
            state_path=state_path,
            envelope_path=envelope_path,
            expected_run_id=42,
            run_value=run(42),
            now=NOW,
        )
        == value
    )

    with pytest.raises(helper.RetainedStateError, match="another workflow run"):
        helper.validate_retained_artifact(
            state_path=state_path,
            envelope_path=envelope_path,
            expected_run_id=41,
            now=NOW,
        )


def test_retained_artifact_rejects_tampering_and_expiry(tmp_path: Path) -> None:
    value = retained(sealed_at=NOW - timedelta(days=91))
    state_path, envelope_path = write_artifact(tmp_path, value, run_id=42)

    with pytest.raises(helper.RetainedStateError, match="more than 90 days old"):
        helper.validate_retained_artifact(
            state_path=state_path,
            envelope_path=envelope_path,
            expected_run_id=42,
            now=NOW,
        )

    document = json.loads(state_path.read_text(encoding="utf-8"))
    document["candidate_version"] = "changed"
    state_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(helper.RetainedStateError, match="digest does not match"):
        helper.validate_retained_artifact(
            state_path=state_path,
            envelope_path=envelope_path,
            expected_run_id=42,
            now=NOW - timedelta(days=91),
        )


def test_retained_artifact_rejects_run_reruns_and_commit_substitution(
    tmp_path: Path,
) -> None:
    state_path, envelope_path = write_artifact(tmp_path, retained(), run_id=42)

    for run_value, message in (
        (run(42, run_attempt=2), "unexpected run_attempt"),
        (run(42, head_sha="f" * 40), "differs from its immutable workflow run"),
    ):
        with pytest.raises(helper.RetainedStateError, match=message):
            helper.validate_retained_artifact(
                state_path=state_path,
                envelope_path=envelope_path,
                expected_run_id=42,
                run_value=run_value,
                now=NOW,
            )


def test_envelope_schema_is_closed(tmp_path: Path) -> None:
    value = retained()
    _, envelope_path = write_artifact(tmp_path, value, run_id=42)
    document = json.loads(envelope_path.read_text(encoding="utf-8"))
    document["extra"] = True
    envelope_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(helper.RetainedStateError, match="unknown extra"):
        helper.RetainedStateEnvelope.read(envelope_path)


def test_retained_artifact_rejects_unexpected_members(tmp_path: Path) -> None:
    state_path, envelope_path = write_artifact(tmp_path, retained(), run_id=42)
    (tmp_path / "untrusted.txt").write_text("extra", encoding="utf-8")

    with pytest.raises(helper.RetainedStateError, match="unexpected members"):
        helper.validate_retained_artifact(
            state_path=state_path,
            envelope_path=envelope_path,
            expected_run_id=42,
            now=NOW,
        )

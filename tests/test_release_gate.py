# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Fail-closed evidence tests for the protected live-provider release gate."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
gate = importlib.import_module("release_gate")
state = importlib.import_module("release_gate_state")

COMMIT = "a" * 40
CONTROLLER = "a" * 40
SOURCE = "b" * 40
TREE = "c" * 40
CONTENTS = "d" * 64
RAW = "e" * 64
NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def record_hash(data: bytes) -> str:
    value = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def write_wheel(path: Path) -> Path:
    dist_info = "prodockit-0.54.0.dist-info"
    files = {
        "prodockit/__init__.py": b'__version__ = "0.54.0"\n',
        f"{dist_info}/METADATA": (b"Metadata-Version: 2.4\nName: prodockit\nVersion: 0.54.0\n\n"),
        f"{dist_info}/WHEEL": (b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
    }
    record_name = f"{dist_info}/RECORD"
    rows = [[name, record_hash(data), str(len(data))] for name, data in files.items()]
    rows.append([record_name, "", ""])
    record = io.StringIO(newline="")
    csv.writer(record, lineterminator="\n").writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 1, 12, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
        info = zipfile.ZipInfo(record_name, date_time=(2026, 9, 1, 12, 0, 0))
        info.external_attr = 0o100644 << 16
        archive.writestr(info, record.getvalue().encode())
    return path


def path_result(provider: str, *, first: bool) -> dict[str, object]:
    repository = state.PROVIDER_DESTINATIONS[provider]
    return {
        "name": "path-one" if first else "path-two",
        "configured_source": None if first else repository,
        "configured_history": None if first else "keep",
        "applied_stages": ["clone", "first-push"] if first else ["clone"],
        "commit": COMMIT,
        "tree": TREE,
        "clean_tree": True,
    }


def result_document(provider: str, **updates: object) -> dict[str, object]:
    repository = state.PROVIDER_DESTINATIONS[provider]
    run_id = 42 if provider == "github" else 43
    workflow_url = (
        f"https://github.com/{state.RELEASE_REPOSITORY}/actions/runs/{run_id}"
        if provider == "github"
        else f"https://gitlab.surrey.ac.uk/{repository}/-/pipelines/{run_id}"
    )
    value: dict[str, object] = {
        "schema": 1,
        "passed": True,
        "provider": provider,
        "release_repository": state.RELEASE_REPOSITORY,
        "release_commit": COMMIT,
        "candidate_version": "0.54.0",
        "wheel_sha256": RAW,
        "wheel_contents_sha256": CONTENTS,
        "controller_commit": CONTROLLER,
        "repository": repository,
        "project_id": 123,
        "path_one": path_result(provider, first=True),
        "path_two": path_result(provider, first=False),
        "source_commit": SOURCE,
        "source_refs_digest": "f" * 64,
        "source_refs_unchanged": True,
        "destination_refs": {"refs/heads/main": COMMIT},
        "destination_deploy_key_enabled": False,
        "workflow_run_id": run_id,
        "workflow_url": workflow_url,
        "started_at_utc": "2026-09-01T11:30:00Z",
        "finished_at_utc": "2026-09-01T11:45:00Z",
    }
    value.update(updates)
    return value


def write_result(path: Path, provider: str, **updates: object) -> Path:
    path.write_text(json.dumps(result_document(provider, **updates)), encoding="utf-8")
    return path


def read_result(tmp_path: Path, provider: str, **updates: object):
    path = write_result(tmp_path / f"{provider}.json", provider, **updates)
    return state.ProviderGateResult.read(path, now=NOW)


def test_provider_result_accepts_only_the_two_exact_clean_paths(tmp_path: Path) -> None:
    result = read_result(tmp_path, "surrey")

    assert result.repository == state.PROVIDER_DESTINATIONS["surrey"]
    assert result.path_one.applied_stages[-1] == "first-push"
    assert result.path_two.configured_history == "keep"
    assert result.destination_deploy_key_enabled is False


def test_provider_result_rejects_unknown_fields_and_stale_runs(tmp_path: Path) -> None:
    unknown = result_document("github")
    unknown["secret"] = "not allowed"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(unknown), encoding="utf-8")

    with pytest.raises(state.StateError, match="unknown secret"):
        state.ProviderGateResult.read(path, now=NOW)

    stale_now = NOW + timedelta(hours=25)
    path = write_result(tmp_path / "stale.json", "github")
    with pytest.raises(state.StateError, match="more than 24 hours old"):
        state.ProviderGateResult.read(path, now=stale_now)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"destination_deploy_key_enabled": True}, "write key is disabled"),
        ({"source_refs_unchanged": False}, "template source stayed unchanged"),
        ({"repository": "somewhere/else"}, "unapproved destination"),
    ],
)
def test_provider_result_rejects_incomplete_containment(
    tmp_path: Path, updates: dict[str, object], message: str
) -> None:
    with pytest.raises(state.StateError, match=message):
        read_result(tmp_path, "surrey", **updates)


def test_assemble_binds_both_providers_to_publication_wheel(tmp_path: Path) -> None:
    wheel = write_wheel(tmp_path / "prodockit-0.54.0-py3-none-any.whl")
    identity = gate.inspect_wheel(wheel)
    github = read_result(
        tmp_path,
        "github",
        wheel_contents_sha256=identity.wheel_contents_sha256,
        wheel_sha256=identity.wheel_sha256,
    )
    surrey = read_result(
        tmp_path,
        "surrey",
        wheel_contents_sha256=identity.wheel_contents_sha256,
        wheel_sha256="9" * 64,
    )

    evidence = gate.assemble(
        github=github,
        surrey=surrey,
        wheel_path=wheel,
        expected_commit=COMMIT,
        expected_version="0.54.0",
        assembled_at=NOW,
    )

    assert evidence.passed is True
    assert evidence.release_commit == COMMIT
    assert evidence.wheel_sha256 == identity.wheel_sha256
    assert evidence.wheel_contents_sha256 == identity.wheel_contents_sha256
    assert evidence.github.result_sha256 != evidence.surrey.result_sha256


def test_assemble_rejects_provider_content_or_commit_drift(tmp_path: Path) -> None:
    wheel = write_wheel(tmp_path / "prodockit-0.54.0-py3-none-any.whl")
    identity = gate.inspect_wheel(wheel)
    github = read_result(tmp_path, "github", wheel_contents_sha256=identity.wheel_contents_sha256)
    surrey = read_result(tmp_path, "surrey", wheel_contents_sha256="1" * 64)

    with pytest.raises(gate.ReleaseGateError, match="different wheel contents"):
        gate.assemble(
            github=github,
            surrey=surrey,
            wheel_path=wheel,
            expected_commit=COMMIT,
            expected_version="0.54.0",
        )

    with pytest.raises(gate.ReleaseGateError, match="another release commit"):
        gate.assemble(
            github=github,
            surrey=read_result(
                tmp_path,
                "surrey",
                release_commit="8" * 40,
                wheel_contents_sha256=identity.wheel_contents_sha256,
            ),
            wheel_path=wheel,
            expected_commit=COMMIT,
            expected_version="0.54.0",
        )


def test_release_checkout_must_be_clean_main_at_origin_main(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=checkout, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=checkout, check=True)
    (checkout / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=checkout, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Candidate"], cwd=checkout, check=True, capture_output=True
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", commit],
        cwd=checkout,
        check=True,
    )

    gate.validate_release_checkout(checkout, expected_commit=commit)

    (checkout / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(gate.ReleaseGateError, match="uncommitted changes"):
        gate.validate_release_checkout(checkout, expected_commit=commit)

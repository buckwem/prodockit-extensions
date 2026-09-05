# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Closed provider-API boundary tests for the release coordinator."""

from __future__ import annotations

import importlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
status = importlib.import_module("release_gate_provider_status")

COMMIT = "a" * 40


def github_run(*, workflow: str = status.GITHUB_WORKFLOW, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 42,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": COMMIT,
        "path": workflow,
        "html_url": f"{status.GITHUB_URL}/actions/runs/42",
        "repository": {"full_name": status.RELEASE_REPOSITORY},
    }
    value.update(updates)
    return value


def test_github_run_is_bound_to_exact_workflow_commit_and_run() -> None:
    status.validate_github_run(github_run(), expected_run_id=42, expected_commit=COMMIT)

    for update, message in (
        ({"head_sha": "b" * 40}, "head_sha"),
        ({"path": ".github/workflows/another.yml"}, "path"),
        ({"conclusion": "failure"}, "conclusion"),
    ):
        with pytest.raises(status.ProviderStatusError, match=message):
            status.validate_github_run(
                github_run(**update), expected_run_id=42, expected_commit=COMMIT
            )


def test_surrey_run_is_bound_to_its_exact_github_actions_workflow() -> None:
    status.validate_surrey_run(
        github_run(workflow=status.SURREY_GITHUB_WORKFLOW),
        expected_run_id=42,
        expected_commit=COMMIT,
    )

    with pytest.raises(status.ProviderStatusError, match="path"):
        status.validate_surrey_run(
            github_run(),
            expected_run_id=42,
            expected_commit=COMMIT,
        )


def check_run(identifier: int, name: str, *, conclusion: str = "success") -> dict[str, object]:
    return {
        "id": identifier,
        "name": name,
        "head_sha": COMMIT,
        "status": "completed",
        "conclusion": conclusion,
        "app": {"id": 7},
    }


def ordinary_run(path: str, identifier: int, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": identifier,
        "path": path,
        "event": "push",
        "head_branch": "main",
        "head_sha": COMMIT,
        "status": "completed",
        "conclusion": "success",
    }
    value.update(updates)
    return value


def test_ordinary_workflows_require_each_exact_commit_push() -> None:
    runs = [ordinary_run(path, number) for number, path in enumerate(status.ORDINARY_WORKFLOWS, 1)]

    status.validate_ordinary_workflows([{"workflow_runs": runs}], expected_commit=COMMIT)

    runs.pop()
    with pytest.raises(status.ProviderStatusError, match="are missing"):
        status.validate_ordinary_workflows([{"workflow_runs": runs}], expected_commit=COMMIT)


def test_ordinary_workflows_reject_the_wrong_event() -> None:
    runs = [ordinary_run(path, number) for number, path in enumerate(status.ORDINARY_WORKFLOWS, 1)]
    runs[0]["event"] = "workflow_dispatch"

    with pytest.raises(status.ProviderStatusError, match="not an exact-commit push"):
        status.validate_ordinary_workflows([{"workflow_runs": runs}], expected_commit=COMMIT)


def test_ordinary_workflows_use_the_latest_run_for_each_workflow() -> None:
    runs = [ordinary_run(path, number) for number, path in enumerate(status.ORDINARY_WORKFLOWS, 1)]
    path = next(iter(status.ORDINARY_WORKFLOWS))
    runs.append(ordinary_run(path, 100, conclusion="failure"))

    with pytest.raises(status.ProviderStatusError, match="has not passed"):
        status.validate_ordinary_workflows([{"workflow_runs": runs}], expected_commit=COMMIT)


def test_required_checks_use_the_latest_exact_commit_result() -> None:
    rules = [
        [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": "CI", "integration_id": 7},
                        {"context": "legacy"},
                    ]
                },
            }
        ]
    ]
    checks = [{"check_runs": [check_run(1, "CI"), check_run(2, "CI")]}]
    statuses = [[{"id": 3, "context": "legacy", "sha": COMMIT, "state": "success"}]]

    status.validate_required_checks(rules, checks, statuses, expected_commit=COMMIT)

    checks[0]["check_runs"].append(check_run(4, "CI", conclusion="failure"))
    with pytest.raises(status.ProviderStatusError, match="has not passed"):
        status.validate_required_checks(rules, checks, statuses, expected_commit=COMMIT)


def test_required_checks_reject_unverified_required_workflow_rules() -> None:
    with pytest.raises(status.ProviderStatusError, match="required-workflows"):
        status.validate_required_checks(
            [[{"type": "workflows", "parameters": {"workflows": []}}]],
            [{"check_runs": []}],
            [[]],
            expected_commit=COMMIT,
        )


def test_required_checks_allow_no_active_status_rule() -> None:
    status.validate_required_checks([[]], [{"check_runs": []}], [[]], expected_commit=COMMIT)


def test_required_context_requires_both_check_and_status_when_both_exist() -> None:
    rules = [
        [
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": [{"context": "CI"}]},
            }
        ]
    ]
    checks = [{"check_runs": [check_run(1, "CI")]}]
    statuses = [[{"id": 2, "context": "CI", "sha": COMMIT, "state": "failure"}]]

    with pytest.raises(status.ProviderStatusError, match=r"required status.*has not passed"):
        status.validate_required_checks(rules, checks, statuses, expected_commit=COMMIT)


def surrey_pipeline(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 43,
        "ref": "main",
        "source": "parent_pipeline",
        "status": "success",
        "sha": "b" * 40,
        "web_url": f"{status.SURREY_URL}/-/pipelines/43",
    }
    value.update(updates)
    return value


def job(identifier: int, name: str) -> dict[str, object]:
    return {
        "id": identifier,
        "name": name,
        "status": "success",
        "ref": "main",
        "pipeline": {"id": 43},
        "artifacts_file": {"filename": "artifacts.zip", "size": 100},
    }


def test_surrey_pipeline_and_seal_job_are_exact() -> None:
    status.validate_surrey_pipeline(surrey_pipeline(), expected_pipeline_id=43)
    jobs = [job(1, "surrey_reset"), job(2, "surrey_candidate"), job(3, "surrey_seal")]

    assert status.select_surrey_seal_job(jobs, expected_pipeline_id=43) == 3

    jobs.append(job(4, "unexpected"))
    with pytest.raises(status.ProviderStatusError, match="exactly the three"):
        status.select_surrey_seal_job(jobs, expected_pipeline_id=43)


def test_extract_surrey_result_reads_only_the_closed_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(status.SURREY_RESULT_MEMBER, json.dumps({"schema": 1}))
        archive.writestr("surrey-provider-result/seal-audit.json", "{}")
    output = tmp_path / "provider-result.json"

    status.extract_surrey_result(archive_path, output)

    assert json.loads(output.read_text(encoding="utf-8")) == {"schema": 1}


def test_extract_surrey_result_rejects_duplicate_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(archive_path, "w") as archive,
    ):
        archive.writestr(status.SURREY_RESULT_MEMBER, "{}")
        archive.writestr(status.SURREY_RESULT_MEMBER, "{}")

    with pytest.raises(status.ProviderStatusError, match="unique provider result"):
        status.extract_surrey_result(archive_path, tmp_path / "result.json")

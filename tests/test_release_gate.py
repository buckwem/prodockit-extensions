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
        else f"https://gitlab.surrey.ac.uk/{state.SURREY_WORKFLOW_PROJECT}/-/pipelines/{run_id}"
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


def test_surrey_provider_result_accepts_exact_github_actions_orchestration(
    tmp_path: Path,
) -> None:
    result = read_result(
        tmp_path,
        "surrey",
        workflow_url=f"https://github.com/{state.RELEASE_REPOSITORY}/actions/runs/43",
    )

    assert result.provider == "surrey"
    assert result.workflow_run_id == 43


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


def test_github_shadow_workflow_keeps_three_credential_boundaries() -> None:
    workflow = (ROOT / ".github" / "workflows" / "bootstrap-live-provider-github.yml").read_text(
        encoding="utf-8"
    )
    reset = workflow[workflow.index("  reset:") : workflow.index("  candidate:")]
    candidate = workflow[workflow.index("  candidate:") : workflow.index("  seal:")]
    seal = workflow[workflow.index("  seal:") :]

    assert "  workflow_dispatch:" in workflow
    for forbidden in ("  pull_request:", "  push:", "  schedule:", "  release:"):
        assert forbidden not in workflow
    assert "cancel-in-progress: false" in workflow
    assert "environment: bootstrap-live-github-reset" in reset
    assert "environment: bootstrap-live-github-candidate" in candidate
    assert "environment: bootstrap-live-github-seal" in seal
    assert "PRODOCKIT_LIVE_GITHUB_LIFECYCLE_TOKEN" in reset
    assert "PRODOCKIT_LIVE_GITHUB_LIFECYCLE_TOKEN" in seal
    assert "PRODOCKIT_LIVE_GITHUB_LIFECYCLE_TOKEN" not in candidate
    assert "PRODOCKIT_LIVE_GITHUB_KEY_WRAP_PUBLIC_KEY" in reset
    assert "PRODOCKIT_LIVE_GITHUB_KEY_WRAP_PUBLIC_KEY" not in candidate
    assert "PRODOCKIT_LIVE_GITHUB_KEY_WRAP_PUBLIC_KEY" not in seal
    assert "PRODOCKIT_LIVE_GITHUB_KEY_WRAP_PRIVATE_KEY" in candidate
    assert "PRODOCKIT_LIVE_GITHUB_KEY_WRAP_PRIVATE_KEY" not in reset
    assert "PRODOCKIT_LIVE_GITHUB_KEY_WRAP_PRIVATE_KEY" not in seal
    assert "PRODOCKIT_LIVE_GITHUB_DEPLOY_PRIVATE_KEY" not in workflow
    assert "PRODOCKIT_LIVE_GITHUB_DEPLOY_PUBLIC_KEY" not in workflow
    assert "deploy-key.enc" in reset
    assert "deploy-key.enc" in candidate
    assert "bootstrap_live_provider_ephemeral_key.py create" in reset
    assert "bootstrap_live_provider_ephemeral_key.py unwrap" in candidate
    assert "brew install --cask visual-studio-code" in candidate
    assert "font-inter" in candidate
    assert "font-jetbrains-mono" in candidate
    for extension in (
        "ms-python.python",
        "zensical.zensical-studio",
        "tamasfe.even-better-toml",
        "ltex-plus.vscode-ltex-plus",
    ):
        assert f"code --install-extension {extension}" in candidate
    assert "if: always() && needs.reset.result == 'success'" in seal
    assert "FIXED_REPOSITORY: buckwem/bootstrap-release-gate" in workflow
    assert "previous_run_id" not in workflow
    assert "create-github-app-token" not in workflow


def test_surrey_shadow_pipeline_keeps_three_credential_boundaries() -> None:
    parent = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    pipeline = (ROOT / ".gitlab" / "bootstrap-live-provider-surrey.yml").read_text(encoding="utf-8")
    reset = pipeline[pipeline.index("surrey_reset:") : pipeline.index("surrey_candidate:")]
    candidate = pipeline[pipeline.index("surrey_candidate:") : pipeline.index("surrey_seal:")]
    seal = pipeline[pipeline.index("surrey_seal:") :]

    assert '$CI_PIPELINE_SOURCE == "web"' in parent
    for forbidden in ('"push"', '"merge_request_event"', '"schedule"'):
        assert forbidden not in parent
    assert "resource_group: bootstrap-live-surrey" in parent
    assert "strategy: mirror" in parent
    assert '$CI_PIPELINE_SOURCE == "parent_pipeline"' in pipeline
    assert "environment:\n    name: bootstrap-live-surrey-reset" in reset
    assert "environment:\n    name: bootstrap-live-surrey-candidate" in candidate
    assert "environment:\n    name: bootstrap-live-surrey-seal" in seal
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" in reset
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" in seal
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" not in candidate
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" in candidate
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in reset
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in seal
    assert "when: always" in seal
    assert '--release-commit "$PRODOCKIT_LIVE_RELEASE_COMMIT"' in reset
    assert '--release-commit "$PRODOCKIT_LIVE_RELEASE_COMMIT"' in candidate
    assert '--release-commit "$PRODOCKIT_LIVE_RELEASE_COMMIT"' in seal


def test_surrey_github_workflow_keeps_three_credential_boundaries() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "bootstrap-live-provider-surrey.yml"
    ).read_text(encoding="utf-8")
    reset = workflow[workflow.index("  reset:") : workflow.index("  candidate:")]
    candidate = workflow[workflow.index("  candidate:") : workflow.index("  seal:")]
    seal = workflow[workflow.index("  seal:") :]

    assert "  workflow_dispatch:" in workflow
    for forbidden in ("  pull_request:", "  push:", "  schedule:", "  release:"):
        assert forbidden not in workflow
    assert "cancel-in-progress: false" in workflow
    assert "environment: bootstrap-live-surrey-reset" in reset
    assert "environment: bootstrap-live-surrey-candidate" in candidate
    assert "environment: bootstrap-live-surrey-seal" in seal
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" in reset
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" in seal
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" not in candidate
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" in candidate
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in reset
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in seal
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PUBLIC_KEY" in reset
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PUBLIC_KEY" not in candidate
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PUBLIC_KEY" not in seal
    assert "if: always() && needs.reset.result != 'skipped'" in seal
    assert "continue-on-error: true" in seal
    assert "bootstrap_live_provider_lifecycle.py revoke" in seal
    assert "surrey-retained-state-${{ github.run_id }}" in seal
    assert "surrey_retained_state.py validate" in reset
    assert "assessment-liveprovider-2026/report-liveprovider-2026-mb0105" in reset
    assert "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git" in candidate


def test_surrey_github_workflow_has_a_fail_closed_candidate_exercise() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "bootstrap-live-provider-surrey.yml"
    ).read_text(encoding="utf-8")
    reset = workflow[workflow.index("  reset:") : workflow.index("  candidate:")]
    candidate = workflow[workflow.index("  candidate:") : workflow.index("  seal:")]
    seal = workflow[workflow.index("  seal:") :]

    assert "exercise_candidate_failure:" in workflow
    assert "default: false" in workflow
    assert "controlled candidate failure" in workflow
    assert "if: inputs.exercise_candidate_failure" in candidate
    failure = candidate[
        candidate.index("Exercise candidate failure before receiving repository credentials") :
        candidate.index("Build an independent candidate wheel")
    ]
    assert '"controlled failure exercise before repository access"' in failure
    assert "exit 1" in failure
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in failure
    assert candidate.index("Exercise candidate failure") < candidate.index(
        "LIVE_DEPLOY_PRIVATE_KEY:"
    )
    assert "Retain only the sanitised candidate report\n        if: always()" in candidate
    assert "exercise_candidate_failure" not in reset
    assert "needs.candidate.result == 'failure'" in seal
    assert "bootstrap_live_provider_lifecycle.py verify-and-seal" in seal
    assert "bootstrap_live_provider_lifecycle.py revoke" in seal


def test_surrey_github_workflow_has_a_fail_closed_stale_main_exercise() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "bootstrap-live-provider-surrey.yml"
    ).read_text(encoding="utf-8")
    reset = workflow[workflow.index("  reset:") : workflow.index("  candidate:")]
    candidate = workflow[workflow.index("  candidate:") : workflow.index("  seal:")]
    seal = workflow[workflow.index("  seal:") :]

    assert "exercise_stale_main:" in workflow
    assert "controlled stale main' || ''" in workflow
    wait = candidate[
        candidate.index("Wait for protected main to advance") :
        candidate.index("Build an independent candidate wheel")
    ]
    assert "if: inputs.exercise_stale_main" in wait
    assert "git ls-remote https://github.com/buckwem/prodockit-extensions.git" in wait
    assert 'test "$current_main" != "$RELEASE_COMMIT"' in wait
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in wait
    assert "project must be absent" in workflow
    assert "Confirm the controlled stale-main reset starts from an absent fixture" in reset
    assert reset.count("if: ${{ !inputs.exercise_stale_main }}") == 2
    assert "The reset controller will continue only if the fixed Surrey project is absent" in reset

    stale = seal[
        seal.index('current_main=""') :
        seal.index("bootstrap_live_provider_lifecycle.py verify-and-seal")
    ]
    assert "git ls-remote https://github.com/buckwem/prodockit-extensions.git" in stale
    assert "bootstrap_live_provider_lifecycle.py revoke" in stale
    assert stale.index("bootstrap_live_provider_lifecycle.py revoke") < stale.index("exit 1")
    assert "access was revoked and stale evidence was rejected" in stale


def test_surrey_recovery_workflow_can_only_revoke_exact_failed_run() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "bootstrap-live-provider-surrey-recovery.yml"
    ).read_text(encoding="utf-8")

    assert "  workflow_dispatch:" in workflow
    for forbidden in ("  pull_request:", "  push:", "  schedule:", "  release:"):
        assert forbidden not in workflow
    assert "environment: bootstrap-live-surrey-seal" in workflow
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" in workflow
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in workflow
    assert "validate-recovery-run" in workflow
    assert "bootstrap_live_provider_lifecycle.py revoke" in workflow
    assert "delete" not in workflow.casefold()


def test_surrey_connectivity_probe_has_no_provider_credentials() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "bootstrap-live-provider-surrey-connectivity.yml"
    ).read_text(encoding="utf-8")

    assert "  workflow_dispatch:" in workflow
    assert "secrets." not in workflow
    assert "gitlab.surrey.ac.uk/api/v4/version" in workflow
    assert "SHA256:qNFkRSExCwCwfRE0H7qQHOo34h0OVr59NjgEjnjoz/o" in workflow


def test_github_shadow_does_not_authorise_current_publication() -> None:
    publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

    assert "release:" in publish
    assert "types: [published]" in publish
    assert "bootstrap-live-provider-github" not in publish


def test_release_coordinator_is_a_read_only_manual_shadow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-gate.yml").read_text(encoding="utf-8")

    assert "  workflow_dispatch:" in workflow
    for forbidden in ("  pull_request:", "  push:", "  schedule:", "  release:"):
        assert forbidden not in workflow
    assert "environment: bootstrap-live-release-gate" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "checks: read" in workflow
    assert "statuses: read" in workflow
    assert "id-token: write" not in workflow
    assert "contents: write" not in workflow
    assert "PRODOCKIT_LIVE_SURREY_STATUS_TOKEN" in workflow
    assert "PRODOCKIT_LIVE_SURREY_GROUP_TOKEN" not in workflow
    assert "PRODOCKIT_LIVE_SURREY_DEPLOY_PRIVATE_KEY" not in workflow
    assert "PRODOCKIT_LIVE_GITHUB_APP_PRIVATE_KEY" not in workflow
    assert "PRODOCKIT_LIVE_GITHUB_DEPLOY_PRIVATE_KEY" not in workflow
    assert "release_gate.py" in workflow
    assert "gh-action-pypi-publish" not in workflow
    assert "release: create" not in workflow

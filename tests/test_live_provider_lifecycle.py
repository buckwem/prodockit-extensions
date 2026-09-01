# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Fail-closed state and lifecycle tests for live-provider Phase 3."""

from __future__ import annotations

import importlib
import json
import sys
import uuid
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
lifecycle = importlib.import_module("bootstrap_live_provider_lifecycle")
state = importlib.import_module("live_provider_state")

COMMIT = "1" * 40
TREE = "2" * 40
WHEEL_SHA = "a" * 64
SOURCE_REFS_SHA = "b" * 64
CONTROLLER_COMMIT = "3" * 40
VERSION = "0.53.0"


def fixture_value(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": 3,
        "provider": "surrey",
        "api_base": state.SURREY_API_BASE,
        "ssh_host": state.SURREY_HOST,
        "group": {"id": 101, "full_path": state.SURREY_GROUP},
        "project": {
            "name": state.SURREY_PROJECT,
            "path_with_namespace": state.SURREY_PATH,
            "visibility": "private",
        },
        "template": {
            "id": 202,
            "path_with_namespace": state.SURREY_TEMPLATE,
            "ssh_url": state.SURREY_TEMPLATE_REMOTE,
            "commit": COMMIT,
            "refs_digest": SOURCE_REFS_SHA,
        },
        "deploy_key": {
            "id": 303,
            "title": state.SURREY_DEPLOY_KEY_TITLE,
            "fingerprint": state.SURREY_DEPLOY_KEY_FINGERPRINT,
        },
    }
    value.update(updates)
    return value


def write_fixture(path: Path, **updates: object) -> Path:
    path.write_text(json.dumps(fixture_value(**updates)), encoding="utf-8")
    return path


def reset_handoff(**updates: object) -> state.ResetHandoff:
    completed = datetime.now(timezone.utc).replace(microsecond=0)
    values: dict[str, object] = {
        "schema": 1,
        "run_id": str(uuid.uuid4()),
        "provider": "surrey",
        "project_id": 404,
        "path_with_namespace": state.SURREY_PATH,
        "repository_empty": True,
        "deploy_key_id": 303,
        "deploy_key_fingerprint": state.SURREY_DEPLOY_KEY_FINGERPRINT,
        "source_commit": COMMIT,
        "source_refs_digest": SOURCE_REFS_SHA,
        "candidate_version": VERSION,
        "wheel_sha256": WHEEL_SHA,
        "controller_commit": CONTROLLER_COMMIT,
        "completed_at_utc": completed.isoformat(),
        "expires_at_utc": (completed + timedelta(minutes=30)).isoformat(),
    }
    values.update(updates)
    return state.ResetHandoff(**values)


def path_result(name: str) -> dict[str, object]:
    return {
        "name": name,
        "configured_source": "" if name == "path-one" else state.SURREY_PATH,
        "configured_history": "" if name == "path-one" else "keep",
        "applied_stages": ["first-push"] if name == "path-one" else [],
        "commit": COMMIT,
        "tree": TREE,
        "clean_tree": True,
    }


def candidate_report(path: Path) -> Path:
    value = {
        "architecture": "arm64",
        "candidate_version": VERSION,
        "destination_transition": "empty -> refs/heads/main",
        "finished_at_utc": "2026-08-31T18:10:00+00:00",
        "manual_provider_review_required": False,
        "operating_system": "macOS",
        "passed": True,
        "path_one": path_result("path-one"),
        "path_two": path_result("path-two"),
        "provider": "surrey",
        "provider_created_refs": [],
        "repository": state.SURREY_PATH,
        "source_refs_digest": SOURCE_REFS_SHA,
        "source_refs_unchanged": True,
        "started_at_utc": "2026-08-31T18:00:00+00:00",
        "wheel_sha256": WHEEL_SHA,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class FakeGitLab:
    """Stateful provider boundary used without GitLab or network access."""

    def __init__(self, fixture: state.LifecycleFixture) -> None:
        self.fixture = fixture
        self.project: dict[str, Any] | None = None
        self.refs: dict[str, str] = {}
        self.deploy_keys: list[dict[str, Any]] = []
        self.pages: dict[str, Any] | None = None
        self.mutations: list[tuple[str, str]] = []
        self._sleep = lambda _delay: None

    def _project(self, project_id: int = 404) -> dict[str, Any]:
        return {
            "id": project_id,
            "name": state.SURREY_PROJECT,
            "path": state.SURREY_PROJECT,
            "path_with_namespace": state.SURREY_PATH,
            "visibility": "private",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "namespace": {"id": self.fixture.group.id},
            "shared_with_groups": [],
            **lifecycle.PROJECT_DISABLE_SETTINGS,
        }

    def get_optional(self, path: str) -> Any | None:
        if path == f"/groups/{state.SURREY_GROUP}":
            return {"id": self.fixture.group.id, "full_path": state.SURREY_GROUP}
        if path == f"/projects/{lifecycle.encoded(state.SURREY_TEMPLATE)}":
            return {
                "id": self.fixture.template.id,
                "path_with_namespace": state.SURREY_TEMPLATE,
            }
        if path == f"/projects/{lifecycle.encoded(state.SURREY_PATH)}":
            return self.project
        if self.project is not None and path == f"/projects/{self.project['id']}":
            return self.project
        if path.startswith("/projects/") and path.removeprefix("/projects/").isdecimal():
            return None
        raise AssertionError(f"unexpected GET {path}")

    def list_all(self, path: str, *, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del query
        group = f"/groups/{self.fixture.group.id}"
        if path == f"{group}/projects":
            return [] if self.project is None else [self.project]
        if path in {
            f"{group}/subgroups",
            f"{group}/variables",
            f"{group}/hooks",
            f"{group}/deploy_tokens",
        }:
            return []
        project_id = 404 if self.project is None else self.project["id"]
        prefix = f"/projects/{project_id}"
        if path == f"{prefix}/repository/branches":
            return [
                {"name": name.removeprefix("refs/heads/"), "commit": {"id": sha}}
                for name, sha in self.refs.items()
                if name.startswith("refs/heads/")
            ]
        if path == f"{prefix}/repository/tags":
            return []
        if path == f"{prefix}/pipelines":
            return [
                {"id": int(name.rsplit("/", 1)[1]), "sha": sha}
                for name, sha in self.refs.items()
                if name.startswith("refs/pipelines/")
            ]
        if path == f"{prefix}/deploy_keys":
            return list(self.deploy_keys)
        if path.startswith(prefix):
            return []
        raise AssertionError(f"unexpected list {path}")

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        expected: object = None,
    ) -> lifecycle.ApiResponse:
        del expected
        self.mutations.append((method, path))
        current_id = self.project["id"] if self.project is not None else None
        if method == "GET" and path == f"/projects/{current_id}/pages":
            status = 404 if self.pages is None else 200
            return lifecycle.ApiResponse(status, self.pages, {})
        if method == "DELETE" and path == f"/projects/{current_id}/pages":
            self.pages = None
            return lifecycle.ApiResponse(204, None, {})
        if method == "DELETE" and path == f"/projects/{current_id}":
            self.project = None
            self.refs = {}
            self.deploy_keys = []
            self.pages = None
            return lifecycle.ApiResponse(204, None, {})
        if method == "POST" and path == "/projects":
            self.project = self._project()
            return lifecycle.ApiResponse(201, self.project, {})
        prefix = "/projects/404"
        if method == "PUT" and path == prefix:
            assert self.project is not None
            self.project.update(body or {})
            return lifecycle.ApiResponse(200, self.project, {})
        key_path = f"{prefix}/deploy_keys/{self.fixture.deploy_key.id}"
        if method == "POST" and path == f"{key_path}/enable":
            self.deploy_keys = [
                {
                    "id": self.fixture.deploy_key.id,
                    "title": self.fixture.deploy_key.title,
                    "key": "ssh-ed25519 AAAA",
                    "can_push": False,
                }
            ]
            return lifecycle.ApiResponse(201, self.deploy_keys[0], {})
        if method == "PUT" and path == key_path:
            self.deploy_keys[0].update(body or {})
            return lifecycle.ApiResponse(200, self.deploy_keys[0], {})
        if method == "DELETE" and path == key_path:
            self.deploy_keys = []
            return lifecycle.ApiResponse(204, None, {})
        raise AssertionError(f"unexpected mutation {method} {path}")


def test_project_snapshot_does_not_query_disabled_features(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))

    class DisabledPipelineEndpoint(FakeGitLab):
        def list_all(
            self, path: str, *, query: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            if path.endswith(("/pipelines", "/merge_requests", "/variables")):
                raise AssertionError("a disabled feature endpoint must not be queried")
            return super().list_all(path, query=query)

    client = DisabledPipelineEndpoint(fixture)
    project = client._project()
    snapshot = lifecycle.project_snapshot(client, fixture, project)

    assert snapshot.refs == {}


def test_template_preflight_requires_group_bot_source_access(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))

    class HiddenTemplate(FakeGitLab):
        def get_optional(self, path: str) -> Any | None:
            if path == f"/projects/{lifecycle.encoded(state.SURREY_TEMPLATE)}":
                return None
            return super().get_optional(path)

    client = HiddenTemplate(fixture)

    with pytest.raises(lifecycle.LifecycleError, match="share mb0105/prodockit-template"):
        lifecycle.template_preflight(client, fixture)


def test_template_preflight_rejects_another_project(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))

    class WrongTemplate(FakeGitLab):
        def get_optional(self, path: str) -> Any | None:
            if path == f"/projects/{lifecycle.encoded(state.SURREY_TEMPLATE)}":
                return {"id": 999, "path_with_namespace": state.SURREY_TEMPLATE}
            return super().get_optional(path)

    with pytest.raises(lifecycle.LifecycleError, match="differs from the reviewed fixture"):
        lifecycle.template_preflight(WrongTemplate(fixture), fixture)


def test_delete_completes_gitlabs_scheduled_deletion_transition(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))

    class ScheduledDeletion(FakeGitLab):
        def __init__(self, fixture: state.LifecycleFixture) -> None:
            super().__init__(fixture)
            self.project = self._project()
            self.permanent_full_path: str | None = None

        def request(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
            expected: object = None,
        ) -> lifecycle.ApiResponse:
            if method == "DELETE" and path == "/projects/404":
                assert self.project is not None
                if query and query.get("permanently_remove") == "true":
                    self.permanent_full_path = str(query.get("full_path"))
                    self.project = None
                    return lifecycle.ApiResponse(204, None, {})
                suffix = "-deletion_scheduled-404"
                self.project.update(
                    {
                        "name": state.SURREY_PROJECT + suffix,
                        "path": state.SURREY_PROJECT + suffix,
                        "path_with_namespace": state.SURREY_PATH + suffix,
                        "marked_for_deletion_on": "2026-09-08",
                    }
                )
                return lifecycle.ApiResponse(202, None, {})
            return super().request(
                method,
                path,
                query=query,
                body=body,
                expected=expected,
            )

    client = ScheduledDeletion(fixture)
    journal = lifecycle.Journal([])

    lifecycle.delete_exact_project(client, fixture, client.project, journal)

    assert client.project is None
    assert client.permanent_full_path == state.SURREY_PATH + "-deletion_scheduled-404"
    assert [entry["operation"] for entry in journal.operations] == [
        "delete-project",
        "permanently-remove-project",
    ]


def test_delete_unpublishes_pages_before_removing_project(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))
    client = FakeGitLab(fixture)
    client.project = client._project()
    client.project["pages_access_level"] = "private"
    client.pages = {
        "url": "https://example.pages.invalid/project/",
        "deployments": [{"path_prefix": "", "url": "https://example.pages.invalid/project/"}],
    }
    journal = lifecycle.Journal([])

    lifecycle.delete_exact_project(client, fixture, client.project, journal)

    assert client.project is None
    assert client.pages is None
    assert client.mutations.index(("DELETE", "/projects/404/pages")) < client.mutations.index(
        ("DELETE", "/projects/404")
    )
    assert [entry["operation"] for entry in journal.operations] == [
        "unpublish-pages",
        "delete-project",
    ]


def test_delete_does_not_query_the_disabled_pages_endpoint(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))

    class DisabledPagesEndpoint(FakeGitLab):
        def request(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
            expected: object = None,
        ) -> lifecycle.ApiResponse:
            if path.endswith("/pages"):
                raise AssertionError("the disabled Pages endpoint must not be queried")
            return super().request(
                method,
                path,
                query=query,
                body=body,
                expected=expected,
            )

    client = DisabledPagesEndpoint(fixture)
    client.project = client._project()
    journal = lifecycle.Journal([])

    lifecycle.delete_exact_project(client, fixture, client.project, journal)

    assert client.project is None
    assert [entry["operation"] for entry in journal.operations] == ["delete-project"]


def test_reset_removes_the_project_if_post_creation_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)

    class InvalidPostCreationState(FakeGitLab):
        def list_all(
            self, path: str, *, query: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            if path.endswith("/hooks") and self.project is not None:
                return [{"id": 999}]
            return super().list_all(path, query=query)

    client = InvalidPostCreationState(fixture)
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: CONTROLLER_COMMIT,
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    args = Namespace(
        fixture=fixture_path,
        previous_state=None,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=tmp_path / "audit.json",
        confirm_project_reset=state.SURREY_PATH,
    )

    with pytest.raises(lifecycle.LifecycleError, match="unexpected hook"):
        lifecycle.reset_project(args, client)

    assert client.project is None
    assert ("DELETE", "/projects/404") in client.mutations


def test_fixture_is_closed_and_pinned_to_the_exact_surrey_project(tmp_path: Path) -> None:
    fixture = state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json"))

    assert fixture.destination_remote == (
        "git@gitlab.surrey.ac.uk:assessment-liveprovider-2026/report-liveprovider-2026-mb0105.git"
    )

    value = fixture_value(unexpected="secret")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(state.StateError, match="unknown unexpected"):
        state.LifecycleFixture.read(path)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"schema": 2}, "schema must be 3"),
        ({"provider": "github"}, "only the Surrey"),
        ({"api_base": "https://example.invalid/api/v4"}, "must be exactly"),
        ({"ssh_host": "example.invalid"}, "must be exactly"),
    ],
)
def test_fixture_identity_changes_fail_closed(
    tmp_path: Path, updates: dict[str, object], message: str
) -> None:
    with pytest.raises(state.StateError, match=message):
        state.LifecycleFixture.read(write_fixture(tmp_path / "fixture.json", **updates))


def test_handoff_is_short_lived_and_rejects_another_project() -> None:
    handoff = reset_handoff()
    handoff.validate()

    expired = reset_handoff(
        completed_at_utc="2026-08-31T17:00:00+00:00",
        expires_at_utc="2026-08-31T17:30:00+00:00",
    )
    with pytest.raises(state.StateError, match="expired"):
        expired.validate(now=datetime(2026, 8, 31, 18, tzinfo=timezone.utc))
    with pytest.raises(state.StateError, match="another project"):
        reset_handoff(path_with_namespace="other/project").validate()


def test_retained_state_allows_only_main_and_same_commit_pipeline_refs() -> None:
    retained = state.RetainedState(
        schema=1,
        provider="surrey",
        project_id=404,
        path_with_namespace=state.SURREY_PATH,
        visibility="private",
        head=COMMIT,
        tree=TREE,
        refs={"refs/heads/main": COMMIT, "refs/pipelines/9": COMMIT},
        destination_deploy_key_enabled=False,
        source_refs_digest=SOURCE_REFS_SHA,
        candidate_version=VERSION,
        wheel_sha256=WHEEL_SHA,
        sealed_at_utc="2026-08-31T18:00:00+00:00",
    )
    retained.validate()

    with pytest.raises(state.StateError, match="unexpected ref"):
        state.RetainedState(
            **{**retained.document(), "refs": {"refs/heads/main": COMMIT, "refs/tags/v1": COMMIT}}
        ).validate()


def test_private_state_writer_uses_mode_0600(tmp_path: Path) -> None:
    path = tmp_path / "private" / "state.json"
    state.write_private_json(path, {"safe": True})

    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"safe": True}


def test_lifecycle_lock_serialises_runs_and_is_removed_after_success(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "fixture.json"

    with lifecycle.exclusive_run_lock(fixture):
        lock = tmp_path / ".fixture.json.phase3-lock"
        assert lock.is_dir()
        assert (lock / "owner.json").stat().st_mode & 0o777 == 0o600
        with (
            pytest.raises(lifecycle.LifecycleError, match="owns the lifecycle lock"),
            lifecycle.exclusive_run_lock(fixture),
        ):
            pass

    assert not lock.exists()


def test_failure_audit_redacts_private_paths_and_uses_mode_0600(tmp_path: Path) -> None:
    private_input = tmp_path / "private" / "fixture.json"
    audit = tmp_path / "audit.json"
    args = Namespace(
        command="reset",
        fixture=private_input,
        audit_report=audit,
    )

    lifecycle.write_failure_audit(
        args,
        lifecycle.LifecycleError(f"could not read {private_input}"),
    )

    value = json.loads(audit.read_text(encoding="utf-8"))
    assert str(tmp_path) not in json.dumps(value)
    assert value["failure"] == "could not read <fixture>"
    assert audit.stat().st_mode & 0o777 == 0o600


def test_failure_audit_does_not_replace_a_completed_seal(tmp_path: Path) -> None:
    audit = tmp_path / "seal-audit.json"
    completed = {
        "schema": 1,
        "passed": True,
        "phase": "verify-and-seal",
        "finished_at_utc": "2026-09-01T16:31:14+00:00",
    }
    state.write_private_json(audit, completed)
    original = audit.read_bytes()
    args = Namespace(
        command="verify-and-seal",
        fixture=tmp_path / "fixture.json",
        audit_report=audit,
    )

    lifecycle.write_failure_audit(
        args,
        lifecycle.LifecycleError("the live-provider project contains an unexpected deploy key"),
    )

    assert audit.read_bytes() == original
    assert json.loads(audit.read_text(encoding="utf-8")) == completed


def test_phase_two_report_requires_exact_matching_paths(tmp_path: Path) -> None:
    handoff = reset_handoff()
    report = candidate_report(tmp_path / "candidate.json")

    assert lifecycle.phase_two_report(report, handoff)["passed"] is True

    value = json.loads(report.read_text(encoding="utf-8"))
    value["path_two"]["tree"] = "4" * 40
    report.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(lifecycle.LifecycleError, match="different repository state"):
        lifecycle.phase_two_report(report, handoff)


def test_reset_refuses_an_existing_project_without_retained_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    client.project = client._project(404)
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle, "validate_controller_checkout", lambda *_args, **_kwargs: CONTROLLER_COMMIT
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    monkeypatch.setattr(
        lifecycle,
        "public_key_fingerprint",
        lambda _record: state.SURREY_DEPLOY_KEY_FINGERPRINT,
    )
    args = Namespace(
        fixture=fixture_path,
        previous_state=None,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=tmp_path / "audit.json",
        confirm_project_reset=state.SURREY_PATH,
    )

    with pytest.raises(lifecycle.LifecycleError, match="no exact retained-state"):
        lifecycle.reset_project(args, client)
    assert client.mutations == []


def test_empty_reset_candidate_and_seal_form_one_bounded_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle, "validate_controller_checkout", lambda *_args, **_kwargs: CONTROLLER_COMMIT
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    monkeypatch.setattr(
        lifecycle,
        "public_key_fingerprint",
        lambda _record: state.SURREY_DEPLOY_KEY_FINGERPRINT,
    )
    handoff_path = tmp_path / "handoff.json"
    reset_audit = tmp_path / "reset-audit.json"
    reset_args = Namespace(
        fixture=fixture_path,
        previous_state=None,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=handoff_path,
        audit_report=reset_audit,
        confirm_project_reset=state.SURREY_PATH,
    )

    lifecycle.reset_project(reset_args, client)

    handoff = state.ResetHandoff.read(handoff_path)
    assert handoff.repository_empty is True
    assert client.deploy_keys[0]["can_push"] is True
    client.refs = {"refs/heads/main": COMMIT}
    report = candidate_report(tmp_path / "candidate.json")
    retained = tmp_path / "retained.json"
    seal_args = Namespace(
        fixture=fixture_path,
        handoff=handoff_path,
        candidate_report=report,
        retained_state=retained,
        audit_report=tmp_path / "seal-audit.json",
    )

    lifecycle.verify_and_seal(seal_args, client)

    sealed = state.RetainedState.read(retained)
    assert sealed.head == COMMIT
    assert sealed.tree == TREE
    assert client.deploy_keys == []
    assert ("DELETE", "/projects/404/deploy_keys/303") in client.mutations


def test_reset_reconciles_lost_mutation_responses_without_replaying_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)

    class AppliedButResponseLost(FakeGitLab):
        def __init__(self, fixture: state.LifecycleFixture) -> None:
            super().__init__(fixture)
            self.lost: set[tuple[str, str]] = set()

        def request(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
            expected: object = None,
        ) -> lifecycle.ApiResponse:
            response = super().request(
                method,
                path,
                query=query,
                body=body,
                expected=expected,
            )
            operation = (method, path)
            if operation not in self.lost and operation in {
                ("POST", "/projects"),
                ("PUT", "/projects/404"),
                ("POST", "/projects/404/deploy_keys/303/enable"),
                ("PUT", "/projects/404/deploy_keys/303"),
            }:
                self.lost.add(operation)
                raise lifecycle.AmbiguousMutation("response lost after apply")
            return response

    client = AppliedButResponseLost(fixture)
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: CONTROLLER_COMMIT,
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    monkeypatch.setattr(
        lifecycle,
        "public_key_fingerprint",
        lambda _record: state.SURREY_DEPLOY_KEY_FINGERPRINT,
    )
    audit_path = tmp_path / "audit.json"
    args = Namespace(
        fixture=fixture_path,
        previous_state=None,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=audit_path,
        confirm_project_reset=state.SURREY_PATH,
    )

    lifecycle.reset_project(args, client)

    assert all(client.mutations.count(operation) == 1 for operation in client.lost)
    outcomes = {
        item["operation"]: item["outcome"]
        for item in json.loads(audit_path.read_text(encoding="utf-8"))["operations"]
    }
    assert outcomes["create-project"] == "response-lost"
    assert outcomes["disable-project-features"] == "response-lost"
    assert outcomes["enable-destination-deploy-key"] == "response-lost"
    assert outcomes["grant-destination-key-write"] == "response-lost"


def test_next_reset_requires_and_consumes_the_exact_retained_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    client.project = client._project(403)
    client.refs = {"refs/heads/main": COMMIT}
    previous = state.RetainedState(
        schema=1,
        provider="surrey",
        project_id=403,
        path_with_namespace=state.SURREY_PATH,
        visibility="private",
        head=COMMIT,
        tree=TREE,
        refs=dict(client.refs),
        destination_deploy_key_enabled=False,
        source_refs_digest=SOURCE_REFS_SHA,
        candidate_version=VERSION,
        wheel_sha256=WHEEL_SHA,
        sealed_at_utc="2026-08-31T18:00:00+00:00",
    )
    previous_path = tmp_path / "previous.json"
    state.write_private_json(previous_path, previous.document())
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: CONTROLLER_COMMIT,
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    monkeypatch.setattr(
        lifecycle,
        "public_key_fingerprint",
        lambda _record: state.SURREY_DEPLOY_KEY_FINGERPRINT,
    )
    args = Namespace(
        fixture=fixture_path,
        previous_state=previous_path,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=tmp_path / "audit.json",
        confirm_project_reset=state.SURREY_PATH,
    )

    lifecycle.reset_project(args, client)

    assert client.project is not None
    assert client.project["id"] == 404
    assert client.refs == {}
    assert ("DELETE", "/projects/403") in client.mutations
    assert ("POST", "/projects") in client.mutations


def test_unexpected_provider_content_blocks_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)

    class UnexpectedHook(FakeGitLab):
        def list_all(
            self, path: str, *, query: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            if path == "/projects/403/hooks":
                return [{"id": 999}]
            return super().list_all(path, query=query)

    client = UnexpectedHook(fixture)
    client.project = client._project(403)
    client.refs = {"refs/heads/main": COMMIT}
    previous = state.RetainedState(
        schema=1,
        provider="surrey",
        project_id=403,
        path_with_namespace=state.SURREY_PATH,
        visibility="private",
        head=COMMIT,
        tree=TREE,
        refs=dict(client.refs),
        destination_deploy_key_enabled=False,
        source_refs_digest=SOURCE_REFS_SHA,
        candidate_version=VERSION,
        wheel_sha256=WHEEL_SHA,
        sealed_at_utc="2026-08-31T18:00:00+00:00",
    )
    previous_path = tmp_path / "previous.json"
    state.write_private_json(previous_path, previous.document())
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: CONTROLLER_COMMIT,
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    args = Namespace(
        fixture=fixture_path,
        previous_state=previous_path,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=tmp_path / "audit.json",
        confirm_project_reset=state.SURREY_PATH,
    )

    with pytest.raises(lifecycle.LifecycleError, match="unexpected hook"):
        lifecycle.reset_project(args, client)
    assert not any(method == "DELETE" for method, _path in client.mutations)


def test_unexpected_deploy_key_blocks_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    client.project = client._project(403)
    client.refs = {"refs/heads/main": COMMIT}
    client.deploy_keys = [{"id": 999, "title": "unreviewed"}]
    previous = state.RetainedState(
        schema=1,
        provider="surrey",
        project_id=403,
        path_with_namespace=state.SURREY_PATH,
        visibility="private",
        head=COMMIT,
        tree=TREE,
        refs=dict(client.refs),
        destination_deploy_key_enabled=False,
        source_refs_digest=SOURCE_REFS_SHA,
        candidate_version=VERSION,
        wheel_sha256=WHEEL_SHA,
        sealed_at_utc="2026-08-31T18:00:00+00:00",
    )
    previous_path = tmp_path / "previous.json"
    state.write_private_json(previous_path, previous.document())
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: CONTROLLER_COMMIT,
    )
    monkeypatch.setattr(lifecycle, "validate_public_key", lambda *_args: "ssh-ed25519 AAAA")
    args = Namespace(
        fixture=fixture_path,
        previous_state=previous_path,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=tmp_path / "audit.json",
        confirm_project_reset=state.SURREY_PATH,
    )

    with pytest.raises(lifecycle.LifecycleError, match="unexpected deploy key"):
        lifecycle.reset_project(args, client)
    assert not any(method == "DELETE" for method, _path in client.mutations)


def test_seal_revokes_write_access_when_candidate_report_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    client.project = client._project(404)
    client.deploy_keys = [
        {
            "id": 303,
            "title": state.SURREY_DEPLOY_KEY_TITLE,
            "key": "ssh-ed25519 AAAA",
            "can_push": True,
        }
    ]
    handoff_path = tmp_path / "handoff.json"
    state.write_private_json(handoff_path, reset_handoff().document())
    bad_report = tmp_path / "candidate.json"
    bad_report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        lifecycle,
        "public_key_fingerprint",
        lambda _record: state.SURREY_DEPLOY_KEY_FINGERPRINT,
    )
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: CONTROLLER_COMMIT,
    )
    args = Namespace(
        fixture=fixture_path,
        handoff=handoff_path,
        candidate_report=bad_report,
        retained_state=tmp_path / "retained.json",
        audit_report=tmp_path / "audit.json",
    )

    with pytest.raises(lifecycle.LifecycleError, match="closed Phase 3 schema"):
        lifecycle.verify_and_seal(args, client)
    assert client.deploy_keys == []
    assert not args.retained_state.exists()


def test_seal_rejects_a_handoff_from_another_controller_before_provider_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    handoff_path = tmp_path / "handoff.json"
    state.write_private_json(handoff_path, reset_handoff().document())
    monkeypatch.setattr(
        lifecycle,
        "validate_controller_checkout",
        lambda *_args, **_kwargs: "4" * 40,
    )
    args = Namespace(
        fixture=fixture_path,
        handoff=handoff_path,
        candidate_report=tmp_path / "candidate.json",
        retained_state=tmp_path / "retained.json",
        audit_report=tmp_path / "audit.json",
    )

    with pytest.raises(lifecycle.LifecycleError, match="trusted controller run"):
        lifecycle.verify_and_seal(args, client)
    assert client.mutations == []


def test_reset_confirmation_must_be_the_complete_exact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = write_fixture(tmp_path / "fixture.json")
    fixture = state.LifecycleFixture.read(fixture_path)
    client = FakeGitLab(fixture)
    monkeypatch.setattr(
        lifecycle,
        "inspect_wheel",
        lambda *_args: SimpleNamespace(version=VERSION, sha256=WHEEL_SHA),
    )
    args = Namespace(
        fixture=fixture_path,
        previous_state=None,
        deploy_public_key=tmp_path / "key.pub",
        wheel=tmp_path / "candidate.whl",
        expected_wheel_sha256=WHEEL_SHA,
        handoff=tmp_path / "handoff.json",
        audit_report=tmp_path / "audit.json",
        confirm_project_reset=state.SURREY_GROUP,
    )

    with pytest.raises(lifecycle.LifecycleError, match="must be exactly"):
        lifecycle.reset_project(args, client)
    assert client.mutations == []


def test_api_client_rejects_cross_origin_and_mutation_network_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = lifecycle.GitLabClient(api_base=state.SURREY_API_BASE, token="token")
    with pytest.raises(lifecycle.LifecycleError, match="invalid GitLab API path"):
        client._url("https://example.invalid/projects", None)

    class FailedOpener:
        def open(self, *_args: object, **_kwargs: object) -> None:
            raise TimeoutError("lost response")

    monkeypatch.setattr(client, "_opener", FailedOpener())
    with pytest.raises(lifecycle.AmbiguousMutation, match="outcome is ambiguous"):
        client.request("POST", "/projects", body={})


def test_lifecycle_tool_changes_select_bootstrap_acceptance_scope() -> None:
    scope = importlib.import_module("ci_scope")

    assert scope.owners_for_path("tools/live_provider_state.py") == frozenset({"bootstrap"})
    assert scope.owners_for_path("tools/bootstrap_live_provider_lifecycle.py") == frozenset(
        {"bootstrap"}
    )

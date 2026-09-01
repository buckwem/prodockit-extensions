# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Stateful fake-GitHub tests for the protected GitHub lifecycle controller."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
lifecycle = importlib.import_module("bootstrap_live_provider_github_lifecycle")
state = importlib.import_module("live_provider_state")

COMMIT = "a" * 40
TREE = "b" * 40
SOURCE = "c" * 40
DIGEST = "d" * 64
WHEEL = "e" * 64
CONTENTS = "f" * 64


def git(checkout: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(checkout), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def key_record() -> tuple[str, str]:
    algorithm = b"ssh-ed25519"
    material = b"k" * 32
    blob = (
        len(algorithm).to_bytes(4, "big") + algorithm + len(material).to_bytes(4, "big") + material
    )
    encoded = base64.b64encode(blob).decode()
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest())
    return (
        f"ssh-ed25519 {encoded} phase-four-test",
        "SHA256:" + fingerprint.rstrip(b"=").decode(),
    )


class FakeGitHub:
    def __init__(self, *, destination: bool = False) -> None:
        self.repository: dict[str, Any] | None = None
        self.destination_refs: dict[str, str] = {}
        self.keys: list[dict[str, Any]] = []
        self.source_refs = {
            "refs/heads/main": SOURCE,
            "refs/tags/v1": "1" * 40,
        }
        self.extra_repositories: set[str] = set()
        self.mutations: list[tuple[str, str]] = []
        self.next_repository_id = 501
        self.next_key_id = 601
        self.actions_enabled = True
        if destination:
            self.repository = self.repository_value(500)
            self.actions_enabled = False

    @staticmethod
    def repository_value(identifier: int) -> dict[str, Any]:
        return {
            "id": identifier,
            "name": lifecycle.REPOSITORY,
            "full_name": lifecycle.GITHUB_PATH,
            "owner": {"login": lifecycle.ORGANISATION},
            "private": True,
            "fork": False,
            "archived": False,
            "has_issues": False,
            "has_projects": False,
            "has_wiki": False,
            "has_discussions": False,
        }

    @staticmethod
    def ref_values(refs: dict[str, str], namespace: str) -> list[dict[str, Any]]:
        prefix = f"refs/{namespace}/"
        return [
            {"ref": ref, "object": {"sha": target, "type": "commit"}}
            for ref, target in refs.items()
            if ref.startswith(prefix)
        ]

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: set[int] | None = None,
    ) -> lifecycle.ApiResponse:
        self.mutations.append((method, path)) if method != "GET" else None
        headers: dict[str, str] = {}
        if method == "GET" and path == "/installation":
            return lifecycle.ApiResponse(
                200,
                {
                    "id": 77,
                    "repository_selection": "all",
                    "permissions": {
                        "administration": "write",
                        "metadata": "read",
                        "pages": "read",
                        "repository_hooks": "read",
                    },
                    "account": {
                        "login": lifecycle.ORGANISATION,
                        "type": "Organization",
                    },
                },
                headers,
            )
        if method == "GET" and path.startswith(f"/orgs/{lifecycle.ORGANISATION}/repos?"):
            values = [{"full_name": name} for name in sorted(self.extra_repositories)]
            if self.repository is not None:
                values.append({"full_name": lifecycle.GITHUB_PATH})
            return lifecycle.ApiResponse(200, values, headers)
        if method == "GET" and path == (f"/repos/{lifecycle.ORGANISATION}/{lifecycle.REPOSITORY}"):
            if self.repository is None:
                return lifecycle.ApiResponse(404, {"message": "Not Found"}, headers)
            return lifecycle.ApiResponse(200, dict(self.repository), headers)
        if method == "DELETE" and path == (
            f"/repos/{lifecycle.ORGANISATION}/{lifecycle.REPOSITORY}"
        ):
            self.repository = None
            self.destination_refs = {}
            self.keys = []
            return lifecycle.ApiResponse(204, None, headers)
        if method == "POST" and path == f"/orgs/{lifecycle.ORGANISATION}/repos":
            assert body is not None and body["name"] == lifecycle.REPOSITORY
            self.repository = self.repository_value(self.next_repository_id)
            self.next_repository_id += 1
            self.actions_enabled = True
            return lifecycle.ApiResponse(201, dict(self.repository), headers)
        if method == "PUT" and path.endswith("/actions/permissions"):
            assert body == {"enabled": False}
            self.actions_enabled = False
            return lifecycle.ApiResponse(204, None, headers)
        if method == "GET" and path.endswith("/actions/permissions"):
            return lifecycle.ApiResponse(200, {"enabled": self.actions_enabled}, headers)
        if method == "GET" and path.endswith("/pages"):
            return lifecycle.ApiResponse(404, {"message": "Not Found"}, headers)
        if method == "GET" and path.endswith("/hooks?per_page=100"):
            return lifecycle.ApiResponse(200, [], headers)

        source_prefix = (
            f"/repos/{lifecycle.SOURCE_OWNER}/{lifecycle.SOURCE_REPOSITORY}/git/matching-refs/"
        )
        destination_prefix = (
            f"/repos/{lifecycle.ORGANISATION}/{lifecycle.REPOSITORY}/git/matching-refs/"
        )
        if method == "GET" and path.startswith(source_prefix):
            namespace = path.removeprefix(source_prefix).split("?", 1)[0]
            return lifecycle.ApiResponse(200, self.ref_values(self.source_refs, namespace), headers)
        if method == "GET" and path.startswith(destination_prefix):
            namespace = path.removeprefix(destination_prefix).split("?", 1)[0]
            if self.repository is None or not self.destination_refs:
                return lifecycle.ApiResponse(409, {"message": "Git Repository is empty."}, headers)
            return lifecycle.ApiResponse(
                200, self.ref_values(self.destination_refs, namespace), headers
            )
        key_path = f"/repos/{lifecycle.ORGANISATION}/{lifecycle.REPOSITORY}/keys"
        if method == "GET" and path == key_path + "?per_page=100":
            return lifecycle.ApiResponse(200, [dict(key) for key in self.keys], headers)
        if method == "POST" and path == key_path:
            assert body is not None
            value = {
                "id": self.next_key_id,
                "title": body["title"],
                "key": body["key"],
                "read_only": body["read_only"],
            }
            self.next_key_id += 1
            self.keys.append(value)
            return lifecycle.ApiResponse(201, dict(value), headers)
        if method == "DELETE" and path.startswith(key_path + "/"):
            identifier = int(path.rsplit("/", 1)[1])
            self.keys = [key for key in self.keys if key["id"] != identifier]
            return lifecycle.ApiResponse(204, None, headers)
        raise AssertionError(f"unexpected fake GitHub request: {method} {path}")


def retained(repository_id: int = 500) -> lifecycle.GitHubRetainedState:
    return lifecycle.GitHubRetainedState(
        schema=1,
        provider="github",
        repository_id=repository_id,
        full_name=lifecycle.GITHUB_PATH,
        head=COMMIT,
        tree=TREE,
        refs={"refs/heads/main": COMMIT},
        destination_deploy_key_enabled=False,
        source_refs_digest=DIGEST,
        candidate_version="0.54.0",
        wheel_sha256=WHEEL,
        wheel_contents_sha256=CONTENTS,
        release_commit=COMMIT,
        controller_commit=COMMIT,
        sealed_at_utc="2026-09-01T12:00:00+00:00",
    )


def perform_reset(
    client: FakeGitHub,
    *,
    previous: lifecycle.GitHubRetainedState | None = None,
) -> state.ResetHandoff:
    record, fingerprint = key_record()
    return lifecycle.reset(
        client=client,
        retained=previous,
        public_key_record=record,
        key_fingerprint=fingerprint,
        candidate_version="0.54.0",
        wheel_sha256=WHEEL,
        wheel_contents_sha256=CONTENTS,
        release_commit=COMMIT,
        controller_commit=COMMIT,
        now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        sleep=lambda _seconds: None,
    )


def candidate_report(
    path: Path,
    *,
    passed: bool = True,
    wheel_sha256: str = WHEEL,
) -> Path:
    value = {
        "architecture": "arm64",
        "candidate_version": "0.54.0",
        "destination_transition": "empty -> refs/heads/main",
        "finished_at_utc": "2026-09-01T12:10:00+00:00",
        "manual_provider_review_required": False,
        "operating_system": "macOS",
        "passed": passed,
        "path_one": {
            "name": "path-one",
            "configured_source": "",
            "configured_history": "",
            "applied_stages": ["clone", "first-push"],
            "commit": COMMIT,
            "tree": TREE,
            "clean_tree": True,
        },
        "path_two": {
            "name": "path-two",
            "configured_source": lifecycle.GITHUB_PATH,
            "configured_history": "keep",
            "applied_stages": ["clone"],
            "commit": COMMIT,
            "tree": TREE,
            "clean_tree": True,
        },
        "provider": "github",
        "provider_created_refs": [],
        "repository": lifecycle.GITHUB_PATH,
        "source_refs_digest": lifecycle.canonical_sha256(
            {
                "refs/heads/main": SOURCE,
                "refs/tags/v1": "1" * 40,
            }
        ),
        "source_refs_unchanged": True,
        "started_at_utc": "2026-09-01T12:01:00+00:00",
        "wheel_sha256": wheel_sha256,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_absent_reset_creates_only_the_exact_private_empty_fixture() -> None:
    client = FakeGitHub()

    handoff = perform_reset(client)

    assert handoff.schema == 2
    assert handoff.provider == "github"
    assert handoff.path_with_namespace == lifecycle.GITHUB_PATH
    assert handoff.project_id == 501
    assert handoff.wheel_contents_sha256 == CONTENTS
    assert client.repository is not None
    assert client.actions_enabled is False
    assert len(client.keys) == 1
    assert client.keys[0]["read_only"] is False
    handoff.validate(now=datetime(2026, 9, 1, 12, 1, tzinfo=timezone.utc))


def test_existing_fixture_requires_and_matches_retained_state() -> None:
    client = FakeGitHub(destination=True)
    client.destination_refs = {"refs/heads/main": COMMIT}

    with pytest.raises(lifecycle.LifecycleError, match="without its exact retained state"):
        perform_reset(client)
    with pytest.raises(lifecycle.LifecycleError, match="ID differs"):
        perform_reset(client, previous=retained(repository_id=999))

    handoff = perform_reset(client, previous=retained())

    assert handoff.project_id == 501
    assert ("DELETE", f"/repos/{lifecycle.ORGANISATION}/{lifecycle.REPOSITORY}") in client.mutations


def test_reset_refuses_missing_retained_repository_and_extra_org_repo() -> None:
    absent = FakeGitHub()
    with pytest.raises(lifecycle.LifecycleError, match="retained state exists"):
        perform_reset(absent, previous=retained())

    unsafe = FakeGitHub()
    unsafe.extra_repositories.add("prodockit-live-tests/valuable")
    with pytest.raises(lifecycle.LifecycleError, match="unapproved repository"):
        perform_reset(unsafe)


def test_reset_requires_the_exact_all_repository_app_installation() -> None:
    class SelectedInstallation(FakeGitHub):
        def request(
            self,
            method: str,
            path: str,
            *,
            body: dict[str, Any] | None = None,
            expected: set[int] | None = None,
        ) -> lifecycle.ApiResponse:
            response = super().request(method, path, body=body, expected=expected)
            if method == "GET" and path == "/installation":
                response.value["repository_selection"] = "selected"
            return response

    with pytest.raises(lifecycle.LifecycleError, match="another installation"):
        perform_reset(SelectedInstallation())


def test_reset_refuses_retained_refs_or_key_drift() -> None:
    changed = FakeGitHub(destination=True)
    changed.destination_refs = {"refs/heads/main": "9" * 40}
    with pytest.raises(lifecycle.LifecycleError, match="refs differ"):
        perform_reset(changed, previous=retained())

    keyed = FakeGitHub(destination=True)
    keyed.destination_refs = {"refs/heads/main": COMMIT}
    keyed.keys = [{"id": 1, "title": "unexpected", "read_only": False}]
    with pytest.raises(lifecycle.LifecycleError, match="still has a deploy key"):
        perform_reset(keyed, previous=retained())


def test_public_key_requires_ed25519_wire_encoding(tmp_path: Path) -> None:
    record, expected = key_record()
    path = tmp_path / "key.pub"
    path.write_text(record + "\n", encoding="utf-8")

    observed, fingerprint = lifecycle.public_key(path)

    assert observed == record
    assert fingerprint == expected
    path.write_text("ssh-rsa AAAA not-approved\n", encoding="utf-8")
    with pytest.raises(lifecycle.LifecycleError, match="Ed25519"):
        lifecycle.public_key(path)


def test_controller_checkout_requires_clean_exact_main(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git(checkout, "init", "-b", "main")
    git(checkout, "config", "user.name", "Controller")
    git(checkout, "config", "user.email", "controller@example.invalid")
    (checkout / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    git(checkout, "add", ".")
    git(checkout, "commit", "-m", "Reviewed")
    commit = git(checkout, "rev-parse", "HEAD")
    git(checkout, "update-ref", "refs/remotes/origin/main", commit)

    assert lifecycle.validate_controller_checkout(checkout, expected_commit=commit) == commit

    (checkout / "untracked.txt").write_text("unreviewed\n", encoding="utf-8")
    with pytest.raises(lifecycle.LifecycleError, match="must be clean"):
        lifecycle.validate_controller_checkout(checkout, expected_commit=commit)


def test_github_api_refuses_redirects_and_anonymous_source_omits_token() -> None:
    class Response:
        status = 200
        headers: ClassVar[dict[str, str]] = {}

        @staticmethod
        def read(_limit: int) -> bytes:
            return b"{}"

    class CaptureOpener:
        request = None

        def open(self, request, *, timeout: float):
            del timeout
            self.request = request
            return Response()

    anonymous = lifecycle.GitHubAPI(None)
    capture = CaptureOpener()
    anonymous._opener = capture
    anonymous.request("GET", "/repos/buckwem/prodockit-template")
    assert capture.request is not None
    assert capture.request.get_header("Authorization") is None

    class RedirectOpener:
        @staticmethod
        def open(request, *, timeout: float):
            del request, timeout
            raise urllib.error.HTTPError(
                "https://api.github.com/redirect",
                301,
                "Moved",
                {},
                io.BytesIO(b'{"message":"Moved"}'),
            )

    authenticated = lifecycle.GitHubAPI("installation-token")
    authenticated._opener = RedirectOpener()
    with pytest.raises(lifecycle.LifecycleError, match="returned 301"):
        authenticated.request("GET", "/repos/prodockit-live-tests/bootstrap-release-gate")


def test_retained_state_schema_is_closed(tmp_path: Path) -> None:
    value = retained().document()
    path = tmp_path / "retained.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    assert lifecycle.GitHubRetainedState.read(path) == retained()

    value["token"] = "not allowed"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(lifecycle.LifecycleError, match="closed schema"):
        lifecycle.GitHubRetainedState.read(path)

    invalid_time = retained().document()
    invalid_time["sealed_at_utc"] = "2026-09-01T12:00:00+01:00"
    path.write_text(json.dumps(invalid_time), encoding="utf-8")
    with pytest.raises(lifecycle.LifecycleError, match="must use UTC"):
        lifecycle.GitHubRetainedState.read(path)


def test_seal_revokes_key_then_produces_closed_provider_result(tmp_path: Path) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    client.destination_refs = {"refs/heads/main": COMMIT}
    candidate_wheel = "9" * 64
    report = candidate_report(tmp_path / "candidate.json", wheel_sha256=candidate_wheel)

    retained_state, provider_result = lifecycle.seal(
        client=client,
        handoff=handoff,
        candidate_report=report,
        workflow_run_id=42,
        workflow_url=("https://github.com/buckwem/prodockit-extensions/actions/runs/42"),
        now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
    )

    assert client.keys == []
    assert retained_state.head == COMMIT
    assert retained_state.destination_deploy_key_enabled is False
    assert provider_result.passed is True
    assert provider_result.path_one.commit == provider_result.path_two.commit
    assert provider_result.wheel_sha256 == candidate_wheel
    assert provider_result.wheel_contents_sha256 == CONTENTS


def test_seal_revokes_key_before_rejecting_bad_candidate(tmp_path: Path) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    client.destination_refs = {"refs/heads/main": COMMIT}
    report = candidate_report(tmp_path / "candidate.json", passed=False)

    with pytest.raises(lifecycle.LifecycleError, match="differs from the reset handoff"):
        lifecycle.seal(
            client=client,
            handoff=handoff,
            candidate_report=report,
            workflow_run_id=42,
            workflow_url=("https://github.com/buckwem/prodockit-extensions/actions/runs/42"),
            now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
        )

    assert client.keys == []


def test_seal_revokes_key_before_rejecting_invalid_candidate_time(tmp_path: Path) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    client.destination_refs = {"refs/heads/main": COMMIT}
    report = candidate_report(tmp_path / "candidate.json")
    value = json.loads(report.read_text(encoding="utf-8"))
    value["finished_at_utc"] = "2026-09-01T13:00:00+01:00"
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(lifecycle.LifecycleError, match="must use UTC"):
        lifecycle.seal(
            client=client,
            handoff=handoff,
            candidate_report=report,
            workflow_run_id=42,
            workflow_url=("https://github.com/buckwem/prodockit-extensions/actions/runs/42"),
            now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
        )

    assert client.keys == []


def test_seal_rejects_destination_drift_after_key_removal(tmp_path: Path) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    client.destination_refs = {"refs/heads/main": "9" * 40}
    report = candidate_report(tmp_path / "candidate.json")

    with pytest.raises(lifecycle.LifecycleError, match="destination refs differ"):
        lifecycle.seal(
            client=client,
            handoff=handoff,
            candidate_report=report,
            workflow_run_id=42,
            workflow_url=("https://github.com/buckwem/prodockit-extensions/actions/runs/42"),
            now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
        )

    assert client.keys == []


def test_seal_rejects_source_drift_after_key_removal(tmp_path: Path) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    client.destination_refs = {"refs/heads/main": COMMIT}
    client.source_refs["refs/heads/main"] = "8" * 40
    report = candidate_report(tmp_path / "candidate.json")

    with pytest.raises(lifecycle.LifecycleError, match="template refs changed"):
        lifecycle.seal(
            client=client,
            handoff=handoff,
            candidate_report=report,
            workflow_run_id=42,
            workflow_url=("https://github.com/buckwem/prodockit-extensions/actions/runs/42"),
            now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
        )

    assert client.keys == []

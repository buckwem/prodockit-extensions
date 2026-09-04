# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Stateful fake-GitHub tests for the protected GitHub lifecycle controller."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
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


def test_seal_entrypoint_does_not_require_the_reset_wheel_dependencies(tmp_path: Path) -> None:
    """Cleanup must start even when third-party wheel tooling is unavailable."""

    (tmp_path / "sitecustomize.py").write_text(
        """\
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "packaging" or name.startswith("packaging."):
        raise ModuleNotFoundError("packaging deliberately unavailable")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "bootstrap_live_provider_github_lifecycle.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


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
            "owner": {"login": lifecycle.ACCOUNT},
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
        if method == "GET" and path == "/user":
            return lifecycle.ApiResponse(
                200,
                {
                    "id": 77,
                    "login": lifecycle.ACCOUNT,
                    "type": "User",
                },
                headers,
            )
        if method == "GET" and path == (f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}"):
            if self.repository is None:
                return lifecycle.ApiResponse(404, {"message": "Not Found"}, headers)
            return lifecycle.ApiResponse(200, dict(self.repository), headers)
        if method == "DELETE" and path == (f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}"):
            self.repository = None
            self.destination_refs = {}
            self.keys = []
            return lifecycle.ApiResponse(204, None, headers)
        if method == "POST" and path == "/user/repos":
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
        destination_prefix = f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}/git/matching-refs/"
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
        key_path = f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}/keys"
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
) -> state.ResetHandoff:
    record, fingerprint = key_record()
    return lifecycle.reset(
        client=client,
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


def test_reset_refuses_a_pre_existing_fixed_repository() -> None:
    client = FakeGitHub(destination=True)
    client.destination_refs = {"refs/heads/main": COMMIT}

    with pytest.raises(lifecycle.LifecycleError, match="previous run did not remove it"):
        perform_reset(client)

    assert client.repository is not None
    assert not any(method == "DELETE" for method, _path in client.mutations)


def test_reset_requires_the_exact_personal_account_token() -> None:
    class OtherAccount(FakeGitHub):
        def request(
            self,
            method: str,
            path: str,
            *,
            body: dict[str, Any] | None = None,
            expected: set[int] | None = None,
        ) -> lifecycle.ApiResponse:
            response = super().request(method, path, body=body, expected=expected)
            if method == "GET" and path == "/user":
                response.value["login"] = "another-account"
            return response

    with pytest.raises(lifecycle.LifecycleError, match="another account"):
        perform_reset(OtherAccount())


def test_reset_removes_its_new_repository_when_configuration_fails() -> None:
    class BrokenActions(FakeGitHub):
        def request(
            self,
            method: str,
            path: str,
            *,
            body: dict[str, Any] | None = None,
            expected: set[int] | None = None,
        ) -> lifecycle.ApiResponse:
            if method == "PUT" and path.endswith("/actions/permissions"):
                raise lifecycle.LifecycleError("simulated configuration failure")
            return super().request(method, path, body=body, expected=expected)

    client = BrokenActions()
    with pytest.raises(lifecycle.LifecycleError, match="simulated configuration failure"):
        perform_reset(client)

    assert client.repository is None
    assert ("DELETE", f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}") in client.mutations


def test_reset_reconciles_lost_mutation_responses_without_repeating_writes() -> None:
    class LostResponses(FakeGitHub):
        def __init__(self) -> None:
            super().__init__()
            self.lost = {"POST /user/repos", "PUT actions", "POST key"}

        def request(
            self,
            method: str,
            path: str,
            *,
            body: dict[str, Any] | None = None,
            expected: set[int] | None = None,
        ) -> lifecycle.ApiResponse:
            response = super().request(method, path, body=body, expected=expected)
            label = (
                "POST /user/repos"
                if method == "POST" and path == "/user/repos"
                else "PUT actions"
                if method == "PUT" and path.endswith("/actions/permissions")
                else "POST key"
                if method == "POST" and path.endswith("/keys")
                else ""
            )
            if label in self.lost:
                self.lost.remove(label)
                raise lifecycle.AmbiguousMutation(f"lost {label} response")
            return response

    client = LostResponses()

    handoff = perform_reset(client)

    assert handoff.project_id == 501
    assert len(client.keys) == 1
    assert client.mutations.count(("POST", "/user/repos")) == 1
    assert sum(method == "PUT" for method, _path in client.mutations) == 1
    assert sum(
        method == "POST" and path.endswith("/keys")
        for method, path in client.mutations
    ) == 1


def test_cleanup_reconciles_lost_delete_response_without_repeating_it() -> None:
    class LostDelete(FakeGitHub):
        lost = True

        def request(
            self,
            method: str,
            path: str,
            *,
            body: dict[str, Any] | None = None,
            expected: set[int] | None = None,
        ) -> lifecycle.ApiResponse:
            response = super().request(method, path, body=body, expected=expected)
            if method == "DELETE" and path.endswith(lifecycle.REPOSITORY) and self.lost:
                self.lost = False
                raise lifecycle.AmbiguousMutation("lost delete response")
            return response

    client = LostDelete(destination=True)

    lifecycle.remove_repository(client, expected_id=500, sleep=lambda _seconds: None)

    assert client.repository is None
    assert client.mutations.count(
        ("DELETE", f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}")
    ) == 1


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
        authenticated.request("GET", f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}")


def test_github_api_retries_throttled_reads_and_honours_retry_after() -> None:
    class Response:
        status = 200
        headers: ClassVar[dict[str, str]] = {}

        @staticmethod
        def read(_limit: int) -> bytes:
            return b"{}"

    class ThrottledThenReady:
        attempts = 0

        def open(self, request, *, timeout: float):
            del request, timeout
            self.attempts += 1
            if self.attempts == 1:
                raise urllib.error.HTTPError(
                    "https://api.github.com/user",
                    403,
                    "Forbidden",
                    {"Retry-After": "7", "X-RateLimit-Remaining": "0"},
                    io.BytesIO(b'{"message":"secondary rate limit"}'),
                )
            return Response()

    delays: list[float] = []
    client = lifecycle.GitHubAPI("installation-token", sleep=delays.append)
    opener = ThrottledThenReady()
    client._opener = opener

    assert client.request("GET", "/user").status == 200
    assert opener.attempts == 2
    assert delays == [7.0]


def test_github_api_retries_transient_non_json_gateway_response() -> None:
    class Response:
        status = 200
        headers: ClassVar[dict[str, str]] = {}

        @staticmethod
        def read(_limit: int) -> bytes:
            return b"{}"

    class GatewayThenReady:
        attempts = 0

        def open(self, request, *, timeout: float):
            del request, timeout
            self.attempts += 1
            if self.attempts == 1:
                raise urllib.error.HTTPError(
                    "https://api.github.com/user",
                    503,
                    "Service Unavailable",
                    {},
                    io.BytesIO(b"upstream unavailable"),
                )
            return Response()

    delays: list[float] = []
    client = lifecycle.GitHubAPI("installation-token", sleep=delays.append)
    opener = GatewayThenReady()
    client._opener = opener

    assert client.request("GET", "/user").status == 200
    assert opener.attempts == 2
    assert delays == [2.0]


def test_github_api_does_not_retry_permission_denial_or_mutation_uncertainty() -> None:
    class Rejected:
        attempts = 0

        def open(self, request, *, timeout: float):
            del timeout
            self.attempts += 1
            if request.method == "POST":
                raise urllib.error.URLError("connection reset")
            raise urllib.error.HTTPError(
                "https://api.github.com/user",
                403,
                "Forbidden",
                {},
                io.BytesIO(b'{"message":"Resource not accessible by token"}'),
            )

    opener = Rejected()
    client = lifecycle.GitHubAPI(
        "installation-token",
        sleep=lambda _delay: pytest.fail("deterministic failure was retried"),
    )
    client._opener = opener
    with pytest.raises(lifecycle.LifecycleError, match="returned 403"):
        client.request("GET", "/user")
    assert opener.attempts == 1

    with pytest.raises(lifecycle.AmbiguousMutation, match="outcome is ambiguous"):
        client.request("POST", "/user/repos", body={"name": lifecycle.REPOSITORY})
    assert opener.attempts == 2


def test_github_api_reports_safe_validation_detail() -> None:
    class ValidationOpener:
        @staticmethod
        def open(request, *, timeout: float):
            del request, timeout
            raise urllib.error.HTTPError(
                "https://api.github.com/repositories/1/keys",
                422,
                "Unprocessable Content",
                {},
                io.BytesIO(
                    json.dumps(
                        {
                            "message": "Validation Failed",
                            "errors": [
                                {
                                    "resource": "PublicKey",
                                    "field": "key",
                                    "code": "custom",
                                    "message": "key is already in use",
                                }
                            ],
                        }
                    ).encode()
                ),
            )

    client = lifecycle.GitHubAPI("installation-token")
    client._opener = ValidationOpener()
    with pytest.raises(
        lifecycle.LifecycleError,
        match="returned 422: Validation Failed; key is already in use",
    ):
        client.request("POST", f"/repos/{lifecycle.ACCOUNT}/{lifecycle.REPOSITORY}/keys")


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
    assert client.repository is None


def test_seal_command_removes_fixture_when_main_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent merge must reject evidence without leaking the fixture."""

    client = FakeGitHub()
    handoff = perform_reset(client)
    handoff_path = tmp_path / "reset-handoff.json"
    handoff_value = handoff.document()
    current = datetime.now(timezone.utc).replace(microsecond=0)
    handoff_value["completed_at_utc"] = current.isoformat()
    handoff_value["expires_at_utc"] = (current + lifecycle.HANDOFF_LIFETIME).isoformat()
    handoff_path.write_text(json.dumps(handoff_value), encoding="utf-8")
    report = candidate_report(tmp_path / "candidate.json")
    audit = tmp_path / "seal-audit.json"
    args = SimpleNamespace(
        candidate_report=report,
        retained_state=tmp_path / "retained-state.json",
        provider_result=tmp_path / "provider-result.json",
        workflow_run_id=42,
        workflow_url="https://github.com/buckwem/prodockit-extensions/actions/runs/42",
        audit_report=audit,
        handoff=handoff_path,
    )

    def advanced_main(_checkout: Path, *, expected_commit: str) -> str:
        assert expected_commit == COMMIT
        raise lifecycle.LifecycleError(
            "GitHub lifecycle controller must match the exact reviewed main commit"
        )

    monkeypatch.setattr(lifecycle, "validate_controller_checkout", advanced_main)

    with pytest.raises(lifecycle.LifecycleError, match="exact reviewed main commit"):
        lifecycle.seal_command(args, client, source_client=client)

    assert client.repository is None
    assert client.keys == []
    assert not args.retained_state.exists()
    assert not args.provider_result.exists()
    value = json.loads(audit.read_text(encoding="utf-8"))
    assert value["passed"] is False
    assert value["repository_removal_attempted"] is True
    assert value["repository_removed"] is True
    assert value["failure"] == (
        "GitHub lifecycle controller must match the exact reviewed main commit"
    )


def test_seal_revokes_key_before_rejecting_bad_candidate(tmp_path: Path) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    client.destination_refs = {"refs/heads/main": COMMIT}
    report = candidate_report(tmp_path / "candidate.json", passed=False)

    with pytest.raises(
        lifecycle.LifecycleError,
        match="candidate failure report has an invalid closed schema",
    ):
        lifecycle.seal(
            client=client,
            handoff=handoff,
            candidate_report=report,
            workflow_run_id=42,
            workflow_url=("https://github.com/buckwem/prodockit-extensions/actions/runs/42"),
            now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
        )

    assert client.keys == []
    assert client.repository is None


def test_seal_preserves_a_closed_candidate_failure_reason_after_cleanup(
    tmp_path: Path,
) -> None:
    client = FakeGitHub()
    handoff = perform_reset(client)
    report = tmp_path / "candidate.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "provider": "github",
                "repository": state.GITHUB_PATH,
                "candidate_version": handoff.candidate_version,
                "wheel_sha256": handoff.wheel_sha256,
                "source_refs_digest": "2" * 64,
                "started_at_utc": "2026-09-04T15:09:00+00:00",
                "finished_at_utc": "2026-09-04T15:09:02+00:00",
                "failure": "the source refs differ from the provider reset handoff",
                "write_outcome": "not pushed",
                "source_refs_unchanged": True,
                "manual_provider_review_required": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        lifecycle.LifecycleError,
        match=(
            "GitHub candidate failed: the source refs differ from the provider "
            "reset handoff; write outcome: not pushed"
        ),
    ):
        lifecycle.seal(
            client=client,
            handoff=handoff,
            candidate_report=report,
            workflow_run_id=42,
            workflow_url=(
                "https://github.com/buckwem/prodockit-extensions/actions/runs/42"
            ),
            now=datetime(2026, 9, 1, 12, 15, tzinfo=timezone.utc),
        )

    assert client.keys == []
    assert client.repository is None


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
    assert client.repository is None


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
    assert client.repository is None


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
    assert client.repository is None

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Trusted lifecycle controller for the fixed GitHub Bootstrap live fixture."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn, Protocol

from live_provider_state import (
    GITHUB_PATH,
    ResetHandoff,
    StateError,
    canonical_sha256,
    read_json,
    write_private_json,
)
from release_gate_state import ProviderGateResult, ProviderPathResult

API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
ACCOUNT = "buckwem"
REPOSITORY = "bootstrap-release-gate"
SOURCE_OWNER = "buckwem"
SOURCE_REPOSITORY = "prodockit-template"
DEPLOY_KEY_TITLE = "prodockit-release-gate-destination"
OBJECT_ID_LENGTHS = {40, 64}
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
HANDOFF_LIFETIME = timedelta(minutes=30)
DELETE_RECONCILIATION_DELAYS = (1.0, 2.0, 5.0, 10.0)


class LifecycleError(RuntimeError):
    """The GitHub fixture is unsafe, ambiguous or unavailable."""


@dataclass(frozen=True)
class ApiResponse:
    status: int
    value: Any
    headers: Mapping[str, str]


class Client(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: set[int] | None = None,
    ) -> ApiResponse: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Treat provider redirects as failures instead of following them."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class GitHubAPI:
    """Small exact-host GitHub REST client without mutation retries."""

    def __init__(self, token: str | None, *, timeout: float = 30.0) -> None:
        if token is not None and (not token or any(character in token for character in "\0\r\n")):
            raise LifecycleError("the GitHub installation token is missing or malformed")
        self._token = token
        self._timeout = timeout
        self._opener = urllib.request.build_opener(NoRedirect())

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: set[int] | None = None,
    ) -> ApiResponse:
        expected = expected or {200}
        if not path.startswith("/") or "\0" in path or "\r" in path or "\n" in path:
            raise LifecycleError("GitHub API path is not a safe absolute path")
        url = API_BASE + path
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com":
            raise LifecycleError("GitHub API request escaped the exact HTTPS host")
        payload = None
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "prodockit-release-gate",
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method.upper())
        try:
            response = self._opener.open(request, timeout=self._timeout)
        except urllib.error.HTTPError as error:
            response = error
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise LifecycleError(f"GitHub API {method} {path} failed: {error}") from error
        status = response.status
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise LifecycleError("GitHub API response exceeded the inspection limit")
        try:
            value = json.loads(raw) if raw else None
        except json.JSONDecodeError as error:
            raise LifecycleError(f"GitHub API {method} {path} returned malformed JSON") from error
        if status not in expected:
            detail = ""
            if isinstance(value, dict):
                messages = [value.get("message")]
                errors = value.get("errors")
                if isinstance(errors, list):
                    messages.extend(
                        error.get("message")
                        for error in errors
                        if isinstance(error, dict)
                    )
                safe_messages = [
                    message.strip()
                    for message in messages
                    if isinstance(message, str)
                    and message.strip()
                    and len(message) <= 240
                    and not any(character in message for character in "\0\r\n")
                ]
                if safe_messages:
                    detail = ": " + "; ".join(dict.fromkeys(safe_messages))
            raise LifecycleError(
                f"GitHub API {method} {path} returned {status}{detail}"
            )
        return ApiResponse(status=status, value=value, headers=dict(response.headers))


def text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in "\0\r\n"):
        raise LifecycleError(f"{label} must be non-empty single-line text")
    return value


def positive_id(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LifecycleError(f"{label} must be a positive integer")
    return value


def object_id(value: Any, *, label: str) -> str:
    value = text(value, label=label)
    if len(value) not in OBJECT_ID_LENGTHS or any(c not in "0123456789abcdef" for c in value):
        raise LifecycleError(f"{label} must be one complete lowercase Git object ID")
    return value


def sha256_digest(value: Any, *, label: str) -> str:
    value = text(value, label=label)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise LifecycleError(f"{label} must be one lowercase SHA-256 digest")
    return value


def object_value(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LifecycleError(f"{label} must be one JSON object")
    return value


def utc_timestamp(value: Any, *, label: str) -> datetime:
    """Parse one explicit UTC timestamp and reject local or naive values."""

    value = text(value, label=label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LifecycleError(f"{label} must be an ISO-8601 timestamp") from error
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise LifecycleError(f"{label} must use UTC")
    return result


def list_value(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise LifecycleError(f"{label} must be one JSON list")
    return value


def public_key_fingerprint(record: str) -> str:
    """Validate one Ed25519 public-key record and return its fingerprint."""

    parts = record.split()
    if len(parts) not in {2, 3} or parts[0] != "ssh-ed25519":
        raise LifecycleError("destination public key must be one Ed25519 public-key record")
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (ValueError, TypeError) as error:
        raise LifecycleError("destination public key contains invalid base64") from error
    algorithm = b"ssh-ed25519"
    if (
        decoded[:4] != len(algorithm).to_bytes(4, "big")
        or decoded[4 : 4 + len(algorithm)] != algorithm
    ):
        raise LifecycleError("destination public key is not encoded as Ed25519")
    digest = base64.b64encode(hashlib.sha256(decoded).digest()).rstrip(b"=").decode()
    return f"SHA256:{digest}"


def public_key(path: Path) -> tuple[str, str]:
    """Read one Ed25519 public key and return its record and SHA-256 fingerprint."""

    try:
        record = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise LifecycleError(f"could not read destination public key: {error}") from error
    return record, public_key_fingerprint(record)


def validate_controller_checkout(checkout: Path, *, expected_commit: str) -> str:
    """Require one clean default-branch checkout at the exact release commit."""

    commands = {
        "branch": ("branch", "--show-current"),
        "head": ("rev-parse", "HEAD"),
        "origin_main": ("rev-parse", "origin/main"),
        "status": ("status", "--porcelain"),
    }
    observed: dict[str, str] = {}
    for label, arguments in commands.items():
        try:
            completed = subprocess.run(
                ("git", "-C", str(checkout), *arguments),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise LifecycleError(f"could not validate the release checkout: {error}") from error
        observed[label] = completed.stdout.strip()
    if observed["branch"] != "main":
        raise LifecycleError("GitHub lifecycle controller must run from the default main branch")
    if observed["status"]:
        raise LifecycleError("GitHub lifecycle controller checkout must be clean")
    if observed["head"] != observed["origin_main"] or observed["head"] != expected_commit:
        raise LifecycleError(
            "GitHub lifecycle controller must match the exact reviewed main commit"
        )
    return observed["head"]


def repository(client: Client) -> dict[str, Any] | None:
    response = client.request(
        "GET",
        f"/repos/{ACCOUNT}/{REPOSITORY}",
        expected={200, 404},
    )
    if response.status == 404:
        return None
    value = object_value(response.value, label="GitHub repository")
    if (
        positive_id(value.get("id"), label="repository.id") <= 0
        or value.get("name") != REPOSITORY
        or value.get("full_name") != GITHUB_PATH
        or object_value(value.get("owner"), label="repository.owner").get("login") != ACCOUNT
        or value.get("private") is not True
        or value.get("fork") is not False
        or value.get("archived") is not False
        or any(
            value.get(name) is not False
            for name in ("has_issues", "has_projects", "has_wiki", "has_discussions")
        )
    ):
        raise LifecycleError("GitHub returned another or unsafe destination repository")
    return value


def refs(client: Client, owner: str, name: str) -> dict[str, str]:
    """Read complete branch and tag refs; refuse pagination ambiguity."""

    observed: dict[str, str] = {}
    for namespace in ("heads", "tags"):
        response = client.request(
            "GET",
            f"/repos/{owner}/{name}/git/matching-refs/{namespace}?per_page=100",
            expected={200, 409},
        )
        if response.status == 409:
            continue
        if 'rel="next"' in response.headers.get("Link", ""):
            raise LifecycleError("GitHub ref response requires unsupported pagination")
        for item in list_value(response.value, label=f"GitHub {namespace} refs"):
            item = object_value(item, label="GitHub ref")
            ref = text(item.get("ref"), label="GitHub ref name")
            if ref in observed:
                raise LifecycleError(f"GitHub repeated ref {ref}")
            target = object_value(item.get("object"), label=f"GitHub ref {ref} object")
            observed[ref] = object_id(target.get("sha"), label=f"GitHub ref {ref}")
    return observed


def source_state(client: Client) -> tuple[str, str]:
    source_refs = refs(client, SOURCE_OWNER, SOURCE_REPOSITORY)
    main = source_refs.get("refs/heads/main")
    if main is None:
        raise LifecycleError("the public GitHub template does not advertise main")
    return main, canonical_sha256(source_refs)


def deploy_keys(client: Client) -> list[dict[str, Any]]:
    response = client.request("GET", f"/repos/{ACCOUNT}/{REPOSITORY}/keys?per_page=100")
    if 'rel="next"' in response.headers.get("Link", ""):
        raise LifecycleError("GitHub deploy-key response requires unsupported pagination")
    return [
        object_value(value, label="GitHub deploy key")
        for value in list_value(response.value, label="GitHub deploy keys")
    ]


def verify_inert_configuration(client: Client) -> None:
    actions = object_value(
        client.request("GET", f"/repos/{ACCOUNT}/{REPOSITORY}/actions/permissions").value,
        label="GitHub Actions permissions",
    )
    if actions.get("enabled") is not False:
        raise LifecycleError("GitHub Actions is enabled on the destination")
    pages = client.request(
        "GET",
        f"/repos/{ACCOUNT}/{REPOSITORY}/pages",
        expected={200, 404},
    )
    if pages.status != 404:
        raise LifecycleError("GitHub Pages is enabled on the destination")
    hooks = client.request("GET", f"/repos/{ACCOUNT}/{REPOSITORY}/hooks?per_page=100")
    if 'rel="next"' in hooks.headers.get("Link", ""):
        raise LifecycleError("GitHub hooks response requires unsupported pagination")
    if list_value(hooks.value, label="GitHub hooks"):
        raise LifecycleError("GitHub destination contains an unexpected webhook")


def verify_controller_identity(client: Client) -> None:
    """Require a user-authorised lifecycle token for the fixed personal account."""

    account = object_value(
        client.request("GET", "/user").value,
        label="GitHub lifecycle account",
    )
    if account.get("login") != ACCOUNT or account.get("type") != "User":
        raise LifecycleError("GitHub lifecycle token belongs to another account")


@dataclass(frozen=True)
class GitHubRetainedState:
    schema: int
    provider: str
    repository_id: int
    full_name: str
    head: str
    tree: str
    refs: dict[str, str]
    destination_deploy_key_enabled: bool
    source_refs_digest: str
    candidate_version: str
    wheel_sha256: str
    wheel_contents_sha256: str
    release_commit: str
    controller_commit: str
    sealed_at_utc: str

    @classmethod
    def read(cls, path: Path) -> GitHubRetainedState:
        value = read_json(path, label="GitHub retained state")
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise LifecycleError("GitHub retained state has an invalid closed schema")
        refs_value = value.get("refs")
        if not isinstance(refs_value, dict) or not refs_value:
            raise LifecycleError("GitHub retained refs must be a non-empty object")
        state = cls(
            schema=value["schema"],
            provider=value["provider"],
            repository_id=positive_id(value["repository_id"], label="repository_id"),
            full_name=text(value["full_name"], label="full_name"),
            head=object_id(value["head"], label="head"),
            tree=object_id(value["tree"], label="tree"),
            refs={
                text(ref, label="retained ref"): object_id(target, label=f"retained {ref}")
                for ref, target in refs_value.items()
            },
            destination_deploy_key_enabled=value["destination_deploy_key_enabled"],
            source_refs_digest=sha256_digest(
                value["source_refs_digest"], label="source_refs_digest"
            ),
            candidate_version=text(value["candidate_version"], label="candidate_version"),
            wheel_sha256=sha256_digest(value["wheel_sha256"], label="wheel_sha256"),
            wheel_contents_sha256=sha256_digest(
                value["wheel_contents_sha256"], label="wheel_contents_sha256"
            ),
            release_commit=object_id(value["release_commit"], label="release_commit"),
            controller_commit=object_id(value["controller_commit"], label="controller_commit"),
            sealed_at_utc=text(value["sealed_at_utc"], label="sealed_at_utc"),
        )
        state.validate()
        return state

    def validate(self) -> None:
        if self.schema != 1 or self.provider != "github" or self.full_name != GITHUB_PATH:
            raise LifecycleError("GitHub retained state identifies another fixture")
        if self.destination_deploy_key_enabled is not False:
            raise LifecycleError("GitHub retained state does not prove write-key removal")
        if self.refs != {"refs/heads/main": self.head}:
            raise LifecycleError("GitHub retained state contains unexpected refs")
        for label, digest in (
            ("source_refs_digest", self.source_refs_digest),
            ("wheel_sha256", self.wheel_sha256),
            ("wheel_contents_sha256", self.wheel_contents_sha256),
        ):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise LifecycleError(f"{label} is not a lowercase SHA-256 digest")
        utc_timestamp(self.sealed_at_utc, label="sealed_at_utc")

    def document(self) -> dict[str, Any]:
        return asdict(self)


def wait_until_absent(client: Client, sleep: Callable[[float], None]) -> None:
    for delay in DELETE_RECONCILIATION_DELAYS:
        if repository(client) is None:
            return
        sleep(delay)
    if repository(client) is not None:
        raise LifecycleError("GitHub repository deletion did not become observable")


def remove_repository(
    client: Client,
    *,
    expected_id: int,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Remove only the fixed repository with the exact expected identity."""

    current = repository(client)
    if current is None:
        return
    if positive_id(current.get("id"), label="repository.id") != expected_id:
        raise LifecycleError("GitHub repository identity changed before removal")
    client.request(
        "DELETE",
        f"/repos/{ACCOUNT}/{REPOSITORY}",
        expected={204},
    )
    wait_until_absent(client, sleep)


def reset(
    *,
    client: Client,
    public_key_record: str,
    key_fingerprint: str,
    candidate_version: str,
    wheel_sha256: str,
    wheel_contents_sha256: str,
    release_commit: str,
    controller_commit: str,
    now: datetime,
    sleep: Callable[[float], None] = time.sleep,
    source_client: Client | None = None,
) -> ResetHandoff:
    """Create only the absent fixed repository and install one write key."""

    verify_controller_identity(client)
    if release_commit != controller_commit:
        raise LifecycleError("GitHub reset controller is not the exact release commit")
    current = repository(client)
    if current is not None:
        raise LifecycleError(
            "GitHub test repository already exists; the previous run did not remove it"
        )

    source_commit, source_digest = source_state(source_client or client)
    created = object_value(
        client.request(
            "POST",
            "/user/repos",
            body={
                "name": REPOSITORY,
                "private": True,
                "has_issues": False,
                "has_projects": False,
                "has_wiki": False,
                "has_discussions": False,
                "auto_init": False,
            },
            expected={201},
        ).value,
        label="created GitHub repository",
    )
    repository_id = positive_id(created.get("id"), label="created repository.id")
    if created.get("full_name") != GITHUB_PATH or created.get("private") is not True:
        raise LifecycleError("GitHub created another or non-private repository")
    try:
        client.request(
            "PUT",
            f"/repos/{ACCOUNT}/{REPOSITORY}/actions/permissions",
            body={"enabled": False},
            expected={204},
        )
        verify_inert_configuration(client)
        if refs(client, ACCOUNT, REPOSITORY):
            raise LifecycleError("new GitHub destination repository is not empty")
        if deploy_keys(client):
            raise LifecycleError("new GitHub destination unexpectedly contains a deploy key")
        key = object_value(
            client.request(
                "POST",
                f"/repos/{ACCOUNT}/{REPOSITORY}/keys",
                body={
                    "title": DEPLOY_KEY_TITLE,
                    "key": public_key_record,
                    "read_only": False,
                },
                expected={201},
            ).value,
            label="created GitHub deploy key",
        )
        key_id = positive_id(key.get("id"), label="deploy_key.id")
        if key.get("title") != DEPLOY_KEY_TITLE or key.get("read_only") is not False:
            raise LifecycleError("GitHub created the destination key with unsafe properties")
    except (LifecycleError, StateError, OSError, ValueError):
        remove_repository(client, expected_id=repository_id, sleep=sleep)
        raise
    completed = now.astimezone(timezone.utc).replace(microsecond=0)
    return ResetHandoff(
        schema=2,
        run_id=str(uuid.uuid4()),
        provider="github",
        project_id=repository_id,
        path_with_namespace=GITHUB_PATH,
        repository_empty=True,
        deploy_key_id=key_id,
        deploy_key_fingerprint=key_fingerprint,
        source_commit=source_commit,
        source_refs_digest=source_digest,
        candidate_version=candidate_version,
        wheel_sha256=wheel_sha256,
        controller_commit=controller_commit,
        completed_at_utc=completed.isoformat(),
        expires_at_utc=(completed + HANDOFF_LIFETIME).isoformat(),
        wheel_contents_sha256=wheel_contents_sha256,
    )


CANDIDATE_REPORT_KEYS = {
    "architecture",
    "candidate_version",
    "destination_transition",
    "finished_at_utc",
    "manual_provider_review_required",
    "operating_system",
    "passed",
    "path_one",
    "path_two",
    "provider",
    "provider_created_refs",
    "repository",
    "source_refs_digest",
    "source_refs_unchanged",
    "started_at_utc",
    "wheel_sha256",
}
PATH_REPORT_KEYS = {
    "name",
    "configured_source",
    "configured_history",
    "applied_stages",
    "commit",
    "tree",
    "clean_tree",
}


def candidate_path(value: Any, *, label: str) -> ProviderPathResult:
    value = object_value(value, label=label)
    if set(value) != PATH_REPORT_KEYS:
        raise LifecycleError(f"candidate {label} has an invalid closed schema")
    normalized = dict(value)
    for name in ("configured_source", "configured_history"):
        if normalized[name] == "":
            normalized[name] = None
    try:
        return ProviderPathResult.parse(normalized, label=label)
    except StateError as error:
        raise LifecycleError(str(error)) from error


@dataclass(frozen=True)
class CandidateEvidence:
    version: str
    wheel_sha256: str
    source_refs_digest: str
    path_one: ProviderPathResult
    path_two: ProviderPathResult
    started_at_utc: str
    finished_at_utc: str


def candidate_evidence(path: Path, handoff: ResetHandoff) -> CandidateEvidence:
    value = read_json(path, label="GitHub candidate report")
    if not isinstance(value, dict) or set(value) != CANDIDATE_REPORT_KEYS:
        raise LifecycleError("GitHub candidate report has an invalid closed schema")
    if (
        value["passed"] is not True
        or value["provider"] != "github"
        or value["repository"] != GITHUB_PATH
        or value["candidate_version"] != handoff.candidate_version
        or value["source_refs_digest"] != handoff.source_refs_digest
        or value["source_refs_unchanged"] is not True
        or value["manual_provider_review_required"] is not False
        or value["destination_transition"] != "empty -> refs/heads/main"
    ):
        raise LifecycleError("GitHub candidate report differs from the reset handoff")
    created_refs = value["provider_created_refs"]
    if not isinstance(created_refs, list) or created_refs:
        raise LifecycleError("GitHub candidate report contains unexpected provider refs")
    wheel_sha256 = sha256_digest(value["wheel_sha256"], label="wheel_sha256")
    path_one = candidate_path(value["path_one"], label="path_one")
    path_two = candidate_path(value["path_two"], label="path_two")
    if (
        path_one.name != "path-one"
        or path_one.configured_source is not None
        or path_one.configured_history is not None
        or path_one.applied_stages.count("first-push") != 1
    ):
        raise LifecycleError("GitHub candidate path one did not perform one initial push")
    if (
        path_two.name != "path-two"
        or path_two.configured_source != GITHUB_PATH
        or path_two.configured_history != "keep"
        or "first-push" in path_two.applied_stages
    ):
        raise LifecycleError("GitHub candidate path two did not reuse option 1 without a push")
    if (
        path_one.clean_tree is not True
        or path_two.clean_tree is not True
        or path_one.commit != path_two.commit
        or path_one.tree != path_two.tree
    ):
        raise LifecycleError("GitHub candidate paths did not finish in one clean Git state")
    started = text(value["started_at_utc"], label="started_at_utc")
    finished = text(value["finished_at_utc"], label="finished_at_utc")
    started_at = utc_timestamp(started, label="started_at_utc")
    finished_at = utc_timestamp(finished, label="finished_at_utc")
    if finished_at < started_at or finished_at - started_at > timedelta(hours=2):
        raise LifecycleError("GitHub candidate duration is invalid or exceeds two hours")
    return CandidateEvidence(
        version=value["candidate_version"],
        wheel_sha256=wheel_sha256,
        source_refs_digest=value["source_refs_digest"],
        path_one=path_one,
        path_two=path_two,
        started_at_utc=started,
        finished_at_utc=finished,
    )


def revoke_handoff_key(client: Client, handoff: ResetHandoff) -> None:
    current = repository(client)
    if (
        current is None
        or positive_id(current.get("id"), label="repository.id") != handoff.project_id
    ):
        raise LifecycleError("GitHub destination identity changed before seal")
    keys = deploy_keys(client)
    if len(keys) != 1:
        raise LifecycleError("GitHub destination does not expose exactly one deploy key")
    key = keys[0]
    if (
        positive_id(key.get("id"), label="deploy_key.id") != handoff.deploy_key_id
        or key.get("title") != DEPLOY_KEY_TITLE
        or key.get("read_only") is not False
    ):
        raise LifecycleError("GitHub destination deploy key differs from the reset handoff")
    key_record = text(key.get("key"), label="deploy_key.key")
    observed = public_key_fingerprint(key_record)
    if observed != handoff.deploy_key_fingerprint:
        raise LifecycleError("GitHub destination deploy key fingerprint changed")
    client.request(
        "DELETE",
        f"/repos/{ACCOUNT}/{REPOSITORY}/keys/{handoff.deploy_key_id}",
        expected={204},
    )
    if deploy_keys(client):
        raise LifecycleError("GitHub destination deploy key removal was not confirmed")


def seal(
    *,
    client: Client,
    handoff: ResetHandoff,
    candidate_report: Path,
    workflow_run_id: int,
    workflow_url: str,
    now: datetime,
    source_client: Client | None = None,
) -> tuple[GitHubRetainedState, ProviderGateResult]:
    """Independently verify provider state after revoking destination write access."""

    verify_controller_identity(client)
    handoff.validate(now=now)
    if handoff.schema != 2 or handoff.provider != "github":
        raise LifecycleError("seal requires one GitHub schema 2 reset handoff")
    try:
        revoke_handoff_key(client, handoff)
        candidate = candidate_evidence(candidate_report, handoff)
        current_source, current_source_digest = source_state(source_client or client)
        if (
            current_source != handoff.source_commit
            or current_source_digest != handoff.source_refs_digest
        ):
            raise LifecycleError("public GitHub template refs changed during the candidate run")
        destination_refs = refs(client, ACCOUNT, REPOSITORY)
        expected_refs = {"refs/heads/main": candidate.path_one.commit}
        if destination_refs != expected_refs:
            raise LifecycleError("GitHub destination refs differ from the candidate result")
        sealed_at = now.astimezone(timezone.utc).replace(microsecond=0)
        retained = GitHubRetainedState(
            schema=1,
            provider="github",
            repository_id=handoff.project_id,
            full_name=GITHUB_PATH,
            head=candidate.path_one.commit,
            tree=candidate.path_one.tree,
            refs=destination_refs,
            destination_deploy_key_enabled=False,
            source_refs_digest=current_source_digest,
            candidate_version=candidate.version,
            wheel_sha256=candidate.wheel_sha256,
            wheel_contents_sha256=text(
                handoff.wheel_contents_sha256, label="wheel_contents_sha256"
            ),
            release_commit=handoff.controller_commit,
            controller_commit=handoff.controller_commit,
            sealed_at_utc=sealed_at.isoformat(),
        )
        retained.validate()
        result = ProviderGateResult(
            schema=1,
            passed=True,
            provider="github",
            release_repository="buckwem/prodockit-extensions",
            release_commit=handoff.controller_commit,
            candidate_version=candidate.version,
            wheel_sha256=candidate.wheel_sha256,
            wheel_contents_sha256=retained.wheel_contents_sha256,
            controller_commit=handoff.controller_commit,
            repository=GITHUB_PATH,
            project_id=handoff.project_id,
            path_one=candidate.path_one,
            path_two=candidate.path_two,
            source_commit=current_source,
            source_refs_digest=current_source_digest,
            source_refs_unchanged=True,
            destination_refs=destination_refs,
            destination_deploy_key_enabled=False,
            workflow_run_id=workflow_run_id,
            workflow_url=workflow_url,
            started_at_utc=candidate.started_at_utc,
            finished_at_utc=sealed_at.isoformat(),
        )
        result.validate(now=sealed_at)
        return retained, result
    finally:
        remove_repository(client, expected_id=handoff.project_id)


def write_once_private_json(path: Path, value: Any) -> None:
    if path.expanduser().resolve().exists():
        raise LifecycleError(f"completed audit already exists: {path}")
    write_private_json(path, value)


def token_from_fd(descriptor: int) -> str:
    try:
        raw = os.read(descriptor, 64 * 1024)
    except OSError as error:
        raise LifecycleError(f"could not read GitHub installation token: {error}") from error
    if len(raw) == 64 * 1024:
        raise LifecycleError("GitHub installation token exceeded the input limit")
    return raw.decode("utf-8").strip()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("reset", "seal"))
    result.add_argument("--token-fd", type=int, required=True)
    result.add_argument("--deploy-public-key", type=Path)
    result.add_argument("--wheel", type=Path)
    result.add_argument("--expected-wheel-sha256")
    result.add_argument("--expected-wheel-contents-sha256")
    result.add_argument("--release-commit")
    result.add_argument("--controller-commit")
    result.add_argument("--handoff", type=Path, required=True)
    result.add_argument("--audit-report", type=Path, required=True)
    result.add_argument("--confirm-repository-reset")
    result.add_argument("--candidate-report", type=Path)
    result.add_argument("--retained-state", type=Path)
    result.add_argument("--provider-result", type=Path)
    result.add_argument("--workflow-run-id", type=int)
    result.add_argument("--workflow-url")
    return result


def reset_command(args: argparse.Namespace, client: Client, *, source_client: Client) -> None:
    required = (
        args.deploy_public_key,
        args.wheel,
        args.expected_wheel_sha256,
        args.expected_wheel_contents_sha256,
        args.release_commit,
        args.controller_commit,
        args.confirm_repository_reset,
    )
    if any(value is None for value in required):
        raise LifecycleError("reset arguments are incomplete")
    if args.confirm_repository_reset != GITHUB_PATH:
        raise LifecycleError(f"reset confirmation must be exactly {GITHUB_PATH}")
    release_commit = object_id(args.release_commit, label="release_commit")
    controller_commit = object_id(args.controller_commit, label="controller_commit")
    checkout = Path(__file__).resolve().parents[1]
    observed_commit = validate_controller_checkout(checkout, expected_commit=release_commit)
    if controller_commit != observed_commit:
        raise LifecycleError("--controller-commit differs from the controller checkout")
    # The sealer must remain able to revoke the deploy key and remove the
    # temporary repository in a fresh standard-library-only runner. Import the
    # reset-only wheel inspector here rather than making cleanup depend on its
    # third-party ``packaging`` dependency.
    try:
        from canonical_wheel import WheelIdentityError, inspect_wheel
    except ImportError as error:
        raise LifecycleError(f"could not load the reset wheel inspector: {error}") from error
    try:
        identity = inspect_wheel(args.wheel)
    except WheelIdentityError as error:
        raise LifecycleError(str(error)) from error
    if identity.wheel_sha256 != args.expected_wheel_sha256:
        raise LifecycleError("candidate wheel raw SHA-256 differs from the approved value")
    if identity.wheel_contents_sha256 != args.expected_wheel_contents_sha256:
        raise LifecycleError("candidate wheel contents differ from the approved value")
    record, fingerprint = public_key(args.deploy_public_key)
    started = datetime.now(timezone.utc)
    print("Provider:       github.com")
    print(f"Repository:     {GITHUB_PATH}")
    print(f"Release commit: {release_commit}")
    print(f"Candidate:      prodockit {identity.version}")
    print(
        "Mutations:      private create, disable Actions, enable ephemeral key, "
        "remove after seal"
    )
    handoff = reset(
        client=client,
        public_key_record=record,
        key_fingerprint=fingerprint,
        candidate_version=identity.version,
        wheel_sha256=identity.wheel_sha256,
        wheel_contents_sha256=identity.wheel_contents_sha256,
        release_commit=release_commit,
        controller_commit=controller_commit,
        now=started,
        source_client=source_client,
    )
    write_private_json(args.handoff, handoff.document())
    write_private_json(
        args.audit_report,
        {
            "schema": 1,
            "operation": "github-reset",
            "passed": True,
            "repository": GITHUB_PATH,
            "repository_id": handoff.project_id,
            "release_commit": release_commit,
            "controller_commit": controller_commit,
            "candidate_version": identity.version,
            "wheel_sha256": identity.wheel_sha256,
            "wheel_contents_sha256": identity.wheel_contents_sha256,
            "source_commit": handoff.source_commit,
            "source_refs_digest": handoff.source_refs_digest,
            "deploy_key_fingerprint": fingerprint,
            "handoff_sha256": canonical_sha256(handoff.document()),
            "started_at_utc": started.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"GitHub reset ready: {GITHUB_PATH}")
    print(f"Candidate handoff: {args.handoff}")


def seal_command(args: argparse.Namespace, client: Client, *, source_client: Client) -> None:
    required = (
        args.candidate_report,
        args.retained_state,
        args.provider_result,
        args.workflow_run_id,
        args.workflow_url,
    )
    if any(value is None for value in required):
        raise LifecycleError("seal arguments are incomplete")
    outputs = (args.audit_report, args.retained_state, args.provider_result)
    existing = [str(path) for path in outputs if path.expanduser().resolve().exists()]
    if existing:
        raise LifecycleError("seal output already exists: " + ", ".join(existing))
    handoff = ResetHandoff.read(args.handoff)
    started = datetime.now(timezone.utc)
    try:
        validate_controller_checkout(
            Path(__file__).resolve().parents[1],
            expected_commit=handoff.controller_commit,
        )
        retained, result = seal(
            client=client,
            handoff=handoff,
            candidate_report=args.candidate_report,
            workflow_run_id=args.workflow_run_id,
            workflow_url=args.workflow_url,
            now=started,
            source_client=source_client,
        )
    except (LifecycleError, StateError, OSError, ValueError) as error:
        cleanup_error: LifecycleError | StateError | OSError | ValueError | None = None
        try:
            # A merge can advance ``main`` between reset and seal. The
            # controller mismatch must still reject the evidence, but the
            # validated handoff remains sufficient to identify and remove
            # only this run's fixed disposable repository.
            verify_controller_identity(client)
            remove_repository(client, expected_id=handoff.project_id)
        except (LifecycleError, StateError, OSError, ValueError) as observed:
            cleanup_error = observed
        failure = str(error)
        if cleanup_error is not None:
            failure += f"; cleanup failed: {cleanup_error}"
        write_once_private_json(
            args.audit_report,
            {
                "schema": 1,
                "operation": "github-seal",
                "passed": False,
                "repository": GITHUB_PATH,
                "repository_id": handoff.project_id,
                "controller_commit": handoff.controller_commit,
                "candidate_version": handoff.candidate_version,
                "wheel_sha256": handoff.wheel_sha256,
                "wheel_contents_sha256": handoff.wheel_contents_sha256,
                "deploy_key_removal_attempted": True,
                "repository_removal_attempted": True,
                "repository_removed": cleanup_error is None,
                "failure": failure,
                "started_at_utc": started.isoformat(),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        if cleanup_error is not None:
            raise LifecycleError(failure) from error
        raise
    write_once_private_json(args.retained_state, retained.document())
    write_once_private_json(args.provider_result, result.document())
    write_once_private_json(
        args.audit_report,
        {
            "schema": 1,
            "operation": "github-seal",
            "passed": True,
            "repository": GITHUB_PATH,
            "repository_id": handoff.project_id,
            "controller_commit": handoff.controller_commit,
            "candidate_version": handoff.candidate_version,
            "wheel_sha256": handoff.wheel_sha256,
            "wheel_contents_sha256": handoff.wheel_contents_sha256,
            "destination_deploy_key_enabled": False,
            "repository_removed": True,
            "retained_state_sha256": canonical_sha256(retained.document()),
            "provider_result_sha256": result.sha256,
            "workflow_run_id": args.workflow_run_id,
            "workflow_url": args.workflow_url,
            "started_at_utc": started.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"GitHub provider verified and sealed: {GITHUB_PATH}")
    print(f"Provider result: {args.provider_result}")


def fail(message: str) -> NoReturn:
    print(f"GitHub live-provider lifecycle failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        token = token_from_fd(args.token_fd)
        client = GitHubAPI(token)
        source_client = GitHubAPI(None)
        if args.command == "reset":
            reset_command(args, client, source_client=source_client)
        else:
            seal_command(args, client, source_client=source_client)
    except (LifecycleError, StateError, OSError, ValueError) as error:
        fail(str(error))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()

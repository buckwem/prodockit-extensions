# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Trusted project lifecycle for Bootstrap live-provider Phase 3.

This controller is deliberately separate from the candidate-wheel harness. It
can reset one hard-coded Surrey GitLab project, but it never installs or imports
the candidate wheel and never receives the private deploy key.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bootstrap_live_provider_read_only import (
    LiveProviderError,
    inspect_wheel,
    private_metadata_path,
    public_key_fingerprint,
    utc_now,
)
from bootstrap_live_provider_read_write import (
    validate_controller_checkout,
    validate_destination_refs,
)
from live_provider_state import (
    SURREY_PATH,
    LifecycleFixture,
    ResetHandoff,
    RetainedState,
    StateError,
    canonical_sha256,
    validate_refs,
    write_private_json,
)

READ_RETRY_DELAYS = (2.0, 5.0, 10.0, 20.0)
TRANSIENT_HTTP_STATUS = {429, 502, 503, 504}
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PROJECT_DISABLE_SETTINGS: dict[str, Any] = {
    "visibility": "private",
    "issues_access_level": "disabled",
    "merge_requests_access_level": "disabled",
    "wiki_access_level": "disabled",
    "snippets_access_level": "disabled",
    "builds_access_level": "disabled",
    "container_registry_access_level": "disabled",
    "package_registry_access_level": "disabled",
    "packages_enabled": False,
    "shared_runners_enabled": False,
    "auto_devops_enabled": False,
    "public_jobs": False,
}
SECRET_NAME_RE = re.compile(r"(?:TOKEN|PASSWORD|SECRET|PRIVATE_KEY)", re.IGNORECASE)
PHASE_TWO_REPORT_KEYS = {
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
PATH_RESULT_KEYS = {
    "name",
    "configured_source",
    "configured_history",
    "applied_stages",
    "commit",
    "tree",
    "clean_tree",
}


class LifecycleError(RuntimeError):
    """The lifecycle controller cannot prove a safe transition."""


class AmbiguousMutation(LifecycleError):
    """A mutation response was lost and its outcome must be observed."""


@contextlib.contextmanager
def exclusive_run_lock(fixture_path: Path) -> Iterator[None]:
    """Serialise local lifecycle runs without retaining a credential.

    A crashed run deliberately leaves the lock directory behind. An operator
    must inspect provider state before removing it, which is safer than
    guessing that an interrupted destructive operation did not happen.
    """

    lock = fixture_path.with_name(f".{fixture_path.name}.phase3-lock")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as error:
        raise LifecycleError(
            f"another or interrupted Phase 3 run owns the lifecycle lock: {lock.name}"
        ) from error
    owner = lock / "owner.json"
    try:
        write_private_json(
            owner,
            {
                "schema": 1,
                "pid": os.getpid(),
                "started_at_utc": utc_now(),
            },
        )
        yield
    finally:
        owner.unlink(missing_ok=True)
        # An unexpected file is evidence of interference. Leave the lock in
        # place so a later run cannot silently proceed.
        with contextlib.suppress(OSError):
            lock.rmdir()


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True)
class ApiResponse:
    status: int
    value: Any
    headers: Mapping[str, str]


@dataclass(frozen=True)
class ProjectSnapshot:
    project: dict[str, Any]
    refs: dict[str, str]
    direct_members: tuple[dict[str, Any], ...]
    access_requests: tuple[dict[str, Any], ...]
    variables: tuple[dict[str, Any], ...]
    hooks: tuple[dict[str, Any], ...]
    deploy_tokens: tuple[dict[str, Any], ...]
    deploy_keys: tuple[dict[str, Any], ...]
    protected_branches: tuple[dict[str, Any], ...]
    merge_requests: tuple[dict[str, Any], ...]

    @property
    def project_id(self) -> int:
        value = self.project.get("id")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise LifecycleError("GitLab returned an invalid project ID")
        return value


@dataclass
class Journal:
    operations: list[dict[str, Any]]

    def record(
        self,
        operation: str,
        *,
        outcome: str,
        status: int | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "request_id": str(uuid.uuid4()),
            "operation": operation,
            "outcome": outcome,
            "started_at_utc": utc_now(),
            "observed_at_utc": utc_now(),
        }
        if status is not None:
            entry["status"] = status
        self.operations.append(entry)


class GitLabClient:
    """Small fail-closed GitLab REST client with observation-only retries."""

    def __init__(
        self,
        *,
        api_base: str,
        token: str,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 20.0,
    ) -> None:
        parsed = urlparse(api_base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
            raise LifecycleError("the GitLab API base must be one HTTPS origin")
        if not token or any(character.isspace() for character in token):
            raise LifecycleError("the lifecycle token is missing or malformed")
        self.api_base = api_base.rstrip("/") + "/"
        self.origin = (parsed.scheme, parsed.hostname, parsed.port)
        self._token = token
        self._sleep = sleep
        self._timeout = timeout
        self._opener = build_opener(_RejectRedirects())

    def close(self) -> None:
        """Drop the only retained reference to the controller credential."""

        self._token = ""

    def _url(self, path: str, query: Mapping[str, Any] | None) -> str:
        if not path.startswith("/") or "\0" in path or "\r" in path or "\n" in path:
            raise LifecycleError("invalid GitLab API path")
        url = urljoin(self.api_base, path.lstrip("/"))
        parsed = urlparse(url)
        if (parsed.scheme, parsed.hostname, parsed.port) != self.origin:
            raise LifecycleError("refusing a GitLab API request to another origin")
        if query:
            url += "?" + urlencode(query, doseq=True)
        return url

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        expected: Collection[int] = (200,),
    ) -> ApiResponse:
        method = method.upper()
        payload = None
        headers = {
            "Accept": "application/json",
            "PRIVATE-TOKEN": self._token,
            "User-Agent": "prodockit-live-provider-lifecycle/3",
        }
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        url = self._url(path, query)
        attempts = 1 + (len(READ_RETRY_DELAYS) if method == "GET" else 0)
        for attempt in range(attempts):
            request = Request(url, data=payload, headers=headers, method=method)
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    status = response.status
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise LifecycleError("GitLab API response exceeded the size limit")
                    value = _decode_json(raw, status=status)
                    if status not in expected:
                        raise LifecycleError(
                            f"GitLab API {method} {path} returned unexpected status {status}"
                        )
                    return ApiResponse(status=status, value=value, headers=dict(response.headers))
            except HTTPError as error:
                if error.code in expected:
                    raw = error.read(MAX_RESPONSE_BYTES + 1)
                    return ApiResponse(
                        status=error.code,
                        value=_decode_json(raw, status=error.code),
                        headers=dict(error.headers),
                    )
                if (
                    method == "GET"
                    and error.code in TRANSIENT_HTTP_STATUS
                    and attempt < attempts - 1
                ):
                    delay = READ_RETRY_DELAYS[attempt]
                    retry_after = error.headers.get("Retry-After", "").strip()
                    if retry_after.isdecimal():
                        delay = min(delay, float(retry_after))
                    self._sleep(delay)
                    continue
                if method != "GET" and error.code in TRANSIENT_HTTP_STATUS:
                    raise AmbiguousMutation(
                        f"GitLab API {method} {path} returned {error.code}; outcome is ambiguous"
                    ) from error
                raise LifecycleError(
                    f"GitLab API {method} {path} returned {error.code}"
                ) from error
            except (TimeoutError, URLError, OSError) as error:
                if method == "GET" and attempt < attempts - 1:
                    self._sleep(READ_RETRY_DELAYS[attempt])
                    continue
                message = f"GitLab API {method} {path} could not be observed"
                if method == "GET":
                    raise LifecycleError(message) from error
                raise AmbiguousMutation(f"{message}; outcome is ambiguous") from error
        raise AssertionError("unreachable API retry state")

    def get_optional(self, path: str) -> Any | None:
        response = self.request("GET", path, expected={200, 404})
        return None if response.status == 404 else response.value

    def list_all(
        self,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        page = 1
        values: list[dict[str, Any]] = []
        while True:
            page_query = dict(query or {})
            page_query.update({"page": page, "per_page": 100})
            response = self.request("GET", path, query=page_query)
            if not isinstance(response.value, list) or not all(
                isinstance(item, dict) for item in response.value
            ):
                raise LifecycleError(f"GitLab API {path} did not return a list of objects")
            values.extend(response.value)
            next_page = response.headers.get("X-Next-Page", "").strip()
            if not next_page:
                return values
            if not next_page.isdecimal() or int(next_page) != page + 1:
                raise LifecycleError(f"GitLab API {path} returned invalid pagination")
            page = int(next_page)
            if page > 1000:
                raise LifecycleError(f"GitLab API {path} exceeded the pagination limit")


def _decode_json(raw: bytes, *, status: int) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LifecycleError(f"GitLab API returned invalid JSON with status {status}") from error


def encoded(value: str) -> str:
    return quote(value, safe="")


def token_from_fd(descriptor: int) -> str:
    if descriptor < 0:
        raise LifecycleError("--token-fd must be a non-negative descriptor")
    try:
        value = os.read(descriptor, 8193)
    except OSError as error:
        raise LifecycleError("could not read the lifecycle token") from error
    if len(value) > 8192:
        raise LifecycleError("the lifecycle token exceeded the size limit")
    try:
        token = value.decode("utf-8").strip()
    except UnicodeError as error:
        raise LifecycleError("the lifecycle token is not UTF-8") from error
    if not token or any(character.isspace() for character in token):
        raise LifecycleError("the lifecycle token is missing or malformed")
    return token


def validate_no_inherited_credentials() -> None:
    names = sorted(name for name in os.environ if SECRET_NAME_RE.search(name))
    allowed = {"SSH_AUTH_SOCK"}
    unexpected = [name for name in names if name not in allowed]
    if unexpected:
        raise LifecycleError(
            "remove inherited credentials before running the lifecycle controller: "
            + ", ".join(unexpected)
        )


def validate_public_key(path: Path, fixture: LifecycleFixture) -> str:
    try:
        record = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise LifecycleError(f"could not read the reviewed deploy public key: {error}") from error
    try:
        fingerprint = public_key_fingerprint(record)
    except LiveProviderError as error:
        raise LifecycleError(str(error)) from error
    if fingerprint != fixture.deploy_key.fingerprint:
        raise LifecycleError("the deploy public key does not match the fixture fingerprint")
    return " ".join(record.split()[:2])


def group_preflight(client: GitLabClient, fixture: LifecycleFixture) -> None:
    group = client.get_optional(f"/groups/{encoded(fixture.group.full_path)}")
    if not isinstance(group, dict):
        raise LifecycleError("the exact Surrey live-provider group is not visible")
    if group.get("id") != fixture.group.id or group.get("full_path") != fixture.group.full_path:
        raise LifecycleError("the Surrey group ID or path differs from the reviewed fixture")
    projects = client.list_all(
        f"/groups/{fixture.group.id}/projects",
        query={"include_subgroups": "true", "with_shared": "false"},
    )
    paths = {item.get("path_with_namespace") for item in projects}
    if paths not in (set(), {fixture.project.path_with_namespace}):
        raise LifecycleError("the isolated Surrey group contains an unrelated project")
    checks = {
        "subgroup": client.list_all(f"/groups/{fixture.group.id}/subgroups"),
        "group variable": client.list_all(f"/groups/{fixture.group.id}/variables"),
        "group hook": client.list_all(f"/groups/{fixture.group.id}/hooks"),
        "group deploy token": client.list_all(f"/groups/{fixture.group.id}/deploy_tokens"),
    }
    for label, values in checks.items():
        if values:
            raise LifecycleError(f"the isolated Surrey group contains an unexpected {label}")


def project_value(client: GitLabClient, fixture: LifecycleFixture) -> dict[str, Any] | None:
    value = client.get_optional(
        f"/projects/{encoded(fixture.project.path_with_namespace)}"
    )
    if value is not None and not isinstance(value, dict):
        raise LifecycleError("GitLab returned an invalid project object")
    return value


def project_snapshot(
    client: GitLabClient,
    fixture: LifecycleFixture,
    project: dict[str, Any],
) -> ProjectSnapshot:
    project_id = project.get("id")
    if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id <= 0:
        raise LifecycleError("GitLab returned an invalid project ID")
    branches = client.list_all(f"/projects/{project_id}/repository/branches")
    tags = client.list_all(f"/projects/{project_id}/repository/tags")
    pipelines = client.list_all(f"/projects/{project_id}/pipelines")
    refs: dict[str, str] = {}
    for prefix, records in (("refs/heads", branches), ("refs/tags", tags)):
        for record in records:
            name = record.get("name")
            commit = record.get("commit")
            object_id = commit.get("id") if isinstance(commit, dict) else None
            if not isinstance(name, str) or not isinstance(object_id, str):
                raise LifecycleError("GitLab returned an invalid repository ref")
            refs[f"{prefix}/{name}"] = object_id
    for pipeline in pipelines:
        pipeline_id = pipeline.get("id")
        sha = pipeline.get("sha")
        if isinstance(pipeline_id, int) and isinstance(sha, str):
            refs[f"refs/pipelines/{pipeline_id}"] = sha
        else:
            raise LifecycleError("GitLab returned an invalid pipeline record")
    return ProjectSnapshot(
        project=project,
        refs=refs,
        direct_members=tuple(client.list_all(f"/projects/{project_id}/members")),
        access_requests=tuple(client.list_all(f"/projects/{project_id}/access_requests")),
        variables=tuple(client.list_all(f"/projects/{project_id}/variables")),
        hooks=tuple(client.list_all(f"/projects/{project_id}/hooks")),
        deploy_tokens=tuple(client.list_all(f"/projects/{project_id}/deploy_tokens")),
        deploy_keys=tuple(client.list_all(f"/projects/{project_id}/deploy_keys")),
        protected_branches=tuple(
            client.list_all(f"/projects/{project_id}/protected_branches")
        ),
        merge_requests=tuple(
            client.list_all(f"/projects/{project_id}/merge_requests", query={"state": "all"})
        ),
    )


def validate_project_identity(
    project: Mapping[str, Any], fixture: LifecycleFixture, *, expected_id: int | None
) -> int:
    project_id = project.get("id")
    namespace = project.get("namespace")
    namespace_id = namespace.get("id") if isinstance(namespace, dict) else None
    if (
        isinstance(project_id, bool)
        or not isinstance(project_id, int)
        or project_id <= 0
        or (expected_id is not None and project_id != expected_id)
        or project.get("path_with_namespace") != fixture.project.path_with_namespace
        or project.get("path") != fixture.project.name
        or project.get("name") != fixture.project.name
        or project.get("visibility") != "private"
        or namespace_id != fixture.group.id
    ):
        raise LifecycleError("the live-provider project identity differs from the fixture")
    return project_id


def validate_no_project_content(
    snapshot: ProjectSnapshot,
    *,
    allowed_deploy_key_id: int | None = None,
) -> None:
    collections = {
        "direct member": snapshot.direct_members,
        "access request": snapshot.access_requests,
        "variable": snapshot.variables,
        "hook": snapshot.hooks,
        "deploy token": snapshot.deploy_tokens,
        "merge request": snapshot.merge_requests,
    }
    shared = snapshot.project.get("shared_with_groups", [])
    if not isinstance(shared, list):
        raise LifecycleError("GitLab returned invalid shared-group state")
    if shared:
        raise LifecycleError("the live-provider project is shared with another group")
    for label, values in collections.items():
        if values:
            raise LifecycleError(f"the live-provider project contains an unexpected {label}")
    deploy_key_ids = [record.get("id") for record in snapshot.deploy_keys]
    expected_deploy_key_ids = (
        [] if allowed_deploy_key_id is None else [allowed_deploy_key_id]
    )
    if deploy_key_ids != expected_deploy_key_ids:
        raise LifecycleError("the live-provider project contains an unexpected deploy key")
    protected_names = {record.get("name") for record in snapshot.protected_branches}
    if not protected_names.issubset({"main"}):
        raise LifecycleError("the live-provider project has an unexpected protected branch")


def validate_retained(
    snapshot: ProjectSnapshot,
    fixture: LifecycleFixture,
    retained: RetainedState,
) -> None:
    validate_project_identity(snapshot.project, fixture, expected_id=retained.project_id)
    validate_no_project_content(snapshot)
    try:
        validate_refs(snapshot.refs, expected_head=retained.head)
    except StateError as error:
        raise LifecycleError(str(error)) from error
    if snapshot.refs != retained.refs:
        raise LifecycleError("the provider refs differ from the exact retained-state record")


def validate_destination_key(
    client: GitLabClient,
    fixture: LifecycleFixture,
    project_id: int,
    *,
    can_push: bool,
) -> None:
    keys = client.list_all(f"/projects/{project_id}/deploy_keys")
    if len(keys) != 1 or keys[0].get("id") != fixture.deploy_key.id:
        raise LifecycleError("the exact deploy key is not the only destination deploy key")
    key = keys[0]
    key_record = key.get("key")
    if key.get("title") != fixture.deploy_key.title or not isinstance(key_record, str):
        raise LifecycleError("the destination deploy key differs from the fixture")
    try:
        fingerprint = public_key_fingerprint(key_record)
    except LiveProviderError as error:
        raise LifecycleError(str(error)) from error
    if (
        fingerprint != fixture.deploy_key.fingerprint
        or key.get("can_push") is not can_push
    ):
        raise LifecycleError("the destination deploy-key permission differs from the fixture")


def wait_for_project(
    client: GitLabClient,
    fixture: LifecycleFixture,
    *,
    present: bool,
) -> dict[str, Any] | None:
    for delay in (0.0, *READ_RETRY_DELAYS):
        if delay:
            client._sleep(delay)
        value = project_value(client, fixture)
        if (value is not None) is present:
            return value
    state = "present" if present else "absent"
    raise LifecycleError(f"the project did not become stably {state} within the observation budget")


def delete_exact_project(
    client: GitLabClient,
    fixture: LifecycleFixture,
    project: dict[str, Any],
    journal: Journal,
) -> None:
    project_id = validate_project_identity(project, fixture, expected_id=None)
    try:
        response = client.request("DELETE", f"/projects/{project_id}", expected={202, 204})
        journal.record("delete-project", outcome="accepted", status=response.status)
    except AmbiguousMutation:
        journal.record("delete-project", outcome="response-lost")
    try:
        wait_for_project(client, fixture, present=False)
        return
    except LifecycleError:
        observed = project_value(client, fixture)
        if not isinstance(observed, dict):
            return
        validate_project_identity(observed, fixture, expected_id=project_id)
        marked = observed.get("marked_for_deletion_on") or observed.get("marked_for_deletion_at")
        if not marked:
            raise LifecycleError(
                "project deletion was not observed; refusing to repeat the destructive request"
            ) from None
    try:
        response = client.request(
            "DELETE",
            f"/projects/{project_id}",
            query={
                "permanently_remove": "true",
                "full_path": fixture.project.path_with_namespace,
            },
            expected={202, 204},
        )
        journal.record("permanently-remove-project", outcome="accepted", status=response.status)
    except AmbiguousMutation:
        journal.record("permanently-remove-project", outcome="response-lost")
    wait_for_project(client, fixture, present=False)


def create_exact_project(
    client: GitLabClient,
    fixture: LifecycleFixture,
    *,
    previous_id: int | None,
    created_after: datetime,
    journal: Journal,
) -> dict[str, Any]:
    body = {
        "name": fixture.project.name,
        "path": fixture.project.name,
        "namespace_id": fixture.group.id,
        **PROJECT_DISABLE_SETTINGS,
    }
    try:
        response = client.request("POST", "/projects", body=body, expected={201})
        journal.record("create-project", outcome="created", status=response.status)
        project = response.value
    except AmbiguousMutation:
        journal.record("create-project", outcome="response-lost")
        project = wait_for_project(client, fixture, present=True)
    if not isinstance(project, dict):
        raise LifecycleError("GitLab did not return the created project")
    project_id = validate_project_identity(project, fixture, expected_id=None)
    if previous_id is not None and project_id == previous_id:
        raise LifecycleError("GitLab reused the deleted project ID unexpectedly")
    created_at = project.get("created_at")
    if not isinstance(created_at, str):
        raise LifecycleError("GitLab omitted the created project timestamp")
    try:
        observed_creation = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise LifecycleError("GitLab returned an invalid project creation timestamp") from error
    now = datetime.now(timezone.utc)
    if (
        observed_creation.tzinfo is None
        or observed_creation < created_after - timedelta(minutes=5)
        or observed_creation > now + timedelta(minutes=5)
    ):
        raise LifecycleError("the project was not created within this reset window")
    observed = wait_for_project(client, fixture, present=True)
    if not isinstance(observed, dict):
        raise LifecycleError("the created project was not observable")
    validate_project_identity(observed, fixture, expected_id=project_id)
    try:
        response = client.request(
            "PUT", f"/projects/{project_id}", body=PROJECT_DISABLE_SETTINGS, expected={200}
        )
        journal.record(
            "disable-project-features", outcome="configured", status=response.status
        )
        configured = response.value
    except AmbiguousMutation:
        journal.record("disable-project-features", outcome="response-lost")
        configured = project_value(client, fixture)
    if not isinstance(configured, dict):
        raise LifecycleError("GitLab returned invalid configured project state")
    for name, expected in PROJECT_DISABLE_SETTINGS.items():
        if name not in configured:
            raise LifecycleError(f"GitLab omitted required project setting {name}")
        if configured[name] != expected:
            raise LifecycleError(f"GitLab did not apply required project setting {name}")
    return configured


def enable_destination_key(
    client: GitLabClient,
    fixture: LifecycleFixture,
    project_id: int,
    public_key: str,
    journal: Journal,
) -> None:
    try:
        response = client.request(
            "POST",
            f"/projects/{project_id}/deploy_keys/{fixture.deploy_key.id}/enable",
            expected={201},
        )
        journal.record("enable-destination-deploy-key", outcome="enabled", status=response.status)
    except AmbiguousMutation:
        journal.record("enable-destination-deploy-key", outcome="response-lost")
    keys = client.list_all(f"/projects/{project_id}/deploy_keys")
    matches = [key for key in keys if key.get("id") == fixture.deploy_key.id]
    if len(keys) != 1 or len(matches) != 1:
        raise LifecycleError("the exact deploy key was not exclusively enabled on the destination")
    key = matches[0]
    normalised = " ".join(str(key.get("key", "")).split()[:2])
    if key.get("title") != fixture.deploy_key.title or normalised != public_key:
        raise LifecycleError("the enabled destination deploy key differs from the fixture")
    try:
        response = client.request(
            "PUT",
            f"/projects/{project_id}/deploy_keys/{fixture.deploy_key.id}",
            body={"title": fixture.deploy_key.title, "can_push": True},
            expected={200},
        )
        journal.record(
            "grant-destination-key-write", outcome="configured", status=response.status
        )
    except AmbiguousMutation:
        journal.record("grant-destination-key-write", outcome="response-lost")
    validate_destination_key(client, fixture, project_id, can_push=True)


def disable_destination_key(
    client: GitLabClient,
    fixture: LifecycleFixture,
    project_id: int,
    journal: Journal,
) -> None:
    keys = client.list_all(f"/projects/{project_id}/deploy_keys")
    matches = [key for key in keys if key.get("id") == fixture.deploy_key.id]
    if not matches:
        journal.record("disable-destination-deploy-key", outcome="already-disabled")
        return
    if len(matches) != 1:
        raise LifecycleError("the destination contains duplicate reviewed deploy keys")
    key = matches[0]
    key_record = key.get("key")
    if key.get("title") != fixture.deploy_key.title or not isinstance(key_record, str):
        raise LifecycleError("the destination deploy key differs from the fixture")
    try:
        fingerprint = public_key_fingerprint(key_record)
    except LiveProviderError as error:
        raise LifecycleError(str(error)) from error
    if fingerprint != fixture.deploy_key.fingerprint:
        raise LifecycleError("the destination deploy-key fingerprint differs from the fixture")
    try:
        response = client.request(
            "DELETE",
            f"/projects/{project_id}/deploy_keys/{fixture.deploy_key.id}",
            expected={204},
        )
        journal.record("disable-destination-deploy-key", outcome="disabled", status=response.status)
    except AmbiguousMutation:
        journal.record("disable-destination-deploy-key", outcome="response-lost")
    remaining = client.list_all(f"/projects/{project_id}/deploy_keys")
    if any(key.get("id") == fixture.deploy_key.id for key in remaining):
        raise LifecycleError("destination deploy-key revocation could not be confirmed")


def reset_project(args: argparse.Namespace, client: GitLabClient) -> None:
    source_checkout = Path(__file__).resolve().parents[1]
    fixture = LifecycleFixture.read(
        private_metadata_path(
            args.fixture,
            label="Phase 3 fixture",
            checkout=source_checkout,
            must_exist=True,
        )
    )
    expected_confirmation = fixture.project.path_with_namespace
    if args.confirm_project_reset != expected_confirmation:
        raise LifecycleError(
            f"--confirm-project-reset must be exactly {expected_confirmation}"
        )
    wheel = inspect_wheel(args.wheel, args.expected_wheel_sha256)
    controller_commit = validate_controller_checkout(
        source_checkout,
        environment=dict(os.environ),
        git_executable="git",
    )
    public_key = validate_public_key(args.deploy_public_key, fixture)
    previous = None
    if args.previous_state:
        previous_path = private_metadata_path(
            args.previous_state,
            label="previous retained-state record",
            checkout=source_checkout,
            must_exist=True,
        )
        previous = RetainedState.read(previous_path)
    handoff_path = private_metadata_path(
        args.handoff,
        label="reset handoff",
        checkout=source_checkout,
        must_exist=False,
    )
    audit_path = private_metadata_path(
        args.audit_report,
        label="reset audit report",
        checkout=source_checkout,
        must_exist=False,
    )
    journal = Journal([])
    started = utc_now()
    group_preflight(client, fixture)
    project = project_value(client, fixture)
    previous_id: int | None = None
    before = "absent"
    if project is not None:
        if previous is None:
            raise LifecycleError(
                "the destination exists but no exact retained-state record was supplied"
            )
        snapshot = project_snapshot(client, fixture, project)
        validate_retained(snapshot, fixture, previous)
        previous_id = snapshot.project_id
        before = "exact-retained"
        print(f"Provider:       {fixture.ssh_host}")
        print(f"Project reset: {fixture.project.path_with_namespace}")
        print(f"Current state: exact retained project {previous_id} at {previous.head}")
        print("Mutations:     delete, create private project, disable features, enable key")
        print(f"Handoff:       {handoff_path}")
        print(f"Audit report:  {audit_path}")
        delete_exact_project(client, fixture, project, journal)
    elif previous is not None:
        raise LifecycleError("the retained-state record exists but the project is absent")
    else:
        print(f"Provider:       {fixture.ssh_host}")
        print(f"Project reset: {fixture.project.path_with_namespace}")
        print("Current state: project absent")
        print("Mutations:     create private project, disable features, enable key")
        print(f"Handoff:       {handoff_path}")
        print(f"Audit report:  {audit_path}")
    created = create_exact_project(
        client,
        fixture,
        previous_id=previous_id,
        created_after=datetime.fromisoformat(started),
        journal=journal,
    )
    project_id = validate_project_identity(created, fixture, expected_id=None)
    empty_snapshot = project_snapshot(client, fixture, created)
    validate_no_project_content(empty_snapshot)
    try:
        validate_refs(empty_snapshot.refs, expected_head=None)
    except StateError as error:
        raise LifecycleError(str(error)) from error
    key_may_be_enabled = False
    try:
        key_may_be_enabled = True
        enable_destination_key(client, fixture, project_id, public_key, journal)
        completed = datetime.now(timezone.utc).replace(microsecond=0)
        handoff = ResetHandoff(
            schema=1,
            run_id=str(uuid.uuid4()),
            provider="surrey",
            project_id=project_id,
            path_with_namespace=fixture.project.path_with_namespace,
            repository_empty=True,
            deploy_key_id=fixture.deploy_key.id,
            deploy_key_fingerprint=fixture.deploy_key.fingerprint,
            source_commit=fixture.template.commit,
            source_refs_digest=fixture.template.refs_digest,
            candidate_version=wheel.version,
            wheel_sha256=wheel.sha256,
            controller_commit=controller_commit,
            completed_at_utc=completed.isoformat(),
            expires_at_utc=(completed + timedelta(minutes=30)).isoformat(),
        )
        handoff.validate(now=completed)
        audit = {
            "schema": 1,
            "passed": True,
            "phase": "reset",
            "provider": "surrey",
            "project_id": project_id,
            "path_with_namespace": fixture.project.path_with_namespace,
            "before": before,
            "after": "empty-private-write-key-enabled",
            "controller_commit": controller_commit,
            "candidate_version": wheel.version,
            "wheel_sha256": wheel.sha256,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "operations": journal.operations,
            "handoff_sha256": canonical_sha256(handoff.document()),
        }
        write_private_json(handoff_path, handoff.document())
        write_private_json(audit_path, audit)
        key_may_be_enabled = False
    except Exception:
        if key_may_be_enabled:
            disable_destination_key(client, fixture, project_id, journal)
        raise
    print(f"Phase 3 reset ready: {fixture.project.path_with_namespace}")
    print(f"Candidate handoff: {handoff_path}")


def phase_two_report(path: Path, handoff: ResetHandoff) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LifecycleError(f"could not read the candidate report: {error}") from error
    if not isinstance(value, dict) or set(value) != PHASE_TWO_REPORT_KEYS:
        raise LifecycleError("the candidate report does not match the closed Phase 3 schema")
    if value.get("passed") is not True:
        raise LifecycleError("the candidate report did not pass")
    if (
        value.get("provider") != "surrey"
        or value.get("repository") != SURREY_PATH
        or value.get("candidate_version") != handoff.candidate_version
        or value.get("wheel_sha256") != handoff.wheel_sha256
        or value.get("source_refs_unchanged") is not True
        or value.get("source_refs_digest") != handoff.source_refs_digest
        or value.get("destination_transition") != "empty -> refs/heads/main"
        or value.get("manual_provider_review_required") is not False
        or value.get("architecture") != "arm64"
    ):
        raise LifecycleError("the candidate report differs from the reset handoff")
    paths: list[dict[str, Any]] = []
    for name in ("path_one", "path_two"):
        result = value.get(name)
        if not isinstance(result, dict) or set(result) != PATH_RESULT_KEYS:
            raise LifecycleError(f"the candidate report contains an invalid {name}")
        if result.get("clean_tree") is not True:
            raise LifecycleError(f"the candidate report did not finish {name} cleanly")
        stages = result.get("applied_stages")
        if not isinstance(stages, list) or not all(
            isinstance(stage, str) for stage in stages
        ):
            raise LifecycleError(f"the candidate report contains invalid stages for {name}")
        paths.append(result)
    if (
        paths[0].get("commit") != paths[1].get("commit")
        or paths[0].get("tree") != paths[1].get("tree")
    ):
        raise LifecycleError("the two candidate paths produced different repository state")
    if (
        paths[0].get("name") != "path-one"
        or paths[0].get("configured_source") != ""
        or paths[0].get("configured_history") != ""
        or paths[0]["applied_stages"].count("first-push") != 1
    ):
        raise LifecycleError("the candidate report does not prove the empty-repository path")
    if (
        paths[1].get("name") != "path-two"
        or paths[1].get("configured_source") != SURREY_PATH
        or paths[1].get("configured_history") != "keep"
        or "first-push" in paths[1]["applied_stages"]
    ):
        raise LifecycleError("the candidate report does not prove the existing-repository path")
    return value


def verify_and_seal(args: argparse.Namespace, client: GitLabClient) -> None:
    source_checkout = Path(__file__).resolve().parents[1]
    fixture = LifecycleFixture.read(
        private_metadata_path(
            args.fixture,
            label="Phase 3 fixture",
            checkout=source_checkout,
            must_exist=True,
        )
    )
    handoff = ResetHandoff.read(
        private_metadata_path(
            args.handoff,
            label="reset handoff",
            checkout=source_checkout,
            must_exist=True,
        )
    )
    controller_commit = validate_controller_checkout(
        source_checkout,
        environment=dict(os.environ),
        git_executable="git",
    )
    if (
        handoff.provider != fixture.provider
        or handoff.path_with_namespace != fixture.project.path_with_namespace
        or handoff.deploy_key_id != fixture.deploy_key.id
        or handoff.deploy_key_fingerprint != fixture.deploy_key.fingerprint
        or handoff.source_commit != fixture.template.commit
        or handoff.source_refs_digest != fixture.template.refs_digest
        or handoff.controller_commit != controller_commit
    ):
        raise LifecycleError("the reset handoff differs from this trusted controller run")
    candidate_path = private_metadata_path(
        args.candidate_report,
        label="candidate report",
        checkout=source_checkout,
        must_exist=True,
    )
    retained_path = private_metadata_path(
        args.retained_state,
        label="retained state",
        checkout=source_checkout,
        must_exist=False,
    )
    audit_path = private_metadata_path(
        args.audit_report,
        label="seal audit report",
        checkout=source_checkout,
        must_exist=False,
    )
    project = project_value(client, fixture)
    if project is None:
        raise LifecycleError("the candidate destination project disappeared")
    validate_project_identity(project, fixture, expected_id=handoff.project_id)
    journal = Journal([])
    try:
        report = phase_two_report(candidate_path, handoff)
        group_preflight(client, fixture)
        snapshot = project_snapshot(client, fixture, project)
        validate_no_project_content(
            snapshot,
            allowed_deploy_key_id=fixture.deploy_key.id,
        )
        validate_destination_key(
            client,
            fixture,
            handoff.project_id,
            can_push=True,
        )
        commit = report["path_one"]["commit"]
        try:
            validate_refs(snapshot.refs, expected_head=commit)
        except StateError as error:
            raise LifecycleError(str(error)) from error
        provider_refs = validate_destination_refs(
            snapshot.refs,
            fixture=_phase_two_fixture(fixture),
            expected_commit=commit,
        )
        if sorted(report["provider_created_refs"]) != list(provider_refs):
            raise LifecycleError("the candidate and provider pipeline refs differ")
    except Exception:
        disable_destination_key(client, fixture, handoff.project_id, journal)
        raise
    disable_destination_key(client, fixture, handoff.project_id, journal)
    # Re-read the provider after the protective mutation. The retained record
    # is written only from this sealed state, never from the candidate report.
    sealed_project = project_value(client, fixture)
    if sealed_project is None:
        raise LifecycleError("the verified project disappeared while it was being sealed")
    snapshot = project_snapshot(client, fixture, sealed_project)
    validate_project_identity(snapshot.project, fixture, expected_id=handoff.project_id)
    validate_no_project_content(snapshot)
    if any(key.get("id") == fixture.deploy_key.id for key in snapshot.deploy_keys):
        raise LifecycleError("the destination write key remains enabled after sealing")
    sealed = RetainedState(
        schema=1,
        provider="surrey",
        project_id=handoff.project_id,
        path_with_namespace=fixture.project.path_with_namespace,
        visibility="private",
        head=commit,
        tree=report["path_one"]["tree"],
        refs=snapshot.refs,
        destination_deploy_key_enabled=False,
        source_refs_digest=handoff.source_refs_digest,
        candidate_version=handoff.candidate_version,
        wheel_sha256=handoff.wheel_sha256,
        sealed_at_utc=utc_now(),
    )
    sealed.validate()
    audit = {
        "schema": 1,
        "passed": True,
        "phase": "verify-and-seal",
        "provider": "surrey",
        "project_id": handoff.project_id,
        "path_with_namespace": fixture.project.path_with_namespace,
        "before": "populated-private-write-key-enabled",
        "after": "retained-private-write-key-disabled",
        "head": sealed.head,
        "tree": sealed.tree,
        "refs": sealed.refs,
        "controller_commit": controller_commit,
        "candidate_version": sealed.candidate_version,
        "wheel_sha256": sealed.wheel_sha256,
        "source_refs_digest": sealed.source_refs_digest,
        "source_refs_unchanged": True,
        "destination_deploy_key_enabled": False,
        "finished_at_utc": utc_now(),
        "operations": journal.operations,
        "retained_state_sha256": canonical_sha256(sealed.document()),
    }
    write_private_json(retained_path, sealed.document())
    write_private_json(audit_path, audit)
    print(f"Phase 3 verified and sealed: {fixture.project.path_with_namespace}")
    print(f"Retained state: {retained_path}")


def _phase_two_fixture(fixture: LifecycleFixture) -> Any:
    """Build the narrow attributes needed by Phase 2 ref validation."""

    return type(
        "RefFixture",
        (),
        {
            "provider": fixture.provider,
            "destination_remote": fixture.destination_remote,
        },
    )()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Reset or seal the exact Surrey Bootstrap live-provider project"
    )
    subparsers = result.add_subparsers(dest="command", required=True)
    reset = subparsers.add_parser("reset")
    reset.add_argument("--fixture", required=True, type=Path)
    reset.add_argument("--previous-state", type=Path)
    reset.add_argument("--deploy-public-key", required=True, type=Path)
    reset.add_argument("--wheel", required=True, type=Path)
    reset.add_argument("--expected-wheel-sha256", required=True)
    reset.add_argument("--handoff", required=True, type=Path)
    reset.add_argument("--audit-report", required=True, type=Path)
    reset.add_argument("--token-fd", type=int, default=0)
    reset.add_argument("--confirm-project-reset", required=True)
    seal = subparsers.add_parser("verify-and-seal")
    seal.add_argument("--fixture", required=True, type=Path)
    seal.add_argument("--handoff", required=True, type=Path)
    seal.add_argument("--candidate-report", required=True, type=Path)
    seal.add_argument("--retained-state", required=True, type=Path)
    seal.add_argument("--audit-report", required=True, type=Path)
    seal.add_argument("--token-fd", type=int, default=0)
    return result


def sanitised_failure(message: str, args: argparse.Namespace) -> str:
    """Remove private input and output paths from one retained error message."""

    cleaned = message
    for name in (
        "fixture",
        "previous_state",
        "deploy_public_key",
        "wheel",
        "handoff",
        "candidate_report",
        "retained_state",
        "audit_report",
    ):
        value = getattr(args, name, None)
        if isinstance(value, Path):
            for form in {str(value), str(value.expanduser().resolve())}:
                cleaned = cleaned.replace(form, f"<{name.replace('_', '-')}>")
    cleaned = cleaned.replace(str(Path.home()), "<home>")
    return cleaned[:1000]


def write_failure_audit(args: argparse.Namespace, error: BaseException) -> None:
    """Best-effort private audit for a failed trusted lifecycle boundary."""

    audit = getattr(args, "audit_report", None)
    if not isinstance(audit, Path):
        return
    checkout = Path(__file__).resolve().parents[1]
    try:
        path = private_metadata_path(
            audit,
            label="failure audit report",
            checkout=checkout,
            must_exist=False,
        )
        write_private_json(
            path,
            {
                "schema": 1,
                "passed": False,
                "phase": args.command,
                "provider": "surrey",
                "path_with_namespace": SURREY_PATH,
                "failure": sanitised_failure(str(error), args),
                "finished_at_utc": utc_now(),
            },
        )
    except (LifecycleError, LiveProviderError, OSError, StateError, ValueError):
        # The original failure remains authoritative. Never obscure it with a
        # secondary report-path or filesystem problem.
        return


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    client: GitLabClient | None = None
    try:
        validate_no_inherited_credentials()
        token = token_from_fd(args.token_fd)
        checkout = Path(__file__).resolve().parents[1]
        fixture_path = private_metadata_path(
            args.fixture,
            label="Phase 3 fixture",
            checkout=checkout,
            must_exist=True,
        )
        args.fixture = fixture_path
        fixture = LifecycleFixture.read(fixture_path)
        with exclusive_run_lock(fixture_path):
            client = GitLabClient(api_base=fixture.api_base, token=token)
            if args.command == "reset":
                reset_project(args, client)
            else:
                verify_and_seal(args, client)
    except (LifecycleError, StateError, LiveProviderError, OSError, ValueError) as error:
        write_failure_audit(args, error)
        fail(str(error))
    finally:
        if client is not None:
            client.close()


def fail(message: str) -> NoReturn:
    print(f"live-provider Phase 3 failed: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()

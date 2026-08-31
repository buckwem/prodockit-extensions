# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Closed, non-secret state contracts for Bootstrap live-provider testing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
FINGERPRINT_RE = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")
PIPELINE_REF_RE = re.compile(r"refs/pipelines/[1-9][0-9]*")
SURREY_API_BASE = "https://gitlab.surrey.ac.uk/api/v4"
SURREY_HOST = "gitlab.surrey.ac.uk"
SURREY_GROUP = "assessment-liveprovider-2026"
SURREY_PROJECT = "report-liveprovider-2026-mb0105"
SURREY_PATH = f"{SURREY_GROUP}/{SURREY_PROJECT}"
SURREY_TEMPLATE = "mb0105/prodockit-template"
SURREY_TEMPLATE_REMOTE = f"git@{SURREY_HOST}:{SURREY_TEMPLATE}.git"
SURREY_DEPLOY_KEY_TITLE = "prodockit-liveprovider-deploy-key"
SURREY_DEPLOY_KEY_FINGERPRINT = (
    "SHA256:Nb3d24rFvoUY7qzFfRK2TSSs3nNjg3hIFGblNcGdYBQ"
)


class StateError(RuntimeError):
    """A live-provider state document is missing, ambiguous or unsafe."""


def _object(value: Any, *, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError(f"{label} must be one JSON object")
    missing = keys - set(value)
    unknown = set(value) - keys
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown {', '.join(sorted(unknown))}")
        raise StateError(f"invalid {label}: " + "; ".join(details))
    return cast(dict[str, Any], value)


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or any(character in value for character in "\0\r\n"):
        raise StateError(f"{label} must be non-empty single-line text")
    return value


def _positive_id(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StateError(f"{label} must be a positive integer")
    return value


def _sha256(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if not SHA256_RE.fullmatch(text):
        raise StateError(f"{label} must be 64 lowercase hexadecimal characters")
    return text


def _object_id(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if not OBJECT_ID_RE.fullmatch(text):
        raise StateError(f"{label} must be one complete lowercase Git object ID")
    return text


def _utc(value: Any, *, label: str) -> datetime:
    value = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise StateError(f"{label} must use UTC")
    return parsed


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StateError(f"could not read {label}: {error}") from error


def write_private_json(path: Path, value: Any) -> None:
    """Atomically write one private state document with mode 0600."""
    path = path.expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class GroupFixture:
    id: int
    full_path: str


@dataclass(frozen=True)
class ProjectFixture:
    name: str
    path_with_namespace: str
    visibility: str


@dataclass(frozen=True)
class TemplateFixture:
    id: int
    path_with_namespace: str
    ssh_url: str
    commit: str
    refs_digest: str


@dataclass(frozen=True)
class DeployKeyFixture:
    id: int
    title: str
    fingerprint: str


@dataclass(frozen=True)
class LifecycleFixture:
    schema: int
    provider: str
    api_base: str
    ssh_host: str
    group: GroupFixture
    project: ProjectFixture
    template: TemplateFixture
    deploy_key: DeployKeyFixture

    @property
    def destination_remote(self) -> str:
        return f"git@{self.ssh_host}:{self.project.path_with_namespace}.git"

    @classmethod
    def read(cls, path: Path) -> LifecycleFixture:
        value = _object(
            read_json(path, label="Phase 3 fixture"),
            label="Phase 3 fixture",
            keys={
                "schema",
                "provider",
                "api_base",
                "ssh_host",
                "group",
                "project",
                "template",
                "deploy_key",
            },
        )
        group = _object(value["group"], label="fixture group", keys={"id", "full_path"})
        project = _object(
            value["project"],
            label="fixture project",
            keys={"name", "path_with_namespace", "visibility"},
        )
        template = _object(
            value["template"],
            label="fixture template",
            keys={"id", "path_with_namespace", "ssh_url", "commit", "refs_digest"},
        )
        key = _object(
            value["deploy_key"],
            label="fixture deploy key",
            keys={"id", "title", "fingerprint"},
        )
        fixture = cls(
            schema=value["schema"],
            provider=value["provider"],
            api_base=value["api_base"],
            ssh_host=value["ssh_host"],
            group=GroupFixture(
                id=_positive_id(group["id"], label="group.id"),
                full_path=_text(group["full_path"], label="group.full_path"),
            ),
            project=ProjectFixture(
                name=_text(project["name"], label="project.name"),
                path_with_namespace=_text(
                    project["path_with_namespace"], label="project.path_with_namespace"
                ),
                visibility=_text(project["visibility"], label="project.visibility"),
            ),
            template=TemplateFixture(
                id=_positive_id(template["id"], label="template.id"),
                path_with_namespace=_text(
                    template["path_with_namespace"], label="template.path_with_namespace"
                ),
                ssh_url=_text(template["ssh_url"], label="template.ssh_url"),
                commit=_object_id(template["commit"], label="template.commit"),
                refs_digest=_sha256(template["refs_digest"], label="template.refs_digest"),
            ),
            deploy_key=DeployKeyFixture(
                id=_positive_id(key["id"], label="deploy_key.id"),
                title=_text(key["title"], label="deploy_key.title"),
                fingerprint=_text(key["fingerprint"], label="deploy_key.fingerprint"),
            ),
        )
        fixture.validate()
        return fixture

    def validate(self) -> None:
        if self.schema != 3:
            raise StateError("the Phase 3 fixture schema must be 3")
        if self.provider != "surrey":
            raise StateError("Phase 3 currently supports only the Surrey provider")
        if self.api_base != SURREY_API_BASE:
            raise StateError(f"the Surrey API base must be exactly {SURREY_API_BASE}")
        parsed = urlparse(self.api_base)
        if parsed.scheme != "https" or parsed.hostname != SURREY_HOST:
            raise StateError("the Phase 3 API must use HTTPS on the exact Surrey host")
        if self.ssh_host != SURREY_HOST:
            raise StateError(f"the Surrey SSH host must be exactly {SURREY_HOST}")
        if self.group.full_path != SURREY_GROUP:
            raise StateError(f"the Surrey group must be exactly {SURREY_GROUP}")
        if (
            self.project.name != SURREY_PROJECT
            or self.project.path_with_namespace != SURREY_PATH
            or self.project.visibility != "private"
        ):
            raise StateError(
                "the Surrey project must derive from account mb0105, course liveprovider, "
                "First assessment, year 2026"
            )
        if (
            self.template.path_with_namespace != SURREY_TEMPLATE
            or self.template.ssh_url != SURREY_TEMPLATE_REMOTE
        ):
            raise StateError("the Surrey template must be the reviewed mb0105 template")
        if self.deploy_key.title != SURREY_DEPLOY_KEY_TITLE:
            raise StateError(f"the deploy-key title must be {SURREY_DEPLOY_KEY_TITLE}")
        if (
            not FINGERPRINT_RE.fullmatch(self.deploy_key.fingerprint)
            or self.deploy_key.fingerprint != SURREY_DEPLOY_KEY_FINGERPRINT
        ):
            raise StateError("the deploy-key fingerprint is not the reviewed Phase 3 key")


@dataclass(frozen=True)
class RetainedState:
    schema: int
    provider: str
    project_id: int
    path_with_namespace: str
    visibility: str
    head: str
    tree: str
    refs: dict[str, str]
    destination_deploy_key_enabled: bool
    source_refs_digest: str
    candidate_version: str
    wheel_sha256: str
    sealed_at_utc: str

    @classmethod
    def read(cls, path: Path) -> RetainedState:
        value = _object(
            read_json(path, label="retained state"),
            label="retained state",
            keys={
                "schema",
                "provider",
                "project_id",
                "path_with_namespace",
                "visibility",
                "head",
                "tree",
                "refs",
                "destination_deploy_key_enabled",
                "source_refs_digest",
                "candidate_version",
                "wheel_sha256",
                "sealed_at_utc",
            },
        )
        refs_value = value["refs"]
        if not isinstance(refs_value, dict) or not refs_value:
            raise StateError("retained refs must be a non-empty JSON object")
        refs: dict[str, str] = {}
        for name, object_id in refs_value.items():
            refs[_text(name, label="retained ref name")] = _object_id(
                object_id, label=f"retained ref {name}"
            )
        state = cls(
            schema=value["schema"],
            provider=value["provider"],
            project_id=_positive_id(value["project_id"], label="project_id"),
            path_with_namespace=_text(
                value["path_with_namespace"], label="path_with_namespace"
            ),
            visibility=_text(value["visibility"], label="visibility"),
            head=_object_id(value["head"], label="head"),
            tree=_object_id(value["tree"], label="tree"),
            refs=refs,
            destination_deploy_key_enabled=value["destination_deploy_key_enabled"],
            source_refs_digest=_sha256(
                value["source_refs_digest"], label="source_refs_digest"
            ),
            candidate_version=_text(value["candidate_version"], label="candidate_version"),
            wheel_sha256=_sha256(value["wheel_sha256"], label="wheel_sha256"),
            sealed_at_utc=_text(value["sealed_at_utc"], label="sealed_at_utc"),
        )
        state.validate()
        return state

    def validate(self) -> None:
        if self.schema != 1 or self.provider != "surrey":
            raise StateError("the retained state must be Surrey schema 1")
        if self.path_with_namespace != SURREY_PATH or self.visibility != "private":
            raise StateError("the retained state identifies another project")
        if not isinstance(self.destination_deploy_key_enabled, bool):
            raise StateError("destination_deploy_key_enabled must be Boolean")
        if self.destination_deploy_key_enabled:
            raise StateError("retained state must record the destination write key as disabled")
        if self.refs.get("refs/heads/main") != self.head:
            raise StateError("retained main must point to the retained head")
        for name, object_id in self.refs.items():
            if name != "refs/heads/main" and not PIPELINE_REF_RE.fullmatch(name):
                raise StateError(f"retained state contains unexpected ref {name}")
            if object_id != self.head:
                raise StateError(f"retained ref {name} does not point to the retained head")
        _utc(self.sealed_at_utc, label="sealed_at_utc")

    def document(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResetHandoff:
    schema: int
    run_id: str
    provider: str
    project_id: int
    path_with_namespace: str
    repository_empty: bool
    deploy_key_id: int
    deploy_key_fingerprint: str
    source_commit: str
    source_refs_digest: str
    candidate_version: str
    wheel_sha256: str
    controller_commit: str
    completed_at_utc: str
    expires_at_utc: str

    @classmethod
    def read(cls, path: Path, *, now: datetime | None = None) -> ResetHandoff:
        value = _object(
            read_json(path, label="reset handoff"),
            label="reset handoff",
            keys={
                "schema",
                "run_id",
                "provider",
                "project_id",
                "path_with_namespace",
                "repository_empty",
                "deploy_key_id",
                "deploy_key_fingerprint",
                "source_commit",
                "source_refs_digest",
                "candidate_version",
                "wheel_sha256",
                "controller_commit",
                "completed_at_utc",
                "expires_at_utc",
            },
        )
        handoff = cls(
            schema=value["schema"],
            run_id=_text(value["run_id"], label="run_id"),
            provider=value["provider"],
            project_id=_positive_id(value["project_id"], label="project_id"),
            path_with_namespace=_text(
                value["path_with_namespace"], label="path_with_namespace"
            ),
            repository_empty=value["repository_empty"],
            deploy_key_id=_positive_id(value["deploy_key_id"], label="deploy_key_id"),
            deploy_key_fingerprint=_text(
                value["deploy_key_fingerprint"], label="deploy_key_fingerprint"
            ),
            source_commit=_object_id(value["source_commit"], label="source_commit"),
            source_refs_digest=_sha256(
                value["source_refs_digest"], label="source_refs_digest"
            ),
            candidate_version=_text(value["candidate_version"], label="candidate_version"),
            wheel_sha256=_sha256(value["wheel_sha256"], label="wheel_sha256"),
            controller_commit=_object_id(
                value["controller_commit"], label="controller_commit"
            ),
            completed_at_utc=_text(value["completed_at_utc"], label="completed_at_utc"),
            expires_at_utc=_text(value["expires_at_utc"], label="expires_at_utc"),
        )
        handoff.validate(now=now)
        return handoff

    def validate(self, *, now: datetime | None = None) -> None:
        if self.schema != 1 or self.provider != "surrey":
            raise StateError("the reset handoff must be Surrey schema 1")
        if self.path_with_namespace != SURREY_PATH:
            raise StateError("the reset handoff identifies another project")
        if self.repository_empty is not True:
            raise StateError("the reset handoff does not prove an empty repository")
        if self.deploy_key_fingerprint != SURREY_DEPLOY_KEY_FINGERPRINT:
            raise StateError("the reset handoff identifies another deploy key")
        try:
            uuid.UUID(self.run_id)
        except (ValueError, AttributeError) as error:
            raise StateError("run_id must be a UUID") from error
        completed = _utc(self.completed_at_utc, label="completed_at_utc")
        expires = _utc(self.expires_at_utc, label="expires_at_utc")
        if expires <= completed or (expires - completed).total_seconds() > 30 * 60:
            raise StateError("the reset handoff validity window must be at most 30 minutes")
        observed_now = now or datetime.now(timezone.utc)
        if observed_now >= expires:
            raise StateError("the reset handoff has expired")

    def document(self) -> dict[str, Any]:
        return asdict(self)


def validate_refs(refs: dict[str, str], *, expected_head: str | None) -> None:
    if expected_head is None:
        if refs:
            raise StateError("the recreated destination repository is not empty")
        return
    if refs.get("refs/heads/main") != expected_head:
        raise StateError("destination main does not match the expected retained head")
    for name, object_id in refs.items():
        if name != "refs/heads/main" and not PIPELINE_REF_RE.fullmatch(name):
            raise StateError(f"destination contains unexpected ref {name}")
        if object_id != expected_head:
            raise StateError(f"destination ref {name} does not point to the expected head")

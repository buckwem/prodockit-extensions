# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Closed evidence contracts for the protected live-provider release gate."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from live_provider_state import StateError, canonical_sha256, read_json

OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PIPELINE_REF_RE = re.compile(r"refs/pipelines/[1-9][0-9]*")
RELEASE_REPOSITORY = "buckwem/prodockit-extensions"
PROVIDER_DESTINATIONS = {
    "github": "prodockit-live-tests/bootstrap-release-gate",
    "surrey": "assessment-liveprovider-2026/report-liveprovider-2026-mb0105",
}
MAX_RESULT_AGE = timedelta(hours=24)
MAX_RUN_DURATION = timedelta(hours=2)


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
    if not isinstance(value, str) or not value or any(c in value for c in "\0\r\n"):
        raise StateError(f"{label} must be non-empty single-line text")
    return value


def _nullable_text(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label=label)


def _positive_id(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StateError(f"{label} must be a positive integer")
    return value


def _object_id(value: Any, *, label: str) -> str:
    value = _text(value, label=label)
    if not OBJECT_ID_RE.fullmatch(value):
        raise StateError(f"{label} must be one complete lowercase Git object ID")
    return value


def _sha256(value: Any, *, label: str) -> str:
    value = _text(value, label=label)
    if not SHA256_RE.fullmatch(value):
        raise StateError(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def _utc(value: Any, *, label: str) -> datetime:
    value = _text(value, label=label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateError(f"{label} must be an ISO-8601 timestamp") from error
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise StateError(f"{label} must use UTC")
    return result


@dataclass(frozen=True)
class ProviderPathResult:
    """One Bootstrap repository path exercised by a provider run."""

    name: str
    configured_source: str | None
    configured_history: str | None
    applied_stages: tuple[str, ...]
    commit: str
    tree: str
    clean_tree: bool

    @classmethod
    def parse(cls, value: Any, *, label: str) -> ProviderPathResult:
        value = _object(
            value,
            label=label,
            keys={
                "name",
                "configured_source",
                "configured_history",
                "applied_stages",
                "commit",
                "tree",
                "clean_tree",
            },
        )
        stages = value["applied_stages"]
        if not isinstance(stages, list) or any(not isinstance(item, str) for item in stages):
            raise StateError(f"{label}.applied_stages must be a list of stage names")
        if len(stages) != len(set(stages)):
            raise StateError(f"{label}.applied_stages repeats a stage")
        return cls(
            name=_text(value["name"], label=f"{label}.name"),
            configured_source=_nullable_text(
                value["configured_source"], label=f"{label}.configured_source"
            ),
            configured_history=_nullable_text(
                value["configured_history"], label=f"{label}.configured_history"
            ),
            applied_stages=tuple(stages),
            commit=_object_id(value["commit"], label=f"{label}.commit"),
            tree=_object_id(value["tree"], label=f"{label}.tree"),
            clean_tree=value["clean_tree"],
        )

    def document(self) -> dict[str, Any]:
        value = asdict(self)
        value["applied_stages"] = list(self.applied_stages)
        return value


@dataclass(frozen=True)
class ProviderGateResult:
    """The complete, non-secret result from one protected provider workflow."""

    schema: int
    passed: bool
    provider: str
    release_repository: str
    release_commit: str
    candidate_version: str
    wheel_sha256: str
    wheel_contents_sha256: str
    controller_commit: str
    repository: str
    project_id: int
    path_one: ProviderPathResult
    path_two: ProviderPathResult
    source_commit: str
    source_refs_digest: str
    source_refs_unchanged: bool
    destination_refs: dict[str, str]
    destination_deploy_key_enabled: bool
    workflow_run_id: int
    workflow_url: str
    started_at_utc: str
    finished_at_utc: str

    @classmethod
    def read(cls, path: Path, *, now: datetime | None = None) -> ProviderGateResult:
        value = _object(
            read_json(path, label="provider gate result"),
            label="provider gate result",
            keys={
                "schema",
                "passed",
                "provider",
                "release_repository",
                "release_commit",
                "candidate_version",
                "wheel_sha256",
                "wheel_contents_sha256",
                "controller_commit",
                "repository",
                "project_id",
                "path_one",
                "path_two",
                "source_commit",
                "source_refs_digest",
                "source_refs_unchanged",
                "destination_refs",
                "destination_deploy_key_enabled",
                "workflow_run_id",
                "workflow_url",
                "started_at_utc",
                "finished_at_utc",
            },
        )
        refs_value = value["destination_refs"]
        if not isinstance(refs_value, dict) or not refs_value:
            raise StateError("destination_refs must be a non-empty JSON object")
        refs = {
            _text(name, label="destination ref name"): _object_id(
                object_id, label=f"destination ref {name}"
            )
            for name, object_id in refs_value.items()
        }
        result = cls(
            schema=value["schema"],
            passed=value["passed"],
            provider=_text(value["provider"], label="provider"),
            release_repository=_text(value["release_repository"], label="release_repository"),
            release_commit=_object_id(value["release_commit"], label="release_commit"),
            candidate_version=_text(value["candidate_version"], label="candidate_version"),
            wheel_sha256=_sha256(value["wheel_sha256"], label="wheel_sha256"),
            wheel_contents_sha256=_sha256(
                value["wheel_contents_sha256"], label="wheel_contents_sha256"
            ),
            controller_commit=_object_id(value["controller_commit"], label="controller_commit"),
            repository=_text(value["repository"], label="repository"),
            project_id=_positive_id(value["project_id"], label="project_id"),
            path_one=ProviderPathResult.parse(value["path_one"], label="path_one"),
            path_two=ProviderPathResult.parse(value["path_two"], label="path_two"),
            source_commit=_object_id(value["source_commit"], label="source_commit"),
            source_refs_digest=_sha256(value["source_refs_digest"], label="source_refs_digest"),
            source_refs_unchanged=value["source_refs_unchanged"],
            destination_refs=refs,
            destination_deploy_key_enabled=value["destination_deploy_key_enabled"],
            workflow_run_id=_positive_id(value["workflow_run_id"], label="workflow_run_id"),
            workflow_url=_text(value["workflow_url"], label="workflow_url"),
            started_at_utc=_text(value["started_at_utc"], label="started_at_utc"),
            finished_at_utc=_text(value["finished_at_utc"], label="finished_at_utc"),
        )
        result.validate(now=now)
        return result

    def validate(self, *, now: datetime | None = None) -> None:
        if self.schema != 1 or self.passed is not True:
            raise StateError("provider result must be a passing schema 1 result")
        if self.release_repository != RELEASE_REPOSITORY:
            raise StateError(f"release_repository must be exactly {RELEASE_REPOSITORY}")
        expected_destination = PROVIDER_DESTINATIONS.get(self.provider)
        if expected_destination is None or self.repository != expected_destination:
            raise StateError("provider result identifies an unapproved destination")
        if self.source_refs_unchanged is not True:
            raise StateError("provider result does not prove its template source stayed unchanged")
        if self.destination_deploy_key_enabled is not False:
            raise StateError("provider result does not prove the destination write key is disabled")
        if self.path_one.name != "path-one" or self.path_two.name != "path-two":
            raise StateError("provider result does not contain the two required paths")
        if (
            self.path_one.configured_source is not None
            or self.path_one.configured_history is not None
        ):
            raise StateError("path one did not start from an empty destination")
        if self.path_one.applied_stages.count("first-push") != 1:
            raise StateError("path one did not perform exactly one first push")
        if (
            self.path_two.configured_source != self.repository
            or self.path_two.configured_history != "keep"
            or "first-push" in self.path_two.applied_stages
        ):
            raise StateError("path two did not reuse the existing destination without pushing")
        for path in (self.path_one, self.path_two):
            if path.clean_tree is not True:
                raise StateError(f"{path.name} did not finish with a clean checkout")
        if self.path_one.commit != self.path_two.commit or self.path_one.tree != self.path_two.tree:
            raise StateError("the two provider paths produced different Git states")
        if self.destination_refs.get("refs/heads/main") != self.path_one.commit:
            raise StateError("destination main does not match the tested commit")
        for name, object_id in self.destination_refs.items():
            if name != "refs/heads/main" and not PIPELINE_REF_RE.fullmatch(name):
                raise StateError(f"destination contains unexpected ref {name}")
            if object_id != self.path_one.commit:
                raise StateError(f"destination ref {name} does not match tested main")

        parsed_url = urlparse(self.workflow_url)
        expected_host = "github.com" if self.provider == "github" else "gitlab.surrey.ac.uk"
        if parsed_url.scheme != "https" or parsed_url.hostname != expected_host:
            raise StateError("workflow_url does not use the selected provider's HTTPS host")
        if str(self.workflow_run_id) not in parsed_url.path:
            raise StateError("workflow_url does not identify workflow_run_id")

        started = _utc(self.started_at_utc, label="started_at_utc")
        finished = _utc(self.finished_at_utc, label="finished_at_utc")
        if finished < started or finished - started > MAX_RUN_DURATION:
            raise StateError("provider run duration is invalid or exceeds two hours")
        observed_now = now or datetime.now(timezone.utc)
        if finished > observed_now + timedelta(minutes=5):
            raise StateError("provider result is dated in the future")
        if observed_now - finished > MAX_RESULT_AGE:
            raise StateError("provider result is more than 24 hours old")

    def document(self) -> dict[str, Any]:
        value = asdict(self)
        value["path_one"] = self.path_one.document()
        value["path_two"] = self.path_two.document()
        return value

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document())

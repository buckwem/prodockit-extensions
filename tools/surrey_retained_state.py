# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Select and validate retained Surrey state from an exact GitHub workflow run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

from live_provider_state import SURREY_PATH, RetainedState, StateError, canonical_sha256

RELEASE_REPOSITORY = "buckwem/prodockit-extensions"
SURREY_WORKFLOW = ".github/workflows/bootstrap-live-provider-surrey.yml"
ARTIFACT_PREFIX = "surrey-retained-state-"
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}")
MAX_STATE_AGE = timedelta(days=90)
MAX_ARTIFACT_MEMBER_SIZE = 1024 * 1024


class RetainedStateError(RuntimeError):
    """A prior workflow run or retained-state envelope is not trustworthy."""


def _object(value: Any, *, label: str, keys: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RetainedStateError(f"{label} must be one JSON object")
    result = cast(dict[str, Any], value)
    if keys is not None:
        missing = keys - set(result)
        unknown = set(result) - keys
        if missing or unknown:
            details: list[str] = []
            if missing:
                details.append(f"missing {', '.join(sorted(missing))}")
            if unknown:
                details.append(f"unknown {', '.join(sorted(unknown))}")
            raise RetainedStateError(f"invalid {label}: " + "; ".join(details))
    return result


def _positive_id(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RetainedStateError(f"{label} must be a positive integer")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or any(char in value for char in "\0\r\n"):
        raise RetainedStateError(f"{label} must be non-empty single-line text")
    return value


def _commit(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if not OBJECT_ID_RE.fullmatch(result):
        raise RetainedStateError(f"{label} must be one full Git commit")
    return result


def _utc(value: Any, *, label: str) -> datetime:
    text = _text(value, label=label)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise RetainedStateError(f"{label} must be an ISO-8601 timestamp") from error
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise RetainedStateError(f"{label} must use UTC")
    return result


def workflow_runs(value: Any) -> list[dict[str, Any]]:
    """Flatten the pages returned by ``gh api --paginate --slurp``."""

    if not isinstance(value, list):
        raise RetainedStateError("workflow-run response must be a JSON list of pages")
    runs: list[dict[str, Any]] = []
    for index, page_value in enumerate(value):
        page = _object(page_value, label=f"workflow-run page {index + 1}")
        page_runs = page.get("workflow_runs")
        if not isinstance(page_runs, list):
            raise RetainedStateError(f"workflow-run page {index + 1} has no run list")
        runs.extend(_object(run, label=f"workflow-run page {index + 1} item") for run in page_runs)
    return runs


def _valid_prior_run(run: dict[str, Any], *, current_run_id: int) -> bool:
    repository = run.get("repository")
    return (
        isinstance(run.get("id"), int)
        and not isinstance(run.get("id"), bool)
        and 0 < run["id"] < current_run_id
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("run_attempt") == 1
        and run.get("head_branch") == "main"
        and run.get("path") == SURREY_WORKFLOW
        and isinstance(run.get("head_sha"), str)
        and bool(OBJECT_ID_RE.fullmatch(run["head_sha"]))
        and isinstance(repository, dict)
        and repository.get("full_name") == RELEASE_REPOSITORY
        and run.get("html_url")
        == f"https://github.com/{RELEASE_REPOSITORY}/actions/runs/{run['id']}"
    )


def select_prior_run(
    value: Any,
    *,
    current_run_id: int,
    override_run_id: int | None = None,
) -> int | None:
    """Select the newest successful prior run, or validate one explicit override."""

    candidates = candidate_prior_runs(value, current_run_id=current_run_id)
    if override_run_id is not None:
        matches = [run_id for run_id in candidates if run_id == override_run_id]
        if len(matches) != 1:
            raise RetainedStateError(
                "the requested previous Surrey run is not one successful prior run of the "
                "exact protected workflow"
            )
        return override_run_id
    if not candidates:
        return None
    return candidates[0]


def candidate_prior_runs(value: Any, *, current_run_id: int) -> tuple[int, ...]:
    """Return exact successful prior run IDs from newest to oldest."""

    candidates = [
        _positive_id(run["id"], label="workflow run id")
        for run in workflow_runs(value)
        if _valid_prior_run(run, current_run_id=current_run_id)
    ]
    return tuple(sorted(set(candidates), reverse=True))


def validate_recovery_run(
    value: Any,
    *,
    expected_run_id: int,
    expected_commit: str,
) -> None:
    """Require one completed, unsuccessful run of the exact Surrey workflow."""

    run = _object(value, label="recovery workflow run")
    repository = _object(run.get("repository"), label="recovery workflow repository")
    required = {
        "id": expected_run_id,
        "event": "workflow_dispatch",
        "status": "completed",
        "run_attempt": 1,
        "head_branch": "main",
        "head_sha": _commit(expected_commit, label="expected release commit"),
        "path": SURREY_WORKFLOW,
        "html_url": (
            f"https://github.com/{RELEASE_REPOSITORY}/actions/runs/{expected_run_id}"
        ),
    }
    for name, expected in required.items():
        if run.get(name) != expected:
            raise RetainedStateError(f"recovery workflow run has an unexpected {name}")
    if run.get("conclusion") not in {"cancelled", "failure", "timed_out"}:
        raise RetainedStateError("recovery is permitted only for an unsuccessful workflow run")
    if repository.get("full_name") != RELEASE_REPOSITORY:
        raise RetainedStateError("recovery workflow run belongs to another repository")


def validate_successful_run(value: Any, *, expected_run_id: int) -> tuple[str, int]:
    """Require one successful first attempt of the exact Surrey workflow."""

    run = _object(value, label="retained-state workflow run")
    repository = _object(run.get("repository"), label="retained-state workflow repository")
    required = {
        "id": expected_run_id,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "head_branch": "main",
        "path": SURREY_WORKFLOW,
        "html_url": (
            f"https://github.com/{RELEASE_REPOSITORY}/actions/runs/{expected_run_id}"
        ),
    }
    for name, expected in required.items():
        if run.get(name) != expected:
            raise RetainedStateError(f"retained-state workflow run has an unexpected {name}")
    if repository.get("full_name") != RELEASE_REPOSITORY:
        raise RetainedStateError("retained-state workflow run belongs to another repository")
    return _commit(run.get("head_sha"), label="retained-state workflow head_sha"), 1


@dataclass(frozen=True)
class RetainedStateEnvelope:
    """GitHub provenance attached to one closed Surrey retained-state document."""

    schema: int
    repository: str
    workflow_path: str
    run_id: int
    run_attempt: int
    release_commit: str
    artifact_name: str
    retained_state_sha256: str
    sealed_at_utc: str

    @classmethod
    def read(cls, path: Path) -> RetainedStateEnvelope:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RetainedStateError(f"could not read retained-state envelope: {error}") from error
        value = _object(
            value,
            label="retained-state envelope",
            keys={
                "schema",
                "repository",
                "workflow_path",
                "run_id",
                "run_attempt",
                "release_commit",
                "artifact_name",
                "retained_state_sha256",
                "sealed_at_utc",
            },
        )
        result = cls(
            schema=value["schema"],
            repository=_text(value["repository"], label="repository"),
            workflow_path=_text(value["workflow_path"], label="workflow_path"),
            run_id=_positive_id(value["run_id"], label="run_id"),
            run_attempt=_positive_id(value["run_attempt"], label="run_attempt"),
            release_commit=_commit(value["release_commit"], label="release_commit"),
            artifact_name=_text(value["artifact_name"], label="artifact_name"),
            retained_state_sha256=_text(
                value["retained_state_sha256"], label="retained_state_sha256"
            ),
            sealed_at_utc=_text(value["sealed_at_utc"], label="sealed_at_utc"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema != 1:
            raise RetainedStateError("retained-state envelope must use schema 1")
        if self.repository != RELEASE_REPOSITORY or self.workflow_path != SURREY_WORKFLOW:
            raise RetainedStateError("retained-state envelope identifies another workflow")
        if self.artifact_name != f"{ARTIFACT_PREFIX}{self.run_id}":
            raise RetainedStateError("retained-state envelope has an unexpected artifact name")
        if self.run_attempt != 1:
            raise RetainedStateError("retained-state envelope must come from the first run attempt")
        if not re.fullmatch(r"[0-9a-f]{64}", self.retained_state_sha256):
            raise RetainedStateError("retained_state_sha256 must be a SHA-256 digest")
        _utc(self.sealed_at_utc, label="sealed_at_utc")

    def document(self) -> dict[str, Any]:
        return asdict(self)


def validate_retained_artifact(
    *,
    state_path: Path,
    envelope_path: Path,
    expected_run_id: int,
    run_value: Any | None = None,
    now: datetime | None = None,
) -> RetainedState:
    """Validate one exact prior artifact and return its lifecycle state."""

    state_path = state_path.resolve()
    envelope_path = envelope_path.resolve()
    if state_path.parent != envelope_path.parent:
        raise RetainedStateError("retained-state artifact members must share one directory")
    expected_members = {"retained-state.json", "retained-state-envelope.json"}
    observed_members = {member.name for member in state_path.parent.iterdir()}
    if observed_members != expected_members:
        raise RetainedStateError("retained-state artifact has unexpected members")
    for member in (state_path, envelope_path):
        if member.is_symlink() or not member.is_file():
            raise RetainedStateError("retained-state artifact member is not a regular file")
        size = member.stat().st_size
        if size <= 0 or size > MAX_ARTIFACT_MEMBER_SIZE:
            raise RetainedStateError("retained-state artifact member has an invalid size")
    retained = RetainedState.read(state_path)
    envelope = RetainedStateEnvelope.read(envelope_path)
    if envelope.run_id != expected_run_id:
        raise RetainedStateError("retained-state artifact came from another workflow run")
    if envelope.retained_state_sha256 != canonical_sha256(retained.document()):
        raise RetainedStateError("retained-state artifact digest does not match its envelope")
    if run_value is not None:
        release_commit, run_attempt = validate_successful_run(
            run_value,
            expected_run_id=expected_run_id,
        )
        if (
            envelope.release_commit != release_commit
            or envelope.run_attempt != run_attempt
        ):
            raise RetainedStateError(
                "retained-state envelope differs from its immutable workflow run"
            )
    if envelope.sealed_at_utc != retained.sealed_at_utc:
        raise RetainedStateError("retained-state envelope and document have different seal times")
    sealed = _utc(retained.sealed_at_utc, label="sealed_at_utc")
    observed_now = now or datetime.now(timezone.utc)
    if sealed > observed_now + timedelta(minutes=5):
        raise RetainedStateError("retained state is dated in the future")
    if observed_now - sealed > MAX_STATE_AGE:
        raise RetainedStateError("retained state is more than 90 days old")
    if retained.path_with_namespace != SURREY_PATH:
        raise RetainedStateError("retained state identifies another Surrey project")
    return retained


def build_envelope(
    *,
    retained: RetainedState,
    run_id: int,
    run_attempt: int,
    release_commit: str,
) -> RetainedStateEnvelope:
    result = RetainedStateEnvelope(
        schema=1,
        repository=RELEASE_REPOSITORY,
        workflow_path=SURREY_WORKFLOW,
        run_id=_positive_id(run_id, label="run_id"),
        run_attempt=_positive_id(run_attempt, label="run_attempt"),
        release_commit=_commit(release_commit, label="release_commit"),
        artifact_name=f"{ARTIFACT_PREFIX}{run_id}",
        retained_state_sha256=canonical_sha256(retained.document()),
        sealed_at_utc=retained.sealed_at_utc,
    )
    result.validate()
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select-run")
    select.add_argument("--runs", required=True, type=Path)
    select.add_argument("--current-run-id", required=True, type=int)
    select.add_argument("--override-run-id", type=int)
    select.add_argument("--github-output", required=True, type=Path)
    validate = commands.add_parser("validate")
    validate.add_argument("--state", required=True, type=Path)
    validate.add_argument("--envelope", required=True, type=Path)
    validate.add_argument("--run-id", required=True, type=int)
    validate.add_argument("--run-document", type=Path)
    recovery = commands.add_parser("validate-recovery-run")
    recovery.add_argument("--document", required=True, type=Path)
    recovery.add_argument("--run-id", required=True, type=int)
    recovery.add_argument("--release-commit", required=True)
    create = commands.add_parser("create-envelope")
    create.add_argument("--state", required=True, type=Path)
    create.add_argument("--run-id", required=True, type=int)
    create.add_argument("--run-attempt", required=True, type=int)
    create.add_argument("--release-commit", required=True)
    create.add_argument("--output", required=True, type=Path)
    return result


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        if args.command == "select-run":
            value = json.loads(args.runs.read_text(encoding="utf-8"))
            selected = select_prior_run(
                value,
                current_run_id=args.current_run_id,
                override_run_id=args.override_run_id,
            )
            with args.github_output.open("a", encoding="utf-8") as output:
                candidates = (
                    (selected,)
                    if args.override_run_id is not None and selected is not None
                    else candidate_prior_runs(value, current_run_id=args.current_run_id)
                )
                print("run_ids=" + ",".join(str(run_id) for run_id in candidates), file=output)
        elif args.command == "validate":
            validate_retained_artifact(
                state_path=args.state,
                envelope_path=args.envelope,
                expected_run_id=args.run_id,
                run_value=(
                    json.loads(args.run_document.read_text(encoding="utf-8"))
                    if args.run_document is not None
                    else None
                ),
            )
        elif args.command == "validate-recovery-run":
            validate_recovery_run(
                json.loads(args.document.read_text(encoding="utf-8")),
                expected_run_id=args.run_id,
                expected_commit=args.release_commit,
            )
        else:
            retained = RetainedState.read(args.state)
            envelope = build_envelope(
                retained=retained,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                release_commit=args.release_commit,
            )
            if args.output.exists():
                raise RetainedStateError("retained-state envelope output already exists")
            args.output.write_text(
                json.dumps(envelope.document(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError, StateError, RetainedStateError) as error:
        fail(str(error))


def fail(message: str) -> NoReturn:
    print(f"Surrey retained-state validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()

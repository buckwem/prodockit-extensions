# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validate provider API responses used by the protected release coordinator."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from live_provider_state import read_json
from release_gate_state import RELEASE_REPOSITORY, SURREY_WORKFLOW_PROJECT

GITHUB_WORKFLOW = ".github/workflows/bootstrap-live-provider-github.yml"
ORDINARY_WORKFLOWS = frozenset(
    {
        ".github/workflows/adopt-install.yml",
        ".github/workflows/bootstrap-install.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/docs.yml",
        ".github/workflows/pdf-built-site-wheel.yml",
    }
)
GITHUB_URL = f"https://github.com/{RELEASE_REPOSITORY}"
SURREY_URL = f"https://gitlab.surrey.ac.uk/{SURREY_WORKFLOW_PROJECT}"
SURREY_RESULT_MEMBER = "surrey-provider-result/provider-result.json"
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}")
MAX_RESULT_SIZE = 1024 * 1024


class ProviderStatusError(RuntimeError):
    """Provider status cannot be trusted by the coordinator."""


def _object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderStatusError(f"{label} must be one JSON object")
    return cast(dict[str, Any], value)


def _list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProviderStatusError(f"{label} must be one JSON list")
    return value


def _positive_id(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProviderStatusError(f"{label} must be a positive integer")
    return value


def validate_github_run(
    value: Any,
    *,
    expected_run_id: int,
    expected_commit: str,
) -> None:
    """Require one successful immutable run of the exact provider workflow."""

    run = _object(value, label="GitHub workflow run")
    repository = _object(run.get("repository"), label="GitHub workflow repository")
    expected_url = f"{GITHUB_URL}/actions/runs/{expected_run_id}"
    required = {
        "id": expected_run_id,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": expected_commit,
        "path": GITHUB_WORKFLOW,
        "html_url": expected_url,
    }
    for name, expected in required.items():
        if run.get(name) != expected:
            raise ProviderStatusError(f"GitHub workflow run has an unexpected {name}")
    if repository.get("full_name") != RELEASE_REPOSITORY:
        raise ProviderStatusError("GitHub workflow run belongs to another repository")


def validate_ordinary_workflows(value: Any, *, expected_commit: str) -> None:
    """Require every ordinary release workflow to pass for the exact commit."""

    runs = _pages(value, item_key="workflow_runs", label="ordinary workflow runs")
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        path = run.get("path")
        identifier = run.get("id")
        if (
            path not in ORDINARY_WORKFLOWS
            or isinstance(identifier, bool)
            or not isinstance(identifier, int)
        ):
            continue
        previous = latest.get(path)
        if previous is None or identifier > previous["id"]:
            latest[path] = run

    missing = sorted(ORDINARY_WORKFLOWS - latest.keys())
    if missing:
        raise ProviderStatusError(
            "ordinary workflows are missing for the release commit: " + ", ".join(missing)
        )
    for path in sorted(ORDINARY_WORKFLOWS):
        run = latest[path]
        if (
            run.get("head_sha") != expected_commit
            or run.get("head_branch") != "main"
            or run.get("event") != "push"
        ):
            raise ProviderStatusError(f"ordinary workflow {path} is not an exact-commit push")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise ProviderStatusError(f"ordinary workflow {path} has not passed")


def _pages(value: Any, *, item_key: str, label: str) -> list[dict[str, Any]]:
    pages = _list(value, label=label)
    items: list[dict[str, Any]] = []
    for index, page_value in enumerate(pages):
        page = _object(page_value, label=f"{label} page {index + 1}")
        for item in _list(page.get(item_key), label=f"{label} page {index + 1}.{item_key}"):
            items.append(_object(item, label=f"{label} item"))
    return items


def _array_pages(value: Any, *, label: str) -> list[dict[str, Any]]:
    pages = _list(value, label=label)
    items: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        for item in _list(page, label=f"{label} page {index + 1}"):
            items.append(_object(item, label=f"{label} item"))
    return items


def validate_required_checks(
    rules_pages: Any,
    check_pages: Any,
    status_pages: Any,
    *,
    expected_commit: str,
) -> None:
    """Require the latest occurrence of every active status-check rule to pass."""

    rules = _array_pages(rules_pages, label="active branch rules")
    checks = _pages(check_pages, item_key="check_runs", label="check runs")
    statuses = _array_pages(status_pages, label="commit statuses")
    specifications: set[tuple[str, int | None]] = set()
    for rule in rules:
        rule_type = rule.get("type")
        if rule_type == "workflows":
            raise ProviderStatusError(
                "protected main uses a required-workflows rule that this shadow cannot verify"
            )
        if rule_type != "required_status_checks":
            continue
        parameters = _object(rule.get("parameters"), label="required status-check parameters")
        for value in _list(
            parameters.get("required_status_checks"),
            label="required status-check parameters.required_status_checks",
        ):
            item = _object(value, label="required check")
            context = item.get("context")
            integration_id = item.get("integration_id")
            if not isinstance(context, str) or not context:
                raise ProviderStatusError("a required check has no context")
            if integration_id == -1:
                integration_id = None
            elif integration_id is not None:
                integration_id = _positive_id(
                    integration_id,
                    label=f"required check {context}.integration_id",
                )
            specifications.add((context, integration_id))
    for context, app_id in sorted(specifications, key=lambda item: item[0]):
        matching_checks = []
        for check in checks:
            app = _object(check.get("app"), label=f"check run {context}.app")
            if (
                check.get("name") == context
                and check.get("head_sha") == expected_commit
                and (app_id is None or app.get("id") == app_id)
            ):
                matching_checks.append(check)
        matching_statuses = [
            item
            for item in statuses
            if item.get("context") == context and item.get("sha") == expected_commit
        ]
        check_candidates = [
            item
            for item in matching_checks
            if isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool)
        ]
        status_candidates = [
            item
            for item in matching_statuses
            if isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool)
        ]
        if not check_candidates and (app_id is not None or not status_candidates):
            raise ProviderStatusError(
                f"required check {context!r} is missing for the release commit"
            )
        if check_candidates:
            latest_check = max(check_candidates, key=lambda item: item["id"])
            if not (
                latest_check.get("status") == "completed"
                and latest_check.get("conclusion") == "success"
            ):
                raise ProviderStatusError(f"required check {context!r} has not passed")
        if app_id is None and status_candidates:
            latest_status = max(status_candidates, key=lambda item: item["id"])
            if latest_status.get("state") != "success":
                raise ProviderStatusError(f"required status {context!r} has not passed")


def validate_surrey_pipeline(
    value: Any,
    *,
    expected_pipeline_id: int,
) -> None:
    """Require the exact successful child pipeline in the fixed mirror project."""

    pipeline = _object(value, label="Surrey pipeline")
    required = {
        "id": expected_pipeline_id,
        "ref": "main",
        "source": "parent_pipeline",
        "status": "success",
        "web_url": f"{SURREY_URL}/-/pipelines/{expected_pipeline_id}",
    }
    for name, expected in required.items():
        if pipeline.get(name) != expected:
            raise ProviderStatusError(f"Surrey pipeline has an unexpected {name}")
    sha = pipeline.get("sha")
    if not isinstance(sha, str) or not OBJECT_ID_RE.fullmatch(sha):
        raise ProviderStatusError("Surrey pipeline has an invalid mirror commit")


def select_surrey_seal_job(value: Any, *, expected_pipeline_id: int) -> int:
    """Return the one successful seal job from the closed child pipeline."""

    jobs = [_object(item, label="Surrey pipeline job") for item in _list(value, label="jobs")]
    names = {job.get("name") for job in jobs}
    expected_names = {"surrey_reset", "surrey_candidate", "surrey_seal"}
    if names != expected_names or len(jobs) != len(expected_names):
        raise ProviderStatusError(
            "Surrey child pipeline does not contain exactly the three gate jobs"
        )
    seal = next(job for job in jobs if job.get("name") == "surrey_seal")
    pipeline = _object(seal.get("pipeline"), label="Surrey seal pipeline")
    if (
        pipeline.get("id") != expected_pipeline_id
        or seal.get("status") != "success"
        or seal.get("ref") != "main"
    ):
        raise ProviderStatusError("Surrey seal job does not prove a successful exact pipeline")
    artifact = _object(seal.get("artifacts_file"), label="Surrey seal artifacts")
    if artifact.get("filename") != "artifacts.zip" or not isinstance(artifact.get("size"), int):
        raise ProviderStatusError("Surrey seal job has no exact artifact archive")
    return _positive_id(seal.get("id"), label="Surrey seal job id")


def extract_surrey_result(archive_path: Path, output_path: Path) -> None:
    """Extract only the closed provider result from a GitLab artifact archive."""

    try:
        with zipfile.ZipFile(archive_path) as archive:
            matches = [item for item in archive.infolist() if item.filename == SURREY_RESULT_MEMBER]
            if len(matches) != 1:
                raise ProviderStatusError("Surrey artifact has no unique provider result")
            item = matches[0]
            if item.is_dir() or item.file_size <= 0 or item.file_size > MAX_RESULT_SIZE:
                raise ProviderStatusError("Surrey provider result has an invalid size")
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ProviderStatusError("Surrey provider result must not be a symbolic link")
            if PurePosixPath(item.filename).parts != tuple(SURREY_RESULT_MEMBER.split("/")):
                raise ProviderStatusError("Surrey provider result has an unsafe path")
            data = archive.read(item)
    except (OSError, zipfile.BadZipFile) as error:
        raise ProviderStatusError(f"could not read Surrey artifact: {error}") from error
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderStatusError("Surrey provider result is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ProviderStatusError("Surrey provider result must be one JSON object")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data if data.endswith(b"\n") else data + b"\n")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    github = commands.add_parser("validate-github-run")
    github.add_argument("--document", type=Path, required=True)
    github.add_argument("--run-id", type=int, required=True)
    github.add_argument("--release-commit", required=True)

    checks = commands.add_parser("validate-required-checks")
    checks.add_argument("--rules", type=Path, required=True)
    checks.add_argument("--check-runs", type=Path, required=True)
    checks.add_argument("--statuses", type=Path, required=True)
    checks.add_argument("--release-commit", required=True)

    ordinary = commands.add_parser("validate-ordinary-workflows")
    ordinary.add_argument("--document", type=Path, required=True)
    ordinary.add_argument("--release-commit", required=True)

    pipeline = commands.add_parser("validate-surrey-pipeline")
    pipeline.add_argument("--document", type=Path, required=True)
    pipeline.add_argument("--pipeline-id", type=int, required=True)

    jobs = commands.add_parser("select-surrey-seal-job")
    jobs.add_argument("--document", type=Path, required=True)
    jobs.add_argument("--pipeline-id", type=int, required=True)

    extract = commands.add_parser("extract-surrey-result")
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    return result


def fail(message: str) -> NoReturn:
    print(f"provider status validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate-github-run":
            validate_github_run(
                read_json(args.document, label="GitHub workflow run"),
                expected_run_id=args.run_id,
                expected_commit=args.release_commit,
            )
        elif args.command == "validate-required-checks":
            validate_required_checks(
                read_json(args.rules, label="active branch rules"),
                read_json(args.check_runs, label="check runs"),
                read_json(args.statuses, label="commit statuses"),
                expected_commit=args.release_commit,
            )
        elif args.command == "validate-ordinary-workflows":
            validate_ordinary_workflows(
                read_json(args.document, label="ordinary workflow runs"),
                expected_commit=args.release_commit,
            )
        elif args.command == "validate-surrey-pipeline":
            validate_surrey_pipeline(
                read_json(args.document, label="Surrey pipeline"),
                expected_pipeline_id=args.pipeline_id,
            )
        elif args.command == "select-surrey-seal-job":
            print(
                select_surrey_seal_job(
                    read_json(args.document, label="Surrey pipeline jobs"),
                    expected_pipeline_id=args.pipeline_id,
                )
            )
        else:
            extract_surrey_result(args.archive, args.output)
    except (OSError, ProviderStatusError) as error:
        fail(str(error))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()

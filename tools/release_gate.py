# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Combine exact GitHub and Surrey evidence for a protected release candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from canonical_wheel import WheelIdentityError, inspect_wheel
from live_provider_state import StateError
from release_gate_state import RELEASE_REPOSITORY, ProviderGateResult


class ReleaseGateError(RuntimeError):
    """Candidate evidence cannot authorise a release."""


@dataclass(frozen=True)
class ProviderEvidence:
    result_sha256: str
    workflow_run_id: int
    workflow_url: str


@dataclass(frozen=True)
class ReleaseEvidence:
    """Public, non-secret evidence assembled before publication checks."""

    schema: int
    passed: bool
    release_repository: str
    release_commit: str
    candidate_version: str
    canonical_format: str
    wheel_sha256: str
    wheel_contents_sha256: str
    github: ProviderEvidence
    surrey: ProviderEvidence
    assembled_at_utc: str

    def document(self) -> dict[str, object]:
        return asdict(self)


def git(checkout: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ReleaseGateError(f"could not inspect release checkout: {detail.strip()}") from error
    return result.stdout.strip()


def validate_release_checkout(checkout: Path, *, expected_commit: str) -> None:
    """Require a clean default branch at the exact remote main commit."""

    if git(checkout, "rev-parse", "HEAD") != expected_commit:
        raise ReleaseGateError("release checkout HEAD differs from the candidate commit")
    if git(checkout, "rev-parse", "refs/remotes/origin/main") != expected_commit:
        raise ReleaseGateError("origin/main differs from the candidate commit")
    if git(checkout, "branch", "--show-current") != "main":
        raise ReleaseGateError("the release gate must run from the default main branch")
    if git(checkout, "status", "--porcelain"):
        raise ReleaseGateError("the release checkout contains uncommitted changes")


def assemble(
    *,
    github: ProviderGateResult,
    surrey: ProviderGateResult,
    wheel_path: Path,
    expected_commit: str,
    expected_version: str,
    assembled_at: datetime | None = None,
) -> ReleaseEvidence:
    """Fail unless both providers approve the same exact candidate contents."""

    if github.provider != "github" or surrey.provider != "surrey":
        raise ReleaseGateError("both the GitHub and Surrey provider results are required")
    values = (github, surrey)
    for result in values:
        if result.release_commit != expected_commit:
            raise ReleaseGateError(f"{result.provider} tested another release commit")
        if result.controller_commit != expected_commit:
            raise ReleaseGateError(f"{result.provider} used another controller commit")
        if result.candidate_version != expected_version:
            raise ReleaseGateError(f"{result.provider} tested another candidate version")
    if github.wheel_contents_sha256 != surrey.wheel_contents_sha256:
        raise ReleaseGateError("GitHub and Surrey tested different wheel contents")

    identity = inspect_wheel(wheel_path)
    if identity.distribution != "prodockit" or identity.version != expected_version:
        raise ReleaseGateError("publication wheel identifies another package or version")
    if identity.wheel_contents_sha256 != github.wheel_contents_sha256:
        raise ReleaseGateError("publication wheel contents differ from provider-tested contents")

    now = assembled_at or datetime.now(timezone.utc)
    return ReleaseEvidence(
        schema=1,
        passed=True,
        release_repository=RELEASE_REPOSITORY,
        release_commit=expected_commit,
        candidate_version=expected_version,
        canonical_format=identity.canonical_format,
        wheel_sha256=identity.wheel_sha256,
        wheel_contents_sha256=identity.wheel_contents_sha256,
        github=ProviderEvidence(
            result_sha256=github.sha256,
            workflow_run_id=github.workflow_run_id,
            workflow_url=github.workflow_url,
        ),
        surrey=ProviderEvidence(
            result_sha256=surrey.sha256,
            workflow_run_id=surrey.workflow_run_id,
            workflow_url=surrey.workflow_url,
        ),
        assembled_at_utc=now.isoformat().replace("+00:00", "Z"),
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--github-result", type=Path, required=True)
    result.add_argument("--surrey-result", type=Path, required=True)
    result.add_argument("--wheel", type=Path, required=True)
    result.add_argument("--expected-commit", required=True)
    result.add_argument("--expected-version", required=True)
    result.add_argument("--release-checkout", type=Path, default=Path.cwd())
    result.add_argument("--output", type=Path, required=True)
    return result


def fail(message: str) -> NoReturn:
    print(f"release evidence assembly failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        github = ProviderGateResult.read(args.github_result)
        surrey = ProviderGateResult.read(args.surrey_result)
        validate_release_checkout(
            args.release_checkout.resolve(), expected_commit=args.expected_commit
        )
        evidence = assemble(
            github=github,
            surrey=surrey,
            wheel_path=args.wheel,
            expected_commit=args.expected_commit,
            expected_version=args.expected_version,
        )
        args.output.write_text(
            json.dumps(evidence.document(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        OSError,
        ReleaseGateError,
        StateError,
        WheelIdentityError,
    ) as error:
        fail(str(error))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()

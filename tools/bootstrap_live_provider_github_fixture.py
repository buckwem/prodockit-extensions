# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Create the closed GitHub candidate fixture from a reset handoff and source clone."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from bootstrap_live_provider_read_write import PUBLIC_TEMPLATE, Fixture, LiveProviderError
from live_provider_state import GITHUB_PATH, ResetHandoff, StateError, write_private_json

HOSTNAME = "github.com"
DESTINATION_NAMESPACE = "buckwem"
DESTINATION_PROJECT = "bootstrap-release-gate"
DESTINATION_REMOTE = f"git@{HOSTNAME}:{GITHUB_PATH}.git"
MARKER_PATH = ".prodockit-template.toml"


class FixtureError(RuntimeError):
    """The source clone cannot safely define the candidate fixture."""


def git(checkout: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(checkout), *arguments),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise FixtureError(f"could not inspect the public template clone: {error}") from error
    return result.stdout.strip()


def create_fixture(*, handoff: ResetHandoff, source_checkout: Path) -> Fixture:
    """Bind one clean public template clone to the exact GitHub reset handoff."""

    handoff.validate()
    if handoff.schema != 2 or handoff.provider != "github":
        raise FixtureError("GitHub candidate fixture requires one schema 2 GitHub handoff")
    checkout = source_checkout.expanduser().resolve()
    if git(checkout, "rev-parse", "HEAD") != handoff.source_commit:
        raise FixtureError("public template clone differs from the handoff source commit")
    if git(checkout, "remote", "get-url", "origin") != PUBLIC_TEMPLATE:
        raise FixtureError("public template clone has an unexpected origin")
    if git(checkout, "status", "--porcelain"):
        raise FixtureError("public template clone is not clean")
    marker = checkout / MARKER_PATH
    try:
        marker_digest = hashlib.sha256(marker.read_bytes()).hexdigest()
    except OSError as error:
        raise FixtureError(f"could not read the public template marker: {error}") from error
    fixture = Fixture(
        schema=2,
        provider="github",
        hostname=HOSTNAME,
        source_remote=PUBLIC_TEMPLATE,
        source_head=handoff.source_commit,
        destination_namespace=DESTINATION_NAMESPACE,
        destination_project=DESTINATION_PROJECT,
        destination_remote=DESTINATION_REMOTE,
        template_marker_path=MARKER_PATH,
        template_marker_sha256=marker_digest,
    )
    fixture.validate()
    return fixture


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--handoff", required=True, type=Path)
    result.add_argument("--source-checkout", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    return result


def fail(message: str) -> NoReturn:
    print(f"GitHub live-provider fixture failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        output = args.output.expanduser().resolve()
        if output.exists():
            raise FixtureError(f"candidate fixture already exists: {output}")
        handoff = ResetHandoff.read(args.handoff)
        fixture = create_fixture(handoff=handoff, source_checkout=args.source_checkout)
        write_private_json(output, asdict(fixture))
    except (FixtureError, LiveProviderError, StateError, OSError, ValueError) as error:
        fail(str(error))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()

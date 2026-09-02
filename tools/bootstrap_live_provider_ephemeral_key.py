# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Create and unwrap one encrypted, run-scoped GitHub deploy key."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from bootstrap_live_provider_github_lifecycle import (
    LifecycleError,
    public_key,
    public_key_fingerprint,
)

ENCRYPTED_KEY_BYTES = 512
COMMAND_TIMEOUT_SECONDS = 30


def private_output(path: Path) -> Path:
    """Resolve one absent output path beneath an existing directory."""

    result = path.expanduser().resolve()
    if result.exists():
        raise LifecycleError(f"refusing to replace existing key output: {result}")
    if not result.parent.is_dir():
        raise LifecycleError(f"key output directory does not exist: {result.parent}")
    return result


def existing_input(path: Path, *, label: str) -> Path:
    """Resolve one regular, non-empty input file."""

    result = path.expanduser().resolve()
    if not result.is_file():
        raise LifecycleError(f"{label} is not a regular file: {result}")
    if result.stat().st_size == 0:
        raise LifecycleError(f"{label} is empty: {result}")
    return result


def run(command: Sequence[str], *, label: str) -> None:
    """Run one bounded local cryptographic command without capturing key material."""

    try:
        subprocess.run(
            tuple(command),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise LifecycleError(f"{label} requires {command[0]} on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise LifecycleError(f"{label} exceeded {COMMAND_TIMEOUT_SECONDS} seconds") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise LifecycleError(f"{label} failed{suffix}") from error


def create(
    *,
    wrapping_public_key: Path,
    deploy_public_key: Path,
    encrypted_private_key: Path,
    comment: str,
) -> str:
    """Generate one Ed25519 key and wrap its private half with RSA-OAEP."""

    wrapping_public_key = existing_input(wrapping_public_key, label="RSA wrapping public key")
    deploy_public_key = private_output(deploy_public_key)
    encrypted_private_key = private_output(encrypted_private_key)
    if not comment or any(character in comment for character in "\0\r\n"):
        raise LifecycleError("deploy-key comment must be non-empty single-line text")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix="prodockit-live-deploy-", dir=encrypted_private_key.parent
    )
    os.close(descriptor)
    temporary_private = Path(temporary_name)
    temporary_private.unlink()
    temporary_public = Path(str(temporary_private) + ".pub")
    completed_successfully = False
    try:
        run(
            (
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                comment,
                "-f",
                str(temporary_private),
            ),
            label="ephemeral Ed25519 key generation",
        )
        run(
            (
                "openssl",
                "pkeyutl",
                "-encrypt",
                "-pubin",
                "-inkey",
                str(wrapping_public_key),
                "-in",
                str(temporary_private),
                "-out",
                str(encrypted_private_key),
                "-pkeyopt",
                "rsa_padding_mode:oaep",
                "-pkeyopt",
                "rsa_oaep_md:sha256",
            ),
            label="ephemeral deploy-key encryption",
        )
        if encrypted_private_key.stat().st_size != ENCRYPTED_KEY_BYTES:
            raise LifecycleError(
                "encrypted deploy key is not a 4096-bit RSA ciphertext; "
                "use the documented wrapping-key size"
            )
        record, fingerprint = public_key(temporary_public)
        deploy_public_key.write_text(record + "\n", encoding="utf-8")
        os.chmod(deploy_public_key, 0o600)
        os.chmod(encrypted_private_key, 0o600)
        completed_successfully = True
        return fingerprint
    finally:
        temporary_private.unlink(missing_ok=True)
        temporary_public.unlink(missing_ok=True)
        if not completed_successfully:
            deploy_public_key.unlink(missing_ok=True)
            encrypted_private_key.unlink(missing_ok=True)


def unwrap(
    *,
    wrapping_private_key: Path,
    encrypted_private_key: Path,
    deploy_private_key: Path,
    expected_fingerprint: str,
) -> None:
    """Decrypt one run-scoped SSH key and bind it to its reviewed fingerprint."""

    wrapping_private_key = existing_input(wrapping_private_key, label="RSA wrapping private key")
    encrypted_private_key = existing_input(encrypted_private_key, label="encrypted deploy key")
    deploy_private_key = private_output(deploy_private_key)
    if encrypted_private_key.stat().st_size != ENCRYPTED_KEY_BYTES:
        raise LifecycleError("encrypted deploy key has an unexpected size")
    completed_successfully = False
    try:
        run(
            (
                "openssl",
                "pkeyutl",
                "-decrypt",
                "-inkey",
                str(wrapping_private_key),
                "-in",
                str(encrypted_private_key),
                "-out",
                str(deploy_private_key),
                "-pkeyopt",
                "rsa_padding_mode:oaep",
                "-pkeyopt",
                "rsa_oaep_md:sha256",
            ),
            label="ephemeral deploy-key decryption",
        )
        os.chmod(deploy_private_key, 0o600)
        try:
            completed = subprocess.run(
                ("ssh-keygen", "-y", "-f", str(deploy_private_key)),
                check=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise LifecycleError(
                f"could not derive the ephemeral deploy public key: {error}"
            ) from error
        observed = public_key_fingerprint(completed.stdout.strip())
        if observed != expected_fingerprint:
            raise LifecycleError("decrypted deploy key differs from the reset handoff")
        completed_successfully = True
    finally:
        if not completed_successfully:
            deploy_private_key.unlink(missing_ok=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--wrapping-public-key", type=Path, required=True)
    create_parser.add_argument("--deploy-public-key", type=Path, required=True)
    create_parser.add_argument("--encrypted-private-key", type=Path, required=True)
    create_parser.add_argument("--comment", required=True)
    unwrap_parser = subparsers.add_parser("unwrap")
    unwrap_parser.add_argument("--wrapping-private-key", type=Path, required=True)
    unwrap_parser.add_argument("--encrypted-private-key", type=Path, required=True)
    unwrap_parser.add_argument("--deploy-private-key", type=Path, required=True)
    unwrap_parser.add_argument("--expected-fingerprint", required=True)
    return result


def fail(message: str) -> NoReturn:
    print(f"Ephemeral GitHub deploy-key preparation failed: {message}", file=os.sys.stderr)
    raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        if args.command == "create":
            fingerprint = create(
                wrapping_public_key=args.wrapping_public_key,
                deploy_public_key=args.deploy_public_key,
                encrypted_private_key=args.encrypted_private_key,
                comment=args.comment,
            )
            print(f"Ephemeral deploy key ready: {fingerprint}")
        else:
            unwrap(
                wrapping_private_key=args.wrapping_private_key,
                encrypted_private_key=args.encrypted_private_key,
                deploy_private_key=args.deploy_private_key,
                expected_fingerprint=args.expected_fingerprint,
            )
            print("Ephemeral deploy key decrypted and verified")
    except (LifecycleError, OSError, ValueError) as error:
        fail(str(error))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()

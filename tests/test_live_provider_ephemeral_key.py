# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for encrypted, run-scoped GitHub live-provider deploy keys."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
ephemeral = importlib.import_module("bootstrap_live_provider_ephemeral_key")
lifecycle = importlib.import_module("bootstrap_live_provider_github_lifecycle")


@pytest.fixture(scope="module")
def wrapping_keys(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if shutil.which("openssl") is None or shutil.which("ssh-keygen") is None:
        pytest.skip("OpenSSL and OpenSSH are required for the live-provider key boundary")
    directory = tmp_path_factory.mktemp("wrapping-keys")
    private = directory / "private.pem"
    public = directory / "public.pem"
    subprocess.run(
        (
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:4096",
            "-out",
            str(private),
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    )
    subprocess.run(
        ("openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    return private, public


def test_ephemeral_deploy_key_round_trip(tmp_path: Path, wrapping_keys: tuple[Path, Path]) -> None:
    wrapping_private, wrapping_public = wrapping_keys
    deploy_public = tmp_path / "deploy.pub"
    encrypted_private = tmp_path / "deploy.enc"
    deploy_private = tmp_path / "deploy"

    fingerprint = ephemeral.create(
        wrapping_public_key=wrapping_public,
        deploy_public_key=deploy_public,
        encrypted_private_key=encrypted_private,
        comment="prodockit-live-github-test",
    )

    assert lifecycle.public_key(deploy_public)[1] == fingerprint
    assert encrypted_private.stat().st_size == ephemeral.ENCRYPTED_KEY_BYTES
    assert b"OPENSSH PRIVATE KEY" not in encrypted_private.read_bytes()
    ephemeral.unwrap(
        wrapping_private_key=wrapping_private,
        encrypted_private_key=encrypted_private,
        deploy_private_key=deploy_private,
        expected_fingerprint=fingerprint,
    )
    derived = subprocess.run(
        ("ssh-keygen", "-y", "-f", str(deploy_private)),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    assert lifecycle.public_key_fingerprint(derived) == fingerprint


def test_unwrap_rejects_another_handoff_fingerprint(
    tmp_path: Path, wrapping_keys: tuple[Path, Path]
) -> None:
    wrapping_private, wrapping_public = wrapping_keys
    encrypted_private = tmp_path / "deploy.enc"
    fingerprint = ephemeral.create(
        wrapping_public_key=wrapping_public,
        deploy_public_key=tmp_path / "deploy.pub",
        encrypted_private_key=encrypted_private,
        comment="prodockit-live-github-test",
    )
    assert fingerprint.startswith("SHA256:")
    deploy_private = tmp_path / "deploy"

    with pytest.raises(lifecycle.LifecycleError, match="differs from the reset handoff"):
        ephemeral.unwrap(
            wrapping_private_key=wrapping_private,
            encrypted_private_key=encrypted_private,
            deploy_private_key=deploy_private,
            expected_fingerprint="SHA256:another-reviewed-key",
        )

    assert not deploy_private.exists()


def test_unwrap_rejects_modified_ciphertext(
    tmp_path: Path, wrapping_keys: tuple[Path, Path]
) -> None:
    wrapping_private, wrapping_public = wrapping_keys
    encrypted_private = tmp_path / "deploy.enc"
    fingerprint = ephemeral.create(
        wrapping_public_key=wrapping_public,
        deploy_public_key=tmp_path / "deploy.pub",
        encrypted_private_key=encrypted_private,
        comment="prodockit-live-github-test",
    )
    ciphertext = bytearray(encrypted_private.read_bytes())
    ciphertext[-1] ^= 1
    encrypted_private.write_bytes(ciphertext)
    deploy_private = tmp_path / "deploy"

    with pytest.raises(lifecycle.LifecycleError):
        ephemeral.unwrap(
            wrapping_private_key=wrapping_private,
            encrypted_private_key=encrypted_private,
            deploy_private_key=deploy_private,
            expected_fingerprint=fingerprint,
        )

    assert not deploy_private.exists()

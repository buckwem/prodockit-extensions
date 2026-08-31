# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.canonical_site_config import create_canonical_config

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def test_canonical_config_adds_consent_gated_analytics_without_changing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "zensical.toml"
    destination = tmp_path / ".zensical-canonical.toml"
    original = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    source.write_text(original, encoding="utf-8")

    create_canonical_config(source, destination, "G-TEST123")

    assert source.read_text(encoding="utf-8") == original
    source_extra = tomllib.loads(original)["project"]["extra"]
    canonical_extra = tomllib.loads(destination.read_text(encoding="utf-8"))["project"][
        "extra"
    ]
    assert "analytics" not in source_extra
    assert "consent" not in source_extra
    assert canonical_extra["analytics"] == {
        "provider": "google",
        "property": "G-TEST123",
    }
    description = " ".join(canonical_extra["consent"]["description"].split())
    assert description == (
        "We use optional analytics cookies to understand which documentation "
        "is useful and improve prodockit."
    )
    assert canonical_extra["consent"]["actions"] == ["accept", "manage"]
    assert canonical_extra["consent"]["cookies"]["analytics"] == {
        "name": "Google Analytics",
        "checked": True,
    }


@pytest.mark.parametrize(
    "measurement_id",
    ("", "BCDJ2LWJT3", "G-", "G-lowercase", "UA-12345-1", "G-ABC 123"),
)
def test_canonical_config_rejects_invalid_measurement_ids(
    tmp_path: Path, measurement_id: str
) -> None:
    with pytest.raises(ValueError, match="GA4 measurement ID"):
        create_canonical_config(
            ROOT / "zensical.toml", tmp_path / "canonical.toml", measurement_id
        )


def test_canonical_config_command_fails_clearly_without_an_id(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "canonical_site_config.py"),
            str(ROOT / "zensical.toml"),
            str(tmp_path / "canonical.toml"),
            "not-an-id",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "GOOGLE_ANALYTICS_ID must be a GA4 measurement ID" in completed.stderr


def test_deployment_keeps_the_secret_after_the_reusable_build_checks() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(
        encoding="utf-8"
    )

    reusable_check = "python -m pytest tests/test_built_docs.py -m built -v"
    canonical_config = (
        "python tools/canonical_site_config.py zensical.toml "
        '.zensical-canonical.toml "$GOOGLE_ANALYTICS_ID"'
    )
    assert "GOOGLE_ANALYTICS_ID: ${{ secrets.GOOGLE_ANALYTICS_ID }}" in workflow
    assert "if: github.repository == 'buckwem/prodockit-extensions'" in workflow
    assert "The prodockit.org deployment needs the GOOGLE_ANALYTICS_ID" in workflow
    assert workflow.index(reusable_check) < workflow.index(canonical_config)


def test_temporary_canonical_config_is_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".zensical-canonical.toml" in ignored

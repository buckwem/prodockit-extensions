# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.pdf.runtime_config import PdfRuntimeConfigError, load_pdf_runtime_config

ROOT = Path(__file__).resolve().parents[1]


def test_missing_policy_uses_defaults_without_writing_a_file(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text("[project]\nsite_name = 'Test'\n", encoding="utf-8")

    policy = load_pdf_runtime_config(config)

    assert policy.exists is False
    assert policy.policy_for("mathjax").version == "latest"
    assert policy.policy_for("mermaid").version == "supported"
    assert all(item.location == "cache" for item in policy.components.values())
    assert not (tmp_path / "pdk-pdf.toml").exists()


def test_policy_is_resolved_beside_an_explicit_project_config(tmp_path: Path) -> None:
    project = tmp_path / "nested"
    project.mkdir()
    (project / "custom.toml").write_text("[project]\n", encoding="utf-8")
    (project / "pdk-pdf.toml").write_text(
        """schema_version = 1

[mathjax]
version = "4.1.3"
location = "cache"
preload = true
""",
        encoding="utf-8",
    )

    policy = load_pdf_runtime_config(project / "custom.toml")

    assert policy.exists is True
    assert policy.project_root == project.resolve()
    assert policy.policy_for("mathjax").version == "4.1.3"
    assert policy.policy_for("mathjax").preload is True
    assert policy.policy_for("pandoc").version == "supported"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("schema_version = 2\n", "schema_version must be 1"),
        ("schema_version = 1\nunknown = true\n", "unknown top-level"),
        ("schema_version = 1\n[mathjax]\nversoin = '4.0.0'\n", "unknown setting"),
        ("schema_version = 1\n[mathjax]\nversion = 'main'\n", "exact version"),
        ("schema_version = 1\n[mathjax]\nlocation = '../shared'\n", "must be 'cache'"),
        ("schema_version = 1\n[pandoc]\npreload = true\n", "unknown setting"),
        ("schema_version = 1\n[mermaid]\npreload = 'yes'\n", "true or false"),
    ],
)
def test_invalid_policy_fails_closed(tmp_path: Path, source: str, message: str) -> None:
    (tmp_path / "pdk-pdf.toml").write_text(source, encoding="utf-8")

    with pytest.raises(PdfRuntimeConfigError, match=message):
        load_pdf_runtime_config(tmp_path / "zensical.toml")


def test_unknown_component_lookup_is_actionable(tmp_path: Path) -> None:
    policy = load_pdf_runtime_config(tmp_path / "zensical.toml")

    with pytest.raises(PdfRuntimeConfigError, match="unknown PDF runtime component"):
        policy.policy_for("browser")


def test_repository_sample_policy_is_valid() -> None:
    policy = load_pdf_runtime_config(ROOT / "zensical.toml")

    assert policy.exists is True
    assert policy.path == ROOT / "pdk-pdf.toml"
    assert policy.schema_version == 1

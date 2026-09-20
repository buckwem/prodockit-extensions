# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from prodockit.project_config import load_project_config
from tools.pdf_configuration_g7_acceptance import _legacy_pdf_fixture


def test_current_template_policy_is_reconstructed_as_a_legacy_migration_fixture(
    tmp_path: Path,
) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text(
        '[project]\nsite_name = "Fixture"\n\n[project.extra]\nheading_numbering = true\n',
        encoding="utf-8",
    )
    policy = tmp_path / "pdk-pdf.toml"
    policy.write_text(
        'schema_version = 1\n\n[document]\npage_size = "A4"\n'
        'extra_css = ["stylesheets/pdk-pdf.css", "stylesheets/print.css"]\n\n'
        '[margins]\nbottom = "2.75cm"\n',
        encoding="utf-8",
    )

    migrated = _legacy_pdf_fixture(config)

    assert migrated == ["pdf_extra_css", "pdf_margin_bottom", "pdf_page_size"]
    extra = load_project_config(config).extra
    assert extra["heading_numbering"] is True
    assert extra["pdf_page_size"] == "A4"
    assert extra["pdf_margin_bottom"] == "2.75cm"
    assert extra["pdf_extra_css"] == [
        "stylesheets/pdk-pdf.css",
        "stylesheets/print.css",
    ]
    assert not policy.exists()


def test_existing_legacy_template_fixture_is_left_unchanged(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    source = (
        '[project]\nsite_name = "Fixture"\n\n[project.extra]\n'
        'pdf_margin_bottom = "2.75cm"\n'
    )
    config.write_text(source, encoding="utf-8")

    assert _legacy_pdf_fixture(config) == ["pdf_margin_bottom"]
    assert config.read_text(encoding="utf-8") == source

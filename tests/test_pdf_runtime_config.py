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


def test_pdf_document_policy_is_strict_and_resolved_by_bounded_group(tmp_path: Path) -> None:
    (tmp_path / "pdk-pdf.toml").write_text(
        """schema_version = 1

[document]
output = "dist/report.pdf"
copyright = "Project PDF"
extra_css = ["stylesheets/print.css"]
page_size = "Letter"
double_sided = true

[margins]
top = "1in"
right = "0.75in"
bottom = "1in"
left = "0.75in"
inner = "1.25in"
outer = "0.5in"

[header_footer]
font_size = "9pt"
color = "#111111"
divider_color = "#cccccc"

[table_of_contents]
include = false
title = "Contents"

[source_bundle]
output = "dist/source.pdf"
""",
        encoding="utf-8",
    )

    settings = load_pdf_runtime_config(
        tmp_path / "zensical.toml"
    ).resolve_pdf_settings()

    assert settings.value("pdf_output") == "dist/report.pdf"
    assert settings.value("pdf_extra_css") == ["stylesheets/print.css"]
    assert settings.value("pdf_page_size") == "Letter"
    assert settings.value("pdf_double_sided") is True
    assert settings.value("pdf_margin_inner") == "1.25in"
    assert settings.value("pdf_header_footer_font_size") == "9pt"
    assert settings.value("pdf_include_table_of_contents") is False
    assert settings.value("pdf_source_bundle_output") == "dist/source.pdf"
    assert settings.source_for("pdf_output") == "pdk-pdf.toml [document].output"


def test_pdk_pdf_setting_wins_over_legacy_fallback_per_setting(tmp_path: Path) -> None:
    (tmp_path / "pdk-pdf.toml").write_text(
        """schema_version = 1
[document]
page_size = "Letter"
""",
        encoding="utf-8",
    )

    settings = load_pdf_runtime_config(tmp_path / "zensical.toml").resolve_pdf_settings(
        {"pdf_page_size": 42, "pdf_margin_top": "3cm"}
    )

    assert settings.value("pdf_page_size") == "Letter"
    assert settings.source_for("pdf_page_size") == "pdk-pdf.toml [document].page_size"
    assert settings.value("pdf_margin_top") == "3cm"
    assert settings.source_for("pdf_margin_top").endswith("(deprecated fallback)")
    assert settings.legacy == ("pdf_margin_top",)
    assert settings.shadowed_legacy == ("pdf_page_size",)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("schema_version = 1\n[document]\noutpt = 'x.pdf'\n", "unknown setting"),
        ("schema_version = 1\n[document]\noutput = 'report.txt'\n", "name a .pdf"),
        ("schema_version = 1\n[document]\ndouble_sided = 'yes'\n", "true or false"),
        ("schema_version = 1\n[margins]\ntop = 1\n", "must be a string"),
        ("schema_version = 1\n[table_of_contents]\ninclude = 1\n", "true or false"),
        ("schema_version = 1\n[source_bundle]\noutput = []\n", "must be a string"),
    ],
)
def test_invalid_pdf_document_policy_fails_closed(
    tmp_path: Path, source: str, message: str
) -> None:
    (tmp_path / "pdk-pdf.toml").write_text(source, encoding="utf-8")

    with pytest.raises(PdfRuntimeConfigError, match=message):
        load_pdf_runtime_config(tmp_path / "zensical.toml")

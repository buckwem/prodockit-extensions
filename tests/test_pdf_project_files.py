from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.pdf.project_files import PdfProjectFilesError, prepare_project_files
from prodockit.pdf.runtime_config import load_pdf_runtime_config


def test_first_pdf_use_creates_policy_and_styles_without_adopt(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Minimal"\n', encoding="utf-8")

    written = prepare_project_files(config)

    assert tmp_path / "pdk-pdf.toml" in written
    assert tmp_path / "pdf-requirements.txt" in written
    assert (tmp_path / "docs/stylesheets/pdk-pdf.css").is_file()
    assert (tmp_path / "docs/stylesheets/print.css").is_file()
    assert load_pdf_runtime_config(config).pdf_values["pdf_extra_css"] == [
        "stylesheets/pdk-pdf.css",
        "stylesheets/print.css",
    ]
    assert prepare_project_files(config) == ()


def test_pdf_use_migrates_legacy_settings_and_packages(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text(
        '[project]\nsite_name = "Legacy"\n\n'
        '[project.extra]\npdf_page_size = "Letter"\n'
        'pdf_extra_css = ["stylesheets/course-print.css"]\n',
        encoding="utf-8",
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "zensical>=0.0.63\nweasyprint==70.0  # project pin\npandoc\n",
        encoding="utf-8",
    )

    prepare_project_files(config)

    assert "pdf_page_size" not in config.read_text(encoding="utf-8")
    assert "weasyprint" not in requirements.read_text(encoding="utf-8")
    assert "pandoc" not in requirements.read_text(encoding="utf-8")
    assert "weasyprint==70.0" in (tmp_path / "pdf-requirements.txt").read_text(encoding="utf-8")
    policy = load_pdf_runtime_config(config)
    assert policy.pdf_values["pdf_page_size"] == "Letter"
    assert "stylesheets/course-print.css" in policy.pdf_values["pdf_extra_css"]
    assert prepare_project_files(config) == ()


def test_pdf_use_rejects_conflicting_policy_without_writes(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\n[project.extra]\npdf_page_size = "Letter"\n', encoding="utf-8")
    pdf = tmp_path / "pdk-pdf.toml"
    pdf.write_text('schema_version = 1\n[document]\npage_size = "A5"\n', encoding="utf-8")

    with pytest.raises(PdfProjectFilesError, match="conflicts"):
        prepare_project_files(config)

    assert 'pdf_page_size = "Letter"' in config.read_text(encoding="utf-8")
    assert not (tmp_path / "pdf-requirements.txt").exists()


def test_yaml_pdf_migration_preserves_other_settings(tmp_path: Path) -> None:
    config = tmp_path / "zensical.yml"
    config.write_text(
        "site_name: Legacy\nextra:\n  pdf_page_size: Letter\n  other: keep\n",
        encoding="utf-8",
    )

    prepare_project_files(config)

    assert "pdf_page_size" not in config.read_text(encoding="utf-8")
    assert "other: keep" in config.read_text(encoding="utf-8")
    assert load_pdf_runtime_config(config).pdf_values["pdf_page_size"] == "Letter"


def test_preconfigured_project_is_a_no_op_and_preserves_pdf_styles(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Ready"\n', encoding="utf-8")
    pdf = tmp_path / "pdk-pdf.toml"
    pdf.write_text(
        'schema_version = 1\n[document]\nextra_css = '
        '["stylesheets/pdk-pdf.css", "stylesheets/print.css"]\n',
        encoding="utf-8",
    )
    (tmp_path / "pdf-requirements.txt").write_text(
        'weasyprint>=70.0; sys_platform != "win32"\n', encoding="utf-8"
    )
    styles = tmp_path / "docs" / "stylesheets"
    styles.mkdir(parents=True)
    (styles / "pdk-pdf.css").write_text("/* managed */\n", encoding="utf-8")
    (styles / "print.css").write_text("/* author */\n", encoding="utf-8")

    assert prepare_project_files(config) == ()
    assert (styles / "pdk-pdf.css").read_text(encoding="utf-8") == "/* managed */\n"
    assert (styles / "print.css").read_text(encoding="utf-8") == "/* author */\n"

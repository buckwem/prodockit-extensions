# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import prodockit.config_diagnostics as config_diagnostics
from prodockit.cli import main
from prodockit.config_diagnostics import EXTENSION_TYPES
from prodockit.settings import EXTRA_SETTINGS, SettingError, validate_extra_settings
from prodockit.template_sync import read_config


@pytest.mark.parametrize("setting", EXTRA_SETTINGS, ids=lambda setting: setting.key)
def test_every_extra_setting_rejects_incompatible_types(setting) -> None:
    for value in (42, None, {}, [1]):
        with pytest.raises(SettingError, match=setting.key):
            validate_extra_settings({setting.key: value})
    valid = (
        False
        if isinstance(setting.default, bool)
        else []
        if isinstance(setting.default, tuple)
        else ""
    )
    validate_extra_settings({setting.key: valid, "custom_author_setting": {"anything": 42}})


@pytest.mark.parametrize(
    "body",
    [
        'heading_numbering = "false"',
        'pdf_double_sided = "false"',
        'pdf_include_table_of_contents = "false"',
        "website_heading_numbering = 0",
        "pdf_page_size = 42",
        'pdf_extra_css = "print.css"',
        'pdf_extra_css = ["print.css", 42]',
    ],
)
def test_config_check_rejects_invalid_extra_types(tmp_path: Path, body: str) -> None:
    path = _config(tmp_path, "\n[project.extra]\n" + body + "\n")
    result = _run(path, check=True)
    assert result.exit_code == 1
    assert "project.extra." + body.split(" =")[0] in result.output
    assert "must be" in result.output
    assert "Traceback" not in result.output


def test_pdf_rejects_invalid_type_before_rendering(tmp_path: Path) -> None:
    path = _config(tmp_path, "\n[project.extra]\npdf_page_size = 42\n")
    result = CliRunner().invoke(main, ["pdf", "--config-file", str(path)])
    assert result.exit_code == 1
    assert "project.extra.pdf_page_size must be a string" in result.output
    assert "Traceback" not in result.output


def test_comment_only_reference_passes_config_check(tmp_path: Path) -> None:
    path = _config(tmp_path)
    (tmp_path / "writing").mkdir()
    (tmp_path / "writing" / "index.md").write_text(
        "# Page\n\n<!-- Example: \\ref{target}. -->\n", encoding="utf-8"
    )
    result = _run(path, check=True)
    assert result.exit_code == 0, result.output
    assert "prodockit.refs is not enabled" not in result.output


def _config(tmp_path: Path, body: str = "") -> Path:
    path = tmp_path / "zensical.toml"
    path.write_text(
        '[project]\nsite_name = "Example"\ndocs_dir = "writing"\n' + body,
        encoding="utf-8",
    )
    return path


def _run(path: Path, *, check: bool = False):
    args = ["config", "--config-file", str(path)]
    if check:
        args.append("--check")
    return CliRunner().invoke(main, args)


def test_reports_explicit_and_default_resolved_values(tmp_path: Path) -> None:
    path = _config(tmp_path, '\n[project.extra]\npdf_page_size = "Letter"\n')

    result = _run(path)

    assert result.exit_code == 0
    assert "pdf_page_size" in result.output
    assert "Letter" in result.output
    assert "project.extra.pdf_page_size" in result.output
    assert "pdf_output" in result.output
    assert "writing/site_documentation.pdf" in result.output
    assert "default" in result.output
    assert "Index generation" in result.output
    assert "State: disabled" in result.output
    assert "Title: Index" in result.output


def test_check_rejects_obsolete_index_settings(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        '\n[project.extra]\npdf_include_index = true\npdf_index_title = "Terms"\n',
    )

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "project.extra.pdf_include_index" in result.output
    assert "project.extra.pdf_index_title" in result.output
    assert "obsolete" in result.output
    assert "prodockit.index" in result.output


def test_check_suggests_a_misspelled_extension_option(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        '\n[project.markdown_extensions."prodockit.index"]\nincldue = true\n',
    )

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "incldue" in result.output
    assert "did you mean 'include'" in result.output


def test_check_suggests_a_misspelled_extension_name(tmp_path: Path) -> None:
    path = _config(tmp_path, '\n[project.markdown_extensions."prodockit.indxe"]\n')

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "prodockit.indxe" in result.output
    assert "did you mean 'prodockit.index'" in result.output


def test_check_suggests_a_misspelled_pdf_setting(tmp_path: Path) -> None:
    path = _config(tmp_path, '\n[project.extra]\npdf_magin_left = "3cm"\n')

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "pdf_magin_left" in result.output
    assert "pdf_margin_left" in result.output


def test_check_allows_unrelated_extra_settings(tmp_path: Path) -> None:
    path = _config(tmp_path, '\n[project.extra]\nanalytics = true\nsocial = ["example"]\n')

    result = _run(path, check=True)

    assert result.exit_code == 0
    assert "Configuration check passed" in result.output


def test_index_status_reports_missing_optional_support(tmp_path: Path, monkeypatch) -> None:
    path = _config(
        tmp_path,
        '\n[project.markdown_extensions."prodockit.index"]\ninclude = true\n',
    )
    monkeypatch.setattr("prodockit.config_diagnostics.index_support_available", lambda: False)

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "Index generation" in result.output
    assert "enabled" in result.output
    assert "not installed" in result.output
    assert "prodockit[index]" in result.output


def test_index_support_rejects_an_installed_module_that_cannot_load(monkeypatch) -> None:
    def broken(_name: str):
        raise OSError("native library is missing")

    monkeypatch.setattr(config_diagnostics.importlib, "import_module", broken)

    assert config_diagnostics.index_support_available() is False


def test_index_support_requires_a_successful_import(monkeypatch) -> None:
    monkeypatch.setattr(config_diagnostics.importlib, "import_module", lambda _name: object())

    assert config_diagnostics.index_support_available() is True


def test_check_passes_valid_prodockit_configuration(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        '\n[project.extra]\npdf_margin_left = "3cm"\n'
        '\n[project.markdown_extensions."prodockit.refs"]\nunresolved = "??"\n',
    )

    result = _run(path, check=True)

    assert result.exit_code == 0
    assert "Configuration check passed" in result.output


def test_check_rejects_invalid_index_value_types(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        '\n[project.markdown_extensions."prodockit.index"]\ninclude = "false"\n',
    )

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "include must be true or false" in result.output


def test_check_rejects_empty_index_title(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        '\n[project.markdown_extensions."prodockit.index"]\ntitle = "   "\n',
    )

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "title must be a non-empty string" in result.output


def test_check_reports_missing_project_inputs(tmp_path: Path) -> None:
    path = _config(tmp_path, '\nextra_css = ["styles/missing.css"]\n')

    result = _run(path, check=True)

    assert result.exit_code == 1
    assert "styles/missing.css" in result.output


def test_diagnostic_registry_covers_every_registered_prodockit_extension() -> None:
    root = Path(__file__).resolve().parent.parent
    package = read_config((root / "pyproject.toml").read_text(encoding="utf-8"))
    registered = package["project"]["entry-points"]["markdown.extensions"]

    assert sorted(EXTENSION_TYPES) == sorted(registered)

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit.pdf.cli import main

_ZENSICAL_TOML = """
[project]
site_name = "Test project"

nav = [
  {"Home" = "index.md"},
]
"""


def _write_project(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Cover\n", encoding="utf-8")
    (tmp_path / "zensical.toml").write_text(_ZENSICAL_TOML, encoding="utf-8")


def _install_fake_pandoc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    pandoc_path = bin_dir / "pandoc"
    pandoc_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    pandoc_path.chmod(pandoc_path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_pdf_command_builds_using_the_default_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 0
    assert "Wrote docs/site_documentation.pdf" in result.output
    assert (tmp_path / "docs" / "site_documentation.pdf").exists()


def test_pdf_command_accepts_a_config_file_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    (tmp_path / "custom.toml").write_text(
        (tmp_path / "zensical.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf", "-f", "custom.toml"])

    assert result.exit_code == 0
    assert (tmp_path / "docs" / "site_documentation.pdf").exists()


def test_pdf_command_exits_non_zero_and_reports_pandoc_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "boom" >&2; exit 1')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_pdf_command_reports_a_missing_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code != 0


def test_pdf_command_reports_a_source_bundle_error_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test: `pdf_source_bundle = true` makes
    build_pdf_from_zensical_config() also call build_source_bundle(),
    which raises SourceBundleError (not PdfBuildError/ValueError/OSError)
    when the project root isn't a git working tree - as tmp_path here
    isn't. The CLI's except clause used to omit SourceBundleError,
    letting the exception escape uncaught instead of exiting cleanly with
    an `Error: ...` message like every other build failure."""
    _write_project(tmp_path)
    zensical_toml = tmp_path / "zensical.toml"
    zensical_toml.write_text(
        zensical_toml.read_text(encoding="utf-8") + "\n[project.extra]\npdf_source_bundle = true\n",
        encoding="utf-8",
    )
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_pdf_command_accepts_a_markdown_file_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    (tmp_path / "docs" / "chapter1.md").write_text("# Chapter One\n", encoding="utf-8")
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf", "-m", "chapter1.md"])

    assert result.exit_code == 0
    assert "Wrote docs/chapter1.pdf" in result.output
    assert (tmp_path / "docs" / "chapter1.pdf").exists()
    assert not (tmp_path / "docs" / "site_documentation.pdf").exists()

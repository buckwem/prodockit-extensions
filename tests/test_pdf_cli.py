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

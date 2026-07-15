# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
from pathlib import Path

import pytest

from zendoc.pdf.config import (
    _find_mmdc_bin,
    _find_tex2svg_script,
    build_pdf_from_zensical_config,
)

_ZENSICAL_TOML = """
[project]
site_name = "Test project"
copyright = "Copyright test"

nav = [
  {{"Home" = "index.md"}},
  {{"Group" = [
    {{"Chapter" = "chapter1.md"}},
  ]}},
]
{extra}
"""


def _write_project(tmp_path: Path, *, extra: str = "") -> Path:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Cover\n", encoding="utf-8")
    (docs_dir / "chapter1.md").write_text("# Chapter One\n\nBody text.\n", encoding="utf-8")
    (tmp_path / "zensical.toml").write_text(
        _ZENSICAL_TOML.format(extra=extra), encoding="utf-8"
    )
    return tmp_path


def _fake_pandoc(bin_dir: Path, script: str) -> None:
    pandoc_path = bin_dir / "pandoc"
    pandoc_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    pandoc_path.chmod(pandoc_path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make(*, extra: str = "", pandoc_script: str = 'echo "%PDF-1.4 stub" > "$3"') -> Path:
        root = _write_project(tmp_path, extra=extra)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        _fake_pandoc(bin_dir, pandoc_script)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.chdir(root)
        return root

    return _make


def test_find_mmdc_bin_prefers_an_explicit_configured_path_that_exists(tmp_path: Path) -> None:
    configured = tmp_path / "my-mmdc"
    configured.write_text("", encoding="utf-8")
    assert _find_mmdc_bin(str(configured)) == str(configured)


def test_find_mmdc_bin_returns_none_when_nothing_is_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    assert _find_mmdc_bin(None) is None
    assert _find_mmdc_bin("/does/not/exist") is None


def test_find_tex2svg_script_returns_none_when_nothing_is_found() -> None:
    assert _find_tex2svg_script(None) is None
    assert _find_tex2svg_script("/does/not/exist") is None


def test_builds_a_pdf_from_a_zensical_toml_project(project) -> None:
    root = project()
    output_path = build_pdf_from_zensical_config(str(root / "zensical.toml"))
    assert output_path == "docs/site_documentation.pdf"
    assert (root / output_path).exists()


def test_pdf_output_path_is_configurable(project) -> None:
    root = project(extra='\n[project.extra]\npdf_output = "dist/out.pdf"\n')
    (root / "dist").mkdir()
    output_path = build_pdf_from_zensical_config(str(root / "zensical.toml"))
    assert output_path == "dist/out.pdf"
    assert (root / output_path).exists()


def test_appendix_front_matter_flag_is_read_from_the_page(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    (root / "docs" / "chapter1.md").write_text(
        "---\nis_appendix: true\n---\n\n# Chapter One\n", encoding="utf-8"
    )

    captured = {}
    import zendoc.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    pages_by_path = {page.docs_rel_path: page for page in captured["pages"]}
    assert pages_by_path["chapter1.md"].is_appendix is True
    assert pages_by_path["index.md"].is_appendix is False


def test_raises_a_clear_error_when_nav_is_empty(project) -> None:
    root = project()
    (root / "zensical.toml").write_text(
        '[project]\nsite_name = "Empty"\nnav = []\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="nav"):
        build_pdf_from_zensical_config(str(root / "zensical.toml"))

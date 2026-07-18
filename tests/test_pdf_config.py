# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
from pathlib import Path

import pytest

from prodockit.pdf.config import (
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
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    pages_by_path = {page.docs_rel_path: page for page in captured["pages"]}
    assert pages_by_path["chapter1.md"].is_appendix is True
    assert pages_by_path["index.md"].is_appendix is False


def test_recto_title_front_matter_is_read_from_the_page(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    (root / "docs" / "chapter1.md").write_text(
        '---\nrecto_title: "Short Title"\n---\n\n# Chapter One\n', encoding="utf-8"
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    pages_by_path = {page.docs_rel_path: page for page in captured["pages"]}
    assert pages_by_path["chapter1.md"].recto_title == "Short Title"
    assert pages_by_path["index.md"].recto_title is None


def test_double_sided_settings_are_read_from_extra_and_passed_through(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(
        extra=(
            "\n[project.extra]\npdf_double_sided = true\n"
            'pdf_margin_inner = "2.5cm"\npdf_margin_outer = "1.5cm"\n'
        )
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["double_sided"] is True
    assert captured["margin_inner"] == "2.5cm"
    assert captured["margin_outer"] == "1.5cm"


def test_double_sided_settings_default_off(project, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project()

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["double_sided"] is False
    assert captured["margin_inner"] == "2cm"
    assert captured["margin_outer"] == "2cm"


def test_raises_a_clear_error_when_nav_is_empty(project) -> None:
    root = project()
    (root / "zensical.toml").write_text(
        '[project]\nsite_name = "Empty"\nnav = []\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="nav"):
        build_pdf_from_zensical_config(str(root / "zensical.toml"))


def test_markdown_file_builds_only_that_page(project) -> None:
    root = project()
    output_path = build_pdf_from_zensical_config(
        str(root / "zensical.toml"), markdown_file="chapter1.md"
    )
    assert output_path == "docs/chapter1.pdf"
    assert (root / output_path).exists()


def test_markdown_file_ignores_an_empty_nav(project) -> None:
    root = project()
    (root / "zensical.toml").write_text(
        '[project]\nsite_name = "Empty"\nnav = []\n', encoding="utf-8"
    )
    output_path = build_pdf_from_zensical_config(
        str(root / "zensical.toml"), markdown_file="chapter1.md"
    )
    assert output_path == "docs/chapter1.pdf"
    assert (root / output_path).exists()


def test_markdown_file_still_honours_an_explicit_pdf_output(project) -> None:
    root = project(extra='\n[project.extra]\npdf_output = "dist/out.pdf"\n')
    (root / "dist").mkdir()
    output_path = build_pdf_from_zensical_config(
        str(root / "zensical.toml"), markdown_file="chapter1.md"
    )
    assert output_path == "dist/out.pdf"
    assert (root / output_path).exists()


def test_markdown_file_passes_only_that_page_to_build_pdf(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"), markdown_file="chapter1.md")

    assert [page.docs_rel_path for page in captured["pages"]] == ["chapter1.md"]


def test_extra_css_is_read_from_zensical_toml_and_passed_through(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(extra='\nextra_css = ["stylesheets/extra.css"]\n')
    (root / "docs" / "stylesheets").mkdir()
    (root / "docs" / "stylesheets" / "extra.css").write_text(
        "@media print { .web-only { display: none; } }\n", encoding="utf-8"
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert ".web-only" in captured["extra_css"]


def test_extra_css_defaults_to_empty_when_unset(project, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project()

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["extra_css"] == ""

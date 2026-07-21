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


def test_find_mmdc_bin_relative_configured_path_resolves_against_cwd_not_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documents a real footgun, not fixed here (see the in-depth test
    review this came from): a relative `pdf_mmdc_bin` is resolved
    against the current working directory, not wherever `config_path`
    itself lives. Running `prodockit pdf -f project/zensical.toml` from
    one directory up silently fails to find a relative pdf_mmdc_bin that
    would resolve fine if run from inside `project/` instead - even
    though config_path itself still correctly points at the right
    zensical.toml either way."""
    project_dir = tmp_path / "project"
    tools_dir = project_dir / "tools" / "mmdc"
    tools_dir.mkdir(parents=True)
    (tools_dir / "mmdc").write_text("", encoding="utf-8")
    relative_configured = os.path.join("tools", "mmdc", "mmdc")

    monkeypatch.chdir(project_dir)
    assert _find_mmdc_bin(relative_configured) == relative_configured

    monkeypatch.chdir(tmp_path)
    assert _find_mmdc_bin(relative_configured) is None


def test_find_tex2svg_script_relative_configured_path_resolves_against_cwd_not_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same footgun as _find_mmdc_bin above, for pdf_tex2svg_script."""
    project_dir = tmp_path / "project"
    tools_dir = project_dir / "tools" / "mathjax"
    tools_dir.mkdir(parents=True)
    (tools_dir / "tex2svg.js").write_text("", encoding="utf-8")
    relative_configured = os.path.join("tools", "mathjax", "tex2svg.js")

    monkeypatch.chdir(project_dir)
    assert _find_tex2svg_script(relative_configured) is not None

    monkeypatch.chdir(tmp_path)
    assert _find_tex2svg_script(relative_configured) is None


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


def test_pdf_extra_css_is_concatenated_after_extra_css(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pdf_extra_css is for a PDF-only override - concatenated *after*
    extra_css so it wins the cascade against a same-specificity rule
    there, matching what build_pdf()'s own generated CSS beneath both
    already promises for extra_css itself."""
    root = project(
        extra=(
            '\nextra_css = ["stylesheets/extra.css"]\n'
            '[project.extra]\npdf_extra_css = ["stylesheets/print.css"]\n'
        )
    )
    styles_dir = root / "docs" / "stylesheets"
    styles_dir.mkdir()
    (styles_dir / "extra.css").write_text(".web-only { display: block; }\n", encoding="utf-8")
    (styles_dir / "print.css").write_text(".hidden { display: none; }\n", encoding="utf-8")

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    extra_css = captured["extra_css"]
    assert ".web-only" in extra_css
    assert ".hidden" in extra_css
    assert extra_css.index(".web-only") < extra_css.index(".hidden")


def test_pdf_extra_css_relative_url_is_also_inlined(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(extra='\n[project.extra]\npdf_extra_css = ["stylesheets/print.css"]\n')
    styles_dir = root / "docs" / "stylesheets"
    styles_dir.mkdir()
    (styles_dir / "logo.png").write_bytes(b"\x89PNG\r\n")
    (styles_dir / "print.css").write_text(
        '.logo { content: url("logo.png"); }\n', encoding="utf-8"
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert "data:image/png;base64," in captured["extra_css"]


def test_pdf_extra_css_defaults_to_empty_when_unset(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["extra_css"] == ""


def test_source_bundle_is_not_built_by_default(project, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project()

    captured = {"called": False}
    import prodockit.pdf.config as config_module

    def _spy(*args, **kwargs):
        captured["called"] = True

    monkeypatch.setattr(config_module, "build_source_bundle", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["called"] is False


def test_source_bundle_is_built_when_enabled(project, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(extra="\n[project.extra]\npdf_source_bundle = true\n")

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(output_path, **kwargs):
        captured["output_path"] = output_path
        captured.update(kwargs)

    monkeypatch.setattr(config_module, "build_source_bundle", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["output_path"] == "source_bundle.pdf"
    assert captured["root"] == str(root)
    assert captured["report_name"] == "Test project"


def test_source_bundle_is_not_built_for_a_markdown_file_scoped_build(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(extra="\n[project.extra]\npdf_source_bundle = true\n")

    captured = {"called": False}
    import prodockit.pdf.config as config_module

    def _spy(*args, **kwargs):
        captured["called"] = True

    monkeypatch.setattr(config_module, "build_source_bundle", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"), markdown_file="chapter1.md")

    assert captured["called"] is False


def test_include_index_defaults_off(project, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project()

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["include_index"] = kwargs["include_index"]
        captured["index_title"] = kwargs["index_title"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["include_index"] is False
    assert captured["index_title"] == "Index"


def test_include_index_reads_from_extra_and_a_custom_title(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(
        extra=(
            "\n[project.extra]\npdf_include_index = true\n"
            'pdf_index_title = "Glossary of Terms"\n'
        )
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["include_index"] = kwargs["include_index"]
        captured["index_title"] = kwargs["index_title"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["include_index"] is True
    assert captured["index_title"] == "Glossary of Terms"


# ---------------------------------------------------------------------------
# Cover page markers
# ---------------------------------------------------------------------------


def _capture_pages(monkeypatch: pytest.MonkeyPatch):
    import prodockit.pdf.config as config_module

    captured = {}

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    return captured


def test_wordcount_marker_is_substituted_with_the_site_wide_word_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_project(tmp_path)
    (root / "docs" / "index.md").write_text("Word count: {WORDCOUNT}\n", encoding="utf-8")
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(root)

    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    cover_html = captured["pages"][0].html
    assert "{WORDCOUNT}" not in cover_html
    assert "Word count: 4" in cover_html  # "Chapter One Body text." on chapter1.md


def test_repourl_marker_is_substituted_with_the_git_detected_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_project(tmp_path)
    (root / "docs" / "index.md").write_text("Repo: {REPOURL}\n", encoding="utf-8")
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(root)

    import prodockit.pdf.config as config_module

    monkeypatch.setattr(config_module, "_get_repo_url", lambda: "https://github.com/x/y")
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert "Repo: https://github.com/x/y" in captured["pages"][0].html


def test_release_marker_is_substituted_when_a_release_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_project(tmp_path)
    (root / "docs" / "index.md").write_text("Release: {RELEASE}\n", encoding="utf-8")
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(root)

    import prodockit.pdf.config as config_module

    monkeypatch.setattr(config_module, "_get_repo_url", lambda: "https://github.com/x/y")
    monkeypatch.setattr(config_module, "get_latest_release_tag", lambda repo_url: "v1.2.3")
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert "Release: v1.2.3" in captured["pages"][0].html


def test_release_marker_line_is_dropped_when_no_release_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_project(tmp_path)
    (root / "docs" / "index.md").write_text(
        "Before\nRelease: {RELEASE}\nAfter\n", encoding="utf-8"
    )
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(root)

    import prodockit.pdf.config as config_module

    monkeypatch.setattr(config_module, "_get_repo_url", lambda: "https://github.com/x/y")
    monkeypatch.setattr(config_module, "get_latest_release_tag", lambda repo_url: "")
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    cover_html = captured["pages"][0].html
    assert "{RELEASE}" not in cover_html
    assert "Release:" not in cover_html
    assert "Before" in cover_html
    assert "After" in cover_html


def test_site_name_marker_is_substituted_literally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_project(tmp_path)
    (root / "docs" / "index.md").write_text("Project: {{ site_name }}\n", encoding="utf-8")
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(root)

    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert "Project: Test project" in captured["pages"][0].html


def test_markers_are_not_substituted_for_a_markdown_file_scoped_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There's no "cover page" concept for a single --markdown-file build -
    even a page that happens to contain a marker-looking string should be
    left completely alone."""
    root = _write_project(tmp_path)
    (root / "docs" / "chapter1.md").write_text(
        "# Chapter One\n\nWord count: {WORDCOUNT}\n", encoding="utf-8"
    )
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(root)

    build_pdf_from_zensical_config(str(root / "zensical.toml"), markdown_file="chapter1.md")

    assert "{WORDCOUNT}" in captured["pages"][0].html


def test_markers_are_not_substituted_when_index_is_the_only_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matches build_pdf.py's own original condition (len(pages) > 1) -
    a single-page site has no separate "content" to compute a word count
    from, so the marker is left as literal text rather than silently
    becoming "Word count: 0"."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("Word count: {WORDCOUNT}\n", encoding="utf-8")
    (tmp_path / "zensical.toml").write_text(
        '[project]\nsite_name = "Test project"\nnav = [{"Home" = "index.md"}]\n',
        encoding="utf-8",
    )
    captured = _capture_pages(monkeypatch)
    monkeypatch.chdir(tmp_path)

    build_pdf_from_zensical_config(str(tmp_path / "zensical.toml"))

    assert "{WORDCOUNT}" in captured["pages"][0].html


# ---------------------------------------------------------------------------
# extra_css relative url(...) inlining
# ---------------------------------------------------------------------------


def test_extra_css_relative_url_is_inlined_as_base64(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(extra='\nextra_css = ["stylesheets/extra.css"]\n')
    styles_dir = root / "docs" / "stylesheets"
    styles_dir.mkdir()
    (styles_dir / "logo.png").write_bytes(b"\x89PNG\r\n")
    (styles_dir / "extra.css").write_text(
        '.md-logo img { content: url("logo.png"); }\n', encoding="utf-8"
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert "data:image/png;base64," in captured["extra_css"]
    assert "logo.png" not in captured["extra_css"]


def test_extra_css_absolute_and_data_and_fragment_urls_are_left_alone(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(extra='\nextra_css = ["stylesheets/extra.css"]\n')
    styles_dir = root / "docs" / "stylesheets"
    styles_dir.mkdir()
    (styles_dir / "extra.css").write_text(
        "a { background: url(https://example.com/x.png); }\n"
        'b { background: url("data:image/png;base64,AAAA"); }\n'
        "c { clip-path: url(#my-clip); }\n",
        encoding="utf-8",
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert "url(https://example.com/x.png)" in captured["extra_css"]
    assert 'url("data:image/png;base64,AAAA")' in captured["extra_css"]
    assert "url(#my-clip)" in captured["extra_css"]


def test_extra_css_url_to_a_missing_file_is_left_unchanged(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(extra='\nextra_css = ["stylesheets/extra.css"]\n')
    styles_dir = root / "docs" / "stylesheets"
    styles_dir.mkdir()
    (styles_dir / "extra.css").write_text(
        'a { background: url("does-not-exist.png"); }\n', encoding="utf-8"
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["extra_css"] = kwargs["extra_css"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert 'url("does-not-exist.png")' in captured["extra_css"]

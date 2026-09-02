# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
import subprocess
from pathlib import Path

import pytest
from zensical.config import parse_config as parse_zensical_config

from prodockit.pdf import config
from prodockit.pdf.config import (
    _find_mmdc_bin,
    _find_tex2svg_script,
    _warn_if_release_sources_disagree,
    build_pdf_from_built_site,
    build_pdf_from_zensical_config,
    build_source_bundle_from_zensical_config,
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
    (tmp_path / "zensical.toml").write_text(_ZENSICAL_TOML.format(extra=extra), encoding="utf-8")
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(
        '<article class="md-content__inner md-typeset"><h1>Cover</h1></article>',
        encoding="utf-8",
    )
    chapter = site_dir / "chapter1" / "index.html"
    chapter.parent.mkdir()
    chapter.write_text(
        '<article class="md-content__inner md-typeset"><h1>Chapter One</h1>'
        '<p>Body text.</p></article>',
        encoding="utf-8",
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


def _npm_bin_dir_as_windows_writes_it(root: Path) -> Path:
    """Builds a `node_modules/.bin` the way `npm` does on Windows: the
    extensionless POSIX shell script that Windows cannot start, alongside
    the `.cmd` and `.ps1` shims that it can (`.ps1` only via PowerShell)."""
    bin_dir = root / "tools" / "mermaid" / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    for name in ("mmdc", "mmdc.cmd", "mmdc.ps1"):
        (bin_dir / name).write_text("", encoding="utf-8")
    return bin_dir


def test_find_mmdc_bin_picks_the_runnable_shim_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The extensionless `mmdc` exists on Windows too, so `os.path.exists`
    is not enough to tell whether it can be run: handing it to
    `subprocess.run` fails with `[WinError 193] %1 is not a valid Win32
    application`, reported per diagram rather than as a setup problem.
    """
    bin_dir = _npm_bin_dir_as_windows_writes_it(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "_WINDOWS", True)

    assert _find_mmdc_bin(None) == str(bin_dir / "mmdc.cmd")
    # And when a config names the bare script explicitly, which is the
    # spelling the documentation for every platform uses.
    assert _find_mmdc_bin(str(bin_dir / "mmdc")) == str(bin_dir / "mmdc.cmd")


def test_find_mmdc_bin_keeps_the_extensionless_name_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror of the test above: `mmdc.cmd` is inert on macOS/Linux, and
    a `.bin` directory can contain one if the tree was installed on Windows
    and copied across."""
    bin_dir = _npm_bin_dir_as_windows_writes_it(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "_WINDOWS", False)

    assert _find_mmdc_bin(None) == str(bin_dir / "mmdc")


def test_find_mmdc_bin_returns_none_when_nothing_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both an empty PATH *and* an empty working directory: the local-install
    # fallbacks are CWD-relative, so running from a checkout that has its own
    # tools/mermaid install would otherwise find that and fail this test for
    # reasons that have nothing to do with the code under test.
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    assert _find_mmdc_bin(None) is None
    assert _find_mmdc_bin("/does/not/exist") is None


def test_find_tex2svg_script_returns_none_when_nothing_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same CWD isolation as the mmdc case above - tools/mathjax/tex2svg.js is
    # resolved relative to the working directory.
    monkeypatch.chdir(tmp_path)
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


def test_a_renamed_render_result_key_raises_a_named_error_not_a_bare_keyerror(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    import zensical.markdown.render as render_module

    monkeypatch.setattr(
        render_module,
        "render",
        lambda *args, **kwargs: {"html": "<p>renamed</p>", "meta": {}},
    )

    with pytest.raises(RuntimeError) as exc_info:
        build_pdf_from_zensical_config(str(root / "zensical.toml"))

    message = str(exc_info.value)
    assert "content" in message
    assert "Zensical" in message
    assert "index.md" in message


def test_a_non_dict_render_result_raises_the_same_named_error(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()

    class _RenamedResultType:
        pass

    import zensical.markdown.render as render_module

    monkeypatch.setattr(render_module, "render", lambda *args, **kwargs: _RenamedResultType())

    with pytest.raises(RuntimeError) as exc_info:
        build_pdf_from_zensical_config(str(root / "zensical.toml"))

    message = str(exc_info.value)
    assert "Zensical" in message
    assert "index.md" in message


def test_a_renamed_render_result_key_stops_the_build_no_pdf_written(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    output_path = root / "docs" / "site_documentation.pdf"
    import zensical.markdown.render as render_module

    monkeypatch.setattr(render_module, "render", lambda *args, **kwargs: {"html": "", "meta": {}})

    with pytest.raises(RuntimeError):
        build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert not output_path.exists()


def test_built_site_candidate_uses_the_documented_build_output(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    captured = {}

    monkeypatch.setattr(
        config,
        "validate_built_site",
        lambda project_config, source_paths: captured.setdefault("built", True),
    )
    monkeypatch.setattr(
        config,
        "page_html",
        lambda project_config, source: f"<h1>{source}</h1>",
    )
    metadata_paths = []
    monkeypatch.setattr(
        config,
        "page_metadata",
        lambda source: metadata_paths.append(source) or {},
    )

    def capture(pages, output_path, **kwargs):
        captured["pages"] = pages
        captured["kwargs"] = kwargs

    monkeypatch.setattr(config, "build_pdf", capture)
    monkeypatch.setattr(config, "publish_pdf_to_built_site", lambda *_args: None)
    monkeypatch.chdir(root.parent)

    output = build_pdf_from_built_site(str(root / "zensical.toml"))

    assert output == "docs/site_documentation.pdf"
    assert captured["built"] is True
    assert [page.docs_rel_path for page in captured["pages"]] == ["index.md", "chapter1.md"]
    assert metadata_paths == [root / "docs" / "index.md", root / "docs" / "chapter1.md"]
    assert captured["kwargs"]["main_font"] == "Roboto"
    assert captured["kwargs"]["mono_font"] == "Roboto Mono"


def test_built_site_pdf_is_written_to_author_and_published_paths(project) -> None:
    root = project(pandoc_script='printf "%s" "%PDF-1.4 exact" > "$3"')

    output = build_pdf_from_built_site(str(root / "zensical.toml"))

    author_pdf = root / output
    published_pdf = root / "site" / "site_documentation.pdf"
    assert author_pdf.read_bytes() == b"%PDF-1.4 exact"
    assert published_pdf.read_bytes() == author_pdf.read_bytes()


def test_built_site_pdf_outside_docs_is_not_published(project) -> None:
    root = project(
        extra='\n[project.extra]\npdf_output = "dist/out.pdf"\n',
        pandoc_script='printf "%s" "%PDF-1.4 external" > "$3"',
    )
    (root / "dist").mkdir()

    output = build_pdf_from_built_site(str(root / "zensical.toml"))

    assert output == "dist/out.pdf"
    assert (root / output).read_bytes() == b"%PDF-1.4 external"
    assert list((root / "site").rglob("*.pdf")) == []


def test_built_site_single_page_pdf_is_published(project) -> None:
    root = project(pandoc_script='printf "%s" "%PDF-1.4 single" > "$3"')

    output = build_pdf_from_built_site(
        str(root / "zensical.toml"), markdown_file="chapter1.md"
    )

    assert output == "docs/chapter1.pdf"
    assert (root / "site" / "chapter1.pdf").read_bytes() == (root / output).read_bytes()


def test_built_site_pdf_resolves_custom_directories_from_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    docs = root / "writing"
    site = root / "public"
    docs.mkdir(parents=True)
    site.mkdir()
    (docs / "index.md").write_text("# Home\n", encoding="utf-8")
    (docs / "chapter.md").write_text("# Chapter\n", encoding="utf-8")
    article = '<article class="md-content__inner md-typeset"><h1>Page</h1></article>'
    (site / "index.html").write_text(article, encoding="utf-8")
    (site / "chapter.html").write_text(article, encoding="utf-8")
    config_path = root / "zensical.toml"
    config_path.write_text(
        """[project]
site_name = "Custom paths"
docs_dir = "writing"
site_dir = "public"
use_directory_urls = false
nav = [
    { "Home" = "index.md" },
    { "Chapter" = "chapter.md" },
]
""",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_pandoc(bin_dir, 'printf "%s" "%PDF-1.4 custom" > "$3"')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)

    output = build_pdf_from_built_site(str(config_path))

    assert output == os.path.join("writing", "site_documentation.pdf")
    assert (docs / "site_documentation.pdf").read_bytes() == b"%PDF-1.4 custom"
    assert (site / "site_documentation.pdf").read_bytes() == b"%PDF-1.4 custom"


@pytest.mark.parametrize("project_override", [False, True])
def test_built_site_icons_follow_compiled_css_then_project_overrides(
    project, monkeypatch: pytest.MonkeyPatch, project_override: bool
) -> None:
    root = project(
        extra=(
            '\n[project.theme.icon.admonition]\n'
            'note = "fontawesome/solid/note-sticky"\n'
        )
    )
    assets = root / "site" / "assets"
    assets.mkdir()
    (assets / "theme.css").write_text(
        '--md-admonition-icon--note:url("data:image/svg+xml,'
        '%3Csvg%3E%3Cpath fill=%22compiled-site%22/%3E%3C/svg%3E")',
        encoding="utf-8",
    )
    (root / "site" / "index.html").write_text(
        '<link rel="stylesheet" href="assets/theme.css">'
        '<article class="md-content__inner md-typeset"><h1>Cover</h1></article>',
        encoding="utf-8",
    )
    override = root / "docs" / ".icons" / "fontawesome" / "solid" / "note-sticky.svg"
    if project_override:
        override.parent.mkdir(parents=True)
        override.write_text('<svg><path fill="project-owned"/></svg>', encoding="utf-8")
    captured = {}

    def capture(_pages, _output_path, **kwargs):
        captured["registry"] = kwargs["icon_registry"]

    monkeypatch.setattr(config, "build_pdf", capture)
    monkeypatch.setattr(config, "publish_pdf_to_built_site", lambda *_args: None)

    build_pdf_from_built_site(str(root / "zensical.toml"))

    icon = captured["registry"]["fontawesome-solid-note-sticky"]
    if project_override:
        assert icon == str(override)
    else:
        assert 'fill="compiled-site"' in icon


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


@pytest.mark.parametrize(
    "renderer",
    [build_pdf_from_built_site, build_pdf_from_zensical_config],
)
def test_complete_pdf_omits_a_website_only_navigation_page(
    project, monkeypatch: pytest.MonkeyPatch, renderer
) -> None:
    root = project()
    (root / "docs" / "chapter1.md").write_text(
        "---\npdf_include: false\n---\n\n# Website only\n", encoding="utf-8"
    )

    captured = {}

    if renderer is build_pdf_from_built_site:
        monkeypatch.setattr(config, "validate_built_site", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(config, "page_html", lambda _config, source: f"<h1>{source}</h1>")
        monkeypatch.setattr(config, "publish_pdf_to_built_site", lambda *_args: None)

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config, "build_pdf", _spy)
    renderer(str(root / "zensical.toml"))

    assert [page.docs_rel_path for page in captured["pages"]] == ["index.md"]


def test_single_page_pdf_ignores_the_website_only_flag(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    (root / "docs" / "chapter1.md").write_text(
        "---\npdf_include: false\n---\n\n# Website only\n", encoding="utf-8"
    )
    captured = {}

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"), markdown_file="chapter1.md")

    assert [page.docs_rel_path for page in captured["pages"]] == ["chapter1.md"]


def test_only_the_first_navigation_index_is_the_pdf_cover(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    about = root / "docs" / "about"
    about.mkdir()
    (about / "index.md").write_text("# About\n", encoding="utf-8")
    (root / "zensical.toml").write_text(
        """[project]
site_name = "Test project"
nav = [
  {"Home" = "index.md"},
  {"Chapter" = "chapter1.md"},
  {"About" = [{"Overview" = "about/index.md"}]},
]
""",
        encoding="utf-8",
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    pages_by_path = {page.docs_rel_path: page for page in captured["pages"]}
    assert pages_by_path["index.md"].is_index is True
    assert pages_by_path["about/index.md"].is_index is False


def test_built_site_pdf_uses_manual_then_file_revision_dates(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project()
    chapter = root / "docs" / "chapter1.md"
    chapter.write_text(
        "---\nrevision_date: 2020-01-02\n---\n\n# Chapter One\n",
        encoding="utf-8",
    )
    index = root / "docs" / "index.md"
    timestamp = 1_726_012_800  # 2024-09-11T00:00:00Z
    os.utime(index, (timestamp, timestamp))
    captured = {}

    monkeypatch.setattr(config, "validate_built_site", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(config, "page_html", lambda _config, source: f"<h1>{source}</h1>")
    monkeypatch.setattr(config, "publish_pdf_to_built_site", lambda *_args: None)

    def _spy(pages, output_path, **kwargs):
        captured["pages"] = pages

    monkeypatch.setattr(config, "build_pdf", _spy)
    build_pdf_from_built_site(str(root / "zensical.toml"))

    pages = {page.docs_rel_path: page for page in captured["pages"]}
    assert pages["index.md"].revision_date == "2024-09-11"
    assert pages["chapter1.md"].revision_date == "2020-01-02"


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
    there. build_pdf() places the generated renderer foundation beneath
    this complete project stylesheet sequence."""
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
    (styles_dir / "print.css").write_text('.logo { content: url("logo.png"); }\n', encoding="utf-8")

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


def _write_git_project(tmp_path: Path, *, extra: str = "") -> Path:
    """Like `_write_project()`, plus an actual git repo -
    `build_source_bundle_from_zensical_config()` needs one, since file
    selection goes through `git ls-files`."""
    root = _write_project(tmp_path, extra=extra)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def _fake_weasyprint(bin_dir: Path, script: str) -> None:
    weasyprint_path = bin_dir / "weasyprint"
    weasyprint_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    weasyprint_path.chmod(weasyprint_path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture()
def source_bundle_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make(*, extra: str = "") -> Path:
        root = _write_git_project(tmp_path, extra=extra)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        _fake_weasyprint(bin_dir, 'echo "%PDF-1.4 stub" > "$2"')
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.chdir(root)
        return root

    return _make


def test_source_bundle_defaults_into_docs_dir(source_bundle_project) -> None:
    """Not the project's top-level directory - the pre-#212 default - so
    Zensical serves it with no separate copy step
    (prodockit-extensions#212)."""
    root = source_bundle_project()

    output_path = build_source_bundle_from_zensical_config(str(root / "zensical.toml"))

    assert output_path == "docs/source_bundle.pdf"
    assert (root / "docs" / "source_bundle.pdf").exists()
    assert not (root / "source_bundle.pdf").exists()


def test_source_bundle_output_path_is_configurable(source_bundle_project) -> None:
    root = source_bundle_project(
        extra='\n[project.extra]\npdf_source_bundle_output = "dist/src.pdf"\n'
    )
    (root / "dist").mkdir()

    output_path = build_source_bundle_from_zensical_config(str(root / "zensical.toml"))

    assert output_path == "dist/src.pdf"
    assert (root / "dist" / "src.pdf").exists()


def test_source_bundle_report_name_is_the_site_name(
    source_bundle_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = source_bundle_project()

    captured = {}

    def _spy(output_path, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(config, "build_source_bundle", _spy)
    build_source_bundle_from_zensical_config(str(root / "zensical.toml"))

    assert captured["report_name"] == "Test project"


def test_source_bundle_page_size_is_shared_with_the_pdf_setting(
    source_bundle_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One physical page size for both PDFs a project publishes, from the
    same `pdf_page_size` setting the main document build already reads -
    not a second, source-bundle-specific setting to keep in step."""
    root = source_bundle_project(extra='\n[project.extra]\npdf_page_size = "Letter"\n')

    captured = {}

    def _spy(output_path, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(config, "build_source_bundle", _spy)
    build_source_bundle_from_zensical_config(str(root / "zensical.toml"))

    assert captured["page_size"] == "Letter"


def test_source_bundle_uses_the_narrow_discovery_not_every_source_file(
    source_bundle_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirms the wiring, not just the discovery function in isolation:
    a project's own Python source must not reach the bundle just because
    it happens to be tracked in git."""
    root = source_bundle_project()
    (root / "README.md").write_text("# Report\n", encoding="utf-8")
    for generated in ("CHANGELOG.md", "CONTRIBUTING.md", "LICENSE.md"):
        (root / generated).write_text("generated\n", encoding="utf-8")
    (root / "macros.py").write_text("def word_count(): ...\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    work_dir = root / "work"
    real_build_source_bundle = config.build_source_bundle

    def _spy(output_path, **kwargs):
        return real_build_source_bundle(
            output_path, **{**kwargs, "work_dir": str(work_dir), "keep_work_dir": True}
        )

    monkeypatch.setattr(config, "build_source_bundle", _spy)
    build_source_bundle_from_zensical_config(str(root / "zensical.toml"))

    html = (work_dir / "_prodockit_source_bundle.html").read_text(encoding="utf-8")
    assert 'class="file-marker">README.md<' in html
    assert 'class="file-marker">docs/index.md<' in html
    assert 'class="file-marker">zensical.toml<' in html
    assert "macros.py" not in html
    for generated in ("CHANGELOG.md", "CONTRIBUTING.md", "LICENSE.md"):
        assert generated not in html


def test_pdf_never_builds_a_source_bundle_as_a_side_effect(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pdf_source_bundle` used to gate an automatic `build_source_bundle()`
    call here - split into its own `build_source_bundle_from_zensical_config()`
    and `prodockit source-bundle` command (prodockit-extensions#212), so a
    document-only build no longer pays for a source-bundle pass it never
    asked for. The old setting is now inert rather than read at all, with
    or without `markdown_file`."""
    root = project(extra="\n[project.extra]\npdf_source_bundle = true\n")

    captured = {"called": False}
    import prodockit.pdf.config as config_module

    def _spy(*args, **kwargs):
        captured["called"] = True

    monkeypatch.setattr(config_module, "build_source_bundle", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))
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


def test_old_extra_index_names_are_not_read(project, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(
        extra=('\n[project.extra]\npdf_include_index = true\npdf_index_title = "Old title"\n')
    )

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["include_index"] = kwargs["include_index"]
        captured["index_title"] = kwargs["index_title"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured == {"include_index": False, "index_title": "Index"}


def test_include_index_reads_from_the_extension_and_a_custom_title(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(
        extra=(
            '\n[project.markdown_extensions."prodockit.index"]\ninclude = true\n'
            'title = "Glossary of Terms"\n'
        )
    )

    parsed = parse_zensical_config(root / "zensical.toml")
    assert parsed["mdx_configs"]["prodockit.index"] == {
        "include": True,
        "title": "Glossary of Terms",
    }

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["include_index"] = kwargs["include_index"]
        captured["index_title"] = kwargs["index_title"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["include_index"] is True
    assert captured["index_title"] == "Glossary of Terms"


@pytest.mark.parametrize(
    "setting",
    ['include = "false"', "include = 1", 'title = ""', 'title = "   "', "title = 1"],
)
def test_invalid_index_configuration_is_rejected_by_pdf_build(project, setting: str) -> None:
    root = project(
        extra=f'\n[project.markdown_extensions."prodockit.index"]\n{setting}\n'
    )

    with pytest.raises(ValueError, match=r"prodockit\.index"):
        build_pdf_from_zensical_config(str(root / "zensical.toml"))


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
    (root / "docs" / "index.md").write_text("Before\nRelease: {RELEASE}\nAfter\n", encoding="utf-8")
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


@pytest.mark.parametrize("marker", ["{{ config.site_name }}", "{{ site_name }}"])
def test_site_name_marker_is_substituted_literally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    root = _write_project(tmp_path)
    (root / "docs" / "index.md").write_text(f"Project: {marker}\n", encoding="utf-8")
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


# ---------------------------------------------------------------------------
# copyright/site_name: copyright is a raw HTML fragment (real DOM element -
# see prodockit.pdf.css/build.py), site_name is still CSS-content-string
# escaped (a plain content: "..." string)
# ---------------------------------------------------------------------------


def _write_custom_project(tmp_path: Path, project_toml: str) -> Path:
    """Like _write_project(), but with full control over [project]'s own
    keys (site_name/copyright) from the start - _ZENSICAL_TOML/project()
    already set both, so appending a second [project] table via extra=
    is a TOML duplicate-table error."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Cover\n", encoding="utf-8")
    (docs_dir / "chapter1.md").write_text("# Chapter One\n\nBody text.\n", encoding="utf-8")
    (tmp_path / "zensical.toml").write_text(project_toml, encoding="utf-8")
    return tmp_path


def test_copyright_with_a_real_link_is_passed_through_unescaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project.copyright is a real HTML fragment now (see
    prodockit.pdf.build.build_pdf's own copyright_text docs) - a real
    <a href="..."> link (or any other markup) passes straight through to
    build_pdf(), not escaped/flattened into a CSS content string the way
    site_name still is."""
    root = _write_custom_project(
        tmp_path,
        '[project]\nsite_name = "Test project"\n'
        'copyright = "Copyright 2026. Made with <a href=\\"https://zensical.org/\\">Zensical</a>."\n'
        'nav = [{"Home" = "index.md"}, {"Chapter" = "chapter1.md"}]\n',
    )
    monkeypatch.chdir(root)

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["copyright_text"] = kwargs["copyright_text"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["copyright_text"] == (
        'Copyright 2026. Made with <a href="https://zensical.org/">Zensical</a>.'
    )


def test_pdf_copyright_falls_back_to_project_copyright_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_custom_project(
        tmp_path,
        '[project]\nsite_name = "Test project"\n'
        'copyright = "Copyright test"\n'
        'nav = [{"Home" = "index.md"}, {"Chapter" = "chapter1.md"}]\n',
    )
    monkeypatch.chdir(root)

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["copyright_text"] = kwargs["copyright_text"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["copyright_text"] == "Copyright test"


def test_pdf_copyright_overrides_project_copyright_for_the_pdf_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """extra.pdf_copyright, when set, is what the PDF's own running
    footer shows instead of project.copyright - e.g. a second line (a real
    <br>, now that this is a real HTML fragment rather than a CSS content
    string) crediting the PDF pipeline specifically, without also adding
    that same markup to the live website's copyright text (which always
    reads project.copyright directly, untouched by this setting)."""
    root = _write_custom_project(
        tmp_path,
        '[project]\nsite_name = "Test project"\n'
        'copyright = "Copyright test"\n'
        'nav = [{"Home" = "index.md"}, {"Chapter" = "chapter1.md"}]\n\n'
        "[project.extra]\n"
        'pdf_copyright = "Copyright test<br>Made with Zensical and prodockit."\n',
    )
    monkeypatch.chdir(root)

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["copyright_text"] = kwargs["copyright_text"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["copyright_text"] == "Copyright test<br>Made with Zensical and prodockit."


def test_site_name_passed_to_build_pdf_is_also_css_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The site_name kwarg passed to build_pdf() (the running header/footer
    CSS) is escaped the same way copyright_text is - separate from the
    {{ config.site_name }} cover-page marker substitution, which uses the raw,
    unescaped value since it's substituted into HTML, not CSS."""
    root = _write_custom_project(
        tmp_path,
        '[project]\nsite_name = "Say \\"hi\\""\n'
        'copyright = "Copyright test"\n'
        'nav = [{"Home" = "index.md"}, {"Chapter" = "chapter1.md"}]\n',
    )
    monkeypatch.chdir(root)

    captured = {}
    import prodockit.pdf.config as config_module

    def _spy(pages, output_path, **kwargs):
        captured["site_name"] = kwargs["site_name"]

    monkeypatch.setattr(config_module, "build_pdf", _spy)
    build_pdf_from_zensical_config(str(root / "zensical.toml"))

    assert captured["site_name"] == 'Say \\"hi\\"'


# --- Release-source disagreement (#125) ------------------------------------
#
# `{{ git.short_tag }}` (website) describes the local checkout;
# `{RELEASE}` (PDF) queries the host's releases API. Both are deliberate, and
# neither changes here - but a disagreement between them used to be entirely
# invisible, so a reader could see two different release numbers with nothing
# having failed.


def test_no_warning_when_both_release_sources_agree(monkeypatch, capsys) -> None:
    monkeypatch.setattr("prodockit.pdf.config._get_release", lambda: "v1.2.0")
    assert _warn_if_release_sources_disagree("v1.2.0") is None
    assert capsys.readouterr().out == ""


def test_warns_when_the_two_release_sources_differ(monkeypatch, capsys) -> None:
    monkeypatch.setattr("prodockit.pdf.config._get_release", lambda: "v1.1.0")
    message = _warn_if_release_sources_disagree("v1.2.0")
    assert message is not None
    out = capsys.readouterr().out
    # Both values named, so the reader can tell which output shows which.
    assert "v1.2.0" in out
    assert "v1.1.0" in out


def test_warns_when_a_tag_exists_but_no_release_is_published(monkeypatch, capsys) -> None:
    """The website shows a release line here and the PDF drops it - a
    divergence that looks like nothing went wrong."""
    monkeypatch.setattr("prodockit.pdf.config._get_release", lambda: "v1.2.0")
    _warn_if_release_sources_disagree("")
    out = capsys.readouterr().out
    assert "v1.2.0" in out
    assert "dropped" in out


def test_warns_when_the_checkout_has_no_tags(monkeypatch, capsys) -> None:
    """The shallow-clone case: the PDF shows a release, the website shows
    nothing at all."""
    monkeypatch.setattr("prodockit.pdf.config._get_release", lambda: "")
    _warn_if_release_sources_disagree("v1.2.0")
    out = capsys.readouterr().out
    assert "v1.2.0" in out
    assert "shallow clone" in out


def test_no_warning_when_neither_source_has_a_release(monkeypatch, capsys) -> None:
    """The common case for a project that has never tagged or released -
    nothing is wrong, so nothing should be said."""
    monkeypatch.setattr("prodockit.pdf.config._get_release", lambda: "")
    assert _warn_if_release_sources_disagree("") is None
    assert capsys.readouterr().out == ""

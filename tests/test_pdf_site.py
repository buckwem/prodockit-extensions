# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from prodockit.pdf.site import (
    BuiltSiteError,
    _icon_probe_source,
    _read_icon_probe,
    _zensical_cli,
    build_site,
    output_path,
    page_html,
    page_metadata,
)
from prodockit.project_config import load_project_config


def _config(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "site").mkdir()
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name = "Test"\n', encoding="utf-8")
    return load_project_config(path)


@pytest.mark.parametrize(
    ("source", "directory_urls", "expected"),
    [
        ("index.md", True, "index.html"),
        ("guide/index.md", True, "guide/index.html"),
        ("guide/start.md", True, "guide/start/index.html"),
        ("guide/start.md", False, "guide/start.html"),
    ],
)
def test_output_path_matches_zensical_routing(
    tmp_path: Path, source: str, directory_urls: bool, expected: str
) -> None:
    assert output_path(source, tmp_path, directory_urls=directory_urls) == tmp_path / expected


def test_page_html_extracts_content_and_drops_website_only_controls(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text(
        '<html><article class="md-content__inner md-typeset">'
        '<a class="md-content__button md-icon">edit</a>'
        '<h1 id="hello">Hello</h1><p>Body</p>'
        '<nav class="md-tags"><a class="md-tag">Get started</a></nav>'
        '<div class="md-feedback"><button>Helpful?</button></div>'
        '<footer class="sponsorship"><a href="/sponsor">Sponsor</a></footer>'
        "</article></html>",
        encoding="utf-8",
    )

    html = page_html(config, "index.md")

    assert "md-content__button" not in html
    assert "md-tags" not in html
    assert "Get started" not in html
    assert "md-feedback" not in html
    assert "Helpful?" not in html
    assert "sponsorship" not in html
    assert "Sponsor" not in html
    assert '<h1 id="hello">Hello</h1>' in html
    assert "<p>Body</p>" in html


def test_page_html_preserves_comments_as_comments(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text(
        '<article class="md-content__inner md-typeset">'
        "<!-- internal author note -->"
        "<p>Visible</p></article>",
        encoding="utf-8",
    )

    html = page_html(config, "index.md")

    assert "<!-- internal author note -->" in html
    assert html.endswith("<p>Visible</p>")


def test_page_html_fails_clearly_when_article_layout_changes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.site_dir / "index.html").write_text("<main>content</main>", encoding="utf-8")

    with pytest.raises(BuiltSiteError, match="generated HTML layout changed"):
        page_html(config, "index.md")


def test_page_metadata_reads_pdf_fields(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(
        '---\nis_appendix: true\nrecto_title: "Short"\npdf_include: false\n---\n# Page\n',
        encoding="utf-8",
    )
    assert page_metadata(page) == {
        "is_appendix": True,
        "recto_title": "Short",
        "pdf_include": False,
    }


def test_build_site_uses_only_the_documented_cli(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    seen = {}

    def run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("prodockit.pdf.site.subprocess.run", run)
    monkeypatch.setattr("prodockit.pdf.site._zensical_cli", lambda: "zensical")
    build_site(config)

    assert seen["command"] == [
        "zensical",
        "build",
        "--clean",
        "--config-file",
        str(config.path),
    ]
    assert seen["kwargs"]["cwd"] == config.root


def test_zensical_cli_comes_from_the_active_python_environment(tmp_path: Path, monkeypatch) -> None:
    scripts = tmp_path / "bin"
    scripts.mkdir()
    python = scripts / "python"
    zensical = scripts / "zensical"
    zensical.touch()
    monkeypatch.setattr("prodockit.pdf.site.sys.executable", str(python))

    assert _zensical_cli() == str(zensical)


def test_icon_probe_uses_configured_shortcodes_and_reads_rendered_svgs(tmp_path: Path) -> None:
    icons = {
        "note": "fontawesome/solid/note-sticky",
        "warning": "fontawesome/solid/triangle-exclamation",
    }
    source = _icon_probe_source(icons)
    assert ":fontawesome-solid-note-sticky:" in source
    assert "## prodockit-icon-warning" in source

    built = tmp_path / "probe.html"
    built.write_text(
        '<h2 id="prodockit-icon-note">note</h2>'
        '<p><span><svg viewBox="0 0 1 1"><path d="M0 0"/></svg></span></p>'
        '<h2 id="prodockit-icon-warning">warning</h2>'
        '<p><svg viewBox="0 0 2 2"><path d="M1 1"/></svg></p>',
        encoding="utf-8",
    )

    registry = _read_icon_probe(built, icons)

    assert '<svg viewBox="0 0 1 1">' in registry["fontawesome-solid-note-sticky"]
    assert '<svg viewBox="0 0 2 2">' in registry["fontawesome-solid-triangle-exclamation"]


def test_build_site_icon_probe_is_removed_after_the_build(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    icons = {"note": "fontawesome/solid/note-sticky"}

    def run(_command, **_kwargs):
        output = config.site_dir / ".prodockit-pdf-icon-probe" / "index.html"
        output.parent.mkdir(parents=True)
        output.write_text(
            '<h2 id="prodockit-icon-note">note</h2><p><svg><path/></svg></p>',
            encoding="utf-8",
        )
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("prodockit.pdf.site.subprocess.run", run)

    registry = build_site(config, icons)

    assert "fontawesome-solid-note-sticky" in registry
    assert not (config.docs_dir / ".prodockit-pdf-icon-probe.md").exists()
    assert not (config.site_dir / ".prodockit-pdf-icon-probe").exists()


def test_build_site_refuses_to_overwrite_an_existing_probe(tmp_path: Path) -> None:
    config = _config(tmp_path)
    probe = config.docs_dir / ".prodockit-pdf-icon-probe.md"
    probe.write_text("author's file", encoding="utf-8")

    with pytest.raises(BuiltSiteError, match="would overwrite"):
        build_site(config, {"note": "fontawesome/solid/note-sticky"})

    assert probe.read_text(encoding="utf-8") == "author's file"

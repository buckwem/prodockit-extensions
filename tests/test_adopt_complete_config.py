# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Regression coverage for the plain-Zensical installation reported in #782."""

from pathlib import Path

import markdown
import pytest

from prodockit.adopt import (
    AdoptError,
    AdoptOptions,
    ensure_zensical_config,
    resolve_options,
    write_manifest,
)
from prodockit.project_config import load_project_config


@pytest.mark.parametrize(
    "filename,source",
    [
        ("zensical.toml", '[project]\nsite_name = "My site"\n'),
        ("mkdocs.yml", "site_name: My site\n"),
    ],
)
def test_adopted_caption_configuration_renders_and_preserves_values(tmp_path, filename, source):
    path = tmp_path / filename
    path.write_text(source)
    ensure_zensical_config(tmp_path, AdoptOptions())
    first = path.read_text()
    config = load_project_config(path)
    assert config.site_name == "My site"
    assert config.extra["pdf_page_size"] == "A4"
    assert config.extra["pdf_margin_bottom"] == "2.5cm"
    caption = config.markdown_extensions["pymdownx.blocks.caption"]
    html = markdown.markdown(
        "![Example](example.png)\n\n/// figure-caption\nAn example figure\n///",
        extensions=["pymdownx.blocks.caption"],
        extension_configs={"pymdownx.blocks.caption": caption},
    )
    assert "prodockit-figure-caption" in html
    assert "<figcaption>" in html
    assert "///" not in html
    ensure_zensical_config(tmp_path, AdoptOptions())
    assert path.read_text() == first


def test_existing_broken_renderer_is_detected_but_explicit_opt_out_wins(tmp_path):
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Site"\n')
    renderer = tmp_path / "tools" / "mathjax"
    renderer.mkdir(parents=True)
    (renderer / "package.json").write_text('{"dependencies":{"mathjax-full":"3.2.2"}}')
    assert resolve_options(tmp_path).options == AdoptOptions(maths=True)
    write_manifest(tmp_path, AdoptOptions())
    assert resolve_options(tmp_path).options == AdoptOptions()


def test_author_pdf_defaults_are_preserved(tmp_path: Path):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name = "Mine"\nextra.pdf_page_size = "letter" # keep\n')
    ensure_zensical_config(tmp_path, AdoptOptions())
    assert 'extra.pdf_page_size = "letter" # keep' in path.read_text()
    assert load_project_config(path).extra["pdf_page_size"] == "letter"


def test_failed_config_replacement_keeps_original(tmp_path: Path, monkeypatch):
    path = tmp_path / "zensical.toml"
    source = '[project]\nsite_name = "Mine"\n'
    path.write_text(source)

    def denied(*args):
        raise PermissionError("test replacement denied")

    monkeypatch.setattr("prodockit.adopt.os.replace", denied)
    with pytest.raises(AdoptError, match="could not safely update"):
        ensure_zensical_config(tmp_path, AdoptOptions())
    assert path.read_text() == source
    assert list(tmp_path.iterdir()) == [path]


def test_second_configuration_pass_does_not_rewrite(tmp_path: Path):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name = "Mine"\n')
    ensure_zensical_config(tmp_path, AdoptOptions())
    before = path.stat().st_mtime_ns
    ensure_zensical_config(tmp_path, AdoptOptions())
    assert path.stat().st_mtime_ns == before


def test_toml_edit_preserves_user_comments_and_literal_values(tmp_path: Path):
    path = tmp_path / "zensical.toml"
    path.write_text(
        "# My project configuration\n[project]\n"
        "site_name = 'My site' # keep this comment\n"
        "extra_css = [\n  'stylesheets/custom.css', # my styling\n]\n"
        "[project.extra]\n"
        "custom = { label = 'Keep me', count = 3 } # user settings\n"
    )
    ensure_zensical_config(tmp_path, AdoptOptions())
    source = path.read_text()
    assert "# My project configuration" in source
    assert "site_name = 'My site' # keep this comment" in source
    assert "'stylesheets/custom.css', # my styling" in source
    assert "custom = { label = 'Keep me', count = 3 } # user settings" in source
    ensure_zensical_config(tmp_path, AdoptOptions())
    assert path.read_text() == source


def test_quoted_false_cannot_accidentally_enable_a_renderer(tmp_path: Path):
    (tmp_path / ".prodockit-components.toml").write_text('[components]\nmermaid = "false"\n')
    with pytest.raises(AdoptError, match="must be TOML true or false"):
        resolve_options(tmp_path)


def test_template_examples_are_commented_without_branding(tmp_path: Path):
    from prodockit.adopt_settings import Snapshot

    snapshot = Snapshot(
        '[project]\nsite_name = "Template branding"\n'
        '[project.extra]\npdf_copyright = "Template footer"\npdf_margin_bottom = "2.75cm"\n'
        '[project.markdown_extensions."prodockit.headings"]\nnumbering = "continuous"\n'
        '[project.markdown_extensions."prodockit.bibliography"]\n'
        'bib_file = "references.bib"\ncsl_style = "harvard-cite-them-right.csl"\n',
        "test:template",
    )
    options = AdoptOptions(template_snapshot=snapshot)
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name = "Mine"\n')
    ensure_zensical_config(tmp_path, options)
    source = path.read_text()
    config = load_project_config(path)
    assert '# "numbering" = "continuous"' in source
    assert '# "bib_file" = "references.bib"' in source
    assert '# "csl_style" = "harvard-cite-them-right.csl"' in source
    assert "template.css" not in source
    assert "Template branding" not in source
    assert "Template footer" not in source
    assert "numbering" not in config.markdown_extensions["prodockit.headings"]
    assert "csl_style" not in config.markdown_extensions["prodockit.bibliography"]
    assert config.extra["pdf_margin_bottom"] == "2.5cm"
    assert "pdf_copyright" not in config.extra
    assert config.site_name == "Mine"
    ensure_zensical_config(tmp_path, options)
    assert path.read_text() == source


def test_template_nested_blocks_caption_is_preserved(tmp_path: Path):
    from prodockit.adopt import CAPTION_TYPES, _extensions, _toml_value, tomllib

    path = tmp_path / "zensical.toml"
    path.write_text(
        '[project]\nsite_name = "Mine"\n'
        "[project.markdown_extensions.pymdownx.blocks.caption]\n"
        f"types = {_toml_value(list(CAPTION_TYPES))}\n"
    )
    ensure_zensical_config(tmp_path, AdoptOptions())
    source = path.read_text()
    assert source.count("types =") == 1
    assert load_project_config(path).markdown_extensions["pymdownx.blocks.caption"][
        "types"
    ] == list(CAPTION_TYPES)
    assert "pymdownx.blocks.caption" in _extensions(tomllib.loads(source))
    ensure_zensical_config(tmp_path, AdoptOptions())
    assert path.read_text() == source

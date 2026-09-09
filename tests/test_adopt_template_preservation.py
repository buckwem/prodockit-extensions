# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""File alignment must preserve template-owned and author-owned content."""

import pytest

from prodockit import adopt, adopt_renderers


@pytest.mark.parametrize(
    "filename,source",
    [
        ("requirements.txt", "prodockit>=999.0.0\n"),
        ("requirements.txt", "prodockit==999.0.0\n"),
        (".prodockit-toolchain.toml", '[packages]\nprodockit = "999.0.0"\n'),
    ],
)
def test_newer_project_blocks_assessment_and_direct_apply(tmp_path, filename, source):
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Newer"\n')
    (tmp_path / filename).write_text(source)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    steps = adopt.assess(tmp_path, adopt.AdoptOptions())
    assert len(steps) == 1
    assert steps[0].status == "wrong"
    assert filename in steps[0].detail
    assert "999.0.0" in steps[0].detail
    with pytest.raises(adopt.AdoptError, match="No project files or software"):
        adopt.apply_step(tmp_path, adopt.AdoptOptions(), "toolchain")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("version", ["0.1.0", adopt.__version__])
def test_same_or_older_project_can_align_to_installed_release(tmp_path, version):
    (tmp_path / "requirements.txt").write_text(f"prodockit>={version}\n")
    adopt._check_project_release(tmp_path)


def test_template_assets_survive_alignment_and_repeat(tmp_path):
    config = tmp_path / "zensical.toml"
    config.write_text("""[project]
site_name = "Template project"
extra_css = ["stylesheets/pdk.css", "stylesheets/template.css", "stylesheets/extra.css"]
extra_javascript = ["javascripts/pdk.js", "javascripts/template.js", "javascripts/extra.js"]
[project.extra]
pdf_extra_css = ["stylesheets/pdk-pdf.css", "stylesheets/print.css"]
""")
    preserved = {
        "docs/stylesheets/template.css": "/* template */",
        "docs/stylesheets/extra.css": "/* author */",
        "docs/stylesheets/print.css": "/* author print */",
        "docs/javascripts/template.js": "// template",
        "docs/javascripts/extra.js": "// author",
        "docs/index.md": "# My content",
        ".gitlab-ci.yml": "# publishing pipeline",
        ".prodockit-template.json": '{"version": "test"}',
    }
    for name, content in preserved.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def align():
        adopt.ensure_zensical_config(tmp_path, adopt.AdoptOptions())
        adopt.ensure_stylesheets(tmp_path)
        adopt.ensure_javascripts(tmp_path)
        for component in ("mermaid", "mathjax"):
            adopt_renderers.align(tmp_path, component, write=adopt._atomic_write)

    align()
    first = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    align()
    second = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second
    for name, content in preserved.items():
        assert (tmp_path / name).read_text() == content
    assert "stylesheets/template.css" in config.read_text()
    assert "javascripts/template.js" in config.read_text()
    assert not (tmp_path / adopt_renderers.BACKUPS).exists()

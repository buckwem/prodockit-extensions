# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""File alignment must preserve template-owned and author-owned content."""

from prodockit import adopt, adopt_renderers


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

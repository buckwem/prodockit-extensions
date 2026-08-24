# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The project-scoped adoption workflow for existing Zensical documents."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from prodockit import __version__
from prodockit.adopt import (
    CORE_EXTENSIONS,
    MANIFEST,
    STYLESHEET,
    AdoptOptions,
    assess,
    ensure_requirement,
    ensure_stylesheet,
    ensure_zensical_config,
    install_tool,
    load_manifest,
)
from prodockit.cli import main


def _project(
    tmp_path: Path,
    config: str | None = None,
    *,
    config_name: str = "zensical.toml",
) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Existing document\n", encoding="utf-8")
    (tmp_path / config_name).write_text(
        config
        or """\
[project]
site_name = "Existing document"
nav = [{ Home = "index.md" }]

[project.markdown_extensions.toc]
""",
        encoding="utf-8",
    )
    return tmp_path


def test_help_sets_the_existing_project_boundary() -> None:
    result = CliRunner().invoke(main, ["adopt", "--help"])

    assert result.exit_code == 0
    output = " ".join(result.output.split())
    assert "existing Zensical or MkDocs document" in output
    assert "virtual environment active" in output
    assert "does not configure Git, SSH, an editor" in output
    assert "--mermaid" in result.output and "--maths" in result.output


def test_report_uses_prominent_phases_and_stages(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    result = CliRunner().invoke(main, ["adopt", "--dry-run"], color=False)

    assert result.exit_code == 0, result.output
    assert "Phase 1/4 — Assess" in result.output
    assert "Stage [3/7] Prodockit dependency" in result.output
    assert "Mermaid diagrams — not selected" in result.output
    assert "Mathematical notation — not selected" in result.output
    assert "Git, SSH, remotes, editors, commits and pushes" in result.output


def test_configure_records_mermaid_and_maths_as_independent_choices(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)

    result = CliRunner().invoke(main, ["adopt", "--configure"], input="y\nn\n")

    assert result.exit_code == 0, result.output
    assert load_manifest(project) == AdoptOptions(mermaid=True, maths=False)
    assert "Mermaid diagrams" in result.output
    assert "mathematical notation" in result.output


def test_core_adoption_preserves_existing_config_and_adds_a_floor(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Mine"
extra_css = ["stylesheets/mine.css"]

[project.theme]
language = "en-GB"
""",
    )
    ensure_requirement(project)
    ensure_stylesheet(project)
    ensure_zensical_config(project, AdoptOptions())

    requirements = (project / "requirements.txt").read_text(encoding="utf-8")
    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert f"prodockit>={__version__}" in requirements
    assert "prodockit==" not in requirements
    assert 'site_name = "Mine"' in config
    assert 'language = "en-GB"' in config
    assert '"stylesheets/mine.css"' in config
    assert '"stylesheets/prodockit.css"' in config
    for extension in CORE_EXTENSIONS:
        assert f'[project.markdown_extensions."{extension}"]' in config
    assert (project / STYLESHEET).is_file()


def test_toml_without_extensions_preserves_zensical_markdown_defaults(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Implicit defaults"
""",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert '[project.markdown_extensions."toc"]\npermalink = true' in config
    assert '[project.markdown_extensions."pymdownx.highlight"]' in config
    assert 'line_spans = "__span"' in config
    assert '[project.markdown_extensions."pymdownx.superfences"]' in config
    assert 'custom_fences = [{ name = "mermaid", class = "mermaid" }]' in config


def test_yaml_without_extensions_preserves_zensical_markdown_defaults(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        "site_name: Implicit defaults\n",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "  toc:\n    permalink: true" in config
    assert "  pymdownx.highlight:" in config
    assert "    line_spans: __span" in config
    assert "  pymdownx.superfences:" in config
    assert "    custom_fences:" in config
    assert "    - name: mermaid" in config


def test_requirement_replaces_an_exact_pin_with_a_floor(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "requirements.txt").write_text(
        "zensical>=0.0.55\nprodockit==0.40.0  # old\n", encoding="utf-8"
    )

    ensure_requirement(project)

    text = (project / "requirements.txt").read_text(encoding="utf-8")
    assert f"prodockit>={__version__}  # old" in text
    assert "prodockit==" not in text


def test_existing_documentation_requirements_file_is_used(tmp_path: Path) -> None:
    project = _project(tmp_path)
    requirements = project / "requirements" / "docs.txt"
    requirements.parent.mkdir()
    requirements.write_text("zensical\n", encoding="utf-8")

    path = ensure_requirement(project)

    assert path == requirements
    assert f"prodockit>={__version__}" in requirements.read_text(encoding="utf-8")
    assert not (project / "requirements.txt").exists()


def test_mermaid_option_does_not_add_math_configuration(tmp_path: Path) -> None:
    project = _project(tmp_path)

    ensure_zensical_config(project, AdoptOptions(mermaid=True, maths=False))

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert "pymdownx.superfences" in config
    assert 'name = "mermaid"' in config
    assert "pymdownx.arithmatex" not in config
    assert "javascripts/mathjax.js" not in config


def test_maths_option_adds_generic_arithmatex_and_scripts(tmp_path: Path) -> None:
    project = _project(tmp_path)

    ensure_zensical_config(project, AdoptOptions(mermaid=False, maths=True))

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert "pymdownx.arithmatex" in config
    assert "generic = true" in config
    assert "javascripts/mathjax.js" in config
    assert "javascripts/vendor/mathjax/tex-svg-full.js" in config
    assert 'name = "mermaid"' not in config


def test_config_updates_are_idempotent(tmp_path: Path) -> None:
    project = _project(tmp_path)
    options = AdoptOptions(mermaid=True, maths=True)

    ensure_zensical_config(project, options)
    first = (project / "zensical.toml").read_text(encoding="utf-8")
    ensure_zensical_config(project, options)

    assert (project / "zensical.toml").read_text(encoding="utf-8") == first


def test_zensical_toml_extension_array_is_extended_in_place(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Array configuration"
markdown_extensions = [
  "toc",
  "pymdownx.superfences",
  "pymdownx.arithmatex",
]
extra_css = ["stylesheets/mine.css"]

[[project.extra.items]]
name = "Later array table"
""",
    )

    ensure_zensical_config(project, AdoptOptions(mermaid=True, maths=True))

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert '"prodockit.headings"' in config
    assert '[project.markdown_extensions."prodockit.headings"]' not in config
    assert '"pymdownx.arithmatex" = { generic = true }' in config
    assert '"pymdownx.superfences" = { custom_fences = [' in config
    assert 'name = "Later array table"' in config


def test_apply_core_never_invokes_git_or_editor_setup(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    result = CliRunner().invoke(main, ["adopt", "--apply"], input="y\ny\n")

    assert result.exit_code == 0, result.output
    assert (project / "requirements.txt").is_file()
    assert (project / STYLESHEET).is_file()
    assert not (project / ".vscode").exists()
    assert "Nothing has been committed or pushed" in result.output


def test_report_refuses_a_directory_without_zensical_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["adopt"])

    assert result.exit_code == 1
    assert "zensical.toml, zensical.yml, zensical.yaml" in result.output
    assert "mkdocs.yml or mkdocs.yaml" in result.output


def test_assessment_skips_unselected_node_components(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    steps = assess(project, AdoptOptions())

    optional = {step.id: step for step in steps if step.id in {"mermaid", "maths"}}
    assert optional["mermaid"].selected is False
    assert optional["maths"].selected is False
    assert not (project / "tools").exists()


def test_manifest_is_not_needed_until_choices_are_saved(tmp_path: Path) -> None:
    project = _project(tmp_path)

    assert load_manifest(project) == AdoptOptions()
    assert not (project / MANIFEST).exists()


def test_mermaid_install_uses_only_the_selected_node_project(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")

    def npm(command, **_kwargs):
        assert command[0] == "/usr/bin/npm"
        assert command[-1].endswith("tools/mermaid")
        binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("renderer", encoding="utf-8")
        (project / "tools" / "mermaid" / "package-lock.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)

    written = install_tool(project, "mermaid")

    assert any(path.name == "package-lock.json" for path in written)
    assert (project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc").is_file()
    assert not (project / "tools" / "mathjax").exists()


def test_maths_install_copies_the_browser_bundle_after_npm(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")

    def npm(command, **_kwargs):
        assert command[0] == "/usr/bin/npm"
        assert command[-1].endswith("tools/mathjax")
        bundle = (
            project
            / "tools"
            / "mathjax"
            / "node_modules"
            / "mathjax-full"
            / "es5"
            / "tex-svg-full.js"
        )
        bundle.parent.mkdir(parents=True)
        bundle.write_text("bundle", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)

    install_tool(project, "mathjax")

    assert (project / "docs" / "javascripts" / "mathjax.js").is_file()
    assert (project / "docs" / "javascripts" / "vendor" / "mathjax" / "tex-svg-full.js").is_file()
    assert not (project / "tools" / "mermaid").exists()


def test_mkdocs_yaml_gets_the_same_core_components_without_conversion(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Existing MkDocs document
extra_css:
    - stylesheets/mine.css
markdown_extensions:
    - toc
""",
        config_name="mkdocs.yml",
    )

    path = ensure_zensical_config(project, AdoptOptions())

    assert path.name == "mkdocs.yml"
    config = path.read_text(encoding="utf-8")
    assert "site_name: Existing MkDocs document" in config
    assert "    - stylesheets/mine.css" in config
    assert "  - stylesheets/prodockit.css" in config
    for extension in CORE_EXTENSIONS:
        assert f"  - {extension}" in config
    assert not (project / "zensical.toml").exists()


def test_zensical_yaml_preserves_python_tags_without_executing_them(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Tagged Zensical document
markdown_extensions:
    - toc:
        slugify: !!python/object/apply:pymdownx.slugs.slugify {kwds: {case: lower}}
    - pymdownx.superfences:
        custom_fences:
            - name: diagram
              format: !!python/name:pymdownx.superfences.fence_code_format
""",
        config_name="zensical.yml",
    )

    path = ensure_zensical_config(project, AdoptOptions())

    assert path.name == "zensical.yml"
    config = path.read_text(encoding="utf-8")
    assert "!!python/object/apply:pymdownx.slugs.slugify" in config
    assert "!!python/name:pymdownx.superfences.fence_code_format" in config
    for extension in CORE_EXTENSIONS:
        assert extension in config


def test_stylesheet_follows_a_custom_docs_directory(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "site_name: Nested content\ndocs_dir: docs/src/markdown\n",
        config_name="zensical.yml",
    )

    path = ensure_stylesheet(project)

    assert path == project / "docs" / "src" / "markdown" / "stylesheets" / "prodockit.css"
    assert path.is_file()
    assert not (project / STYLESHEET).exists()


def test_mkdocs_mermaid_and_maths_remain_independent_options(tmp_path: Path) -> None:
    mermaid_project = tmp_path / "mermaid"
    mermaid_project.mkdir()
    _project(
        mermaid_project,
        "site_name: Mermaid\nmarkdown_extensions:\n    - toc\n",
        config_name="mkdocs.yaml",
    )
    ensure_zensical_config(mermaid_project, AdoptOptions(mermaid=True))
    mermaid = (mermaid_project / "mkdocs.yaml").read_text(encoding="utf-8")
    assert "name: mermaid" in mermaid
    assert "pymdownx.arithmatex" not in mermaid
    assert "mathjax.js" not in mermaid

    maths_project = tmp_path / "maths"
    maths_project.mkdir()
    _project(
        maths_project,
        "site_name: Maths\nmarkdown_extensions:\n    - toc\n",
        config_name="mkdocs.yml",
    )
    ensure_zensical_config(maths_project, AdoptOptions(maths=True))
    maths = (maths_project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "pymdownx.arithmatex:" in maths
    assert "generic: true" in maths
    assert "javascripts/mathjax.js" in maths
    assert "name: mermaid" not in maths


def test_mkdocs_existing_superfence_settings_are_preserved(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Configured
markdown_extensions:
    - pymdownx.superfences:
        preserve_tabs: true
""",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions(mermaid=True))

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "preserve_tabs: true" in config
    assert "custom_fences:" in config
    assert "name: mermaid" in config


def test_mkdocs_inline_css_list_is_extended_without_a_duplicate_key(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "site_name: Inline\nextra_css: [stylesheets/mine.css]\n",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert config.count("extra_css:") == 1
    assert "stylesheets/mine.css, stylesheets/prodockit.css" in config


def test_mkdocs_indentless_css_list_keeps_its_valid_yaml_style(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "site_name: Indentless\nextra_css:\n- css/termynal.css\n- css/custom.css\n",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "extra_css:\n- stylesheets/prodockit.css\n- css/termynal.css" in config


def test_mkdocs_extension_mapping_is_extended_as_a_mapping(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Extension mapping
markdown_extensions:
  toc:
    permalink: true
  pymdownx.superfences:
    custom_fences:
    - name: mermaid
      class: mermaid
extra_css:
- css/custom.css
""",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions(maths=True))

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "  prodockit.headings: null" in config
    assert "  pymdownx.arithmatex:\n    generic: true" in config
    assert "\n  - prodockit.headings" not in config


def test_mkdocs_yaml_updates_are_idempotent(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "site_name: Repeatable\nmarkdown_extensions:\n    - toc\n",
        config_name="mkdocs.yml",
    )
    options = AdoptOptions(mermaid=True, maths=True)

    ensure_zensical_config(project, options)
    first = (project / "mkdocs.yml").read_text(encoding="utf-8")
    ensure_zensical_config(project, options)

    assert (project / "mkdocs.yml").read_text(encoding="utf-8") == first

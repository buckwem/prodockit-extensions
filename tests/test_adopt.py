# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The project-scoped adoption workflow for existing Zensical documents."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import prodockit.renderer_resilience as renderer_resilience
from prodockit import __version__
from prodockit.adopt import (
    CORE_EXTENSIONS,
    MANIFEST,
    STYLESHEET,
    AdoptError,
    AdoptOptions,
    _mermaid_bin,
    assess,
    ensure_requirement,
    ensure_stylesheet,
    ensure_tools,
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

    result = CliRunner().invoke(main, ["adopt", "--dry-run"], color=True)

    assert result.exit_code == 0, result.output
    assert "Phase 1/4 — Assess" in result.output
    assert "Stage [3/7] Prodockit dependency" in result.output
    assert "\x1b[94m" in result.output
    assert "\x1b[34m" in result.output
    assert "\x1b[96m" not in result.output
    assert "\x1b[36m" not in result.output
    assert "Mermaid diagrams — not selected" in result.output
    assert "Mathematical notation — not selected" in result.output
    assert "WAIT  Ready for local build" in result.output
    assert "apply the selected integration stages" in result.output
    assert "zensical build --clean --strict" in result.output
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
    assert '"stylesheets/pdk.css"' in config
    assert config.index('"stylesheets/pdk.css"') < config.index('"stylesheets/mine.css"')
    for extension in CORE_EXTENSIONS:
        assert f'[project.markdown_extensions."{extension}"]' in config
    stylesheet = (project / STYLESHEET).read_text(encoding="utf-8")
    assert "logo_white.png" not in stylesheet
    assert "logo_black.png" not in stylesheet


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


def test_official_zensical_starter_dotted_extensions_are_adopted_in_place(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Zensical starter"

[project.markdown_extensions]
toc.permalink = true
pymdownx.arithmatex.generic = true
pymdownx.emoji.emoji_generator = "zensical.extensions.emoji.to_svg"
pymdownx.emoji.emoji_index = "zensical.extensions.emoji.twemoji"
pymdownx.superfences.custom_fences = [
  { name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" },
]
""",
    )

    ensure_zensical_config(project, AdoptOptions(mermaid=True, maths=True))

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert config.count("pymdownx.arithmatex") == 1
    assert config.count("pymdownx.superfences") == 2
    assert config.count("pymdownx.emoji") == 2
    assert "[project.markdown_extensions.pymdownx" not in config


def test_adoption_without_optional_renderers_passes_config_check(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "No renderer adoption"
site_dir = "public"
nav = [{ Home = "index.md" }]
""",
    )
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    adopted = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--no-mermaid", "--no-maths"],
        input="y\ny\n",
    )
    checked = CliRunner().invoke(main, ["config", "--check"])

    assert adopted.exit_code == 0, adopted.output
    assert "Ready for local build" in adopted.output
    assert checked.exit_code == 0, checked.output
    assert "Configuration check passed" in checked.output


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


def test_assessment_upgrades_an_older_prodockit_floor(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "requirements.txt").write_text(
        "zensical\nprodockit>=0.47.0\n", encoding="utf-8"
    )

    dependency = next(step for step in assess(project, AdoptOptions()) if step.id == "dependency")

    assert dependency.status == "missing"
    assert f"prodockit>={__version__}" in dependency.detail

    ensure_requirement(project)
    assert f"prodockit>={__version__}" in (project / "requirements.txt").read_text(
        encoding="utf-8"
    )


def test_assessment_keeps_a_newer_prodockit_floor(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "requirements.txt").write_text(
        "prodockit>=999.0.0\n", encoding="utf-8"
    )

    dependency = next(step for step in assess(project, AdoptOptions()) if step.id == "dependency")

    assert dependency.status == "ok"


def test_assessment_refreshes_the_managed_stylesheet(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ensure_requirement(project)
    ensure_zensical_config(project, AdoptOptions())
    stylesheet = project / STYLESHEET
    stylesheet.parent.mkdir(parents=True, exist_ok=True)
    stylesheet.write_text("/* old managed stylesheet */\n", encoding="utf-8")

    core = next(step for step in assess(project, AdoptOptions()) if step.id == "core")

    assert core.status == "missing"
    ensure_stylesheet(project)
    assert stylesheet.read_text(encoding="utf-8") != "/* old managed stylesheet */\n"
    core = next(step for step in assess(project, AdoptOptions()) if step.id == "core")
    assert core.status == "ok"


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


def test_toml_extension_array_materialises_the_tree_icon_renderer(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Adopt Tree Reproduction"
site_dir = "public"
nav = [
  { Home = "index.md" },
  { Tree = "tree.md" },
]

markdown_extensions = [
  "attr_list",
  "toc",
  "pymdownx.superfences",
  "pymdownx.arithmatex",
]
""",
    )
    (project / "docs" / "tree.md").write_text(
        "# Tree test\n\n/// tree\ndocs/\n  index.md\n  features.md\n///\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)
    result = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--no-mermaid", "--no-maths"],
        input="y\ny\n",
    )
    assert result.exit_code == 0, result.output

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert '"pymdownx.emoji" = {' in config
    assert 'emoji_index = "zensical.extensions.emoji.twemoji"' in config
    assert 'emoji_generator = "zensical.extensions.emoji.to_svg"' in config

    repeated = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--no-mermaid", "--no-maths"],
    )
    assert repeated.exit_code == 0, repeated.output
    assert "already configured" in repeated.output
    assert (project / "zensical.toml").read_text(encoding="utf-8") == config

    completed = subprocess.run(
        [sys.executable, "-m", "zensical", "build", "--clean", "--strict"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    html = (project / "public" / "tree" / "index.html").read_text(encoding="utf-8")
    assert ":lucide-folder:" not in html
    assert ":lucide-file:" not in html
    assert html.count('class="twemoji"') >= 3


def test_existing_tree_icon_settings_are_preserved_in_table_form(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Existing icon configuration"

[project.markdown_extensions."pymdownx.emoji"]
emoji_index = "zensical.extensions.emoji.twemoji"
custom_icons = "icons"
""",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert 'custom_icons = "icons"' in config
    assert config.count('emoji_index = "zensical.extensions.emoji.twemoji"') == 1
    assert config.count('emoji_generator = "zensical.extensions.emoji.to_svg"') == 1


@pytest.mark.parametrize(
    "extensions",
    (
        "  - attr_list\n  - toc\n",
        "  attr_list: {}\n  toc:\n    permalink: true\n",
    ),
    ids=("sequence", "mapping"),
)
def test_yaml_extensions_materialise_a_buildable_tree_icon_renderer(
    tmp_path: Path,
    extensions: str,
) -> None:
    project = _project(
        tmp_path,
        f"""\
site_name: Existing YAML extensions
site_dir: public
markdown_extensions:
{extensions}""",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "emoji_index: !!python/name:zensical.extensions.emoji.twemoji" in config
    assert "emoji_generator: !!python/name:zensical.extensions.emoji.to_svg" in config

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "zensical",
            "build",
            "-f",
            "mkdocs.yml",
            "--clean",
            "--strict",
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_yaml_tree_icon_plain_strings_are_upgraded_to_callable_tags(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Legacy callback strings
markdown_extensions:
  - pymdownx.emoji:
      emoji_generator: zensical.extensions.emoji.to_svg
      emoji_index: zensical.extensions.emoji.twemoji
""",
        config_name="zensical.yml",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "zensical.yml").read_text(encoding="utf-8")
    assert "emoji_generator: !!python/name:zensical.extensions.emoji.to_svg" in config
    assert "emoji_index: !!python/name:zensical.extensions.emoji.twemoji" in config


def test_apply_core_never_invokes_git_or_editor_setup(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    result = CliRunner().invoke(main, ["adopt", "--apply"], input="y\ny\n")

    assert result.exit_code == 0, result.output
    assert (project / "requirements.txt").is_file()
    assert (project / STYLESHEET).is_file()
    assert "ok    Ready for local build" in result.output
    assert "Run `zensical build --clean --strict`" in result.output
    assert not (project / ".vscode").exists()
    assert "Nothing has been committed or pushed" in result.output

    repeated = CliRunner().invoke(main, ["adopt", "--apply"])

    assert repeated.exit_code == 0, repeated.output
    assert "All selected prodockit components are already configured" in repeated.output
    assert "No changes made" in repeated.output
    assert "Run `zensical build --clean --strict`" not in repeated.output


@pytest.mark.parametrize(
    ("config_name", "command"),
    (
        ("zensical.toml", "zensical build --clean --strict"),
        ("zensical.yml", "zensical build -f zensical.yml --clean --strict"),
        ("zensical.yaml", "zensical build -f zensical.yaml --clean --strict"),
        ("mkdocs.yml", "zensical build -f mkdocs.yml --clean --strict"),
        ("mkdocs.yaml", "zensical build -f mkdocs.yaml --clean --strict"),
    ),
)
def test_report_recommends_the_discovered_configuration(
    tmp_path: Path,
    monkeypatch,
    config_name: str,
    command: str,
) -> None:
    config = None if config_name == "zensical.toml" else "site_name: Existing document\n"
    project = _project(tmp_path, config, config_name=config_name)
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    result = CliRunner().invoke(main, ["adopt", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert command in result.output


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

    def npm(command, **kwargs):
        assert command[0] == "/usr/bin/npm"
        assert command == [
            "/usr/bin/npm",
            "ci",
            "--legacy-peer-deps",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
        ]
        assert kwargs["cwd"] == project / "tools" / "mermaid"
        binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("renderer", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path: SimpleNamespace(path=path, ok=True, version="11.0.0", error=None),
    )

    written = install_tool(project, "mermaid")

    lock = project / "tools" / "mermaid" / "package-lock.json"
    assert written.count(lock) == 1
    assert (project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc").is_file()
    assert not (project / "tools" / "mathjax").exists()


def test_mermaid_health_prefers_the_runnable_windows_command_shim(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    bin_dir = project / "tools" / "mermaid" / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "mmdc").write_text("posix shim", encoding="utf-8")
    windows_shim = bin_dir / "mmdc.cmd"
    windows_shim.write_text("windows shim", encoding="utf-8")
    monkeypatch.setattr("prodockit.adopt.sys.platform", "win32")

    assert _mermaid_bin(project) == windows_shim


def test_maths_install_copies_the_browser_bundle_after_npm(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")

    def npm(command, **kwargs):
        assert command[0] == "/usr/bin/npm"
        assert command == [
            "/usr/bin/npm",
            "ci",
            "--legacy-peer-deps",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
        ]
        assert kwargs["cwd"] == project / "tools" / "mathjax"
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
        (bundle.parent.parent / "LICENSE").write_text("Apache-2.0", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mathjax",
        lambda node, script: SimpleNamespace(path=script, ok=True, version=None, error=None),
    )

    install_tool(project, "mathjax")

    assert (project / "docs" / "javascripts" / "mathjax.js").is_file()
    assert (project / "docs" / "javascripts" / "vendor" / "mathjax" / "tex-svg-full.js").is_file()
    assert (project / "docs" / "javascripts" / "vendor" / "mathjax" / "LICENSE").is_file()
    assert not (project / "tools" / "mermaid").exists()


def test_maths_install_rejects_npm_success_when_renderer_probe_fails(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/tool")

    def npm(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mathjax",
        lambda node, script: SimpleNamespace(
            path=script, ok=False, version=None, error="Cannot find module"
        ),
    )

    with pytest.raises(AdoptError, match="npm completed but MathJax is unusable"):
        install_tool(project, "mathjax")


def test_custom_node_manifest_without_a_lock_uses_npm_install(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    manifest = project / "tools" / "mermaid" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name": "author-owned"}\n', encoding="utf-8")
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")

    def npm(command, **kwargs):
        assert command == [
            "/usr/bin/npm",
            "install",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
        ]
        binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("renderer", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path: SimpleNamespace(path=path, ok=True, version="11.0.0", error=None),
    )

    install_tool(project, "mermaid")

    assert not (manifest.parent / "package-lock.json").exists()


def test_mermaid_install_rejects_npm_success_when_cli_probe_fails(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")

    def npm(_command, **_kwargs):
        binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("incomplete", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path: SimpleNamespace(
            path=path,
            ok=False,
            version=None,
            error="ERR_MODULE_NOT_FOUND",
        ),
    )

    with pytest.raises(AdoptError, match="npm completed but Mermaid CLI is unusable"):
        install_tool(project, "mermaid")


def test_mermaid_install_retries_a_completed_transient_npm_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")
    attempts = []

    def npm(command, **_kwargs):
        attempts.append(command)
        modules = project / "tools/mermaid/node_modules"
        if len(attempts) == 1:
            modules.mkdir(parents=True)
            (modules / "partial").write_text("partial", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1, "", "npm ERR! code ECONNRESET")
        assert not modules.exists()
        binary = modules / ".bin/mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("renderer", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("prodockit.adopt.subprocess.run", npm)
    monkeypatch.setattr(renderer_resilience.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path, **_kwargs: SimpleNamespace(
            path=path, ok=True, version="11.0.0", error=None
        ),
    )
    notices = []

    install_tool(project, "mermaid", retry_reporter=notices.append)

    assert len(attempts) == 2
    assert len(notices) == 1
    assert notices[0].attempt == 1


def test_adoption_readiness_rejects_an_unusable_mermaid_cli(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    options = AdoptOptions(mermaid=True, maths=False)
    ensure_requirement(project)
    ensure_stylesheet(project)
    ensure_zensical_config(project, options)
    ensure_tools(project, options)
    binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
    binary.parent.mkdir(parents=True)
    binary.write_text("incomplete", encoding="utf-8")
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path: SimpleNamespace(
            path=path,
            ok=False,
            version=None,
            error="ERR_MODULE_NOT_FOUND",
        ),
    )

    steps = {step.id: step for step in assess(project, options)}

    assert steps["mermaid"].status == "missing"
    assert "health check failed: ERR_MODULE_NOT_FOUND" in steps["mermaid"].detail
    assert steps["verify"].status == "wait"


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
    assert "  - stylesheets/pdk.css" in config
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

    assert path == project / "docs" / "src" / "markdown" / "stylesheets" / "pdk.css"
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
    assert "stylesheets/pdk.css, stylesheets/mine.css" in config


def test_mkdocs_indentless_css_list_keeps_its_valid_yaml_style(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "site_name: Indentless\nextra_css:\n- css/termynal.css\n- css/custom.css\n",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "extra_css:\n- stylesheets/pdk.css\n- css/termynal.css" in config


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


def test_mkdocs_mapping_form_adds_mermaid_without_an_assertion(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """\
site_name: YAML mapping adoption reproduction
markdown_extensions:
  attr_list: {}
  toc:
    permalink: true
""",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions(mermaid=True))

    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "  pymdownx.superfences:\n    custom_fences:" in config
    assert "      - name: mermaid" in config
    assert config.count("pymdownx.superfences:") == 1


def test_apply_mapping_form_mermaid_is_transactional(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(
        tmp_path,
        """\
site_name: YAML mapping adoption reproduction
markdown_extensions:
  attr_list: {}
  toc:
    permalink: true
""",
        config_name="mkdocs.yml",
    )
    (project / "requirements.txt").write_text("mkdocs-material==9.7.7\n", encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)
    monkeypatch.setattr(
        "prodockit.adopt.install_tool", lambda root, component, **_kwargs: []
    )

    preview = CliRunner().invoke(main, ["adopt", "--dry-run", "--mermaid", "--no-maths"])
    assert preview.exit_code == 0, preview.output

    result = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--mermaid", "--no-maths"],
        input="y\ny\ny\n",
    )

    assert result.exit_code == 0, result.output
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "  pymdownx.superfences:\n    custom_fences:" in config
    assert "      - name: mermaid" in config
    assert f"prodockit>={__version__}" in (project / "requirements.txt").read_text(
        encoding="utf-8"
    )


def test_apply_refuses_an_unsafe_yaml_form_before_updating_requirements(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Unsupported inline settings
markdown_extensions:
  pymdownx.superfences: { preserve_tabs: true }
""",
        config_name="mkdocs.yml",
    )
    requirements = project / "requirements.txt"
    requirements.write_text("mkdocs-material==9.7.7\n", encoding="utf-8")
    before_config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    before_requirements = requirements.read_text(encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    preview = CliRunner().invoke(
        main,
        ["adopt", "--dry-run", "--mermaid", "--no-maths"],
    )

    assert preview.exit_code != 0
    assert "cannot update safely" in preview.output
    assert (project / "mkdocs.yml").read_text(encoding="utf-8") == before_config
    assert requirements.read_text(encoding="utf-8") == before_requirements

    result = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--mermaid", "--no-maths"],
    )

    assert result.exit_code != 0
    assert "cannot update safely" in result.output
    assert (project / "mkdocs.yml").read_text(encoding="utf-8") == before_config
    assert requirements.read_text(encoding="utf-8") == before_requirements


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

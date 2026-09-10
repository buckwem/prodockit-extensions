# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The project-scoped adoption workflow for existing Zensical documents."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

import prodockit.renderer_resilience as renderer_resilience
from prodockit import __version__
from prodockit.adopt import (
    CORE_EXTENSIONS,
    MANIFEST,
    STYLESHEET,
    AdoptChoiceResolution,
    AdoptError,
    AdoptOptions,
    Step,
    _mermaid_bin,
    assess,
    ensure_javascripts,
    ensure_requirement,
    ensure_stylesheet,
    ensure_stylesheets,
    ensure_tools,
    ensure_zensical_config,
    install_tool,
    load_manifest,
    resolve_options,
    write_manifest,
)
from prodockit.adopt import (
    apply as apply_adoption,
)
from prodockit.cli import main
from prodockit.pins import TESTED_VERSIONS
from prodockit.project_config import load_project_config
from prodockit.shared_files import resource_bytes


@pytest.fixture(autouse=True)
def _supported_toolchain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep adoption unit tests independent of the interpreter running pytest.

    Dedicated toolchain tests below exercise mismatches. These configuration
    tests describe an already-supported active environment.
    """

    from prodockit.adopt_browser import BrowserPlan
    from prodockit.adopt_node import NodePlan

    monkeypatch.setattr("prodockit.adopt_node.plan", lambda **kwargs: NodePlan())
    monkeypatch.setattr("prodockit.adopt_browser.plan", lambda *args, **kwargs: BrowserPlan())
    monkeypatch.setattr(
        "prodockit.adopt_browser.prepare",
        lambda *args, **kwargs: {"PUPPETEER_SKIP_DOWNLOAD": "true"},
    )
    monkeypatch.setattr("prodockit.adopt_browser.complete", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "prodockit.toolchain.installed_python_version",
        lambda: TESTED_VERSIONS["python"],
    )
    monkeypatch.setattr(
        "prodockit.toolchain.installed_distribution_version",
        lambda package: TESTED_VERSIONS[package],
    )
    monkeypatch.setattr(
        "prodockit.toolchain._fresh_distribution_versions",
        lambda packages: {package: TESTED_VERSIONS[package] for package in packages},
    )
    monkeypatch.setattr(
        "prodockit.toolchain.installed_pandoc_version",
        lambda: TESTED_VERSIONS["pandoc"],
    )
    # Individual adoption tests use temporary project roots while pytest runs
    # from this repository's own virtual environment. Environment-boundary
    # behaviour has dedicated tests below and in test_environment.py.
    monkeypatch.setattr("prodockit.adopt._interpreter_problem", lambda _root: None)


def _project(
    tmp_path: Path,
    config: str | None = None,
    *,
    config_name: str = "zensical.toml",
) -> Path:
    (tmp_path / "docs").mkdir()
    from prodockit.adopt import ensure_local_ignores

    ensure_local_ignores(tmp_path)
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
    assert "existing Zensical document" in output
    assert "Zensical or MkDocs" not in output
    assert "virtual environment active" in output
    assert "separately confirmed Git and repository setup" in output
    assert "--mermaid" in result.output and "--maths" in result.output


def test_report_uses_prominent_phases_and_stages(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    result = CliRunner().invoke(main, ["adopt", "--dry-run"], color=True)

    assert result.exit_code == 0, result.output
    assert "Phase 1/5 — Assess" in result.output
    assert "Phase 5/5 — Site and repository details" in result.output
    assert "Activity [3/11] Supported toolchain" in result.output
    assert "Component choices" in result.output
    assert "\x1b[94m" in result.output
    assert "\x1b[34m" in result.output
    assert "\x1b[96m" not in result.output
    assert "\x1b[36m" not in result.output
    assert "Mermaid diagrams — not selected" in result.output
    assert "Mathematical notation — not selected" in result.output
    assert "WAIT  Ready for local build" in result.output
    assert "apply the selected integration activities" in result.output
    assert "zensical build --clean --strict" in result.output
    assert (
        "active project environment, local project files and selected runtime prerequisites"
        in result.output
    )
    assert "Excluded: SSH, editors, commits, pushes and Pages configuration" in result.output


def test_adopt_refuses_a_mixed_project_environment_before_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    (project / ".venv").mkdir()
    monkeypatch.setattr("sys.prefix", str(project / ".venv"))
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)
    monkeypatch.setattr(
        "prodockit.adopt._interpreter_problem",
        lambda _root: "python uses 3.12 but pdk uses 3.14; run pdk diag first",
    )

    result = CliRunner().invoke(main, ["adopt", "--apply"])

    assert result.exit_code != 0
    assert "Active project environment" in result.output
    assert "python uses 3.12 but pdk uses 3.14" in result.output
    assert "before project files can be changed" in result.output


def test_assessment_warns_without_venv_and_rejects_wrong_active_venv(tmp_path, monkeypatch):
    from prodockit.adopt import AdoptOptions, assess

    project = _project(tmp_path)
    (project / ".venv").mkdir()
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: False)
    steps = assess(project, AdoptOptions(), offline=True)
    environment = next(step for step in steps if step.id == "environment")
    assert environment.status == "warn"
    assert not environment.needs_work
    assert "No virtual environment is active" in environment.detail

    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)
    monkeypatch.setattr(
        "prodockit.adopt._interpreter_problem",
        lambda _root: (
            "Active Python is not the project's .venv: running parent-venv; "
            "project environment .venv"
        ),
    )
    steps = assess(project, AdoptOptions(), offline=True)
    environment = next(step for step in steps if step.id == "environment")
    assert environment.status == "wrong"
    assert "Active Python is not the project's .venv" in environment.detail


def test_assessment_blocks_selected_renderers_when_node_is_unavailable(tmp_path, monkeypatch):
    from prodockit.adopt import AdoptOptions, assess
    from prodockit.adopt_node import NodePlan

    monkeypatch.setattr(
        "prodockit.adopt_node.plan",
        lambda **kwargs: NodePlan(
            blocked="Node.js/npm needs installation or repair, but Adopt is offline"
        ),
    )

    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: False)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: None)

    steps = assess(project, AdoptOptions(mermaid=True, maths=True), offline=True)

    step = next(item for item in steps if item.id == "node")
    assert step.status == "wrong"
    assert "Adopt is offline" in step.detail


def test_apply_checks_renderer_prerequisites_before_changing_project(tmp_path, monkeypatch):
    from prodockit.adopt_node import NodePlan

    monkeypatch.setattr(
        "prodockit.adopt_node.plan",
        lambda **kwargs: NodePlan(blocked="Node.js/npm cannot be installed offline"),
    )
    project = _project(tmp_path)
    config = project / "zensical.toml"
    before = config.read_bytes()
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: None)

    result = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--mermaid", "--maths"],
    )

    assert result.exit_code != 0
    assert "ADOPT CANNOT CONTINUE" in result.output
    assert "Problem:  Node.js/npm cannot be installed offline" in result.output
    assert "no project files have been changed" in result.output
    assert "Apply this stage?" not in result.output
    assert config.read_bytes() == before
    assert not (project / MANIFEST).exists()
    assert not (project / "requirements.txt").exists()


def test_renderer_blocker_summary_is_prominently_coloured(tmp_path, monkeypatch):
    from prodockit.adopt_node import NodePlan

    monkeypatch.setattr(
        "prodockit.adopt_node.plan",
        lambda **kwargs: NodePlan(blocked="Node.js/npm cannot be installed offline"),
    )
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: None)

    result = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--mermaid", "--no-maths"],
        color=True,
    )

    assert result.exit_code != 0
    assert click.style("ADOPT CANNOT CONTINUE", bold=True, fg="bright_magenta") in (result.output)
    assert (
        click.style(
            "Problem:  Node.js/npm cannot be installed offline", fg="bright_magenta", bold=True
        )
        in result.output
    )


def test_reusable_apply_runs_selected_stages_and_verifies(monkeypatch, tmp_path) -> None:
    completed: set[str] = set()

    def planned(*args, **kwargs):
        ready = {"dependency", "core"} <= completed
        return [
            Step(
                "dependency",
                "Integrate",
                "Supported toolchain",
                "ok" if "dependency" in completed else "missing",
                "toolchain",
            ),
            Step(
                "core",
                "Integrate",
                "Standard components",
                "ok" if "core" in completed else "missing",
                "configuration",
            ),
            Step("verify", "Verify", "Ready", "ok" if ready else "wait", "ready"),
        ]

    def apply_one(root, options, step_id, **kwargs):
        completed.add(step_id)
        path = root / f"{step_id}.txt"
        path.write_text(step_id, encoding="utf-8")
        return [path]

    monkeypatch.setattr("prodockit.adopt.assess", planned)
    monkeypatch.setattr("prodockit.adopt.apply_step", apply_one)

    written = apply_adoption(tmp_path, AdoptOptions())

    assert completed == {"dependency", "core"}
    assert {path.name for path in written} == {"dependency.txt", "core.txt"}


def test_reusable_apply_refuses_a_blocking_assessment(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "prodockit.adopt.assess",
        lambda *args, **kwargs: [
            Step("environment", "Assess", "Active environment", "wrong", "not active")
        ],
    )

    with pytest.raises(AdoptError, match="Active environment: not active"):
        apply_adoption(tmp_path, AdoptOptions())


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
    assert config.index('site_name = "Mine"') < config.index("extra_css = [")
    assert load_project_config(project / "zensical.toml").extra["pdf_extra_css"] == [
        "stylesheets/pdk-pdf.css",
        "stylesheets/print.css",
    ]
    assert config.index("extra_javascript = [") < config.index("[project.theme]")
    assert config.index('"stylesheets/pdk.css"') < config.index('"stylesheets/mine.css"')
    for extension in CORE_EXTENSIONS:
        assert f'[project.markdown_extensions."{extension}"]' in config
    assert '[project.markdown_extensions."prodockit.citations"]' not in config
    stylesheet = (project / STYLESHEET).read_text(encoding="utf-8")
    assert "logo_white.png" not in stylesheet
    assert "logo_black.png" not in stylesheet


def test_core_adoption_installs_and_registers_the_stylesheet_hierarchy(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Styled"
extra_css = ["stylesheets/template.css", "stylesheets/extra.css"]

[project.extra]
pdf_extra_css = ["stylesheets/print.css"]
""",
    )
    styles = project / "docs" / "stylesheets"
    styles.mkdir()
    extra = styles / "extra.css"
    print_css = styles / "print.css"
    extra.write_text("/* author website styles */\n", encoding="utf-8")
    print_css.write_text("/* author PDF styles */\n", encoding="utf-8")

    ensure_zensical_config(project, AdoptOptions())
    written = ensure_stylesheets(project)

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert config.index('"stylesheets/pdk.css"') < config.index('"stylesheets/template.css"')
    assert config.index('"stylesheets/template.css"') < config.index('"stylesheets/extra.css"')
    assert config.index('"stylesheets/pdk-pdf.css"') < config.index('"stylesheets/print.css"')
    assert {path.name for path in written} == {
        "pdk.css",
        "pdk-pdf.css",
        "extra.css",
        "print.css",
    }
    assert extra.read_text(encoding="utf-8") == "/* author website styles */\n"
    assert print_css.read_text(encoding="utf-8") == "/* author PDF styles */\n"


def test_core_adoption_preserves_dotted_project_extra_settings(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Dotted extras"
extra.pdf_copyright = "Keep this footer"
extra.pdf_extra_css = ["stylesheets/course-print.css"]
""",
    )

    ensure_zensical_config(project, AdoptOptions())

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert 'extra.pdf_copyright = "Keep this footer"' in config
    assert not re.search(r"(?m)^\[project.extra\]", config)
    assert config.index('"stylesheets/pdk-pdf.css"') < config.index(
        '"stylesheets/course-print.css"'
    )
    assert config.index('"stylesheets/course-print.css"') < config.index('"stylesheets/print.css"')


def test_core_adoption_creates_missing_user_managed_styles_without_replacing_them(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)

    ensure_zensical_config(project, AdoptOptions())
    ensure_stylesheets(project)
    styles = project / "docs" / "stylesheets"
    extra = styles / "extra.css"
    print_css = styles / "print.css"
    assert "project-specific website and PDF" in extra.read_text(encoding="utf-8")
    assert "project-specific PDF-only" in print_css.read_text(encoding="utf-8")

    extra.write_text("/* keep my website CSS */\n", encoding="utf-8")
    print_css.write_text("/* keep my PDF CSS */\n", encoding="utf-8")
    (styles / "pdk.css").write_text("/* old managed CSS */\n", encoding="utf-8")
    (styles / "pdk-pdf.css").write_text("/* old managed PDF CSS */\n", encoding="utf-8")

    ensure_stylesheets(project)

    assert extra.read_text(encoding="utf-8") == "/* keep my website CSS */\n"
    assert print_css.read_text(encoding="utf-8") == "/* keep my PDF CSS */\n"
    assert (styles / "pdk.css").read_text(encoding="utf-8") != "/* old managed CSS */\n"
    assert (styles / "pdk-pdf.css").read_text(encoding="utf-8") != ("/* old managed PDF CSS */\n")


def test_core_adoption_installs_javascript_without_mathjax(tmp_path: Path) -> None:
    project = _project(tmp_path)

    ensure_zensical_config(project, AdoptOptions(maths=False))
    written = ensure_javascripts(project)

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert config.index('"javascripts/pdk.js"') < config.index('"javascripts/extra.js"')
    assert "javascripts/mathjax.js" not in config
    assert "javascripts/vendor/mathjax/tex-svg-full.js" not in config
    assert {path.name for path in written} == {"pdk.js", "extra.js"}
    assert (project / "docs/javascripts/extra.js").read_text(encoding="utf-8") == ""


def test_core_adoption_orders_javascript_with_mathjax(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """[project]
site_name = "Scripted"
extra_javascript = ["javascripts/site.js", "javascripts/extra.js"]
""",
    )

    ensure_zensical_config(project, AdoptOptions(maths=True))
    ensure_javascripts(project)

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    ordered = (
        '"javascripts/pdk.js"',
        '"javascripts/mathjax.js"',
        '"javascripts/vendor/mathjax/tex-svg-full.js"',
        '"javascripts/site.js"',
        '"javascripts/extra.js"',
    )
    assert [config.index(value) for value in ordered] == sorted(
        config.index(value) for value in ordered
    )


def test_core_adoption_preserves_cache_versioned_assets_without_duplicates(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """[project]
site_name = "Cache-versioned assets"
extra_css = ["stylesheets/pdk.css?v=4", "stylesheets/extra.css?v=2"]
extra_javascript = [
  "javascripts/mathjax.js?v=config-2",
  "javascripts/vendor/mathjax/tex-svg-full.js?v=3.2.2",
  "javascripts/extra.js?v=7",
]

[project.extra]
pdf_extra_css = ["stylesheets/pdk-pdf.css?v=4", "stylesheets/print.css?v=2"]
""",
    )

    ensure_zensical_config(project, AdoptOptions(maths=True))
    ensure_stylesheets(project)
    ensure_javascripts(project)
    first = (project / "zensical.toml").read_text(encoding="utf-8")
    ensure_zensical_config(project, AdoptOptions(maths=True))
    second = (project / "zensical.toml").read_text(encoding="utf-8")

    assert second == first
    assert '"javascripts/mathjax.js",' not in second
    assert '"javascripts/vendor/mathjax/tex-svg-full.js",' not in second
    assert second.count("javascripts/mathjax.js?v=config-2") == 1
    assert second.count("javascripts/vendor/mathjax/tex-svg-full.js?v=3.2.2") == 1
    assert second.index('"javascripts/pdk.js"') < second.index(
        '"javascripts/mathjax.js?v=config-2"'
    )
    core = next(step for step in assess(project, AdoptOptions(maths=True)) if step.id == "core")
    assert core.status == "ok", core.detail


def test_mkdocs_adoption_preserves_cache_versioned_assets(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """site_name: Cache-versioned YAML
extra_css:
  - stylesheets/pdk.css?v=4
  - stylesheets/extra.css?v=2
extra_javascript:
  - javascripts/mathjax.js?v=config-2
  - javascripts/vendor/mathjax/tex-svg-full.js?v=3.2.2
  - javascripts/extra.js?v=7
extra:
  pdf_extra_css:
    - stylesheets/pdk-pdf.css?v=4
    - stylesheets/print.css?v=2
""",
        config_name="mkdocs.yml",
    )

    ensure_zensical_config(project, AdoptOptions(maths=True))
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")

    assert "- javascripts/mathjax.js\n" not in config
    assert "- javascripts/vendor/mathjax/tex-svg-full.js\n" not in config
    assert config.count("javascripts/mathjax.js?v=config-2") == 1
    assert config.count("javascripts/vendor/mathjax/tex-svg-full.js?v=3.2.2") == 1
    assert config.index("- javascripts/pdk.js") < config.index(
        "- javascripts/mathjax.js?v=config-2"
    )


def test_core_adoption_refreshes_pdk_javascript_but_preserves_extra(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ensure_zensical_config(project, AdoptOptions())
    ensure_javascripts(project)
    scripts = project / "docs/javascripts"
    (scripts / "pdk.js").write_text("// old managed behaviour\\n", encoding="utf-8")
    (scripts / "extra.js").write_text("// keep my behaviour\\n", encoding="utf-8")

    ensure_javascripts(project)

    assert (scripts / "pdk.js").read_bytes() == resource_bytes("pdk.js")
    assert (scripts / "extra.js").read_text(encoding="utf-8") == "// keep my behaviour\\n"


def test_core_adoption_empties_only_the_former_stock_extra_javascript(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    ensure_zensical_config(project, AdoptOptions())
    scripts = project / "docs/javascripts"
    scripts.mkdir(parents=True)
    scripts.joinpath("extra.js").write_bytes(resource_bytes("pdk.js"))

    ensure_javascripts(project)

    assert scripts.joinpath("pdk.js").read_bytes() == resource_bytes("pdk.js")
    assert scripts.joinpath("extra.js").read_text(encoding="utf-8") == ""


def test_yaml_adoption_registers_website_and_pdf_styles_in_cascade_order(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """\
site_name: Styled
extra_css: [stylesheets/theme.css]
extra:
  pdf_extra_css: [stylesheets/custom-print.css]
""",
        config_name="zensical.yml",
    )

    ensure_zensical_config(project, AdoptOptions())
    ensure_stylesheets(project)

    config = (project / "zensical.yml").read_text(encoding="utf-8")
    assert (
        "extra_css: [stylesheets/pdk.css, stylesheets/theme.css, stylesheets/extra.css]" in config
    )
    assert (
        "pdf_extra_css: [stylesheets/pdk-pdf.css, stylesheets/custom-print.css, "
        "stylesheets/print.css]" in config
    )
    assert all(
        (project / "docs" / "stylesheets" / name).is_file()
        for name in ("pdk.css", "pdk-pdf.css", "extra.css", "print.css")
    )


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
    assert (
        load_project_config(project / "zensical.toml").markdown_extensions["toc"]["permalink"]
        is True
    )
    assert '[project.markdown_extensions."pymdownx.highlight"]' in config
    assert 'line_spans = "__span"' in config
    assert '[project.markdown_extensions."pymdownx.superfences"]' in config
    assert load_project_config(project / "zensical.toml").markdown_extensions[
        "pymdownx.superfences"
    ]["custom_fences"] == [{"name": "mermaid", "class": "mermaid"}]


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
    active = "\n".join(line for line in config.splitlines() if not line.lstrip().startswith("#"))
    assert active.count("pymdownx.emoji") == 2
    assert "[project.markdown_extensions.pymdownx" not in active


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
        input="y\ny\ny\n",
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
    (project / "requirements.txt").write_text("zensical\nprodockit>=0.47.0\n", encoding="utf-8")

    dependency = next(step for step in assess(project, AdoptOptions()) if step.id == "dependency")

    assert dependency.status == "missing"
    assert "align version declarations" in dependency.detail

    ensure_requirement(project)
    assert f"prodockit>={__version__}" in (project / "requirements.txt").read_text(encoding="utf-8")


def test_assessment_rejects_a_newer_prodockit_floor(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "requirements.txt").write_text("prodockit>=999.0.0\n", encoding="utf-8")

    steps = assess(project, AdoptOptions())
    assert len(steps) == 1
    assert steps[0].status == "wrong"
    assert "999.0.0" in steps[0].detail
    assert "No project files or software have been changed" in steps[0].detail


def test_crlf_stylesheet_does_not_need_adopt_refresh(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ensure_requirement(project)
    ensure_zensical_config(project, AdoptOptions())
    ensure_stylesheet(project)
    stylesheet = project / STYLESHEET
    content = stylesheet.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    stylesheet.write_bytes(content)
    core = next(step for step in assess(project, AdoptOptions()) if step.id == "core")
    assert core.status == "ok"
    assert stylesheet.read_bytes() == content


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
    choices = next(step for step in assess(project, AdoptOptions()) if step.id == "choices")
    assert choices.status == "missing"
    assert f"save the selected component choices in {MANIFEST}" in choices.detail
    write_manifest(project, AdoptOptions())
    choices = next(step for step in assess(project, AdoptOptions()) if step.id == "choices")
    assert choices.status == "ok"


def test_existing_inline_citations_are_preserved_as_the_bibliography_alternative(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    ensure_zensical_config(project, AdoptOptions())
    config_path = project / "zensical.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            '[project.markdown_extensions."prodockit.bibliography"]',
            '[project.markdown_extensions."prodockit.citations"]',
        ),
        encoding="utf-8",
    )
    ensure_stylesheet(project)
    write_manifest(project, AdoptOptions())

    core = next(step for step in assess(project, AdoptOptions()) if step.id == "core")
    ensure_zensical_config(project, AdoptOptions())
    updated = config_path.read_text(encoding="utf-8")

    assert core.status == "ok"
    assert '[project.markdown_extensions."prodockit.citations"]' in updated
    assert '[project.markdown_extensions."prodockit.bibliography"]' not in updated


def test_core_assessment_names_only_the_missing_inputs(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ensure_zensical_config(project, AdoptOptions())
    ensure_stylesheet(project)
    config_path = project / "zensical.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            '[project.markdown_extensions."prodockit.steps"]\n', ""
        ),
        encoding="utf-8",
    )

    core = next(step for step in assess(project, AdoptOptions()) if step.id == "core")

    assert core.status == "missing"
    assert core.detail == "add standard extension(s): prodockit.steps"
    assert "stylesheet" not in core.detail


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
    assert not re.search(r'(?m)^\[project.markdown_extensions\."prodockit.headings"\]', config)
    extensions = load_project_config(project / "zensical.toml").markdown_extensions
    assert extensions["pymdownx.arithmatex"]["generic"] is True
    assert extensions["pymdownx.superfences"]["custom_fences"][0]["name"] == "mermaid"
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
        input="y\ny\ny\n",
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

    result = CliRunner().invoke(main, ["adopt", "--apply"], input="y\ny\ny\n")

    assert result.exit_code == 0, result.output
    assert (project / "requirements.txt").is_file()
    assert (project / STYLESHEET).is_file()
    assert "ok    Ready for local build" in result.output
    assert "  pdk diag\n  zensical build --clean --strict" in result.output
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


def test_missing_manifest_keeps_optional_renderers_off_despite_capable_configuration(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Existing document"

[project.extra]
pdf_mmdc_bin = "tools/mermaid/node_modules/.bin/mmdc"
pdf_tex2svg_script = "tools/mathjax/tex2svg.js"

[project.markdown_extensions.pymdownx.arithmatex]
generic = true

[project.markdown_extensions.pymdownx.superfences]
custom_fences = [{ name = "mermaid", class = "mermaid" }]
""",
    )

    resolution = resolve_options(project)

    assert resolution == AdoptChoiceResolution(AdoptOptions(), "defaults", False)


def test_adopt_labels_unconfigured_choices_as_default_off(tmp_path: Path, monkeypatch) -> None:
    project = _project(
        tmp_path,
        """\
[project]
site_name = "Existing document"

[project.markdown_extensions.pymdownx.arithmatex]
generic = true

[project.markdown_extensions.pymdownx.superfences]
custom_fences = [{ name = "mermaid" }]
""",
    )
    monkeypatch.chdir(project)
    monkeypatch.setattr("prodockit.adopt._in_venv", lambda: True)

    result = CliRunner().invoke(main, ["adopt", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Options:  Mermaid off · maths off" in result.output
    assert "Choices:" not in result.output
    assert "Use --verbose" in result.output
    verbose = CliRunner().invoke(main, ["adopt", "--dry-run", "--verbose"])
    assert verbose.exit_code == 0, verbose.output
    assert "Choices:  not configured; Mermaid and maths default off" in verbose.output
    assert f"Will save: {project / MANIFEST}" in verbose.output


@pytest.mark.parametrize("offline", [True, False])
def test_mermaid_install_uses_only_the_selected_node_project(
    tmp_path: Path, monkeypatch, offline: bool
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr("prodockit.adopt.shutil.which", lambda _name: "/usr/bin/npm")

    def npm(command, **kwargs):
        assert command[0] == "/usr/bin/npm"
        assert command == [
            "/usr/bin/npm",
            "ci",
            "--no-audit",
            "--no-fund",
            "--offline" if offline else "--prefer-offline",
        ]
        assert kwargs["cwd"] == project / "tools" / "mermaid"
        binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("renderer", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.renderer_resilience.run_installer", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path: SimpleNamespace(path=path, ok=True, version="11.0.0", error=None),
    )

    written = install_tool(project, "mermaid", offline=offline)

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

    monkeypatch.setattr("prodockit.renderer_resilience.run_installer", npm)
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

    monkeypatch.setattr("prodockit.renderer_resilience.run_installer", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mathjax",
        lambda node, script: SimpleNamespace(
            path=script, ok=False, version=None, error="Cannot find module"
        ),
    )

    with pytest.raises(AdoptError, match="npm completed but MathJax is unusable"):
        install_tool(project, "mathjax")


def test_custom_node_manifest_is_backed_up_before_locked_install(
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
            "ci",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
        ]
        binary = project / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("renderer", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prodockit.renderer_resilience.run_installer", npm)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path: SimpleNamespace(path=path, ok=True, version="11.0.0", error=None),
    )

    install_tool(project, "mermaid")

    assert (manifest.parent / "package-lock.json").exists()
    backups = list((project / ".prodockit-adopt-backups").rglob("package.json"))
    assert len(backups) == 1
    assert backups[0].read_text() == '{"name": "author-owned"}\n'


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

    monkeypatch.setattr("prodockit.renderer_resilience.run_installer", npm)
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

    monkeypatch.setattr("prodockit.renderer_resilience.run_installer", npm)
    monkeypatch.setattr(renderer_resilience.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        "prodockit.adopt.probe_mermaid",
        lambda path, **_kwargs: SimpleNamespace(path=path, ok=True, version="11.0.0", error=None),
    )
    notices = []

    install_tool(project, "mermaid", retry_reporter=notices.append)

    assert len(attempts) == 2
    assert len(notices) == 1
    assert notices[0].attempt == 1


def test_adoption_readiness_rejects_an_unusable_mermaid_cli(tmp_path: Path, monkeypatch) -> None:
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
    stylesheet_dir = project / "docs" / "src" / "markdown" / "stylesheets"
    assert all(
        (stylesheet_dir / name).is_file()
        for name in ("pdk.css", "extra.css", "pdk-pdf.css", "print.css")
    )
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
    assert len(re.findall(r"(?m)^extra_css:", config)) == 1
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


@pytest.mark.parametrize("renderer_usable", [True, False])
def test_apply_mapping_form_mermaid_is_transactional(
    tmp_path: Path, monkeypatch, renderer_usable: bool
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
    installed = set()

    def install(root, component, **_kwargs):
        if renderer_usable:
            installed.add(component)
        return []

    monkeypatch.setattr("prodockit.adopt.install_tool", install)
    monkeypatch.setattr(
        "prodockit.adopt._tool_health",
        lambda root, component, **_kwargs: (component in installed, "test renderer"),
    )

    preview = CliRunner().invoke(main, ["adopt", "--dry-run", "--mermaid", "--no-maths"])
    assert preview.exit_code == 0, preview.output

    result = CliRunner().invoke(
        main,
        ["adopt", "--apply", "--mermaid", "--no-maths"],
        input="y\ny\ny\ny\n",
    )

    assert result.exit_code == (0 if renderer_usable else 1), result.output
    if not renderer_usable:
        assert "ADOPTION IS INCOMPLETE" in result.output
        assert "Adoption configuration verified" not in result.output
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")
    assert "  pymdownx.superfences:\n    custom_fences:" in config
    assert "      - name: mermaid" in config
    assert f"prodockit=={__version__}" in (project / "requirements.txt").read_text(encoding="utf-8")


def test_apply_uses_current_readiness_when_initial_probe_recovers(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    calls = 0

    def assessment(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [
            Step(
                "core",
                "Integrate",
                "Standard authoring components",
                "configure" if calls == 1 else "ok",
                "probe result",
            )
        ]

    monkeypatch.setattr("prodockit.cli.assess_adoption", assessment)
    result = CliRunner().invoke(main, ["adopt", "--apply"])
    assert result.exit_code == 0, result.output
    assert "already configured" in result.output
    assert "declined" not in result.output
    assert "Apply this activity?" not in result.output


def test_declining_all_required_activities_reports_incomplete(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    source = (project / "zensical.toml").read_text()
    monkeypatch.chdir(project)
    result = CliRunner().invoke(main, ["adopt", "--apply"], input="n\n" * 10)
    assert result.exit_code == 1, result.output
    assert "ADOPTION IS INCOMPLETE" in result.output
    assert "required activities were declined" in result.output
    assert (project / "zensical.toml").read_text() == source
    assert not (project / MANIFEST).exists()


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

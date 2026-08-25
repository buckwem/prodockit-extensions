# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.project_config import ProjectConfigError, load_project_config


def test_loads_zensical_toml_and_normalises_nested_navigation(tmp_path: Path) -> None:
    path = tmp_path / "zensical.toml"
    path.write_text(
        """\
[project]
site_name = "Example"
docs_dir = "content"
site_dir = "public"
nav = [
    { "Home" = "index.md" },
    { "Guide" = [
        { "Start" = "guide/index.md" },
        { "Details" = "guide/details.md" },
    ] },
]
""",
        encoding="utf-8",
    )

    config = load_project_config(path)

    assert config.site_name == "Example"
    assert config.docs_dir == tmp_path / "content"
    assert config.site_dir == tmp_path / "public"
    assert [(page.title, page.source_path, page.is_index) for page in config.nav_pages] == [
        ("Home", "index.md", True),
        ("Start", "guide/index.md", True),
        ("Details", "guide/details.md", False),
    ]


def test_loads_mkdocs_yaml_without_importing_python_tag_targets(tmp_path: Path) -> None:
    path = tmp_path / "mkdocs.yml"
    path.write_text(
        """\
site_name: YAML example
docs_dir: source
nav:
    - Home: index.md
    - Guide:
        - Intro: guide/intro.md
markdown_extensions:
    - pymdownx.superfences:
        custom_fences:
            - name: mermaid
              format: !!python/name:pymdownx.superfences.fence_code_format
""",
        encoding="utf-8",
    )

    config = load_project_config(path)

    assert config.site_name == "YAML example"
    assert config.docs_dir == tmp_path / "source"
    assert [page.source_path for page in config.nav_pages] == ["index.md", "guide/intro.md"]
    assert (
        config.markdown_extensions["pymdownx.superfences"]["custom_fences"][0]["format"]
        == "pymdownx.superfences.fence_code_format"
    )


def test_paths_are_relative_to_the_config_not_the_callers_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "zensical.toml"
    path.write_text('[project]\ndocs_dir = "writing"\nsite_dir = "output"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = load_project_config(path)

    assert config.docs_dir == project / "writing"
    assert config.site_dir == project / "output"


def test_toml_requires_a_project_table(tmp_path: Path) -> None:
    path = tmp_path / "zensical.toml"
    path.write_text('site_name = "wrong level"\n', encoding="utf-8")

    with pytest.raises(ProjectConfigError, match=r"\[project\]"):
        load_project_config(path)


def test_missing_config_is_reported_with_its_path(tmp_path: Path) -> None:
    path = tmp_path / "zensical.toml"

    with pytest.raises(ProjectConfigError, match=r"zensical\.toml"):
        load_project_config(path)


def test_navigation_rejects_an_unknown_shape_instead_of_silently_omitting_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "zensical.toml"
    path.write_text("[project]\nnav = [42]\n", encoding="utf-8")

    with pytest.raises(ProjectConfigError, match="navigation entry"):
        load_project_config(path)

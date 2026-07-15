# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import subprocess
from pathlib import Path

import pytest
from zensical.extensions.macros import MacroEnv

import zendoc.zensical_macros as zensical_macros
from zendoc.zensical_macros import define_env


def _write_project(tmp_path: Path) -> dict:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Cover\n\nignored, this is the cover page.\n", encoding="utf-8")
    (docs_dir / "chapter1.md").write_text("# Chapter One\n\none two three four five\n", encoding="utf-8")
    (docs_dir / "excluded.md").write_text(
        "---\nexclude_from_word_count: true\n---\n\n# Excluded\n\nsix seven eight\n",
        encoding="utf-8",
    )
    return {
        "docs_dir": str(docs_dir),
        "site_name": "Test project",
        "extra": {},
        "nav": [
            {"url": "index.md", "is_index": True, "children": []},
            {"url": "chapter1.md", "is_index": False, "children": []},
            {"url": "excluded.md", "is_index": False, "children": []},
        ],
    }


@pytest.fixture(autouse=True)
def _no_real_git_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file runs against a fake project, not this
    repository's own git checkout - stub out the git subprocess call so
    _get_repo_url() (and therefore define_env()) doesn't pick up whatever
    remote happens to be configured wherever the test suite is run."""

    def _raise(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(zensical_macros.subprocess, "check_output", _raise)


def test_define_env_sets_word_count_repo_url_and_site_name(tmp_path: Path) -> None:
    env = MacroEnv(conf=_write_project(tmp_path))
    define_env(env)
    # chapter1.md only ("Chapter One" + "one two three four five") - the
    # cover page (index.md, first in nav) and excluded.md (flagged
    # exclude_from_word_count: true) are both left out.
    assert env.variables["word_count"] == "7"
    assert env.variables["repo_url"] == ""
    assert env.variables["site_name"] == "Test project"


def test_get_repo_url_converts_ssh_syntax_to_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        zensical_macros.subprocess,
        "check_output",
        lambda *a, **k: b"git@github.com:buckwem/zendoc-template.git\n",
    )
    assert zensical_macros._get_repo_url() == "https://github.com/buckwem/zendoc-template"


def test_get_repo_url_strips_embedded_ci_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        zensical_macros.subprocess,
        "check_output",
        lambda *a, **k: b"https://gitlab-ci-token:abc123@gitlab.example.com/group/project.git\n",
    )
    assert zensical_macros._get_repo_url() == "https://gitlab.example.com/group/project"


def test_reference_style_defaults_to_the_tight_european_look(tmp_path: Path) -> None:
    env = MacroEnv(conf=_write_project(tmp_path))
    define_env(env)
    css = env.macros["reference_style"]()
    assert "margin-top: -0.8em !important;" in css
    assert "padding-left" not in css


def test_reference_style_switches_to_the_global_look_when_configured(tmp_path: Path) -> None:
    conf = _write_project(tmp_path)
    conf["extra"]["reference_style"] = "global"
    env = MacroEnv(conf=conf)
    define_env(env)
    css = env.macros["reference_style"]()
    assert "padding-left: 1.27cm !important;" in css
    assert "margin-top: 2em !important;" in css


def test_acronym_and_glossary_style_always_use_the_tight_spacing(tmp_path: Path) -> None:
    conf = _write_project(tmp_path)
    conf["extra"]["reference_style"] = "global"
    env = MacroEnv(conf=conf)
    define_env(env)
    assert "margin-top: -0.8em !important;" in env.macros["acronym_style"]()
    assert "margin-top: -0.8em !important;" in env.macros["glossary_style"]()


def test_heading_counter_reset_disabled_via_config(tmp_path: Path) -> None:
    conf = _write_project(tmp_path)
    conf["extra"]["heading_numbering"] = False
    env = MacroEnv(conf=conf)
    define_env(env)
    css = env.macros["heading_counter_reset"](object())
    assert 'content: "" !important;' in css


def test_heading_counter_reset_falls_back_to_zero_outside_a_real_build(tmp_path: Path) -> None:
    """zendoc.headings.prescan() returns None outside an active Zensical
    build - heading_counter_reset() should degrade to a harmless
    counter-reset-to-zero rather than raising."""
    env = MacroEnv(conf=_write_project(tmp_path))
    define_env(env)
    page = type("Page", (), {"path": "chapter1.md"})()
    css = env.macros["heading_counter_reset"](page)
    assert "counter-reset: h1-count 0 !important;" in css

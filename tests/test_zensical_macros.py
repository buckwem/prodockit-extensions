# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import subprocess
from pathlib import Path

import pytest

import prodockit.zensical_macros as zensical_macros
from prodockit.zensical_macros import define_env


class _MacroEnvironment:
    """The documented macro-module contract used by ``define_env``.

    Deliberately local: importing Zensical's internal ``MacroEnv`` made these
    Prodockit tests fail when an implementation class moved, even though the
    documented ``define_env(env)`` contract had not changed.
    """

    def __init__(self, config: dict) -> None:
        self.variables = {"config": config}
        self.macros: dict[str, object] = {}

    def macro(self, function):
        self.macros[function.__name__] = function
        return function


def _macro_env(config: dict) -> _MacroEnvironment:
    return _MacroEnvironment(config)


def _write_project(tmp_path: Path) -> dict:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text(
        "# Cover\n\nignored, this is the cover page.\n", encoding="utf-8"
    )
    (docs_dir / "chapter1.md").write_text(
        "# Chapter One\n\none two three four five\n", encoding="utf-8"
    )
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
    _get_repo_url()/_get_release() (and therefore define_env()) don't pick
    up whatever remote/tags happen to be configured wherever the test
    suite is run."""

    def _raise(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(zensical_macros.subprocess, "check_output", _raise)


def test_define_env_sets_word_count_repo_url_release_and_site_name(tmp_path: Path) -> None:
    env = _macro_env(_write_project(tmp_path))
    define_env(env)
    # chapter1.md only ("Chapter One" + "one two three four five") - the
    # cover page (index.md, first in nav) and excluded.md (flagged
    # exclude_from_word_count: true) are both left out.
    assert env.variables["word_count"] == "7"
    assert env.variables["repo_url"] == ""
    assert env.variables["release"] == ""
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


def test_get_release_returns_the_latest_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        zensical_macros.subprocess,
        "check_output",
        lambda *a, **k: b"1.2.0\n",
    )
    assert zensical_macros._get_release() == "1.2.0"


def test_get_release_is_empty_with_no_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(zensical_macros.subprocess, "check_output", _raise)
    assert zensical_macros._get_release() == ""


def test_reference_style_defaults_to_the_tight_european_look(tmp_path: Path) -> None:
    env = _macro_env(_write_project(tmp_path))
    define_env(env)
    css = env.macros["reference_style"]()
    assert "margin-top: -0.8em !important;" in css
    assert "padding-left" not in css


def test_reference_style_switches_to_the_global_look_when_configured(tmp_path: Path) -> None:
    conf = _write_project(tmp_path)
    conf["extra"]["reference_style"] = "global"
    env = _macro_env(conf)
    define_env(env)
    css = env.macros["reference_style"]()
    assert "padding-left: 1.27cm !important;" in css
    assert "margin-top: 2em !important;" in css


def test_acronym_and_glossary_style_always_use_the_tight_spacing(tmp_path: Path) -> None:
    conf = _write_project(tmp_path)
    conf["extra"]["reference_style"] = "global"
    env = _macro_env(conf)
    define_env(env)
    assert "margin-top: -0.8em !important;" in env.macros["acronym_style"]()
    assert "margin-top: -0.8em !important;" in env.macros["glossary_style"]()


def test_heading_counter_reset_disabled_via_config(tmp_path: Path) -> None:
    conf = _write_project(tmp_path)
    conf["extra"]["heading_numbering"] = False
    env = _macro_env(conf)
    define_env(env)
    css = env.macros["heading_counter_reset"](object())
    assert 'content: "" !important;' in css


def test_heading_counter_reset_falls_back_to_zero_outside_a_real_build(tmp_path: Path) -> None:
    """prodockit.headings.prescan() returns None outside an active Zensical
    build - heading_counter_reset() should degrade to a harmless
    counter-reset-to-zero rather than raising."""
    env = _macro_env(_write_project(tmp_path))
    define_env(env)
    page = type("Page", (), {"path": "chapter1.md"})()
    css = env.macros["heading_counter_reset"](page)
    assert "counter-reset: h1-count 0 !important;" in css


def test_heading_counter_reset_seeds_from_a_real_prescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The "real build, non-appendix page with n>0" branch - continuing
    the numeric sequence from earlier nav pages' own h1 count - had no
    test at all; only the "outside a build, falls back to 0" branch did."""
    env = _macro_env(_write_project(tmp_path))
    define_env(env)
    monkeypatch.setattr(zensical_macros, "prescan", lambda: ({"chapter2.md": 3}, {}))
    page = type("Page", (), {"path": "chapter2.md"})()
    css = env.macros["heading_counter_reset"](page)
    assert "counter-reset: h1-count 3 !important;" in css
    assert "counter-reset: toc1 4 !important;" in css


def test_heading_counter_reset_letters_an_appendix_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The appendix-letter CSS branch had no test at all - only the
    disabled and outside-a-build fallback branches did."""
    env = _macro_env(_write_project(tmp_path))
    define_env(env)
    monkeypatch.setattr(zensical_macros, "prescan", lambda: ({}, {"acronyms.md": "A"}))
    page = type("Page", (), {"path": "acronyms.md"})()
    css = env.macros["heading_counter_reset"](page)
    assert 'content: "Appendix A. " !important;' in css
    assert 'content: "A." counter(h2-count) " " !important;' in css
    assert 'content: "A." counter(h2-count) "." counter(h3-count) " " !important;' in css
    assert 'content: "Figure A." !important;' in css
    assert 'content: "Table A." !important;' in css


# --- The shallow-clone case (#125) ------------------------------------------
#
# `git describe --tags` returns nothing in a shallow clone even when the
# repository has tags, so `{{ release }}` resolves to an empty string and the
# cover line simply disappears - correct-looking output, no error, and it
# works in every full local clone. That combination shipped twice.
#
# Having no tags at all is a normal state and stays silent; only the shallow
# case warns, because that is the one where a tag was expected.


def _reset_shallow_warning() -> None:
    zensical_macros._warned_about_shallow_clone = False


def test_warns_when_a_shallow_clone_lost_the_release(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _reset_shallow_warning()
    monkeypatch.setattr(zensical_macros, "_repository_is_shallow", lambda: True)
    assert zensical_macros._warn_if_release_lost_to_a_shallow_clone("") is True
    out = capsys.readouterr().out
    assert "shallow clone" in out
    # Names the fix for both CI systems, not just the symptom.
    assert "fetch-depth: 0" in out
    assert "GIT_DEPTH" in out


def test_does_not_warn_when_a_full_clone_simply_has_no_tags(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A project that has never tagged is perfectly normal - warning there
    would train people to ignore the message."""
    _reset_shallow_warning()
    monkeypatch.setattr(zensical_macros, "_repository_is_shallow", lambda: False)
    assert zensical_macros._warn_if_release_lost_to_a_shallow_clone("") is False
    assert capsys.readouterr().out == ""


def test_does_not_warn_when_the_release_resolved(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _reset_shallow_warning()
    monkeypatch.setattr(zensical_macros, "_repository_is_shallow", lambda: True)
    assert zensical_macros._warn_if_release_lost_to_a_shallow_clone("1.2.0") is False
    assert capsys.readouterr().out == ""


def test_warns_only_once_per_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`zensical serve` re-enters define_env() on every save, so a per-build
    warning would scroll the terminal for the whole session."""
    _reset_shallow_warning()
    monkeypatch.setattr(zensical_macros, "_repository_is_shallow", lambda: True)
    assert zensical_macros._warn_if_release_lost_to_a_shallow_clone("") is True
    capsys.readouterr()
    assert zensical_macros._warn_if_release_lost_to_a_shallow_clone("") is False
    assert capsys.readouterr().out == ""


def test_shallow_detection_against_a_real_repository(tmp_path: Path) -> None:
    """The detection itself, against real git rather than a stub - a full
    clone must not be reported as shallow, or every project would warn."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert zensical_macros._repository_is_shallow() is False
    finally:
        os.chdir(original)

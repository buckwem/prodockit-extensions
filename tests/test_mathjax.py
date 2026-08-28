# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for `prodockit init-mathjax` - the one MathJax installer.

The configuration used to exist twice, in bootstrap and in a template's
CI, and two copies of it is the problem this module exists to remove
(prodockit-extensions#276). So these tests are about the *installer*
rather than about either caller.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.mathjax import CONFIG_SOURCE, MathJaxError, install_mathjax


def _project(tmp_path: Path, *, pinned: bool = True) -> Path:
    (tmp_path / "docs").mkdir()
    if pinned:
        package = tmp_path / "tools" / "mathjax" / "node_modules" / "mathjax-full"
        es5 = package / "es5"
        es5.mkdir(parents=True)
        (es5 / "tex-svg-full.js").write_text("BUNDLE", encoding="utf-8")
        (package / "LICENSE").write_text("APACHE", encoding="utf-8")
    return tmp_path


def test_it_writes_the_config_and_copies_the_bundle_and_license(tmp_path: Path) -> None:
    project = _project(tmp_path)

    result = install_mathjax(project)

    assert result.bundle.read_text(encoding="utf-8") == "BUNDLE"
    assert result.license.read_text(encoding="utf-8") == "APACHE"
    config = result.config.read_text(encoding="utf-8")
    assert "processHtmlClass" in config and "arithmatex" in config


def test_the_delimiters_are_the_ones_arithmatex_emits(tmp_path: Path) -> None:
    """The reason one copy matters. Four layers of escaping, and a copy
    that looks right can be wrong - which fails silently, because both
    versions are valid JavaScript and the page simply shows raw TeX."""
    install_mathjax(_project(tmp_path))
    config = (tmp_path / "docs" / "javascripts" / "mathjax.js").read_text(encoding="utf-8")

    assert r'inlineMath: [["\\(", "\\)"]]' in config
    assert r'displayMath: [["\\[", "\\]"]]' in config


def test_the_config_is_loaded_before_the_bundle_by_construction() -> None:
    """MathJax reads `window.MathJax` once at startup, so a config that
    arrives afterwards is ignored - which is the whole of #263. The file
    says so, because whoever edits `extra_javascript` needs to know."""
    assert "once at startup" in CONFIG_SOURCE


def test_both_files_are_ignored_rather_than_committed(tmp_path: Path) -> None:
    """The bundle is third-party code and does not belong in a project's
    repository."""
    project = _project(tmp_path)
    (project / ".gitignore").write_text("tools/*/node_modules/\n", encoding="utf-8")

    result = install_mathjax(project)

    ignored = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "docs/javascripts/vendor/" in ignored
    assert "docs/javascripts/mathjax.js" in ignored
    assert "tools/*/node_modules/" in ignored, "an existing entry must survive"
    assert result.ignored


def test_running_it_twice_does_not_stack_entries(tmp_path: Path) -> None:
    project = _project(tmp_path)

    install_mathjax(project)
    second = install_mathjax(project)

    ignored = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ignored.count("docs/javascripts/vendor/") == 1
    assert second.ignored == [], "nothing left to add"


def test_it_can_be_told_to_leave_gitignore_alone(tmp_path: Path) -> None:
    """A caller that manages its own ignore rules - or a CI runner, which
    has no repository to protect - should not have one written for it."""
    project = _project(tmp_path)

    install_mathjax(project, update_gitignore=False)

    assert not (project / ".gitignore").exists()


def test_a_missing_pinned_install_says_what_to_run(tmp_path: Path) -> None:
    """The bundle is copied from `tools/mathjax` rather than downloaded,
    so that the website and the PDF use the same MathJax. Fetching a
    different one instead would be worse than failing."""
    project = _project(tmp_path, pinned=False)

    with pytest.raises(MathJaxError) as exc_info:
        install_mathjax(project)

    assert "npm ci --prefix tools/mathjax" in str(exc_info.value)


def test_a_missing_package_license_says_what_to_run(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "tools" / "mathjax" / "node_modules" / "mathjax-full" / "LICENSE").unlink()

    with pytest.raises(MathJaxError) as exc_info:
        install_mathjax(project)

    assert "LICENSE" in str(exc_info.value)
    assert "npm ci --prefix tools/mathjax" in str(exc_info.value)


def test_the_cli_reports_what_it_wrote(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from prodockit.cli import main

    project = _project(tmp_path)
    result = CliRunner().invoke(main, ["init-mathjax", "--root", str(project)])

    assert result.exit_code == 0
    assert all(name in result.output for name in ("mathjax.js", "tex-svg-full.js", "LICENSE"))


def test_repository_generates_mathjax_before_every_site_build() -> None:
    root = Path(__file__).resolve().parent.parent
    for name in ("ci.yml", "docs.yml", "drift.yml"):
        workflow = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        install = "prodockit init-mathjax --no-gitignore"
        build = "zensical build --clean --strict"
        assert "npm ci --prefix tools/mathjax" in workflow
        assert install in workflow
        assert workflow.index(install) < workflow.index(build), (
            f"{name} builds before installing the website MathJax assets"
        )


def test_repository_does_not_track_generated_mathjax_assets() -> None:
    import subprocess

    root = Path(__file__).resolve().parent.parent
    ignored = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "docs/javascripts/vendor/" in ignored
    assert "docs/javascripts/mathjax.js" in ignored

    tracked = subprocess.run(
        ["git", "ls-files", "docs/javascripts/mathjax.js", "docs/javascripts/vendor"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert not tracked, f"generated MathJax assets are still tracked: {tracked}"


def test_the_cli_fails_clearly_without_the_toolchain(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from prodockit.cli import main

    result = CliRunner().invoke(
        main, ["init-mathjax", "--root", str(_project(tmp_path, pinned=False))]
    )

    assert result.exit_code == 1
    assert "npm ci --prefix tools/mathjax" in result.output

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit import __version__
from prodockit.pdf.cli import main

_ZENSICAL_TOML = """
[project]
site_name = "Test project"

nav = [
  {"Home" = "index.md"},
]
"""


def _write_project(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Cover\n", encoding="utf-8")
    (tmp_path / "zensical.toml").write_text(_ZENSICAL_TOML, encoding="utf-8")


def _install_fake_pandoc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    pandoc_path = bin_dir / "pandoc"
    pandoc_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    pandoc_path.chmod(pandoc_path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_pdf_command_builds_using_the_default_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 0
    assert "Wrote docs/site_documentation.pdf" in result.output
    assert (tmp_path / "docs" / "site_documentation.pdf").exists()


def test_pdf_command_accepts_a_config_file_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    (tmp_path / "custom.toml").write_text(
        (tmp_path / "zensical.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf", "-f", "custom.toml"])

    assert result.exit_code == 0
    assert (tmp_path / "docs" / "site_documentation.pdf").exists()


def test_cli_registers_only_the_public_and_hidden_legacy_pdf_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "pdf" in main.commands
    assert "pdf-legacy" in main.commands
    assert main.commands["pdf-legacy"].hidden
    assert "pdf-built-site" not in main.commands
    assert "pdf-legacy" not in result.output
    assert "pdf-built-site" not in result.output


def test_hidden_legacy_command_routes_only_to_the_old_renderer(monkeypatch) -> None:
    import prodockit.cli as cli_module

    calls = []

    def legacy(config_file, *, markdown_file, on_stage):
        calls.append((config_file, markdown_file))
        return "legacy.pdf"

    def built_site(*args, **kwargs):
        raise AssertionError("the hidden command must call only the legacy renderer")

    monkeypatch.setattr(cli_module, "build_pdf_from_zensical_config", legacy)
    monkeypatch.setattr(cli_module, "build_pdf_from_built_site", built_site)

    result = CliRunner().invoke(
        main,
        ["pdf-legacy", "--config-file", "project.toml", "--markdown-file", "page.md"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("project.toml", "page.md")]
    assert "Wrote legacy.pdf" in result.output


def test_public_pdf_command_routes_only_to_the_built_site_renderer(monkeypatch) -> None:
    import prodockit.cli as cli_module

    calls = []

    def built_site(config_file, *, markdown_file, on_stage):
        calls.append((config_file, markdown_file))
        return "built-site.pdf"

    def legacy(*args, **kwargs):
        raise AssertionError("the public command must not use the legacy renderer")

    monkeypatch.setattr(cli_module, "build_pdf_from_zensical_config", legacy)
    monkeypatch.setattr(cli_module, "build_pdf_from_built_site", built_site)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 0, result.output
    assert calls == [("zensical.toml", None)]
    assert "Wrote built-site.pdf" in result.output


def test_public_pdf_command_reports_built_site_boundary_errors(monkeypatch) -> None:
    import prodockit.cli as cli_module

    def fail(*args, **kwargs):
        raise cli_module.BuiltSiteError("generated page is missing its article")

    monkeypatch.setattr(cli_module, "build_pdf_from_built_site", fail)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 1
    assert "Error: generated page is missing its article" in result.output


def test_markdown_file_help_distinguishes_pdf_contents_from_the_site_build() -> None:
    result = CliRunner().invoke(main, ["pdf", "--help"])

    assert result.exit_code == 0
    assert "Include only this Markdown file in the PDF" in result.output
    assert "rebuilds the full site" in result.output


def test_pdf_command_exits_non_zero_and_reports_pandoc_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "boom" >&2; exit 1')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_pdf_command_prints_the_failing_commands_own_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exception's message names a command and an exit code; the cause
    is in the stderr it captured.

    Regression test with a real cost behind it (#188): a reader following
    the User Guide on a clean macOS machine got `pandoc exited with status
    43` and nothing else, while the stderr prodockit had already collected
    said WeasyPrint could not load `libgobject-2.0-0` and linked its
    install instructions. Diagnosing it needed a script calling the Python
    API directly to reach `PdfBuildError.stderr`.

    The stub below stands in for that: pandoc's own warnings first, the
    engine's real complaint last - the shape that makes truncating the
    *head* of this output the wrong thing to do.
    """
    _write_project(tmp_path)
    _install_fake_pandoc(
        tmp_path,
        monkeypatch,
        'echo "[WARNING] Ignoring duplicate attribute role=\\"list\\"." >&2; '
        "echo \"OSError: cannot load library 'libgobject-2.0-0'\" >&2; "
        "exit 43",
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 1
    assert "status 43" in result.output, "the summary line should still be there"
    assert "cannot load library 'libgobject-2.0-0'" in result.output, (
        "the cause must reach the user, not just the exit code"
    )
    assert "[WARNING] Ignoring duplicate attribute" in result.output, (
        "printed whole - a head-truncated excerpt would drop the tail, "
        "which is where a pandoc failure puts the real error"
    )


def test_pdf_command_says_nothing_extra_when_no_stderr_was_captured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure with nothing on stderr must not gain an empty, unexplained
    heading - the counterpart to the test above, and what stops the fix
    from being "always print a header"."""
    _write_project(tmp_path)
    _install_fake_pandoc(tmp_path, monkeypatch, "exit 1")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Output from the failing command:" not in result.output


def test_pdf_command_reports_a_missing_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code != 0


def test_pdf_command_no_longer_builds_a_source_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pdf_source_bundle` used to make `prodockit pdf` also call
    `build_source_bundle()` as a side effect - split into its own
    `source-bundle` command (prodockit-extensions#212), so a project that
    wants only the document no longer pays for a source-bundle pass (a
    `git ls-files` scan and a second `weasyprint` invocation) it never
    asked for. `tmp_path` here is deliberately not a git working tree -
    if `pdf` still triggered a source bundle, that alone would raise
    `SourceBundleError` and fail this test."""
    _write_project(tmp_path)
    zensical_toml = tmp_path / "zensical.toml"
    zensical_toml.write_text(
        zensical_toml.read_text(encoding="utf-8") + "\n[project.extra]\npdf_source_bundle = true\n",
        encoding="utf-8",
    )
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "source_bundle.pdf").exists()
    assert not (tmp_path / "docs" / "source_bundle.pdf").exists()


def _install_fake_weasyprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    weasyprint_path = bin_dir / "weasyprint"
    weasyprint_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    weasyprint_path.chmod(weasyprint_path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_source_bundle_command_builds_into_docs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The output lives inside `docs_dir` by default (prodockit-extensions#212)
    - unlike the pre-#212 default of the project's top-level directory -
    so Zensical serves it with no separate copy step."""
    _write_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    _install_fake_weasyprint(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$2"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["source-bundle"])

    assert result.exit_code == 0, result.output
    assert "Wrote docs/source_bundle.pdf" in result.output
    assert (tmp_path / "docs" / "source_bundle.pdf").exists()
    assert not (tmp_path / "source_bundle.pdf").exists()


def test_source_bundle_command_reports_a_source_bundle_error_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tmp_path` here is deliberately not a git working tree, so
    `discover_markdown_and_config_files()` raises `SourceBundleError`
    before `weasyprint` is ever invoked. Guards the same class of bug the
    `pdf` command already learned from once (prodockit-extensions#188):
    an except clause that omits `SourceBundleError` lets it escape
    uncaught instead of exiting cleanly with an `Error: ...` message."""
    _write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["source-bundle"])

    assert isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_pdf_command_accepts_a_markdown_file_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    (tmp_path / "docs" / "chapter1.md").write_text("# Chapter One\n", encoding="utf-8")
    _install_fake_pandoc(tmp_path, monkeypatch, 'echo "%PDF-1.4 stub" > "$3"')
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["pdf", "-m", "chapter1.md"])

    assert result.exit_code == 0
    assert "Wrote docs/chapter1.pdf" in result.output
    assert (tmp_path / "docs" / "chapter1.pdf").exists()
    assert not (tmp_path / "docs" / "site_documentation.pdf").exists()


def test_version_flag_prints_the_bare_version() -> None:
    """Matches `zensical --version`, which prints just the number. The two
    are normally installed and reported together, and click's own default
    ("prodockit, version X.Y.Z") would need parsing to compare them."""
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_version_flag_matches_the_version_declared_in_pyproject() -> None:
    """The flag exists to answer "which version is this", so the number it
    prints has to be the project's real one.

    Compared against `pyproject.toml` rather than
    `importlib.metadata.version()`: in an editable checkout the installed
    metadata is only regenerated on reinstall, so it still reports the
    version from whenever `pip install -e .` last ran. That made this test
    fail against a freshly bumped tree - the stale oracle, not the flag.
    `pyproject.toml` is the declaration a release is actually cut from."""
    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert declared is not None, "no version found in pyproject.toml"

    result = CliRunner().invoke(main, ["--version"])

    assert result.output.strip() == declared.group(1)


def test_version_appears_in_help() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert "--version" in result.output
    assert "Show the version and exit." in result.output


def test_the_build_says_which_stage_it_is_on(monkeypatch, tmp_path) -> None:
    """prodockit-extensions#375.

    A PDF build printed one line at the start and one at the end, with
    minutes of silence between - and a silent terminal is
    indistinguishable from a hung one.
    """
    _write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_build(config_path, *, markdown_file=None, on_stage=None):
        assert on_stage is not None, "the CLI has to ask for progress to get any"
        on_stage(1, 3, "Preparing pages")
        on_stage(3, 3, "Building the PDF")
        return "docs/site_documentation.pdf"

    monkeypatch.setattr("prodockit.cli.build_pdf_from_built_site", fake_build)
    result = CliRunner().invoke(main, ["pdf"])

    assert result.exit_code == 0, result.output
    assert "[1/3] Preparing pages" in result.output
    assert "[3/3] Building the PDF" in result.output
    # ...and how long the whole thing took, on the line that says it is done.
    assert re.search(r"Wrote docs/site_documentation\.pdf in \d", result.output), result.output


def test_the_stage_list_grows_when_an_index_is_wanted() -> None:
    """The page numbers an index needs do not exist until the document
    has been laid out, so an indexed build lays it out twice - two more
    stages, and a reader watching should see why it is building again."""
    from prodockit.pdf.build import _stage_titles

    plain = _stage_titles(include_index=False)
    indexed = _stage_titles(include_index=True)

    assert len(indexed) == len(plain) + 2
    assert "Collecting index entries" in indexed
    assert "Rebuilding with page numbers" in indexed
    # Laying the document out is what an indexed build ends on, having
    # done it twice. Nothing follows it: a stage that named work already
    # finished was reported for every build until #482.
    assert plain[-1] == "Building the PDF"
    assert indexed[-1] == "Rebuilding with page numbers"


def test_a_duration_is_readable_out_loud() -> None:
    """ "182.4s" makes a reader do the division themselves."""
    from prodockit.cli import _took

    assert _took(9.87) == "9.9s"
    assert _took(59.9) == "59.9s"
    assert _took(60) == "1m 0s"
    assert _took(182.4) == "3m 2s"

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Failure boundaries for individual ``pdk boot`` stages.

These cases deliberately describe broken or incomplete machines.  They use
the same hermetic command runner as the CLI harness, so none of the probes can
fall through to the workstation or network running the suite.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from bootstrap_cli_harness import CliFakeRunner, unreachable

import prodockit.bootstrap.stages as stages
from prodockit.bootstrap import BootstrapConfig, CommandResult, Status, build_context
from prodockit.bootstrap.model import MACOS, UBUNTU


def _context(
    tmp_path: Path,
    *,
    runner: CliFakeRunner | None = None,
    platform: str = MACOS,
    **config: str,
):
    values = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.test",
        "username": "ada",
        "host": "github.com",
        "namespace": "ada",
        "project_name": "report",
        "project_dir": str(tmp_path / "report"),
    }
    values.update(config)
    return build_context(
        BootstrapConfig(**values),  # type: ignore[arg-type]
        runner=runner or CliFakeRunner(),
        platform=platform,
        home=tmp_path,
        fetch=unreachable,
    )


def test_clone_stage_distinguishes_a_directory_from_a_git_clone(tmp_path: Path) -> None:
    (tmp_path / "report").mkdir()

    result = stages._check_clone(_context(tmp_path))

    assert result.status is Status.WRONG
    assert "not a git repository" in result.detail


def test_project_probe_is_unknown_until_its_address_is_configured(tmp_path: Path) -> None:
    context = _context(tmp_path, namespace="")

    assert stages.project_on_host(context) is None
    assert stages.own_project_exists(context) is False


def test_remote_project_probe_rejects_a_clone_whose_tree_cannot_be_read(
    tmp_path: Path,
) -> None:
    runner = CliFakeRunner(
        {
            "clone --depth 1 --filter=blob:none": CommandResult(0),
            "ls-tree --name-only HEAD": CommandResult(1, stderr="bad tree"),
        }
    )

    assert stages._remote_holds_a_project(_context(tmp_path, runner=runner)) is False


def test_remote_project_probe_rejects_a_clone_failure(tmp_path: Path) -> None:
    runner = CliFakeRunner(
        {"clone --depth 1 --filter=blob:none": CommandResult(1, stderr="unreachable")}
    )

    assert stages._remote_holds_a_project(_context(tmp_path, runner=runner)) is False


@pytest.mark.parametrize(
    "responses",
    [
        {"clone --depth 1 --no-checkout": CommandResult(1, stderr="unreachable")},
        {
            "clone --depth 1 --no-checkout": CommandResult(0),
            "ls-tree --name-only HEAD": CommandResult(0, "README.md"),
            "rev-list --count HEAD": CommandResult(1, stderr="bad history"),
        },
    ],
)
def test_readme_only_probe_treats_any_incomplete_probe_as_unsafe(
    tmp_path: Path, responses: dict[str, CommandResult]
) -> None:
    assert (
        stages.remote_is_only_its_first_readme(_context(tmp_path, runner=CliFakeRunner(responses)))
        is False
    )


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("\nPandoc 3.10.1\n", None),
        ("pandoc\n", None),
        ("header\npandoc 3.10.1\n", "3.10.1"),
    ],
)
def test_pandoc_version_parser_handles_malformed_and_prefixed_output(
    output: str, expected: str | None
) -> None:
    assert stages._pandoc_version(output) == expected


def test_pandoc_stage_reports_an_unreadable_installed_version(tmp_path: Path) -> None:
    runner = CliFakeRunner({"pandoc --version": CommandResult(0, "pandoc")})

    result = stages._check_pandoc(_context(tmp_path, runner=runner))

    assert result.status is Status.WRONG
    assert "version could not be read" in result.detail


def test_font_fallback_handles_an_empty_font_directory(tmp_path: Path) -> None:
    (tmp_path / "Library" / "Fonts").mkdir(parents=True)
    runner = CliFakeRunner({"fc-list : family": CommandResult(127)})

    assert stages._absent_pdf_fonts(_context(tmp_path, runner=runner)) == ""


def test_font_fallback_normalises_font_filenames(tmp_path: Path) -> None:
    fonts = tmp_path / "Library" / "Fonts"
    fonts.mkdir(parents=True)
    (fonts / "Inter-Regular.ttf").touch()
    (fonts / "JetBrains_Mono.ttf").touch()
    runner = CliFakeRunner({"fc-list : family": CommandResult(127)})

    assert stages._absent_pdf_fonts(_context(tmp_path, runner=runner)) == ""


def test_project_environment_reports_a_missing_requirements_file(tmp_path: Path) -> None:
    project = tmp_path / "report"
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "python").touch()

    result = stages._check_project_env(_context(tmp_path))

    assert result.status is Status.WRONG
    assert "no requirements.txt" in result.detail


def test_project_environment_reports_dependencies_that_do_not_import(tmp_path: Path) -> None:
    project = tmp_path / "report"
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "python").touch()
    (project / "requirements.txt").touch()

    result = stages._check_project_env(_context(tmp_path))

    assert result.status is Status.MISSING
    assert "dependencies are not installed" in result.detail


def test_node_stage_rejects_an_unreadable_version(tmp_path: Path) -> None:
    runner = CliFakeRunner({"node --version": CommandResult(0, "development")})

    result = stages._check_node(_context(tmp_path, runner=runner))

    assert result.status is Status.WRONG
    assert "could not read a version" in result.detail


def test_node_stage_requests_missing_configuration_after_tool_checks(
    tmp_path: Path,
) -> None:
    runner = CliFakeRunner(
        {"node --version": CommandResult(0, "v24.1.0"), "npm --version": CommandResult(0, "11")}
    )

    result = stages._check_node(_context(tmp_path, runner=runner, project_name=""))

    assert result.status is Status.UNKNOWN


def test_node_stage_can_succeed_before_the_project_directory_exists(tmp_path: Path) -> None:
    runner = CliFakeRunner(
        {"node --version": CommandResult(0, "v24.1.0"), "npm --version": CommandResult(0, "11")}
    )

    result = stages._check_node(_context(tmp_path, runner=runner))

    assert result.status is Status.OK


def test_ubuntu_locale_without_lang_is_unknown(tmp_path: Path) -> None:
    runner = CliFakeRunner({"locale": CommandResult(0, "LC_TIME=en_GB.UTF-8")})

    assert stages._reader_language(_context(tmp_path, runner=runner, platform=UBUNTU)) is None


def test_vscode_settings_reject_a_non_object_document(tmp_path: Path) -> None:
    settings = tmp_path / "report" / ".vscode" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("[]", encoding="utf-8")

    result = stages._check_vscode_settings(_context(tmp_path))

    assert result.status is Status.WRONG
    assert "not a JSON object" in result.detail


def test_vscode_settings_report_missing_markdown_associations(tmp_path: Path) -> None:
    settings = tmp_path / "report" / ".vscode" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}", encoding="utf-8")

    result = stages._check_vscode_settings(_context(tmp_path))

    assert result.status is Status.MISSING
    assert "Markdown is not associated" in result.detail


def test_vscode_settings_report_a_language_mismatch(tmp_path: Path) -> None:
    settings = tmp_path / "report" / ".vscode" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "files.associations": {"*.md": "python-markdown"},
                "ltex.language": "en-US",
            }
        ),
        encoding="utf-8",
    )
    runner = CliFakeRunner({"defaults read -g AppleLocale": CommandResult(0, "en_GB")})

    result = stages._check_vscode_settings(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert "LTeX+ is not set to en-GB" in result.detail


def test_csl_scanner_ignores_comments_and_empty_values(tmp_path: Path) -> None:
    project = tmp_path / "report"
    project.mkdir()
    (project / "zensical.toml").write_text(
        "# csl_style = 'ignored.csl'\ncsl_style = ''\n", encoding="utf-8"
    )

    assert stages._configured_csl_style(_context(tmp_path)) == stages.DEFAULT_CSL_STYLE


def test_site_url_is_empty_when_a_required_component_is_missing(tmp_path: Path) -> None:
    assert stages.site_url(_context(tmp_path, namespace="")) == ""


def test_history_keep_choice_checks_file_mode_both_ways(tmp_path: Path) -> None:
    project = tmp_path / "report"
    (project / ".git").mkdir(parents=True)
    template = _context(tmp_path).host.template_remote

    wrong = stages._check_fresh_history(
        _context(
            tmp_path,
            history="keep",
            runner=CliFakeRunner(
                {
                    "remote get-url origin": CommandResult(0, template),
                    "config core.fileMode": CommandResult(0, "true"),
                }
            ),
        )
    )
    kept = stages._check_fresh_history(
        _context(
            tmp_path,
            history="keep",
            runner=CliFakeRunner(
                {
                    "remote get-url origin": CommandResult(0, template),
                    "config core.fileMode": CommandResult(0, "false"),
                }
            ),
        )
    )

    assert wrong.status is Status.WRONG
    assert kept.status is Status.OK


def test_namespace_report_is_silent_for_a_host_without_special_guidance(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    context = replace(context, host=replace(context.host, namespace_note=""))

    assert stages._namespace_report(context) == []


def test_remote_stage_reports_an_unexpected_origin(tmp_path: Path) -> None:
    (tmp_path / "report" / ".git").mkdir(parents=True)
    runner = CliFakeRunner(
        {"remote get-url origin": CommandResult(0, "git@example.test:wrong.git")}
    )

    result = stages._check_remote(_context(tmp_path, runner=runner))

    assert result.status is Status.WRONG
    assert "expected" in result.detail


def test_mathjax_stage_accepts_an_install_after_its_pinned_source_is_removed(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _source, _license_source, bundle, license_path, config = stages._mathjax_paths(context)
    bundle.parent.mkdir(parents=True)
    bundle.touch()
    license_path.touch()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()

    result = stages._check_mathjax(context)

    assert result.status is Status.OK


def test_site_stage_is_not_applicable_without_a_fixed_pages_address(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    context = replace(context, host=replace(context.host, pages_url=""))

    result = stages._check_site_published(context)

    assert result.status is Status.OK
    assert "not checked" in result.detail


def test_first_push_reports_an_unreachable_origin(tmp_path: Path) -> None:
    (tmp_path / "report" / ".git").mkdir(parents=True)
    runner = CliFakeRunner(
        {
            "remote get-url origin": CommandResult(0, "git@github.com:ada/report.git"),
            "status --porcelain": CommandResult(0, ""),
            "ls-remote origin HEAD": CommandResult(1, stderr="offline"),
        }
    )

    result = stages._check_first_push(_context(tmp_path, runner=runner))

    assert result.status is Status.WRONG
    assert "could not reach origin" in result.detail


def test_first_push_reports_a_remote_commit_without_a_local_commit(tmp_path: Path) -> None:
    (tmp_path / "report" / ".git").mkdir(parents=True)
    runner = CliFakeRunner(
        {
            "remote get-url origin": CommandResult(0, "git@github.com:ada/report.git"),
            "status --porcelain": CommandResult(0, ""),
            "ls-remote origin HEAD": CommandResult(0, "abc123\tHEAD"),
            "rev-parse HEAD": CommandResult(1, stderr="no commit"),
        }
    )

    result = stages._check_first_push(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert "nothing committed here" in result.detail


def test_pages_stage_can_skip_a_host_without_an_anonymous_metadata_api(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    context = replace(context, host=replace(context.host, repo_api=""))

    result = stages._check_pages(context)

    assert result.status is Status.OK
    assert "no anonymous metadata" in result.detail


@pytest.mark.parametrize("payload", ["not json", "[]", "null"])
def test_pages_metadata_parser_rejects_invalid_or_non_object_json(payload: str) -> None:
    assert stages._json_object(payload) is None

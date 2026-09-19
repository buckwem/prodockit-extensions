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
from prodockit.bootstrap import BootstrapConfig, CommandResult, Status, build_context, plan_all
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS


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
        guided=True,
    )


@pytest.mark.parametrize("platform", [MACOS, WINDOWS, UBUNTU])
@pytest.mark.parametrize("source_url", ["", "group/existing"])
def test_project_environment_does_not_install_pandoc(
    tmp_path, monkeypatch, platform, source_url
):
    context = _context(tmp_path, platform=platform, source_url=source_url)
    project = context.config.resolved_project_dir(context.home)
    python = stages._venv_python(context)
    python.parent.mkdir(parents=True)
    python.touch()
    (project / "requirements.txt").write_text("prodockit\n")
    (project / stages.ADOPT_MANIFEST).write_text("schema = 1\n")
    monkeypatch.setattr(stages, "_project_venv_is_structurally_complete", lambda c: True)
    monkeypatch.setattr(stages, "_imports_from_project_venv", lambda c, m: CommandResult(0))
    result = stages._check_project_env(context)
    assert result.status is Status.OK
    plan = stages._plan_project_env(context)
    assert not any("install-pandoc" in command for command in plan.commands)


def _pushed_context(
    tmp_path: Path,
    *,
    runner: CliFakeRunner | None = None,
    platform: str = MACOS,
):
    """A context whose own commit has already reached its remote."""
    (tmp_path / "report" / ".git").mkdir(parents=True, exist_ok=True)
    ready = {
        "remote get-url origin": CommandResult(0, "git@github.com:ada/report.git\n"),
        "status --porcelain": CommandResult(0, ""),
        "ls-remote origin HEAD": CommandResult(0, "abc123\tHEAD\n"),
        "rev-parse HEAD": CommandResult(0, "abc123\n"),
    }
    actual_runner = runner or CliFakeRunner()
    actual_runner.responses = ready | actual_runner.responses
    return _context(tmp_path, runner=actual_runner, platform=platform)


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
    (project / ".venv" / "bin" / "activate").touch()
    (project / "requirements.txt").touch()
    runner = CliFakeRunner({"-m pip --version": CommandResult(0, "pip 26.0.1")})

    result = stages._check_project_env(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert "dependencies are not installed" in result.detail


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


def test_site_stage_is_not_applicable_without_a_fixed_pages_address(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    context = replace(context, host=replace(context.host, pages_url=""))

    result = stages._check_site_published(context)

    assert result.status is Status.OK
    assert "not checked" in result.detail


def test_site_stage_requires_confirmation_for_oauth_redirect_found_by_system_curl(
    tmp_path: Path,
) -> None:
    runner = CliFakeRunner({"curl": CommandResult(47, "302")})
    context = _pushed_context(tmp_path, runner=runner)

    result = stages._check_site_published(context)

    assert result.status is Status.MISSING
    assert result.verifiable is False
    assert "does not prove that this specific site exists" in result.detail
    assert any(call[0] == "curl" and "--max-redirs" in call for call in runner.calls)


def test_unavailable_site_probe_takes_a_browser_confirmation_on_trust(
    tmp_path: Path,
) -> None:
    result = stages._check_site_published(_pushed_context(tmp_path))

    assert result.status is Status.MISSING
    assert result.verifiable is False
    assert "confirm it in your browser" in result.detail


def test_windows_certificate_failure_is_diagnosed_without_disabling_tls(
    tmp_path: Path,
) -> None:
    runner = CliFakeRunner(
        {
            "curl.exe": CommandResult(
                60,
                "000",
                "curl: (60) schannel: SEC_E_UNTRUSTED_ROOT (0x80090325) - "
                "The certificate chain was issued by an authority that is not trusted.",
            )
        }
    )

    context = _pushed_context(tmp_path, runner=runner, platform=WINDOWS)
    result = stages._check_site_published(context)

    assert result.status is Status.MISSING
    assert result.verifiable is False
    assert "certificate chain is not trusted" in result.detail
    assert "browser" in result.detail
    assert "probe did not run" not in result.detail
    curl = next(call for call in runner.calls if call[0] == "curl.exe")
    assert "-k" not in curl and "--insecure" not in curl


@pytest.mark.parametrize("platform", [MACOS, UBUNTU, WINDOWS])
def test_own_environment_recovery_resumes_with_bootstrap(tmp_path: Path, platform: str) -> None:
    context = _context(
        tmp_path,
        platform=platform,
        runner=CliFakeRunner({"import ensurepip, venv": CommandResult(1)}),
    )

    instructions = "\n".join(stages._plan_own_venv(context).instructions)

    assert "prodockit bootstrap" in instructions
    assert "pdk bootstrap" not in instructions


def _write_usable_github_keypair(tmp_path: Path) -> None:
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519_github").write_text("private", encoding="utf-8")
    (ssh / "id_ed25519_github.pub").write_text("public", encoding="utf-8")


def _ready_github_ssh() -> dict[str, CommandResult]:
    return {
        "ssh-keygen -lf": CommandResult(
            0, "256 SHA256:test ada@example.test (ED25519)"
        ),
        "ssh-add -l": CommandResult(
            0, "256 SHA256:test ada@example.test (ED25519)"
        ),
        "ssh": CommandResult(1, stderr="Hi ada! You've successfully authenticated"),
    }


def test_first_push_waits_for_the_ssh_agent_when_the_remote_cannot_be_inspected(
    tmp_path: Path,
) -> None:
    (tmp_path / "report" / ".git").mkdir(parents=True)
    _write_usable_github_keypair(tmp_path)
    runner = CliFakeRunner(
        {
            "remote get-url origin": CommandResult(0, "git@github.com:ada/report.git"),
            "status --porcelain": CommandResult(0, ""),
            **_ready_github_ssh(),
            "ssh-add -l": CommandResult(
                2, stderr="Could not open a connection to your authentication agent."
            ),
            "ls-remote origin HEAD": CommandResult(1, stderr="offline"),
        }
    )
    stage = next(stage for stage in stages.STAGES if stage.id == "first-push")

    report = plan_all(_context(tmp_path, runner=runner), (stage,))[0]

    assert report.result.status is Status.BLOCKED
    assert "SSH" in report.result.detail
    assert "agent" in report.result.detail
    assert report.plan is None


def test_first_push_reports_an_unreachable_origin_after_ssh_is_ready(
    tmp_path: Path,
) -> None:
    (tmp_path / "report" / ".git").mkdir(parents=True)
    _write_usable_github_keypair(tmp_path)
    runner = CliFakeRunner(
        {
            "remote get-url origin": CommandResult(0, "git@github.com:ada/report.git"),
            "status --porcelain": CommandResult(0, ""),
            **_ready_github_ssh(),
            "ls-remote origin HEAD": CommandResult(1, stderr="offline"),
        }
    )

    result = stages._check_first_push(_context(tmp_path, runner=runner))

    assert result.status is Status.WRONG
    assert "could not reach origin" in result.detail


def test_first_push_reports_a_remote_commit_without_a_local_commit(tmp_path: Path) -> None:
    (tmp_path / "report" / ".git").mkdir(parents=True)
    _write_usable_github_keypair(tmp_path)
    runner = CliFakeRunner(
        {
            "remote get-url origin": CommandResult(0, "git@github.com:ada/report.git"),
            "status --porcelain": CommandResult(0, ""),
            **_ready_github_ssh(),
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

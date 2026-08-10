# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for `prodockit bootstrap`'s stage model, config and hosts.

The point of the design is that none of this needs anything installed: a
stage returns the commands that *would* set something up, so a test
asserts on those commands. That is what lets all three platforms' logic
be checked from whichever one the suite happens to run on
(prodockit-extensions#217).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from prodockit.bootstrap import (
    HOSTS,
    STAGES,
    BootstrapConfig,
    BootstrapConfigError,
    CommandResult,
    Status,
    UnsupportedHostError,
    build_context,
    check_all,
    config_path,
    load,
    plan_all,
    save,
)
from prodockit.bootstrap.model import GITHUB_COM, MACOS, SURREY_GITLAB, UBUNTU, WINDOWS
from prodockit.bootstrap.stages import VSCODE_EXTENSIONS


class FakeRunner:
    """A runner that answers from a table instead of running anything.

    Keyed on the first word of the command, or the whole command joined,
    so a test can be as specific as it needs. Records every command it was
    asked to run, which is what the plan assertions check.
    """

    def __init__(self, responses: dict[str, CommandResult] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def run(self, command: Sequence[str]) -> CommandResult:
        self.calls.append(list(command))
        joined = " ".join(command)
        for key in (joined, command[0]):
            if key in self.responses:
                return self.responses[key]
        return CommandResult(returncode=127, stderr="not found")


def _config(**overrides: str) -> BootstrapConfig:
    base = {
        "full_name": "Ada Lovelace",
        "email": "al01234@surrey.ac.uk",
        "username": "al01234",
        "host": "surrey",
        "namespace": "comm058-2026",
        "project_name": "report-al01234",
        "project_dir": "~/GitLab/report-al01234",
    }
    base.update(overrides)
    return BootstrapConfig(**base)  # type: ignore[arg-type]


def _context(tmp_path: Path, *, platform: str = MACOS, runner: FakeRunner | None = None, **cfg):
    return build_context(
        _config(**cfg),
        runner=runner or FakeRunner(),
        platform=platform,
        home=tmp_path,
    )


# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------


def test_key_suffix_matches_the_documented_filename() -> None:
    """Regression: the key file is named for the *kind* of host, not the
    instance. The User Guide's own `ssh-keygen -f` line writes
    `id_ed25519_gitlab` for Surrey's instance, so keying the filename on
    `host.key` ("surrey") reported a missing key on a machine that had a
    working one - and would then have created a second key beside it.
    Found by running `--check` against a real machine.
    """
    assert SURREY_GITLAB.key == "surrey"
    assert SURREY_GITLAB.key_suffix == "gitlab"
    assert HOSTS["gitlab"].key_suffix == "gitlab"
    assert GITHUB_COM.key_suffix == "github"


def test_the_keypair_check_looks_where_the_guide_says_to_create_it(tmp_path: Path) -> None:
    """The other half of the regression above: the record being right is
    no use if the check reads the wrong field off it. A key created by
    following the User Guide verbatim must be found."""
    (tmp_path / ".ssh").mkdir()
    for suffix in ("", ".pub"):
        (tmp_path / ".ssh" / f"id_ed25519_gitlab{suffix}").write_text("k", encoding="utf-8")
    context = _context(tmp_path)
    result = next(s for s in STAGES if s.id == "ssh-key").check(context)
    assert result.status is Status.OK
    assert result.detail.endswith("id_ed25519_gitlab")


def test_declared_but_unsupported_hosts_are_refused_clearly() -> None:
    """gitlab.com and github.com exist as records so the shape is right,
    but phase 1 has tested neither - refusing beats half-working."""
    for key in ("gitlab", "github"):
        with pytest.raises(UnsupportedHostError) as exc_info:
            build_context(_config(host=key))
        assert "not yet supported" in str(exc_info.value)


def test_an_unknown_host_names_the_ones_that_exist() -> None:
    with pytest.raises(UnsupportedHostError) as exc_info:
        build_context(_config(host="bitbucket"))
    assert "surrey" in str(exc_info.value)


def test_remote_url_shape_is_the_same_for_every_host() -> None:
    for host in HOSTS.values():
        assert host.remote_url("group", "proj") == f"git@{host.hostname}:group/proj.git"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.toml"
    save(path, _config())
    assert load(path) == _config()


def test_a_missing_config_is_defaults_not_an_error(tmp_path: Path) -> None:
    assert load(tmp_path / "absent.toml") == BootstrapConfig()


def test_a_malformed_line_names_the_file_and_line(tmp_path: Path) -> None:
    """A hand-edited config that silently reverted to defaults would
    re-prompt for everything with no explanation - the exact silent
    failure this project keeps finding elsewhere."""
    path = tmp_path / "bootstrap.toml"
    path.write_text('full_name = "Ada"\nemail = no-quotes-here\n', encoding="utf-8")
    with pytest.raises(BootstrapConfigError) as exc_info:
        load(path)
    assert "bootstrap.toml:2" in str(exc_info.value)


def test_an_unknown_key_is_ignored_rather_than_fatal(tmp_path: Path) -> None:
    """A config written by a newer prodockit should still start on an
    older one."""
    path = tmp_path / "bootstrap.toml"
    path.write_text('full_name = "Ada"\nfuture_setting = "x"\n', encoding="utf-8")
    assert load(path).full_name == "Ada"


def test_the_saved_file_warns_against_putting_secrets_in_it(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.toml"
    save(path, _config())
    assert "Never put a password, token or passphrase" in path.read_text(encoding="utf-8")


def test_config_path_follows_each_platform_convention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config_path(tmp_path) == tmp_path / ".config" / "prodockit" / "bootstrap.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path(tmp_path).parent.parent == tmp_path / "xdg"


def test_project_dir_expands_a_leading_tilde(tmp_path: Path) -> None:
    config = _config(project_dir="~/GitLab/report")
    assert config.resolved_project_dir(tmp_path) == tmp_path / "GitLab" / "report"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def test_git_installed_but_unconfigured_is_wrong_not_missing(tmp_path: Path) -> None:
    """Telling a reader to install git they already have sends them the
    wrong way entirely - that is why `WRONG` exists separately."""
    runner = FakeRunner(
        {
            "git --version": CommandResult(0, "git version 2.43.0"),
            "git config --global user.name": CommandResult(0, "Ada\n"),
            "git config --global user.email": CommandResult(1, ""),
        }
    )
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "git").check(context)
    assert result.status is Status.WRONG
    assert "user.email" in result.detail


def test_ssh_success_is_read_from_the_greeting_not_the_exit_code(tmp_path: Path) -> None:
    """`ssh -T` against a git host exits non-zero even when the key works -
    there is no shell to give you. Reading the exit code would report every
    correctly configured machine as broken.
    """
    runner = FakeRunner(
        {"ssh": CommandResult(1, stderr="Welcome to GitLab, @al01234!")}
    )
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "ssh-upload").check(context)
    assert result.status is Status.OK


def test_a_rejected_key_is_missing_not_merely_unconfirmed(tmp_path: Path) -> None:
    runner = FakeRunner({"ssh": CommandResult(255, stderr="Permission denied (publickey).")})
    context = _context(tmp_path, runner=runner)
    assert next(s for s in STAGES if s.id == "ssh-upload").check(context).status is Status.MISSING


def test_half_a_keypair_is_wrong(tmp_path: Path) -> None:
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_ed25519_gitlab").write_text("private", encoding="utf-8")
    context = _context(tmp_path)
    result = next(s for s in STAGES if s.id == "ssh-key").check(context)
    assert result.status is Status.WRONG


def test_node_without_npm_is_wrong(tmp_path: Path) -> None:
    """The signature of Ubuntu's own nodejs package, or a NodeSource install
    whose `curl` line failed - a real failure this family has already hit."""
    runner = FakeRunner({"node": CommandResult(0, "v22.14.0\n")})
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "node").check(context)
    assert result.status is Status.WRONG
    assert "npm" in result.detail


def test_node_older_than_the_builds_use_is_wrong(tmp_path: Path) -> None:
    runner = FakeRunner(
        {"node": CommandResult(0, "v18.19.0\n"), "npm": CommandResult(0, "10.2.3\n")}
    )
    context = _context(tmp_path, runner=runner)
    assert next(s for s in STAGES if s.id == "node").check(context).status is Status.WRONG


def test_stages_needing_project_details_report_unknown_not_missing(tmp_path: Path) -> None:
    """Regression: with no config these built a URL out of empty strings and
    reported `git@gitlab.surrey.ac.uk:/.git is not reachable`, which tells a
    first-time reader nothing except that something is broken - and nothing
    is. Found by running `--check` on a machine with no config.
    """
    context = _context(tmp_path, namespace="", project_name="", project_dir="")
    reports = {r.stage.id: r.result for r in check_all(context)}
    for stage_id in ("clone", "own-project", "remote"):
        assert reports[stage_id].status is Status.UNKNOWN, stage_id
        assert "needs" in reports[stage_id].detail


def test_extensions_reports_which_are_missing(tmp_path: Path) -> None:
    present = "\n".join(VSCODE_EXTENSIONS[:-1])
    runner = FakeRunner({"code --list-extensions": CommandResult(0, present)})
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "extensions").check(context)
    assert result.status is Status.WRONG
    assert VSCODE_EXTENSIONS[-1] in result.detail


# ---------------------------------------------------------------------------
# Plans - the whole point: every platform, from any platform
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "platform,expected",
    [
        (MACOS, "brew"),
        (UBUNTU, "apt"),
        (WINDOWS, "winget"),
    ],
)
def test_every_platforms_install_plan_is_generated_from_any_platform(
    tmp_path: Path, platform: str, expected: str
) -> None:
    """The reason the runner is injected: this asserts on Ubuntu's and
    Windows' commands while running on whatever the suite runs on, with
    nothing installed and no network."""
    context = _context(tmp_path, platform=platform)
    plan = next(s for s in STAGES if s.id == "vscode").plan(context)
    flat = " ".join(" ".join(command) for command in plan.commands)
    assert expected in flat


def test_git_plan_skips_reinstalling_an_already_installed_git(tmp_path: Path) -> None:
    """A rerun repairing unset identity must not reinstall git underneath a
    working one."""
    runner = FakeRunner({"git": CommandResult(0, "git version 2.43.0")})
    context = _context(tmp_path, runner=runner)
    plan = next(s for s in STAGES if s.id == "git").plan(context)
    flat = " ".join(" ".join(command) for command in plan.commands)
    assert "brew" not in flat
    assert "user.email" in flat


def test_the_two_browser_stages_carry_instructions_and_a_verification(
    tmp_path: Path,
) -> None:
    """Guide-and-verify: the instruction is what a human does, the command
    is how bootstrap confirms it actually worked."""
    context = _context(tmp_path)
    for stage_id in ("ssh-upload", "own-project"):
        plan = next(s for s in STAGES if s.id == stage_id).plan(context)
        assert plan.instructions, stage_id
        assert plan.commands, stage_id


def test_browser_instructions_use_the_hosts_own_vocabulary(tmp_path: Path) -> None:
    """A GitHub user should read "repository", not GitLab's "project"."""
    context = _context(tmp_path)
    plan = next(s for s in STAGES if s.id == "own-project").plan(context)
    joined = " ".join(plan.instructions)
    assert "project" in joined
    assert SURREY_GITLAB.new_project_url in joined


def test_remote_plan_repoints_and_then_syncs(tmp_path: Path) -> None:
    """`git remote set-url` alone leaves the clone advertising the
    template's own repository in zensical.toml and the README badges."""
    context = _context(tmp_path)
    plan = next(s for s in STAGES if s.id == "remote").plan(context)
    flat = [" ".join(command) for command in plan.commands]
    assert any("remote set-url" in c for c in flat)
    assert any("sync-repo" in c for c in flat)


def test_plan_all_leaves_satisfied_stages_without_a_plan(tmp_path: Path) -> None:
    """The point of a rerun is to repair what is broken, not reinstall what
    works."""
    runner = FakeRunner(
        {
            "git --version": CommandResult(0, "git version 2.43.0"),
            "git config --global user.name": CommandResult(0, "Ada\n"),
            "git config --global user.email": CommandResult(0, "a@b.c\n"),
        }
    )
    context = _context(tmp_path, runner=runner)
    reports = {r.stage.id: r for r in plan_all(context)}
    assert reports["git"].result.status is Status.OK
    assert reports["git"].plan is None
    assert reports["vscode"].plan is not None


def test_every_stage_has_a_check_and_a_plan_for_every_platform(tmp_path: Path) -> None:
    """A stage that raises on one platform would only be found when
    somebody ran it there - which for Windows means a student, since this
    family has no Windows CI at all."""
    for platform in (MACOS, UBUNTU, WINDOWS):
        context = _context(tmp_path, platform=platform)
        for stage in STAGES:
            assert stage.check(context) is not None, (stage.id, platform)
            assert stage.plan(context) is not None, (stage.id, platform)


def test_unknown_stages_get_no_plan(tmp_path: Path) -> None:
    """Regression: a plan built from unanswered configuration rendered as
    `create a blank project named '' in the group ''` and
    `git ls-remote git@gitlab.surrey.ac.uk:/.git` - which reads as an
    instruction to follow rather than as the missing answer it is. Found
    by running `--dry-run` on a machine with no config.
    """
    context = _context(tmp_path, namespace="", project_name="", project_dir="")
    reports = {r.stage.id: r for r in plan_all(context)}
    for stage_id in ("clone", "own-project", "remote"):
        assert reports[stage_id].result.status is Status.UNKNOWN, stage_id
        assert reports[stage_id].plan is None, stage_id
    # Stages that need no configuration still plan normally.
    assert reports["vscode"].plan is not None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Invokes the real command against a fake machine.

    `build_context` is replaced rather than the checks themselves, so the
    genuine stage code runs - just against a runner that answers from a
    table instead of the network. A real check would `ssh -T` Surrey's
    GitLab, which a test suite has no business doing.
    """
    from click.testing import CliRunner

    from prodockit.cli import main

    def _invoke(*args: str, responses: dict[str, CommandResult] | None = None):
        monkeypatch.setattr(
            "prodockit.cli.build_bootstrap_context",
            lambda config: build_context(
                config,
                runner=FakeRunner(responses or {}),
                platform=MACOS,
                home=tmp_path,
            ),
        )
        return CliRunner().invoke(main, ["bootstrap", "--config", str(tmp_path / "b.toml"), *args])

    return _invoke


def test_bare_bootstrap_defaults_to_checking(cli_bootstrap) -> None:
    """Running it with no options must report rather than refuse - and,
    once applying exists, must not start installing software because
    somebody typed the command to see what it did."""
    result = cli_bootstrap()
    assert "Visual Studio Code" in result.output
    assert "stages need work" in result.output
    # The old behaviour: a usage error telling you to pass a flag.
    assert result.exit_code == 1
    assert "supports --check and --dry-run only" not in result.output


def test_bare_bootstrap_prints_no_commands(cli_bootstrap) -> None:
    """Checking is read-only, so it must not print a plan - that is what
    --dry-run is for, and showing commands implies something ran them."""
    result = cli_bootstrap()
    assert "run:" not in result.output
    assert "--dry-run" in result.output


def test_dry_run_prints_the_commands(cli_bootstrap) -> None:
    result = cli_bootstrap("--dry-run")
    assert "run: brew install --cask visual-studio-code" in result.output


def test_bootstrap_exits_zero_when_everything_is_set_up(
    cli_bootstrap, tmp_path: Path
) -> None:
    """Usable as a script check, matching `sync-repo --check`."""
    (tmp_path / ".ssh").mkdir()
    for suffix in ("", ".pub"):
        (tmp_path / ".ssh" / f"id_ed25519_gitlab{suffix}").write_text("k", encoding="utf-8")
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    (project / "tools").mkdir()
    save(tmp_path / "b.toml", _config())
    result = cli_bootstrap(
        responses={
            "code": CommandResult(0, "\n".join(VSCODE_EXTENSIONS)),
            "git --version": CommandResult(0, "git version 2.43.0"),
            "git config --global user.name": CommandResult(0, "Ada\n"),
            "git config --global user.email": CommandResult(0, "a@b.c\n"),
            "ssh": CommandResult(1, stderr="Welcome to GitLab, @al01234!"),
            "git": CommandResult(
                0, "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git\n"
            ),
            "pandoc": CommandResult(0, "pandoc 3.10.1"),
            "node": CommandResult(0, "v22.14.0\n"),
            "npm": CommandResult(0, "10.9.2\n"),
        }
    )
    assert "All 10 stages are set up." in result.output
    assert result.exit_code == 0

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
        self.cwds: list[str | None] = []

    def run(self, command: Sequence[str], cwd: str | None = None) -> CommandResult:
        self.calls.append(list(command))
        self.cwds.append(cwd)
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


def _looks_like_vscode_app(path: Path) -> bool:
    text = str(path)
    return "Visual Studio Code" in text or text.endswith(("/usr/share/code", "/snap/code"))


def _context(
    tmp_path: Path,
    *,
    platform: str = MACOS,
    runner: FakeRunner | None = None,
    vscode_app: bool = False,
    **cfg,
):
    """A context describing a machine, never reading this one.

    `vscode_app` says whether the VS Code *application* is installed -
    separate from whether the `code` command is on PATH, which the runner
    answers. Defaults to absent so a test states it when it matters.
    """
    return build_context(
        _config(**cfg),
        runner=runner or FakeRunner(),
        platform=platform,
        home=tmp_path,
        # Only the VS Code application paths are described; everything
        # else is a real path under tmp_path and answers for itself.
        exists=lambda path: (
            vscode_app if _looks_like_vscode_app(path) else path.exists()
        ),
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
    tmp_path: Path, platform: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason the runner is injected: this asserts on Ubuntu's and
    Windows' commands while running on whatever the suite runs on, with
    nothing installed and no network.

    `_vscode_app_installed` is pinned false because it reads the real
    filesystem rather than going through the runner - so without this the
    result depends on whether the machine running the tests happens to
    have VS Code, which is precisely the coupling the injected runner
    exists to remove. It caught this test out once already.
    """
    context = _context(tmp_path, platform=platform, vscode_app=False)
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
    # Both commands run in the project: sync-repo reads its config from the
    # working directory and has no path flag.
    assert plan.cwd is not None and plan.cwd.endswith("report-al01234")
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

    def _invoke(
        *args: str,
        responses: dict[str, CommandResult] | None = None,
        input: str | None = None,
    ):
        monkeypatch.setattr(
            "prodockit.cli.build_bootstrap_context",
            lambda config: build_context(
                config,
                runner=FakeRunner(responses or {}),
                platform=MACOS,
                home=tmp_path,
            ),
        )
        return CliRunner().invoke(
            main, ["bootstrap", "--config", str(tmp_path / "b.toml"), *args], input=input
        )

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


def test_dry_run_prints_the_commands(cli_bootstrap, monkeypatch: pytest.MonkeyPatch) -> None:
    # Same host-state coupling as above: pinned to "no VS Code installed"
    # so the assertion describes a machine rather than this one.
    import prodockit.bootstrap.stages as stages_module

    monkeypatch.setattr(stages_module, "_vscode_app_installed", lambda context: False)
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
            # The repoint stage checks the config is synced too, not just
            # the remote - see test_repoint_is_not_done_until_the_config_is_synced_too.
            "prodockit sync-repo --check": CommandResult(0),
            "pandoc": CommandResult(0, "pandoc 3.10.1"),
            "node": CommandResult(0, "v22.14.0\n"),
            "npm": CommandResult(0, "10.9.2\n"),
        }
    )
    assert "All 10 stages are set up." in result.output
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Phase 2: template source, and applying
# ---------------------------------------------------------------------------


def test_surrey_clones_the_template_from_surrey_not_github(tmp_path: Path) -> None:
    """Regression: phase 1 hardcoded the GitHub URL. Surrey mirrors the
    template onto its own GitLab, and a student there has no GitHub
    account - cloning the original would ask them for credentials they
    have not got.
    """
    context = _context(tmp_path, source_url="")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)
    assert plan.commands[0][2] == "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git"


def test_source_url_overrides_the_template(tmp_path: Path) -> None:
    """A reader given their own repository clones that instead - the
    template would be a detour through work the host already did."""
    own = "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git"
    context = _context(tmp_path, source_url=own)
    plan = next(s for s in STAGES if s.id == "clone").plan(context)
    assert plan.commands[0][2] == own


def test_building_a_plan_makes_no_network_call(tmp_path: Path) -> None:
    """`--dry-run` builds every plan, so plan-building has to stay cheap
    and side-effect-free. An earlier version probed the host to decide
    which repository to clone, which put a network call inside it."""
    runner = FakeRunner()
    context = _context(tmp_path, runner=runner)
    next(s for s in STAGES if s.id == "clone").plan(context)
    assert runner.calls == []


def test_apply_reruns_the_check_afterwards(tmp_path: Path) -> None:
    """A command exiting zero says the installer ran, not that the thing
    works - every failure this project has had exited zero while producing
    something broken."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"brew": CommandResult(0), "code": CommandResult(127)})
    context = _context(tmp_path, runner=runner)
    outcome = apply_stage(context, next(s for s in STAGES if s.id == "vscode"))
    assert outcome.failed is None          # the install command "succeeded"
    assert not outcome.ok                  # but the check still fails
    assert outcome.verified is not None


def test_apply_stops_at_the_first_failing_command(tmp_path: Path) -> None:
    """Later commands in a plan depend on earlier ones, so pressing on
    turns one clear failure into several confusing ones."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"git": CommandResult(1, stderr="boom")})
    context = _context(tmp_path, runner=runner)
    outcome = apply_stage(context, next(s for s in STAGES if s.id == "remote"))
    assert outcome.failed is not None
    assert len(outcome.ran) == 1           # set-url failed; sync-repo never ran


def test_the_runner_never_inherits_stdin() -> None:
    """Regression: `subprocess` inherits stdin by default, so `ssh -T`
    during a check consumed the answers typed for bootstrap's own prompts
    and every later prompt aborted on end-of-input. Found by running
    `--apply` with piped answers.
    """
    import inspect
    import subprocess as sp

    from prodockit.bootstrap.model import SubprocessRunner

    source = inspect.getsource(SubprocessRunner.run)
    assert "stdin=subprocess.DEVNULL" in source
    assert sp.DEVNULL is not None


def test_missing_keys_ignores_the_optional_override() -> None:
    """A blank `source_url` means "use the template" - the common answer,
    so treating it as missing would ask everyone a question most people
    should skip."""
    from prodockit.bootstrap import missing_keys

    assert missing_keys(_config(source_url="")) == []
    assert "project_name" in missing_keys(_config(project_name=""))


def test_gaps_are_offered_as_prompts_not_a_file_to_edit(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Telling a first-time reader a value is "not set in your bootstrap
    config" points them at a file they may not know how to edit - which is
    the kind of step this command exists to remove.

    Only the blank fields are asked for: filling one gap must not mean
    walking the whole list again.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config(project_name="", project_dir=""))
    result = cli_bootstrap(input="y\nreport-al01234\n~/GitLab/report-al01234\n")
    assert "Answer them now?" in result.output
    # Asked for the two blanks, not for the five already answered.
    assert "Your full name" not in result.output
    assert "Your project name" in result.output
    assert load(tmp_path / "b.toml").project_name == "report-al01234"


def test_declining_the_offer_carries_on(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config(project_name=""))
    result = cli_bootstrap(input="n\n")
    assert "Carrying on" in result.output
    assert load(tmp_path / "b.toml").project_name == ""


def test_a_piped_run_reports_instead_of_prompting(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scripted or piped run must report and exit rather than block on a
    prompt nobody is there to answer."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)
    save(tmp_path / "b.toml", _config(project_name=""))
    result = cli_bootstrap()
    assert "Answer them now?" not in result.output
    assert "--configure" in result.output


def test_vscode_installed_without_the_shell_command_is_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression, reported from real use: the app and the `code` command
    are separate installs, and on macOS the cask gives you only the first.
    Treating a missing `code` as a missing VS Code reported "not
    installed" on a machine that plainly had it, then tried to reinstall,
    which fails outright:

        Error: It seems there is already an App at
        '/Applications/Visual Studio Code.app'.
    """
    context = _context(tmp_path, vscode_app=True)  # FakeRunner: `code` not on PATH
    stage = next(s for s in STAGES if s.id == "vscode")

    result = stage.check(context)
    assert result.status is Status.WRONG
    assert "not on PATH" in result.detail

    plan = stage.plan(context)
    # The fix is the Command Palette action, not an install that would fail.
    assert plan.commands == []
    assert any("Shell Command" in i for i in plan.instructions)


def test_vscode_genuinely_absent_still_installs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, vscode_app=False)
    stage = next(s for s in STAGES if s.id == "vscode")
    assert stage.check(context).status is Status.MISSING
    assert stage.plan(context).commands[0][0] == "brew"


def test_a_relative_project_dir_resolves_against_the_current_directory(
    tmp_path: Path,
) -> None:
    """Reported from real use: a bare name landed in the home directory.
    The User Guide's flow is "navigate to your GitLab folder, then clone",
    so it belongs where the command was run from."""
    config = _config(project_dir="report-al01234")
    here = tmp_path / "GitLab"
    assert config.resolved_project_dir(tmp_path, cwd=here) == here / "report-al01234"


def test_an_absolute_project_dir_is_left_alone(tmp_path: Path) -> None:
    config = _config(project_dir=str(tmp_path / "elsewhere"))
    assert config.resolved_project_dir(tmp_path, cwd=tmp_path / "GitLab") == (
        tmp_path / "elsewhere"
    )


def test_the_project_dir_default_is_offered_as_here(tmp_path: Path) -> None:
    """Offered as `./<name>` even when a value is stored - the one field
    where the stored answer does not win.

    A stored path that was wrong is otherwise the one thing a reader
    cannot correct by pressing Enter, which is how the same clone landed
    in a home directory twice. It also means a project that has been
    *moved* self-heals: re-running --configure from its new location
    offers here, rather than the path it used to be at.
    """
    from prodockit.bootstrap import default_for

    assert default_for(_config(project_dir=""), "project_dir") == "./report-al01234"
    # Even with a stale absolute value stored.
    stale = _config(project_dir=str(tmp_path / "somewhere" / "else"))
    assert default_for(stale, "project_dir") == "./report-al01234"


def test_every_other_field_still_keeps_its_stored_answer() -> None:
    """The project_dir exception has to stay an exception - a rerun that
    silently discarded your name and email would be worse than the
    problem it solves."""
    from prodockit.bootstrap import default_for

    config = _config(full_name="Ada Lovelace", namespace="comm058-2026")
    assert default_for(config, "full_name") == "Ada Lovelace"
    assert default_for(config, "namespace") == "comm058-2026"


def test_extensions_plan_installs_only_what_is_missing(tmp_path: Path) -> None:
    """Reported from real use: with one extension absent the plan listed
    an install for all three, which reads as though the check had not
    been consulted at all."""
    present = "\n".join(VSCODE_EXTENSIONS[:-1])
    runner = FakeRunner({"code --list-extensions": CommandResult(0, present)})
    context = _context(tmp_path, runner=runner)
    stage = next(s for s in STAGES if s.id == "extensions")

    plan = stage.plan(context)
    assert len(plan.commands) == 1
    assert plan.commands[0][-1] == VSCODE_EXTENSIONS[-1]

    # And the check names what is already there, not only what is not.
    detail = stage.check(context).detail
    assert "2 of 3 installed" in detail
    assert VSCODE_EXTENSIONS[-1] in detail


def test_a_manual_step_is_retried_not_failed(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reported from real use: pressing Enter before creating the project
    on the website failed the run and exited, throwing away every stage
    already completed.

    Checking too early is the normal case, not an error - you cannot
    create a project on a website and have it exist before you have done
    it. So it says "not there yet" and asks again.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config())
    # `git ls-remote` always fails: the project is never created, so the
    # only way out is declining the retry.
    result = cli_bootstrap(
        "--apply",
        responses={"code": CommandResult(0, "\n".join(VSCODE_EXTENSIONS))},
        input="n\n" * 20,
    )
    assert "not there yet" in result.output or "skipped" in result.output
    # The old behaviour: a hard exit on the first failed verification.
    assert "Stopping - later stages depend on this one." not in result.output


def test_a_git_banner_is_reduced_to_its_one_useful_line() -> None:
    """Git wraps remote errors in `=====` banners and empty `remote:`
    markers, so printing the lot buries the sentence that matters."""
    from prodockit.cli import _first_meaningful_line

    stderr = (
        "remote: \n"
        "remote: ========================================================\n"
        "remote: \n"
        "remote: The project you were looking for could not be found.\n"
        "remote: ========================================================\n"
    )
    assert _first_meaningful_line(stderr) == (
        "The project you were looking for could not be found."
    )


def test_repoint_is_not_done_until_the_config_is_synced_too(tmp_path: Path) -> None:
    """Reported from real use: `git remote set-url` succeeded, sync-repo
    did not run, and the stage then reported itself done - leaving a clone
    that pushed to the right place while every page still advertised the
    template's repository.
    """
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    wanted = "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git"
    runner = FakeRunner(
        {
            "git": CommandResult(0, wanted + "\n"),
            "prodockit sync-repo --check": CommandResult(1, stderr="would update: repo_url"),
        }
    )
    context = _context(tmp_path, runner=runner, project_dir=str(project))
    result = next(s for s in STAGES if s.id == "remote").check(context)
    assert result.status is Status.WRONG
    assert "needs syncing" in result.detail

    # And once sync-repo is happy, so is the stage.
    runner.responses["prodockit sync-repo --check"] = CommandResult(0)
    assert next(s for s in STAGES if s.id == "remote").check(context).status is Status.OK


# ---------------------------------------------------------------------------
# A command that can stop for a human is a broken check
# (prodockit-extensions#225)
# ---------------------------------------------------------------------------


def test_the_ssh_probe_cannot_stop_for_a_human(tmp_path: Path) -> None:
    """Regression: `stdin=DEVNULL` is necessary but not sufficient.

    ssh reads passwords from `/dev/tty` directly, bypassing stdin
    entirely, so a check on a machine whose key was not yet uploaded fell
    back to password authentication and sat there:

        git@gitlab.surrey.ac.uk's password:

    Testing stopped. `BatchMode=yes` is what makes ssh fail instead of
    ask; nothing else in the invocation does.
    """
    runner = FakeRunner()
    context = _context(tmp_path, runner=runner)
    next(s for s in STAGES if s.id == "ssh-upload").check(context)

    probe = next(call for call in runner.calls if call[0] == "ssh")
    assert "BatchMode=yes" in probe
    assert "ConnectTimeout=10" in probe


def test_an_unknown_host_is_reported_not_silently_trusted(tmp_path: Path) -> None:
    """Accepting a host key is a trust decision, and a tool that makes it
    silently on a reader's behalf has taken something from them they did
    not know they had. With `BatchMode` the probe fails instead - so the
    failure has to carry the way out, or it is just a dead end.
    """
    runner = FakeRunner(
        {"ssh": CommandResult(255, stderr="Host key verification failed.")}
    )
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=runner)
    )
    assert result.status is Status.WRONG
    assert "not a known host" in result.detail
    assert "ssh -T git@gitlab.surrey.ac.uk" in result.detail


def test_every_ssh_command_any_stage_runs_is_non_interactive(tmp_path: Path) -> None:
    """The invariant, rather than the two instances of it.

    `ssh -T` was fixed once already and `git ls-remote` - which runs ssh
    underneath - had exactly the same hang waiting in stage 6. Asserting
    per-command would have caught the first and missed the second.
    """
    context = _context(tmp_path, runner=FakeRunner())
    for stage in STAGES:
        for command in stage.plan(context).commands:
            if command[0] == "ssh":
                assert "BatchMode=yes" in command, f"{stage.id}: {command}"


def test_the_real_runner_tells_git_not_to_ask_either(tmp_path: Path) -> None:
    """git prompts for HTTPS credentials on its own and runs ssh for
    everything else, so `git ls-remote` and `git clone` inherit the same
    hang. Checked against the real runner and a real child process: the
    environment is the only thing carrying this, and a fake runner would
    never notice it had been dropped.
    """
    import sys

    from prodockit.bootstrap.model import SubprocessRunner

    script = "import os; print(os.environ.get('GIT_TERMINAL_PROMPT'), os.environ.get('GIT_SSH_COMMAND'))"
    result = SubprocessRunner().run([sys.executable, "-c", script])
    assert result.ok
    assert result.stdout.startswith("0 ssh ")
    assert "BatchMode=yes" in result.stdout


def test_a_readers_own_ssh_wrapper_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Someone who has configured `GIT_SSH_COMMAND` has a reason. Silently
    replacing it would break a working setup to fix a hypothetical one."""
    import sys

    from prodockit.bootstrap.model import SubprocessRunner

    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i /keys/mine")
    result = SubprocessRunner().run(
        [sys.executable, "-c", "import os; print(os.environ['GIT_SSH_COMMAND'])"]
    )
    assert result.stdout.strip() == "ssh -i /keys/mine"

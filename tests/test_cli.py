# ---------------------------------------------------------------------------
# `prodockit template-sync`
# ---------------------------------------------------------------------------

import pytest


def test_template_sync_flushes_progress_before_fresh_process(tmp_path, monkeypatch) -> None:
    """Redirected Windows output must survive the package handoff (#733)."""
    from types import SimpleNamespace

    from prodockit import cli

    flushed: list[str] = []

    class Stream:
        def __init__(self, name: str) -> None:
            self.name = name

        def flush(self) -> None:
            flushed.append(self.name)

    monkeypatch.setattr(cli.sys, "stdout", Stream("stdout"))
    monkeypatch.setattr(cli.sys, "stderr", Stream("stderr"))

    def run(command, *, cwd, check):
        assert flushed == ["stdout", "stderr"]
        assert command == ["python", "-m", "prodockit"]
        assert cwd == tmp_path
        assert check is False
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli._run_template_sync_resume(["python", "-m", "prodockit"], tmp_path) == 0


def test_bootstrap_records_the_pristine_template_release(tmp_path) -> None:
    """The tag must be persisted before bootstrap archives template history."""
    import subprocess

    from click.testing import CliRunner

    from prodockit.cli import main
    from prodockit.template_sync import read_applied_release, read_stamp

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True
    )
    (tmp_path / "template.txt").write_text("template\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "template.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "template"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "tag", "template-v1.4.0"], check=True)

    result = CliRunner().invoke(
        main, ["_record-template-release", "--project-root", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert read_applied_release(tmp_path) == "template-v1.4.0"
    assert read_stamp(tmp_path) == subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_template_sync_refuses_outside_a_repository(tmp_path, monkeypatch) -> None:
    """Run from the project, and only from its root."""
    from click.testing import CliRunner

    from prodockit.cli import main

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["template-sync"])

    assert result.exit_code == 1
    assert "not a git repository" in result.output


def test_template_sync_refuses_from_a_subdirectory(tmp_path, monkeypatch) -> None:
    """A subdirectory would half-work: git resolves upwards, so the branch
    and the staging land correctly while every path written is relative to
    the wrong place."""
    from click.testing import CliRunner

    from prodockit.cli import main

    (tmp_path / ".git").mkdir()
    inner = tmp_path / "docs"
    inner.mkdir()
    monkeypatch.chdir(inner)

    result = CliRunner().invoke(main, ["template-sync"])

    assert result.exit_code == 1
    # Names the project it is inside, and the directory to move to. VS Code
    # opens its terminal at the workspace root, which is frequently not the
    # project root, so this is the message a reader hits first.
    assert "is inside" in result.output
    assert f"cd {tmp_path}" in result.output


def test_template_sync_names_the_projects_a_workspace_holds(tmp_path, monkeypatch) -> None:
    """A VS Code workspace is often the folder *holding* the projects. Told
    only "not a git repository", a reader has to guess what to do next."""
    from click.testing import CliRunner

    from prodockit.cli import main

    for name in ("report-one", "report-two"):
        (tmp_path / name / ".git").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["template-sync"])

    assert result.exit_code == 1
    assert "holds projects rather than being one" in result.output
    assert "report-one" in result.output and "report-two" in result.output


def test_template_sync_has_no_root_option() -> None:
    """It works where it is run. A `--root` invites being pointed at one
    project from inside another, which is how the wrong repository gets a
    branch created in it."""
    from prodockit.cli import main

    names = {
        option
        for param in main.commands["template-sync"].params
        for option in getattr(param, "opts", [])
    }
    assert "--root" not in names
    assert {"--apply", "--verbose", "--force", "--template-path"} <= names


def test_template_sync_help_is_written_for_an_author() -> None:
    from click.testing import CliRunner

    from prodockit.cli import main

    result = CliRunner().invoke(main, ["template-sync", "--help"])

    assert result.exit_code == 0
    assert "Your writing, figures, and bibliography are left alone" in result.output
    assert "only previews" in result.output
    assert "--force FILE-PATH" in result.output
    assert "does not require a PR/MR" in result.output


def test_template_sync_apply_stops_before_writing_when_metadata_is_ambiguous(
    tmp_path, monkeypatch
) -> None:
    from click.testing import CliRunner

    from prodockit import diagnostics
    from prodockit.cli import main

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        diagnostics,
        "distribution_metadata_problems",
        lambda: (
            "prodockit: prodockit-0.41.0.dist-info, prodockit-0.56.0.dist-info",
        ),
    )

    result = CliRunner().invoke(main, ["template-sync", "--apply"])

    assert result.exit_code == 1
    assert "pdk diag --fix" in result.output
    assert "nothing has been changed" in result.output
    assert not any(path.name.startswith("template-update-") for path in tmp_path.iterdir())


def test_template_sync_survives_a_directory_it_cannot_read(tmp_path, monkeypatch) -> None:
    """`/tmp` holds mounted images whose entries raise on stat, and the
    first real run outside a repository crashed there rather than
    explaining itself. Crashing while explaining a wrong directory is a
    poor way to explain anything.
    """
    import os

    from click.testing import CliRunner

    from prodockit.cli import main

    forbidden = tmp_path / "locked"
    forbidden.mkdir()
    os.chmod(forbidden, 0o000)
    try:
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(main, ["template-sync"])
    finally:
        os.chmod(forbidden, 0o755)  # so the fixture can be cleaned up

    assert result.exit_code == 1
    assert "not a git repository" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_template_sync_logs_a_run_that_failed(tmp_path, monkeypatch) -> None:
    """A run that raised is the one most worth reading afterwards.

    So the log is written from a `finally`, not from the end of the happy
    path - a student reporting "it did not work" has, by definition, not
    reached the end.
    """
    import subprocess

    from click.testing import CliRunner

    from prodockit.cli import main
    from prodockit.template_sync import LOG_FILE

    project = tmp_path / "report"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)

    monkeypatch.chdir(project)
    # No origin, so stage 1 raises - and the log should exist regardless.
    result = CliRunner().invoke(main, ["template-sync"])

    assert result.exit_code == 1
    assert (project / LOG_FILE).exists()
    assert "started" in (project / LOG_FILE).read_text(encoding="utf-8")
    assert "finished" in (project / LOG_FILE).read_text(encoding="utf-8")


def test_template_sync_logs_the_full_detail_even_without_verbose(tmp_path, monkeypatch) -> None:
    """The run a student reports is the one they ran with no flags.

    A log holding only what the terminal was asked for would be no use
    for diagnosing it, so the reports are rendered twice - summary to the
    terminal, full detail to the log.
    """
    import inspect

    from prodockit import cli

    source = inspect.getsource(cli._run_template_sync)

    assert "verbose=True" in source, "the log must take the verbose form whatever the terminal got"
    assert "logged.extend" in source


def test_template_sync_warns_before_replacing_managed_stylesheets() -> None:
    """A generic edited-file report does not tell an author where CSS belongs."""
    import inspect

    from prodockit import cli

    source = inspect.getsource(cli._run_template_sync)

    assert "edited_managed_stylesheets(plan)" in source
    assert "Warning - managed stylesheet changes found" in source
    assert "Move website changes to extra.css and PDF-only changes to print.css" in source


def test_template_sync_previews_an_exact_package_only_downgrade(tmp_path, monkeypatch) -> None:
    """The template relationship wins over latest PyPI and a newer runtime."""
    import subprocess

    from click.testing import CliRunner

    from prodockit import cli

    template = tmp_path / "prodockit-template"
    project = tmp_path / "report"
    template.mkdir()
    project.mkdir()
    manifest = """
[template]
owns = ["managed.txt"]
[project]
owns = ["docs/**"]
[shared]
files = ["requirements.txt"]
[excluded]
paths = [".prodockit-template.toml"]
"""
    (template / ".prodockit-template.toml").write_text(manifest, encoding="utf-8")
    (template / "managed.txt").write_text("current\n", encoding="utf-8")
    (template / "requirements.txt").write_text("prodockit>=0.42.1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(template), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(template), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(template),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "template",
        ],
        check=True,
    )
    version = subprocess.run(
        ["git", "-C", str(template), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    (project / "managed.txt").write_text("current\n", encoding="utf-8")
    (project / ".prodockit-template").write_text(f"{version}\n", encoding="utf-8")
    (project / ".gitignore").write_text(".prodockit-template.log\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "project",
        ],
        check=True,
    )

    monkeypatch.chdir(project)
    monkeypatch.setattr(cli, "__version__", "0.43.2")
    result = CliRunner().invoke(
        cli.main,
        ["template-sync", "--template-path", str(template)],
    )

    assert result.exit_code == 0, result.output
    assert "Action:   DOWNGRADE" in result.output
    assert "Current:  Prodockit 0.43.2" in result.output
    assert "Required: Prodockit 0.42.1 (incoming template)" in result.output
    assert "prodockit==0.42.1" in result.output
    assert "fresh-process handoff required" in result.output
    assert "nothing to commit or push" in result.output
    assert "rebuild the Pages or documentation pipeline" in result.output
    assert "already up to date" not in result.output

    unattended = CliRunner().invoke(
        cli.main,
        ["template-sync", "--template-path", str(template), "--apply"],
    )
    assert unattended.exit_code == 1
    assert "needs both --accept-prodockit and --accept-adopt" in unattended.output
    assert "template remains unapplied" in unattended.output

    monkeypatch.setattr(cli, "_template_sync_is_interactive", lambda: True)
    declined = CliRunner().invoke(
        cli.main,
        ["template-sync", "--template-path", str(template), "--apply"],
        input="n\n",
    )
    assert declined.exit_code == 0, declined.output
    assert "Stopped safely" in declined.output
    assert "No template files, metadata, or branch were changed" in declined.output
    monkeypatch.setattr(cli, "_template_sync_is_interactive", lambda: False)

    def failed_install(*args, **kwargs) -> None:
        from prodockit.template_sync import TemplateSyncError

        raise TemplateSyncError("simulated download failure")

    monkeypatch.setattr(
        "prodockit.template_prerequisites.install_prodockit",
        failed_install,
    )
    failed = CliRunner().invoke(
        cli.main,
        [
            "template-sync",
            "--template-path",
            str(template),
            "--apply",
            "--accept-prodockit",
            "--accept-adopt",
        ],
    )
    assert failed.exit_code == 1
    assert "simulated download failure" in failed.output
    assert subprocess.run(
        ["git", "-C", str(project), "branch", "--list", "template-update-*"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout == ""

    installed: list[object] = []
    resumed: list[tuple[list[str], object]] = []
    monkeypatch.setattr(
        "prodockit.template_prerequisites.install_prodockit",
        lambda planned, **kwargs: installed.append(planned),
    )
    monkeypatch.setattr(
        cli,
        "_run_template_sync_resume",
        lambda command, root: resumed.append((list(command), root)) or 0,
    )
    applied = CliRunner().invoke(
        cli.main,
        [
            "template-sync",
            "--template-path",
            str(template),
            "--apply",
            "--accept-prodockit",
            "--accept-adopt",
        ],
    )

    assert applied.exit_code == 0, applied.output
    assert len(installed) == 1
    assert len(resumed) == 1
    command, root = resumed[0]
    assert command[:4] == [cli.sys.executable, "-m", "prodockit", "template-sync"]
    assert command[command.index("--resume-version") + 1] == "0.42.1"
    assert command[command.index("--template-path") + 1] == str(template)
    assert "--accept-prodockit" in command and "--accept-adopt" in command
    assert root == project
    assert subprocess.run(
        ["git", "-C", str(project), "branch", "--list", "template-update-*"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout == ""


def test_template_sync_rejects_a_stale_resume_before_resolving_the_template(
    tmp_path, monkeypatch
) -> None:
    from click.testing import CliRunner

    from prodockit import cli

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli.main,
        ["template-sync", "--apply", "--resume-version", "999.0"],
    )

    assert result.exit_code == 1
    assert "fresh process loaded" in result.output
    assert "template update remains unapplied" in result.output


@pytest.mark.parametrize("has_manifest", [False, True])
@pytest.mark.parametrize(
    "remote",
    [
        "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git",
        "git@github.com:buckwem/prodockit-template.git",
    ],
)
def test_a_sibling_checkout_is_never_selected(
    tmp_path, monkeypatch, has_manifest: bool, remote: str
) -> None:
    """A nearby template cannot override the remote selected for the project.

    Even a checkout with a valid manifest can be old or edited. Local template
    development is explicit through ``--template-path``; an ordinary run must
    fetch the resolved GitHub or GitLab template instead.
    """
    import subprocess

    from prodockit.cli import _template_checkout

    workspace = tmp_path / "GitLab"
    project = workspace / "my-report"
    sibling = workspace / "prodockit-template"
    for path in (project, sibling):
        path.mkdir(parents=True)
        subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    if has_manifest:
        (sibling / ".prodockit-template.toml").write_text(
            "[template]\n", encoding="utf-8"
        )

    fetched: dict[str, object] = {}

    def fake_ensure(remote: str, path, run) -> str:
        fetched["path"] = path
        path.mkdir(parents=True, exist_ok=True)
        return "cloned"

    monkeypatch.setattr("prodockit.template_sync.ensure_template", fake_ensure)
    monkeypatch.setattr("prodockit.template_sync.cache_root", lambda *a, **k: tmp_path / "cache")

    where, how = _template_checkout(project, remote)

    assert where != sibling, "the sibling checkout must not be used"
    assert where == fetched["path"], "it should have fetched instead"
    assert how == "fetched just now"


def test_apply_commits_sets_upstream_and_publishes_the_review_branch(
    tmp_path, monkeypatch
) -> None:
    """The normal author path finishes without asking them to recover with Git."""
    import subprocess

    from click.testing import CliRunner

    from prodockit import cli
    from prodockit.template_sync import branch_name, read_applied_release, read_stamp

    template = tmp_path / "template"
    project = tmp_path / "report"
    remote = tmp_path / "remote.git"
    template.mkdir()
    project.mkdir()
    manifest = """
[template]
owns = ["managed.txt", ".github/workflows/**"]
[project]
owns = ["docs/**"]
[shared]
files = ["requirements.txt"]
[excluded]
paths = []
"""
    (template / ".prodockit-template.toml").write_text(manifest, encoding="utf-8")
    (template / "managed.txt").write_text("old\n", encoding="utf-8")
    (template / "requirements.txt").write_text(
        "prodockit>=0.39.0\nzensical>=0.0.53\n", encoding="utf-8"
    )
    (template / ".github" / "workflows").mkdir(parents=True)
    (template / ".github" / "workflows" / "docs.yml").write_text(
        "run: pip install prodockit==0.39.0 zensical==0.0.53\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(template), "init", "-b", "main", "-q"], check=True)
    subprocess.run(["git", "-C", str(template), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(template),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "old template",
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(template), "tag", "template-v1.0.0"], check=True)
    old = subprocess.run(
        ["git", "-C", str(template), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (template / "managed.txt").write_text("new\n", encoding="utf-8")
    (template / "requirements.txt").write_text(
        f"prodockit>={cli.__version__}\nzensical>=0.0.57\n", encoding="utf-8"
    )
    (template / ".github" / "workflows" / "docs.yml").write_text(
        f"run: pip install prodockit=={cli.__version__} zensical==0.0.57\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(template),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qam",
            "new template",
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(template), "tag", "template-v2.0.0"], check=True)

    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(
        ["git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True
    )
    subprocess.run(["git", "-C", str(project), "init", "-b", "main", "-q"], check=True)
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(project), "config", key, value], check=True)
    (project / "managed.txt").write_text("old\n", encoding="utf-8")
    (project / "requirements.txt").write_text(
        "prodockit[index]>=0.39.0\nzensical>=0.0.53\n", encoding="utf-8"
    )
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / ".github" / "workflows" / "docs.yml").write_text(
        "run: pip install prodockit==0.39.0 zensical==0.0.53\n", encoding="utf-8"
    )
    (project / ".prodockit-shared-files.toml").write_text(
        'version = 1\n\n[[files]]\nsource = "pdk.css"\n'
        'target = "docs/stylesheets/pdk.css"\n',
        encoding="utf-8",
    )
    (project / "docs" / "stylesheets").mkdir(parents=True)
    (project / "docs" / "stylesheets" / "pdk.css").write_text(
        "outdated\n", encoding="utf-8"
    )
    (project / ".prodockit-template").write_text(f"{old}\n", encoding="utf-8")
    (project / ".gitignore").write_text(".prodockit-template.log\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "project"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "remote", "add", "origin", str(remote)], check=True
    )
    subprocess.run(
        ["git", "-C", str(project), "push", "-qu", "origin", "main"], check=True
    )

    monkeypatch.chdir(project)
    from prodockit.adopt import Step
    from prodockit.toolchain import ToolchainPlan

    monkeypatch.setattr(
        cli,
        "assess_adoption",
        lambda *args, **kwargs: [
            Step(
                "dependency",
                "Integrate",
                "Supported toolchain",
                "missing",
                "align exact installed tools",
            )
        ],
    )
    def fake_adopt(root, *args, **kwargs):
        path = root / "adopted.txt"
        path.write_text("adopted\n", encoding="utf-8")
        return [path]

    monkeypatch.setattr(cli, "apply_adoption", fake_adopt)
    monkeypatch.setattr(
        "prodockit.toolchain.plan",
        lambda *args, **kwargs: ToolchainPlan((), (), (), ()),
    )
    # The bare repository is deliberately local. Keep the production host
    # selection covered by the unit tests and use the host-neutral push here
    # so this integration test remains completely offline.
    monkeypatch.setattr(
        "prodockit.template_sync.review_push_command",
        lambda _origin, _target, remote="origin": (
            ["git", "push", "--set-upstream", remote, "HEAD"],
            False,
        ),
    )
    monkeypatch.setattr("prodockit.template_sync.review_url", lambda *_args: None)
    result = CliRunner().invoke(
        cli.main,
        [
            "template-sync",
            "--template-path",
            str(template),
            "--apply",
            "--accept-adopt",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "No Git commands are needed" in result.output
    assert "Build dependencies: aligned managed pins" in result.output
    assert "Shared files: refreshed 1 managed file" in result.output
    assert "Adopt applied and verified" in result.output
    assert (project / "adopted.txt").read_text(encoding="utf-8") == "adopted\n"
    assert f"prodockit[index]>={cli.__version__}" in (project / "requirements.txt").read_text()
    assert "zensical>=0.0.57" in (project / "requirements.txt").read_text()
    assert "prodockit==" + cli.__version__ in (
        project / ".github" / "workflows" / "docs.yml"
    ).read_text()
    assert (project / "docs" / "stylesheets" / "pdk.css").read_text() != "outdated\n"
    assert read_applied_release(project) == "template-v2.0.0"
    assert read_stamp(project) == subprocess.run(
        ["git", "-C", str(template), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    update_branch = branch_name(old)
    upstream = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--abbrev-ref", "@{upstream}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert upstream == f"origin/{update_branch}"
    assert subprocess.run(
        ["git", "-C", str(remote), "rev-parse", f"refs/heads/{update_branch}"],
        check=False,
        capture_output=True,
    ).returncode == 0

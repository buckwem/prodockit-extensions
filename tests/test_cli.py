# ---------------------------------------------------------------------------
# `prodockit template-sync`
# ---------------------------------------------------------------------------

import pytest


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


@pytest.mark.parametrize("arguments", [[], ["--apply"]])
def test_template_sync_explains_a_package_only_update(
    tmp_path, monkeypatch, arguments: list[str]
) -> None:
    """An environment upgrade produces no Git diff, but published outputs
    still need rebuilding with the new package."""
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
    monkeypatch.setattr(
        "prodockit.template_sync.latest_prodockit_version", lambda: "0.43.3"
    )
    result = CliRunner().invoke(
        cli.main,
        ["template-sync", "--template-path", str(template), *arguments],
    )

    assert result.exit_code == 0, result.output
    assert "installed: 0.43.2" in result.output
    assert "latest available: 0.43.3" in result.output
    assert 'python -m pip install --upgrade "prodockit>=0.43.3"' in result.output
    assert "nothing to commit or push" in result.output
    assert "rebuild the Pages or documentation pipeline" in result.output
    assert "already up to date" not in result.output


def test_a_sibling_checkout_without_a_manifest_is_passed_over(tmp_path, monkeypatch) -> None:
    """An old clone beside a project must not stop the command.

    A checkout taken before the manifest existed answers nothing this
    asks, and preferring it produced a hard failure with a perfectly good
    copy one fetch away - which is what happened to the first person to
    run this against a real Surrey project.
    """
    import subprocess

    from prodockit.cli import _template_checkout

    workspace = tmp_path / "GitLab"
    project = workspace / "my-report"
    stale = workspace / "prodockit-template"
    for path in (project, stale):
        path.mkdir(parents=True)
        subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    # The stale sibling has a checkout but no manifest.
    assert not (stale / ".prodockit-template.toml").exists()

    fetched: dict[str, object] = {}

    def fake_ensure(remote: str, path, run) -> str:
        fetched["path"] = path
        path.mkdir(parents=True, exist_ok=True)
        return "cloned"

    monkeypatch.setattr("prodockit.template_sync.ensure_template", fake_ensure)
    monkeypatch.setattr("prodockit.template_sync.cache_root", lambda *a, **k: tmp_path / "cache")

    where, how = _template_checkout(project, "git@gitlab.example.com:someone/prodockit-template.git")

    assert where != stale, "the stale sibling must not be used"
    assert where == fetched["path"], "it should have fetched instead"
    assert "passed over" in how and str(stale) in how, f"the run must say why: {how}"


def test_a_sibling_checkout_with_a_manifest_is_still_preferred(tmp_path, monkeypatch) -> None:
    """The case the skip must not break: a maintainer editing all three
    repositories means the copy beside the project."""
    import subprocess

    from prodockit.cli import _template_checkout

    workspace = tmp_path / "GitHub"
    project = workspace / "my-report"
    sibling = workspace / "prodockit-template"
    for path in (project, sibling):
        path.mkdir(parents=True)
        subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    (sibling / ".prodockit-template.toml").write_text("[template]\n", encoding="utf-8")

    def explode(*args, **kwargs):
        raise AssertionError("must not fetch when a usable sibling is there")

    monkeypatch.setattr("prodockit.template_sync.ensure_template", explode)

    where, how = _template_checkout(project, "git@github.com:someone/prodockit-template.git")

    assert where == sibling
    assert how == "beside this project"

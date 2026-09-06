from pathlib import Path

import click
import pytest

from prodockit import windows_terminal as terminal


def test_refresh_preserves_active_scripts(monkeypatch, capsys):
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setenv("PATH", "old")
    monkeypatch.setattr(
        terminal.shutil,
        "which",
        lambda name: name if "saved" in terminal.os.environ["PATH"] else None,
    )
    monkeypatch.setattr(
        "prodockit.bootstrap.model.refresh_windows_path",
        lambda: terminal.os.environ.update(PATH="saved", WEASYPRINT_DLL_DIRECTORIES="pango"),
    )
    terminal.prepare_template_environment(Path("project"))
    assert terminal.os.environ["PATH"].split(";")[0] == str(Path(terminal.sys.prefix) / "Scripts")
    assert terminal.os.environ["WEASYPRINT_DLL_DIRECTORIES"] == "pango"
    assert "refreshed" in capsys.readouterr().out


def test_unresolved_git_exits_with_restart_banner(monkeypatch, capsys):
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", lambda name: None)
    monkeypatch.setattr("prodockit.bootstrap.model.refresh_windows_path", lambda: None)
    with pytest.raises(click.ClickException, match="Commands still unavailable"):
        terminal.prepare_template_environment(Path("project"))
    output = capsys.readouterr().out
    assert "=" * 60 in output
    assert "RESTART YOUR TERMINAL" in output
    assert "Template Sync cannot continue" in output

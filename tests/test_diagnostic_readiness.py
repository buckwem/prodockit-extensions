# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import subprocess

import pytest

from prodockit.diagnostic_readiness import checks
from prodockit.project_config import ProjectConfig


def config(root, **settings):
    return ProjectConfig(root / "zensical.toml", settings, (), {})


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_starter_site_warns_without_git_and_does_not_write(tmp_path):
    before = list(tmp_path.iterdir())
    result = checks(
        config(tmp_path, site_name="Documentation", site_url="https://www.example.com/")
    )
    check = result[0]
    assert check.status == "warn"
    assert "local testing can continue" in check.summary
    assert any("Stage 6" in item for item in check.details)
    assert any("site_url" in item for item in check.details)
    assert list(tmp_path.iterdir()) == before


def test_remote_mismatch_and_custom_domain_are_preserved(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "remote", "add", "origin", "git@github.com:author/report.git")
    settings = config(
        tmp_path,
        site_name="Report",
        site_url="https://docs.example.net/",
        repo_url="https://github.com/old/report",
    )
    check = checks(settings)[0]
    assert check.status == "warn"
    assert any("repo_url" in item for item in check.details)
    assert not any("site_url" in item for item in check.details)
    assert settings.project["site_url"] == "https://docs.example.net/"


def test_git_ignore_and_already_tracked_files_are_distinct(tmp_path):
    git(tmp_path, "init")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/pyvenv.cfg").write_text("test")
    git(tmp_path, "add", ".venv")
    (tmp_path / ".gitignore").write_text(
        ".venv/\n__pycache__/\ntools/*/node_modules/\nsite/\ndocs/.prodockit-pdf-mermaid/\ndocs/*.pdf\n"
    )
    check = next(
        item for item in checks(config(tmp_path)) if item.id == "repository.generated-files"
    )
    assert check.status == "warn"
    assert any("already tracked" in line for line in check.details)
    assert not any("Ignore rules are missing" in line for line in check.details)
    assert (tmp_path / ".venv/pyvenv.cfg").is_file()


@pytest.mark.parametrize("workflow", [".github/workflows/docs.yml", ".gitlab-ci.yml"])
def test_stock_workflow_and_missing_requirements(tmp_path, workflow):
    path = tmp_path / workflow
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("run: pip install zensical\n")
    check = next(item for item in checks(config(tmp_path)) if item.id == "publishing.workflow")
    assert check.status == "warn"
    assert any("pdk adopt --apply" in line for line in check.details)
    path.write_text("run: pip install -r requirements.txt\n")
    check = next(item for item in checks(config(tmp_path)) if item.id == "publishing.workflow")
    assert any("missing requirements.txt" in line for line in check.details)


def test_native_pdf_activity_is_not_omitted(tmp_path, monkeypatch):
    from prodockit import adopt, diagnostics

    monkeypatch.setattr(
        adopt,
        "resolve_options",
        lambda root: adopt.AdoptChoiceResolution(adopt.AdoptOptions(), "defaults", False),
    )
    monkeypatch.setattr(
        adopt,
        "assess",
        lambda *a, **kw: [
            adopt.Step(
                "pdf-runtime",
                "Integrate",
                "Native PDF libraries and fonts",
                "missing",
                "Inter is missing",
            )
        ],
    )
    check = diagnostics._adopt_readiness_checks(tmp_path, online=False)[0]
    assert check.status == "warn"
    assert "pdf-runtime" in check.data["pending"]
    assert any("adopt --dry-run" in line for line in check.details)


def test_configured_site_and_ignored_outputs_pass(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "remote", "add", "origin", "git@gitlab.surrey.ac.uk:author/report.git")
    (tmp_path / ".gitignore").write_text(
        ".venv/\n__pycache__/\ntools/*/node_modules/\nsite/\n"
        "docs/.prodockit-pdf-mermaid/\ndocs/*.pdf\n"
    )
    result = checks(
        config(
            tmp_path,
            site_name="My report",
            site_url="https://docs.example.net/",
            repo_url="https://gitlab.surrey.ac.uk/author/report",
            repo_name="author/report",
        )
    )
    assert all(item.status == "pass" for item in result)


def test_unparseable_remote_warns_without_exposing_it(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "remote", "add", "origin", "/private/repository")
    check = checks(config(tmp_path, site_name="Report", site_url="https://docs.example.net/"))[0]
    assert check.status == "warn"
    assert "/private/repository" not in str(check.details)


def test_commented_install_is_not_a_workflow_problem(tmp_path):
    path = tmp_path / ".github/workflows/publish.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("# old: pip install zensical\nrun: echo ok\n")
    check = next(item for item in checks(config(tmp_path)) if item.id == "publishing.workflow")
    assert check.status == "pass"

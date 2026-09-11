# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import pytest
import yaml

from prodockit import toolchain
from prodockit.adopt import LOCAL_IGNORE_PATTERNS, ensure_local_ignores
from prodockit.adopt_workflow import STOCK_GITHUB, plan, plans


def test_stock_workflow_repair_is_valid_and_idempotent(tmp_path):
    path = tmp_path / ".github/workflows/docs.yml"
    path.parent.mkdir(parents=True)
    path.write_text(STOCK_GITHUB)
    target, content = plan(tmp_path)
    assert target == path
    steps = yaml.safe_load(content)["jobs"]["deploy"]["steps"]
    assert steps[3]["run"] == "python -m pip install -r requirements.txt"
    assert "npm ci --prefix tools/mathjax" in steps[4]["run"]
    assert steps[5]["run"] == "zensical build --clean"
    path.write_text(content)
    assert plan(tmp_path) is None


def test_custom_workflow_untouched(tmp_path):
    path = tmp_path / ".github/workflows/docs.yml"
    path.parent.mkdir(parents=True)
    path.write_text("steps:\n  - run: pip install zensical custom-package\n")
    original = path.read_text()
    target, content = plan(tmp_path)
    assert target == tmp_path / "pdk.yml"
    assert path.read_text() == original
    assert yaml.safe_load(content)["jobs"]
    target.write_text(content + "# User review notes\n")
    assert plan(tmp_path) is None


def test_custom_workflow_with_stock_install_line_is_not_overwritten(tmp_path):
    path = tmp_path / ".github/workflows/docs.yml"
    path.parent.mkdir(parents=True)
    path.write_text(STOCK_GITHUB + "# My custom workflow\n")
    assert plan(tmp_path)[0] == tmp_path / "pdk.yml"


def test_both_hosts_get_separate_inactive_proposals(tmp_path):
    github = tmp_path / ".github/workflows/docs.yml"
    github.parent.mkdir(parents=True)
    github.write_text("# Custom GitHub workflow\n")
    gitlab = tmp_path / ".gitlab-ci.yml"
    gitlab.write_text("include: custom.yml\n")
    pending = plans(tmp_path)
    assert [p.name for p, _ in pending] == ["pdk.yml", ".gitlab-pdk.yml"]
    for path, content in pending:
        assert path.parent == tmp_path
        assert yaml.safe_load(content)
        path.write_text(content)
    assert plans(tmp_path) == []
    assert github.read_text() == "# Custom GitHub workflow\n"
    assert gitlab.read_text() == "include: custom.yml\n"
    assert list(yaml.safe_load(pending[1][1])) == [".prodockit-pages-example"]


def test_no_workflow_does_not_create_one(tmp_path):
    assert plans(tmp_path) == []


@pytest.mark.parametrize(
    "filename",
    [
        ".github/workflows/docs.yml",
        ".github/workflows/custom.yaml",
        ".gitlab-ci.yml",
        ".gitlab-ci.yaml",
        ".gitlab/ci/build.yml",
    ],
)
def test_toolchain_does_not_rewrite_ci_pins(tmp_path, filename):
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    original = "# Custom pipeline\nscript:\n  - pip install zensical==0.0.1\n"
    path.write_text(original)
    toolchain.write_declarations(tmp_path)
    assert path.read_text() == original
    assert filename not in toolchain._declarations(tmp_path)[0]
    assert toolchain.write_declarations(tmp_path) == []


def test_alternative_requirements_used_in_proposals(tmp_path):
    requirements = tmp_path / "requirements/docs.txt"
    requirements.parent.mkdir()
    requirements.write_text("prodockit\n")
    (tmp_path / ".gitlab-ci.yml").write_text("# Custom\n")
    _, content = plan(tmp_path)
    assert "pip install -r requirements/docs.txt" in content


def test_adopt_core_writes_both_proposals_and_preserves_review_edits(tmp_path):
    from prodockit.adopt import AdoptOptions, apply_step

    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Report"\n')
    github = tmp_path / ".github/workflows/docs.yml"
    github.parent.mkdir(parents=True)
    github.write_text("# Keep this custom workflow\n")
    gitlab = tmp_path / ".gitlab-ci.yml"
    gitlab.write_text("# Keep this pipeline\n")
    written = apply_step(tmp_path, AdoptOptions(), "core")
    assert tmp_path / "pdk.yml" in written
    assert tmp_path / ".gitlab-pdk.yml" in written
    for name in ("pdk.yml", ".gitlab-pdk.yml"):
        (tmp_path / name).write_text("# My manual review\n")
    apply_step(tmp_path, AdoptOptions(), "core")
    assert github.read_text() == "# Keep this custom workflow\n"
    assert gitlab.read_text() == "# Keep this pipeline\n"
    assert (tmp_path / "pdk.yml").read_text() == "# My manual review\n"
    assert (tmp_path / ".gitlab-pdk.yml").read_text() == "# My manual review\n"


def test_proposal_notice_does_not_claim_automatic_publishing(tmp_path, monkeypatch, capsys):
    from prodockit import adopt_identity, cli

    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Report"\n')
    (tmp_path / "pdk.yml").write_text("# Proposal\n")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(adopt_identity, "configure", lambda *a, **kw: None)
    cli._adopt_finish_details(tmp_path, apply=True, offline=True)
    output = capsys.readouterr().out
    assert "BUILD AUTOMATION — MANUAL REVIEW NEEDED" in output
    assert "./pdk.yml → ./.github/workflows/docs.yml" in output
    assert "do not run automatically" in output


def test_ignores_preserve_authored_rules_and_are_idempotent(tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text("# Custom rule\nprivate/\n")
    assert ensure_local_ignores(tmp_path) == [path]
    content = path.read_text()
    assert content.startswith("# Custom rule\nprivate/\n")
    assert all(line in content.splitlines() for line in LOCAL_IGNORE_PATTERNS)
    assert ensure_local_ignores(tmp_path) == []

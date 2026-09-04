# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import pathlib

import pytest

from prodockit.template_prerequisites import (
    ProdockitPrerequisite,
    install_prodockit,
    plan_prodockit,
    template_prodockit_version,
)


def _template(root: pathlib.Path, requirement: str, workflow: str = "") -> pathlib.Path:
    root.mkdir()
    (root / "requirements.txt").write_text(requirement + "\n", encoding="utf-8")
    if workflow:
        path = root / ".github" / "workflows" / "docs.yml"
        path.parent.mkdir(parents=True)
        path.write_text(workflow, encoding="utf-8")
    return root


def test_template_release_relationship_supplies_exact_version_and_extras(tmp_path) -> None:
    template = _template(
        tmp_path / "template",
        "prodockit[index,testing]>=0.57.0",
        "run: pip install prodockit==0.58.0\n",
    )

    assert template_prodockit_version(template) == ("0.58.0", "[index,testing]")


@pytest.mark.parametrize(
    ("installed", "target", "action"),
    [
        ("0.57.0", "0.58.0", "upgrade"),
        ("0.59.0", "0.58.0", "downgrade"),
        ("0.58.0", "0.58.0", "check"),
    ],
)
def test_plan_names_install_upgrade_downgrade_and_match(
    tmp_path, installed: str, target: str, action: str
) -> None:
    template = _template(tmp_path / "template", f"prodockit[index]>={target}")

    planned = plan_prodockit(template, installed=installed)

    assert planned.action == action
    assert planned.specifier == f"prodockit[index]=={target}"
    assert planned.needs_work is (installed != target)


def test_offline_plan_uses_active_interpreter_and_wheelhouse_policy(tmp_path, monkeypatch) -> None:
    template = _template(tmp_path / "template with spaces", "prodockit>=0.58.0")
    wheelhouse = tmp_path / "wheel house"
    monkeypatch.setenv("PDK_WHEELHOUSE", str(wheelhouse))

    planned = plan_prodockit(template, installed="0.57.0", offline=True)

    assert planned.command[1:4] == ("-m", "pip", "install")
    assert "--no-index" in planned.command
    assert planned.command[planned.command.index("--find-links") + 1] == str(wheelhouse)
    assert planned.command[-1] == "prodockit==0.58.0"


def test_install_reuses_shared_resilient_runner(tmp_path, monkeypatch) -> None:
    command = ("python with spaces", "-m", "pip", "install", "prodockit==0.58.0")
    planned = ProdockitPrerequisite("0.57.0", "0.58.0", "", command)
    calls: list[tuple[tuple[str, ...], pathlib.Path, bool]] = []

    monkeypatch.setattr(
        "prodockit.template_prerequisites.run_install_command",
        lambda value, *, root, reporter, offline: calls.append((value, root, offline)),
    )

    install_prodockit(planned, root=tmp_path)

    assert calls == [(command, tmp_path, False)]

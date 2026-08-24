# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety and normalisation checks for the installed-wheel acceptance driver."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
adopt_acceptance = importlib.import_module("tools.adopt_acceptance")


def test_a_wheel_file_or_single_wheel_directory_is_accepted(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    assert adopt_acceptance.resolve_wheel(wheel) == wheel.resolve()
    assert adopt_acceptance.resolve_wheel(tmp_path) == wheel.resolve()


def test_an_ambiguous_wheel_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "prodockit-1-py3-none-any.whl").write_bytes(b"one")
    (tmp_path / "prodockit-2-py3-none-any.whl").write_bytes(b"two")

    with pytest.raises(adopt_acceptance.AcceptanceError, match="more than one"):
        adopt_acceptance.resolve_wheel(tmp_path)


@pytest.mark.parametrize("machine", ["arm64", "aarch64"])
def test_arm64_architecture_names_are_accepted(monkeypatch, machine: str) -> None:
    monkeypatch.setattr(adopt_acceptance.platform, "machine", lambda: machine)

    assert adopt_acceptance.assert_arm64() == machine


def test_x64_is_rejected_when_arm64_is_required(monkeypatch) -> None:
    monkeypatch.setattr(adopt_acceptance.platform, "machine", lambda: "x86_64")

    with pytest.raises(adopt_acceptance.AcceptanceError, match="must be ARM64"):
        adopt_acceptance.assert_arm64()


def test_architecture_requirements_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        adopt_acceptance.parser().parse_args(
            ["--wheel", "candidate.whl", "--require-x64", "--require-arm64"]
        )


def test_a_real_project_is_copied_without_generated_or_git_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    (source / "docs").mkdir(parents=True)
    (source / "docs" / "index.md").write_text("# Kept\n", encoding="utf-8")
    for ignored in (".git", ".venv", ".cache", "site", "node_modules"):
        path = source / ignored
        path.mkdir()
        (path / "ignored").write_text("ignored", encoding="utf-8")

    adopt_acceptance.copy_project(source, output)

    assert (output / "docs" / "index.md").is_file()
    for ignored in (".git", ".venv", ".cache", "site", "node_modules"):
        assert not (output / ignored).exists()


def test_copy_refuses_to_replace_or_nest_inside_the_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()

    with pytest.raises(adopt_acceptance.AcceptanceError, match="separate"):
        adopt_acceptance.copy_project(source, source / "copy")
    with pytest.raises(adopt_acceptance.AcceptanceError, match="refusing to replace"):
        adopt_acceptance.copy_project(source, existing)


def test_site_snapshot_ignores_only_assets_added_by_adoption(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    original = b"<html><head></head><body><p>Same</p></body></html>"
    adopted = (
        b'<html><head><link rel="stylesheet" href="./stylesheets/prodockit.css">'
        b"</head><body><p>Same</p>"
        b'<script src="./javascripts/mathjax.js"></script></body></html>'
    )
    (before / "index.html").write_bytes(original)
    (after / "index.html").write_bytes(adopted)

    assert adopt_acceptance.snapshot(before, site=True) == adopt_acceptance.snapshot(
        after, site=True
    )

    (after / "index.html").write_bytes(adopted.replace(b"Same", b"Changed"))
    assert adopt_acceptance.snapshot(before, site=True) != adopt_acceptance.snapshot(
        after, site=True
    )

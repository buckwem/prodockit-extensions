# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for the remaining MathJax-only Node tooling scaffold."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit.cli import main
from prodockit.init_tools import (
    COMPONENT_FILES,
    TEMPLATE_DIR,
    InitToolsError,
    gitignore_lines,
    init_tools,
    install_commands,
)
from prodockit.pdf.config import _find_tex2svg_script


def test_scaffolds_mathjax_by_default(tmp_path: Path) -> None:
    result = init_tools(tmp_path / "tools")

    assert result.wrote_anything
    assert result.components == ["mathjax"]
    assert (tmp_path / "tools/mathjax/package.json").is_file()
    assert (tmp_path / "tools/mathjax/package-lock.json").is_file()
    assert (tmp_path / "tools/mathjax/tex2svg.js").is_file()
    assert result.skipped == []


def test_rejects_mermaid_as_an_owned_component(tmp_path: Path) -> None:
    with pytest.raises(InitToolsError, match="unknown component"):
        init_tools(tmp_path / "tools", components=("mermaid",))


def test_does_not_overwrite_an_existing_file(tmp_path: Path) -> None:
    init_tools(tmp_path / "tools")
    edited = tmp_path / "tools/mathjax/package.json"
    edited.write_text('{"name": "locally-customised"}', encoding="utf-8")

    result = init_tools(tmp_path / "tools")

    assert edited.read_text(encoding="utf-8") == '{"name": "locally-customised"}'
    assert edited in result.skipped
    assert edited not in result.written


def test_does_not_pair_canonical_lock_with_custom_manifest(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    manifest = tools / "mathjax" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name": "author-owned"}\n', encoding="utf-8")

    result = init_tools(tools)

    lock = tools / "mathjax" / "package-lock.json"
    assert not lock.exists()
    assert lock in result.skipped


def test_force_overwrites(tmp_path: Path) -> None:
    init_tools(tmp_path / "tools")
    edited = tmp_path / "tools/mathjax/package.json"
    edited.write_text('{"name": "locally-customised"}', encoding="utf-8")

    result = init_tools(tmp_path / "tools", force=True)

    assert "locally-customised" not in edited.read_text(encoding="utf-8")
    assert edited in result.written


def test_scaffolded_manifest_is_locked_and_private(tmp_path: Path) -> None:
    init_tools(tmp_path / "tools")

    package = json.loads((tmp_path / "tools/mathjax/package.json").read_text())
    lock = json.loads((tmp_path / "tools/mathjax/package-lock.json").read_text())
    assert "mathjax-full" in package["dependencies"]
    assert "puppeteer-core" in package["dependencies"]
    assert package["private"] is True
    assert lock["packages"][""]["dependencies"] == package["dependencies"]
    assert package["overrides"]["@xmldom/xmldom"] == "0.9.12"
    assert lock["packages"]["node_modules/@xmldom/xmldom"]["version"] == "0.9.12"


def test_scaffold_lands_where_pdf_build_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init_tools("tools")
    assert _find_tex2svg_script(None) == str((tmp_path / "tools/mathjax/tex2svg.js").resolve())


def test_tex2svg_script_is_shipped_and_substantive() -> None:
    script = TEMPLATE_DIR / "mathjax/tex2svg.js"
    source = script.read_text(encoding="utf-8")
    assert "mathjax-full/js/mathjax.js" in source
    assert "process.stdin" in source
    assert len(source) > 500


def test_every_declared_template_file_is_packaged() -> None:
    assert set(COMPONENT_FILES) == {"mathjax"}
    for filename in COMPONENT_FILES["mathjax"]:
        assert (TEMPLATE_DIR / "mathjax" / filename).is_file()


def test_documentation_mathjax_fixture_matches_the_packaged_template() -> None:
    root = Path(__file__).resolve().parents[1]
    for filename in COMPONENT_FILES["mathjax"]:
        assert (root / "tools/mathjax" / filename).read_bytes() == (
            TEMPLATE_DIR / "mathjax" / filename
        ).read_bytes()


def test_guidance_targets_only_mathjax(tmp_path: Path) -> None:
    result = init_tools(tmp_path / "tools")
    assert gitignore_lines(result) == [
        f"{(tmp_path / 'tools').as_posix()}/mathjax/node_modules/"
    ]
    assert len(install_commands(result)) == 1
    command = install_commands(result)[0]
    assert command.startswith("npm --prefix ")
    assert "/tools/mathjax ci --legacy-peer-deps " in command
    assert "--no-audit --no-fund --prefer-offline" in command
    assert "mermaid" not in command


def test_cli_no_longer_offers_managed_mermaid_scaffolding() -> None:
    help_result = CliRunner().invoke(main, ["init-tools", "--help"])
    assert help_result.exit_code == 0
    assert "--mermaid" not in help_result.output
    assert "--no-mermaid" not in help_result.output

    rejected = CliRunner().invoke(main, ["init-tools", "--mermaid"])
    assert rejected.exit_code == 2

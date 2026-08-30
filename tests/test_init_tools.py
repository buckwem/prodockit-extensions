# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for `prodockit.init_tools` - scaffolding the Node tooling
`prodockit.pdf` needs for Mermaid diagrams and TeX maths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prodockit.init_tools import (
    COMPONENT_FILES,
    TEMPLATE_DIR,
    InitToolsError,
    ci_environment,
    gitignore_lines,
    init_tools,
    install_commands,
)
from prodockit.pdf.config import _find_mmdc_bin, _find_tex2svg_script


def test_scaffolds_both_components_by_default(tmp_path: Path) -> None:
    result = init_tools(tmp_path / "tools")

    assert result.wrote_anything
    assert (tmp_path / "tools/mermaid/package.json").is_file()
    assert (tmp_path / "tools/mermaid/package-lock.json").is_file()
    assert (tmp_path / "tools/mathjax/package.json").is_file()
    assert (tmp_path / "tools/mathjax/package-lock.json").is_file()
    assert (tmp_path / "tools/mathjax/tex2svg.js").is_file()
    assert result.skipped == []


def test_scaffolds_only_what_was_asked_for(tmp_path: Path) -> None:
    """A project with diagrams but no maths shouldn't be handed a
    mathjax install it will never use."""
    init_tools(tmp_path / "tools", components=("mermaid",))

    assert (tmp_path / "tools/mermaid/package.json").is_file()
    assert not (tmp_path / "tools/mathjax").exists()


def test_rejects_an_unknown_component(tmp_path: Path) -> None:
    with pytest.raises(InitToolsError, match="unknown component"):
        init_tools(tmp_path / "tools", components=("mermaid", "graphviz"))


def test_does_not_overwrite_an_existing_file(tmp_path: Path) -> None:
    """A project will have run `npm ci` against its own committed
    lockfile - replacing its package.json underneath that would be a
    genuinely damaging default."""
    init_tools(tmp_path / "tools")
    edited = tmp_path / "tools/mermaid/package.json"
    edited.write_text('{"name": "locally-customised"}', encoding="utf-8")

    result = init_tools(tmp_path / "tools")

    assert edited.read_text(encoding="utf-8") == '{"name": "locally-customised"}'
    assert edited in result.skipped
    assert edited not in result.written


def test_does_not_pair_the_canonical_lock_with_a_custom_manifest(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    manifest = tools / "mermaid" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name": "author-owned"}\n', encoding="utf-8")

    result = init_tools(tools, components=("mermaid",))

    lock = tools / "mermaid" / "package-lock.json"
    assert not lock.exists()
    assert lock in result.skipped


def test_force_overwrites(tmp_path: Path) -> None:
    init_tools(tmp_path / "tools")
    edited = tmp_path / "tools/mermaid/package.json"
    edited.write_text('{"name": "locally-customised"}', encoding="utf-8")

    result = init_tools(tmp_path / "tools", force=True)

    assert "locally-customised" not in edited.read_text(encoding="utf-8")
    assert edited in result.written


def test_scaffolded_manifests_are_valid_json_with_the_expected_dependency(
    tmp_path: Path,
) -> None:
    init_tools(tmp_path / "tools")

    mermaid = json.loads((tmp_path / "tools/mermaid/package.json").read_text(encoding="utf-8"))
    mathjax = json.loads((tmp_path / "tools/mathjax/package.json").read_text(encoding="utf-8"))

    assert "@mermaid-js/mermaid-cli" in mermaid["dependencies"]
    assert "mathjax-full" in mathjax["dependencies"]
    # Both are private scaffolds, never published.
    assert mermaid["private"] is True
    assert mathjax["private"] is True

    mermaid_lock = json.loads(
        (tmp_path / "tools/mermaid/package-lock.json").read_text(encoding="utf-8")
    )
    mathjax_lock = json.loads(
        (tmp_path / "tools/mathjax/package-lock.json").read_text(encoding="utf-8")
    )
    assert mermaid_lock["packages"][""]["dependencies"] == mermaid["dependencies"]
    assert mathjax_lock["packages"][""]["dependencies"] == mathjax["dependencies"]


def test_scaffold_lands_exactly_where_the_pdf_build_looks_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the command. `_find_tex2svg_script` resolves a
    real scaffolded file; `_find_mmdc_bin` needs an actual npm install, so
    its own path is covered by faking just the binary that install would
    produce - the directory layout being asserted is the same one.
    """
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    init_tools("tools")

    assert _find_tex2svg_script(None) == str((tmp_path / "tools/mathjax/tex2svg.js").resolve())

    mmdc = tmp_path / "tools/mermaid/node_modules/.bin/mmdc"
    mmdc.parent.mkdir(parents=True)
    mmdc.write_text("#!/bin/sh\n", encoding="utf-8")
    assert _find_mmdc_bin(None) == str(mmdc.resolve())


def test_tex2svg_script_is_shipped_and_looks_like_the_real_thing() -> None:
    """Guards against the packaged copy going missing from the wheel -
    an empty or absent template would scaffold silently and fail only at
    PDF build time."""
    script = TEMPLATE_DIR / "mathjax/tex2svg.js"
    source = script.read_text(encoding="utf-8")
    assert "mathjax-full/js/mathjax.js" in source
    assert "process.stdin" in source
    assert len(source) > 500


def test_every_declared_template_file_is_actually_packaged() -> None:
    for component, filenames in COMPONENT_FILES.items():
        for filename in filenames:
            assert (TEMPLATE_DIR / component / filename).is_file(), (
                f"{component}/{filename} is declared in COMPONENT_FILES but "
                "missing from the packaged template"
            )


# --- The guidance the command prints ---------------------------------------


def test_gitignore_lines_cover_the_installs_not_the_manifests(tmp_path: Path) -> None:
    result = init_tools(tmp_path / "tools")
    lines = gitignore_lines(result)
    assert any(line.endswith("mermaid/node_modules/") for line in lines)
    assert any(line.endswith("mathjax/node_modules/") for line in lines)
    assert not any("package.json" in line for line in lines)


def test_install_commands_target_each_scaffolded_component(tmp_path: Path) -> None:
    result = init_tools(tmp_path / "tools", components=("mermaid",))
    commands = install_commands(result)
    assert len(commands) == 1
    assert "--prefix" in commands[0]
    assert " ci " in commands[0]
    assert "--legacy-peer-deps" in commands[0]
    assert commands[0].startswith("npm --prefix ")
    assert "--no-audit --no-fund --prefer-offline" in commands[0]
    assert "/tools/mermaid ci " in commands[0]


def test_ci_environment_uses_the_variable_puppeteer_actually_honours() -> None:
    """The pre-rename PUPPETEER_SKIP_CHROMIUM_DOWNLOAD is what everyone
    reaches for, and puppeteer 25.x (what mermaid-cli 11.x resolves to)
    ignores it - downloading a full Chrome build on every CI run before
    falling back to PUPPETEER_EXECUTABLE_PATH anyway. Both downstream
    projects had it wrong."""
    env = ci_environment()
    assert env["PUPPETEER_SKIP_DOWNLOAD"] == "true"
    assert "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD" not in env
    assert env["PUPPETEER_EXECUTABLE_PATH"]

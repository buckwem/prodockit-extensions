# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import json
from types import SimpleNamespace

import pytest

from prodockit import adopt
from prodockit import adopt_renderers as renderers
from prodockit.init_tools import TEMPLATE_DIR


@pytest.mark.parametrize("component", ["mermaid", "mathjax"])
@pytest.mark.parametrize("old_version", ["0.1.0", "999.0.0"])
def test_upgrade_and_downgrade_restore_locked_release(tmp_path, component, old_version):
    directory = tmp_path / "tools" / component
    directory.mkdir(parents=True)
    original = json.dumps({"dependencies": {renderers.PACKAGES[component]: old_version}})
    (directory / "package.json").write_text(original)
    renderers.align(tmp_path, component, write=adopt._atomic_write)
    assert (directory / "package.json").read_bytes() == (
        TEMPLATE_DIR / component / "package.json"
    ).read_bytes()
    assert not renderers.changes(tmp_path, component)
    backups = list((tmp_path / renderers.BACKUPS).rglob("package.json"))
    assert len(backups) == 1
    assert backups[0].read_text() == original
    assert renderers.align(tmp_path, component, write=adopt._atomic_write) == []


def test_all_backups_precede_any_replacement(tmp_path):
    directory = tmp_path / "tools" / "mermaid"
    directory.mkdir(parents=True)
    for name in ("package.json", "package-lock.json"):
        (directory / name).write_text("old")

    def fail_backup(path, content):
        if path.name == "package-lock.json":
            raise OSError("disk full")
        adopt._atomic_write(path, content)

    with pytest.raises(OSError, match="disk full"):
        renderers.align(tmp_path, "mermaid", write=fail_backup)
    assert (directory / "package.json").read_text() == "old"
    assert (directory / "package-lock.json").read_text() == "old"
    renderers.align(tmp_path, "mermaid", write=adopt._atomic_write)
    assert not renderers.changes(tmp_path, "mermaid")


def test_symlinked_renderer_directory_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "tools").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        renderers.align(tmp_path, "mermaid", write=adopt._atomic_write)
    assert list(outside.iterdir()) == []


def test_healthy_but_wrong_mermaid_version_needs_alignment(tmp_path, monkeypatch):
    renderers.align(tmp_path, "mermaid", write=adopt._atomic_write)
    binary = tmp_path / "tools/mermaid/node_modules/.bin/mmdc"
    binary.parent.mkdir(parents=True)
    binary.write_text("test")
    monkeypatch.setattr(
        adopt, "probe_mermaid", lambda *args: SimpleNamespace(ok=True, version="0.1.0")
    )
    ok, detail = adopt._tool_health(tmp_path, "mermaid")
    assert not ok
    assert f"supported {renderers.expected_version('mermaid')}" in detail


def test_line_endings_alone_do_not_trigger_alignment(tmp_path):
    renderers.align(tmp_path, "mathjax", write=adopt._atomic_write)
    script = tmp_path / "tools/mathjax/tex2svg.js"
    script.write_bytes(script.read_bytes().replace(b"\n", b"\r\n"))
    assert not renderers.changes(tmp_path, "mathjax")


def test_interrupted_pair_replacement_can_resume(tmp_path):
    directory = tmp_path / "tools/mermaid"
    directory.mkdir(parents=True)
    for name in ("package.json", "package-lock.json"):
        (directory / name).write_text("old " + name)

    def interrupt(path, content):
        if path == directory / "package-lock.json":
            raise OSError("interrupted replacement")
        adopt._atomic_write(path, content)

    with pytest.raises(OSError, match="interrupted"):
        renderers.align(tmp_path, "mermaid", write=interrupt)
    renderers.align(tmp_path, "mermaid", write=adopt._atomic_write)
    assert not renderers.changes(tmp_path, "mermaid")
    backups = list((tmp_path / renderers.BACKUPS).rglob("*.json"))
    assert sorted(path.read_text() for path in backups) == [
        "old package-lock.json",
        "old package.json",
    ]


def test_mathjax_metadata_version_is_checked_even_with_complete_inputs(tmp_path, monkeypatch):
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Test"\n')
    renderers.align(tmp_path, "mathjax", write=adopt._atomic_write)
    for name in (
        "tools/mathjax/node_modules/mathjax-full/es5/tex-svg-full.js",
        "docs/javascripts/mathjax.js",
        "docs/javascripts/vendor/mathjax/tex-svg-full.js",
        "docs/javascripts/vendor/mathjax/LICENSE",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    metadata = tmp_path / "tools/mathjax/node_modules/mathjax-full/package.json"
    metadata.write_text('{"version": "0.1.0"}')
    monkeypatch.setattr(adopt, "probe_mathjax", lambda *args: pytest.fail("wrong version accepted"))
    ok, detail = adopt._tool_health(tmp_path, "mathjax")
    assert not ok
    assert "align MathJax 0.1.0 to supported" in detail

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

from zendoc.pdf.icons import ADMONITION_ACCENT_COLORS, admonition_icon_svg, build_icon_registry


def _write_svg(path: Path, fill: str = "currentColor") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<svg><path fill="{fill}"/></svg>', encoding="utf-8")


def test_build_icon_registry_indexes_by_multiple_shortcode_forms(tmp_path: Path) -> None:
    icons_dir = tmp_path / ".icons"
    _write_svg(icons_dir / "fontawesome" / "solid" / "note-sticky.svg")
    registry = build_icon_registry([str(icons_dir)])
    assert "fontawesome-solid-note-sticky" in registry
    assert "fa-solid-note-sticky" in registry
    assert "fontawesome-note-sticky" in registry
    assert "note-sticky" in registry


def test_build_icon_registry_skips_non_svg_files(tmp_path: Path) -> None:
    icons_dir = tmp_path / ".icons"
    icons_dir.mkdir()
    (icons_dir / "readme.txt").write_text("not an icon", encoding="utf-8")
    registry = build_icon_registry([str(icons_dir)])
    assert registry == {}


def test_admonition_icon_svg_returns_none_when_not_configured(tmp_path: Path) -> None:
    icons_dir = tmp_path / ".icons"
    _write_svg(icons_dir / "fontawesome" / "solid" / "note-sticky.svg")
    registry = build_icon_registry([str(icons_dir)])
    assert admonition_icon_svg("note", None, registry) is None
    assert admonition_icon_svg("note", {}, registry) is None


def test_admonition_icon_svg_returns_none_when_icon_file_missing(tmp_path: Path) -> None:
    registry: dict[str, str] = {}
    config = {"note": "fontawesome/solid/note-sticky"}
    assert admonition_icon_svg("note", config, registry) is None


def test_admonition_icon_svg_replaces_currentcolor_with_the_accent_colour(tmp_path: Path) -> None:
    icons_dir = tmp_path / ".icons"
    _write_svg(icons_dir / "fontawesome" / "solid" / "note-sticky.svg", fill="currentColor")
    registry = build_icon_registry([str(icons_dir)])
    config = {"note": "fontawesome/solid/note-sticky"}
    svg = admonition_icon_svg("note", config, registry)
    assert svg is not None
    assert ADMONITION_ACCENT_COLORS["note"] in svg
    assert "currentColor" not in svg


def test_admonition_icon_svg_shortcode_matching_is_case_and_slash_insensitive(tmp_path: Path) -> None:
    icons_dir = tmp_path / ".icons"
    _write_svg(icons_dir / "fontawesome" / "solid" / "note-sticky.svg")
    registry = build_icon_registry([str(icons_dir)])
    config = {"note": "/FontAwesome/Solid/Note-Sticky/"}
    assert admonition_icon_svg("note", config, registry) is not None

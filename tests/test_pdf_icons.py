# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from prodockit.pdf.icons import (
    ADMONITION_ACCENT_COLORS,
    admonition_icon_svg,
    build_icon_registry,
    discover_icon_dirs,
)


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


def test_build_icon_registry_derived_short_key_keeps_the_first_dirs_icon(tmp_path: Path) -> None:
    """The one explicit behavioural claim in build_icon_registry's own
    docstring - "earlier entries win on key collision" - applies to the
    *derived* short-form keys (via `if key not in registry`), confirmed
    directly here with two dirs whose icons share a derived
    "fontawesome-note-sticky" short key (same first/last path segments,
    different middle segment) but different full slugs."""
    first_dir = tmp_path / "first" / ".icons"
    second_dir = tmp_path / "second" / ".icons"
    _write_svg(first_dir / "fontawesome" / "solid" / "note-sticky.svg", fill="red")
    _write_svg(second_dir / "fontawesome" / "regular" / "note-sticky.svg", fill="blue")

    registry = build_icon_registry([str(first_dir), str(second_dir)])

    with open(registry["fontawesome-note-sticky"], encoding="utf-8") as f:
        assert "red" in f.read()


def test_build_icon_registry_primary_slug_key_is_overwritten_by_a_later_dir(
    tmp_path: Path,
) -> None:
    """Unlike the derived short forms above, the *primary* hyphen_slug key
    is unconditionally (re)written each time it's seen (see
    build_icon_registry's own docstring) - a later dir's exact same icon
    overwrites an earlier one for that one key, the opposite of the
    "earlier wins" claim that only applies to the derived forms."""
    first_dir = tmp_path / "first" / ".icons"
    second_dir = tmp_path / "second" / ".icons"
    _write_svg(first_dir / "note.svg", fill="red")
    _write_svg(second_dir / "note.svg", fill="blue")

    registry = build_icon_registry([str(first_dir), str(second_dir)])

    with open(registry["note"], encoding="utf-8") as f:
        assert "blue" in f.read()


def test_discover_icon_dirs_finds_project_local_dirs_in_priority_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "overrides" / ".icons").mkdir(parents=True)
    (tmp_path / ".icons").mkdir()
    (tmp_path / "docs" / ".icons").mkdir(parents=True)

    dirs = discover_icon_dirs("docs")

    assert dirs[:3] == [
        str(tmp_path / "overrides" / ".icons"),
        str(tmp_path / ".icons"),
        str(tmp_path / "docs" / ".icons"),
    ]


def test_discover_icon_dirs_returns_empty_when_nothing_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real running environment's own site-packages (e.g. zensical's
    bundled templates/.icons) would otherwise leak into this result, so
    site's own lookups are stubbed out here to isolate the project-local
    (docs_dir/overrides/venv) discovery this test actually means to
    cover."""
    import site

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(site, "getsitepackages", lambda: [], raising=False)
    monkeypatch.setattr(site, "getusersitepackages", lambda: "", raising=False)

    assert discover_icon_dirs("docs") == []

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import markdown
import pytest

import zendoc._zensical as zendoc_zensical
from zendoc.headings import HeadingsExtension, prescan
from zendoc.util import DuplicateIdError, IdRegistry


def _convert(text: str, registry: IdRegistry, source: str) -> str:
    md = markdown.Markdown(
        extensions=["attr_list", HeadingsExtension(registry=registry, source=source)]
    )
    return md.convert(text)


def test_heading_gets_an_id_and_is_registered() -> None:
    registry = IdRegistry()
    html = _convert("# Introduction\n", registry, "intro.md")
    assert 'id="introduction"' in html
    record = registry.get("introduction")
    assert record is not None
    assert record.source == "intro.md"
    assert record.level == 1
    assert record.text == "Introduction"
    assert record.number == "1"


def test_nested_headings_get_hierarchical_numbers() -> None:
    registry = IdRegistry()
    _convert("# Chapter\n\n## Setup\n\n## Usage\n\n# Next Chapter\n", registry, "doc.md")
    assert registry.get("chapter").number == "1"  # type: ignore[union-attr]
    assert registry.get("setup").number == "1.1"  # type: ignore[union-attr]
    assert registry.get("usage").number == "1.2"  # type: ignore[union-attr]
    assert registry.get("next-chapter").number == "2"  # type: ignore[union-attr]


def test_unnumbered_heading_has_no_number_but_gets_an_id() -> None:
    registry = IdRegistry()
    _convert("# Cover Page {: .unnumbered }\n\n# Introduction\n", registry, "doc.md")
    assert registry.get("cover-page").number is None  # type: ignore[union-attr]
    # unnumbered heading doesn't consume a counter slot
    assert registry.get("introduction").number == "1"  # type: ignore[union-attr]


def test_explicit_id_is_respected() -> None:
    registry = IdRegistry()
    _convert("# Introduction {: #custom-id }\n", registry, "intro.md")
    assert registry.get("custom-id") is not None
    assert registry.get("introduction") is None


def test_shared_registry_across_sources() -> None:
    registry = IdRegistry()
    _convert("# Introduction\n", registry, "intro.md")
    _convert("# Setup\n", registry, "setup.md")
    assert registry.get("introduction").source == "intro.md"  # type: ignore[union-attr]
    assert registry.get("setup").source == "setup.md"  # type: ignore[union-attr]


def test_duplicate_id_across_sources_raises() -> None:
    registry = IdRegistry()
    _convert("# Introduction\n", registry, "intro.md")
    with pytest.raises(DuplicateIdError):
        _convert("# Introduction\n", registry, "other.md")


def test_rebuilding_same_source_does_not_raise() -> None:
    registry = IdRegistry()
    _convert("# Introduction\n", registry, "intro.md")
    _convert("# Introduction\n", registry, "intro.md")
    assert registry.get("introduction").source == "intro.md"  # type: ignore[union-attr]


def test_stale_heading_cleared_on_rebuild() -> None:
    registry = IdRegistry()
    _convert("# Old Title\n", registry, "intro.md")
    _convert("# New Title\n", registry, "intro.md")
    assert registry.get("old-title") is None
    new_title = registry.get("new-title")
    assert new_title is not None
    assert new_title.source == "intro.md"


def test_reuses_callers_own_toc_config() -> None:
    registry = IdRegistry()
    md = markdown.Markdown(
        extensions=[
            "toc",
            HeadingsExtension(registry=registry, source="intro.md"),
        ],
        extension_configs={"toc": {"permalink": True}},
    )
    html = md.convert("# Introduction\n")
    assert "headerlink" in html
    assert registry.get("introduction") is not None


def test_entry_point_name_resolves() -> None:
    md = markdown.Markdown(extensions=["zendoc.headings"])
    assert md.convert("# Introduction\n") == (
        '<h1 id="introduction">Introduction</h1>'
    )


def test_prescan_wrapper_delegates_to_the_internal_nav_prescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """zendoc.headings.prescan() is the public seam a consuming project's
    own build tooling (e.g. a template macro emitting a matching CSS
    counter-reset override) uses to look up the same start-counts/appendix-
    letters HeadingsExtension itself computes for numbering="continuous"."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n", encoding="utf-8")
    (docs_dir / "appendix.md").write_text(
        "---\nis_appendix: true\n---\n\n# Appendix\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        zendoc_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page1.md", "appendix.md"]),
    )
    start_counts, appendix_letters = prescan()  # type: ignore[misc]
    assert start_counts == {"page1.md": 0}
    assert appendix_letters == {"appendix.md": "A"}


def test_prescan_wrapper_returns_none_outside_zensical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zendoc_zensical, "nav_pages", lambda: None)
    assert prescan() is None

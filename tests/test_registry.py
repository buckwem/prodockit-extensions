# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown
import pytest

from zendoc import DuplicateIdError, IdRegistry
from zendoc.extension import ZendocExtension


def _convert(text: str, registry: IdRegistry, source: str) -> str:
    md = markdown.Markdown(
        extensions=["attr_list", ZendocExtension(registry=registry, source=source)]
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
            ZendocExtension(registry=registry, source="intro.md"),
        ],
        extension_configs={"toc": {"permalink": True}},
    )
    html = md.convert("# Introduction\n")
    assert "headerlink" in html
    assert registry.get("introduction") is not None

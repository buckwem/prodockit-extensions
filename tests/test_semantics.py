# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Shared semantics retain their behaviour without a renderer or global state."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from prodockit.semantics import (
    PageCollector,
    PageContext,
    PageOutline,
    continuous_numbering,
    resolve_reference,
)
from prodockit.util import DuplicateIdError, IdRegistry


def test_core_runs_with_renderers_and_legacy_adapters_unavailable(tmp_path: Path) -> None:
    code = """
import importlib.abc
import sys

class BlockRenderers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ('markdown', 'zensical', 'prodockit._zensical', 'prodockit._zensical_page_context',
                   'prodockit.headings', 'prodockit.refs', 'prodockit.project_config')
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('semantic core tried to import ' + fullname)

sys.meta_path.insert(0, BlockRenderers())
from prodockit.semantics import PageCollector, PageContext, resolve_reference
from prodockit.util import IdRegistry

registry = IdRegistry()
page = PageCollector(PageContext('guide/setup.md', start_count=2), registry)
page.heading('setup', 1, 'Setup')
page.caption('figure-caption', 'diagram', 'A diagram')
reference = resolve_reference(PageContext('intro/index.md'), registry, 'diagram')
assert (reference.text, reference.href) == ('Figure 3.1', '../guide/setup.md#diagram')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("appendix", [None, "B"])
def test_numbering_and_reference_labels_preserve_authored_semantics(appendix: str | None) -> None:
    registry = IdRegistry()
    collector = PageCollector(PageContext("guide.md", 2, appendix), registry)
    chapter = appendix or "3"
    cover = collector.heading("cover", 1, "Cover", unnumbered=True)
    heading = collector.heading("chapter", 1, "Café & tea")
    detail = collector.heading("detail", 3, "Detail")
    collector.caption("figure-caption", "__figure-caption_1", "Unlabelled")
    figure = collector.caption("figure-caption", "diagram", "Diagram words")
    table = collector.caption("table-caption", "results", "Results words")
    assert [cover.number, heading.number, detail.number] == [None, chapter, f"{chapter}.1.1"]
    assert figure is not None and figure.number == f"Figure {chapter}.2"
    assert table is not None and table.number == f"Table {chapter}.1"
    assert registry.get("__figure-caption_1") is None
    for target, expected in (
        ("cover", "Cover"), ("chapter", f"{chapter} Café & tea"),
        ("diagram", f"Figure {chapter}.2"), ("results", f"Table {chapter}.1"),
    ):
        reference = resolve_reference(PageContext("nested/page.md"), registry, target)
        assert reference is not None
        assert (reference.text, reference.href) == (expected, f"../guide.md#{target}")


def test_recollection_and_collision_policy_keep_registries_scoped() -> None:
    registry = IdRegistry()
    original = PageCollector(PageContext("first.md"), registry)
    original.heading("shared", 1, "First")
    original.heading("removed", 2, "Removed")
    with pytest.raises(DuplicateIdError):
        PageCollector(PageContext("second.md"), registry).heading("shared", 1, "Second")
    PageCollector(PageContext("second.md"), registry, strict=False).heading("shared", 1, "Second")
    assert registry.get("shared").source == "first.md"
    replacement = PageCollector(PageContext("first.md", 4), registry)
    replacement.heading("new", 1, "Replacement")
    assert resolve_reference(PageContext("first.md"), registry, "removed") is None
    assert resolve_reference(PageContext("first.md"), registry, "shared") is None
    reference = resolve_reference(PageContext("first.md"), registry, "new")
    assert reference is not None and (reference.text, reference.href) == ("5 Replacement", "#new")
    other_project = IdRegistry()
    PageCollector(PageContext("first.md"), other_project).heading("new", 1, "Independent")
    assert registry.get("new").number == "5"
    assert other_project.get("new").number == "1"


def test_chapter_plan_counts_h1s_and_preserves_appendix_order() -> None:
    starts, appendices = continuous_numbering([
        PageOutline("cover.md", 0), PageOutline("chapters.md", 2),
        PageOutline("annex.md", 3, True), PageOutline("later.md", 1),
        PageOutline("glossary.md", 1, True),
    ])
    assert starts == {"cover.md": 0, "chapters.md": 0, "later.md": 2}
    assert appendices == {"annex.md": "A", "glossary.md": "B"}

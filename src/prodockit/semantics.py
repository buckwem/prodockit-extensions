# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Heading and reference semantics with explicit inputs and no renderer context.

Adapters own parsing, source discovery and output. These rules operate only on
collected values and caller-owned registries, so legacy rendering and portable
preparation can use the same numbering and reference resolution.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from prodockit.util import HeadingRecord, IdRegistry, cross_page_href

CAPTION_LEVEL = 0
CAPTION_LABELS = {"figure-caption": "Figure", "table-caption": "Table"}


@dataclass(frozen=True)
class PageContext:
    """Original page identity and the numbering seed supplied by its caller."""

    source: str
    start_count: int = 0
    appendix_letter: str | None = None


@dataclass(frozen=True)
class PageOutline:
    """The facts needed to allocate chapters in navigation order."""

    source: str
    numbered_h1s: int
    is_appendix: bool = False


def continuous_numbering(
    pages: Iterable[PageOutline],
) -> tuple[dict[str, int], dict[str, str]]:
    """Allocate page seeds; appendix pages do not consume numeric chapters.

    Keep the legacy letter allocation here. Adapters can impose a narrower
    supported range, as portable preparation currently does for A–Z.
    """
    starts: dict[str, int] = {}
    appendices: dict[str, str] = {}
    running_total = 0
    appendix_count = 0
    for page in pages:
        if page.is_appendix:
            appendices[page.source] = chr(ord("A") + appendix_count)
            appendix_count += 1
        else:
            starts[page.source] = running_total
            running_total += page.numbered_h1s
    return starts, appendices


class NumberingState:
    """One page's heading and caption counters, independent of its parser."""

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.counters = [context.start_count, 0, 0, 0, 0, 0]
        self.captions = dict.fromkeys(CAPTION_LABELS, 0)

    def heading(self, level: int, *, unnumbered: bool = False) -> str | None:
        if not 1 <= level <= 6:
            raise ValueError(f"invalid heading level: {level}")
        if unnumbered:
            return None
        # Backfill skipped ancestors, preserving a supplied chapter seed.
        for shallower in range(level - 1):
            if self.counters[shallower] == 0:
                self.counters[shallower] = 1
        self.counters[level - 1] += 1
        for deeper in range(level, 6):
            self.counters[deeper] = 0
        first = self.context.appendix_letter
        if first is None:
            first = str(self.counters[0])
        return ".".join([first] + [str(c) for c in self.counters[1:level]])

    def caption(self, kind: str) -> str:
        self.captions[kind] += 1
        return self.caption_label(kind)

    def caption_label(self, kind: str) -> str:
        """The current label after registering a caption of this kind."""
        chapter = self.context.appendix_letter
        if chapter is None:
            chapter = str(self.counters[0] or 1)
        return f"{CAPTION_LABELS[kind]} {chapter}.{self.captions[kind]}"


class PageCollector:
    """Register one page's targets using the caller's collision policy.

    Recollecting a page replaces its old targets. No registry or numbering
    state is global, and registration retains IdRegistry's existing rules.
    """

    def __init__(self, context: PageContext, registry: IdRegistry, *, strict: bool = True) -> None:
        self.context = context
        self.registry = registry
        self.strict = strict
        self.numbering = NumberingState(context)
        registry.clear_source(context.source)

    def _register(self, ident: str, level: int, text: str, number: str | None) -> HeadingRecord:
        record = HeadingRecord(self.context.source, ident, level, text, number)
        self.registry.register(
            source=record.source, id=record.id, level=record.level, text=record.text,
            number=record.number, strict=self.strict,
        )
        return record

    def heading(
        self, ident: str, level: int, text: str, *, unnumbered: bool = False
    ) -> HeadingRecord:
        return self._register(
            ident, level, text, self.numbering.heading(level, unnumbered=unnumbered)
        )

    def caption(self, kind: str, ident: str | None, text: str) -> HeadingRecord | None:
        number = self.numbering.caption(kind)
        # Automatically generated caption IDs are page-local implementation
        # details. They advance the counter but are not cross-page targets.
        if not ident or re.fullmatch(rf"__{re.escape(kind)}_\d+(?:_\d+)*", ident):
            return None
        return self._register(ident, CAPTION_LEVEL, text, number)


@dataclass(frozen=True)
class ResolvedReference:
    target: HeadingRecord
    text: str
    href: str


def resolve_reference(
    context: PageContext, registry: IdRegistry, target_id: str,
) -> ResolvedReference | None:
    """Resolve a target; adapters decide how to report an unknown reference."""
    target = registry.get(target_id)
    if target is None:
        return None
    if target.level == CAPTION_LEVEL and target.number:
        text = target.number
    else:
        text = f"{target.number} {target.text}" if target.number else target.text
    return ResolvedReference(
        target, text, cross_page_href(target.source, context.source, target_id)
    )

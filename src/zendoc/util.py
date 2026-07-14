# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Shared data structures used by more than one zendoc extension.

A single :class:`IdRegistry` instance is meant to be shared across every
source document in a build (one extension instance per document, e.g. one
:class:`~zendoc.headings.HeadingsExtension` call per page), so that
:mod:`zendoc.refs` (and a future citation extension) can resolve an id to
the document, heading, and current section number that defines it,
regardless of which document is currently being converted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeadingRecord:
    source: str
    id: str
    level: int
    text: str
    number: str | None = None


class DuplicateIdError(ValueError):
    """Raised when the same id is registered from two different sources."""


class IdRegistry:
    def __init__(self) -> None:
        self._headings: dict[str, HeadingRecord] = {}

    def register(
        self, source: str, id: str, level: int, text: str, number: str | None = None
    ) -> None:
        existing = self._headings.get(id)
        if existing is not None and existing.source != source:
            raise DuplicateIdError(
                f"heading id {id!r} is already registered from "
                f"{existing.source!r}; cannot also register it from {source!r}"
            )
        self._headings[id] = HeadingRecord(
            source=source, id=id, level=level, text=text, number=number
        )

    def get(self, id: str) -> HeadingRecord | None:
        return self._headings.get(id)

    def __contains__(self, id: str) -> bool:
        return id in self._headings

    def clear_source(self, source: str) -> None:
        """Drops every entry previously registered from source.

        Needed so re-converting the same document (e.g. a live-reload dev
        server) can't leave a stale id behind after a heading's text - and
        therefore its slug - changes between builds.
        """
        for stale_id in [k for k, v in self._headings.items() if v.source == source]:
            del self._headings[stale_id]

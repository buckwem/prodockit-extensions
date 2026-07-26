# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Shared data structures used by more than one prodockit extension.

A single :class:`IdRegistry` instance is meant to be shared across every
source document in a build (one extension instance per document, e.g. one
:class:`~prodockit.headings.HeadingsExtension` call per page), so that
:mod:`prodockit.refs` can resolve an id to the document, heading, and current
section number that defines it, regardless of which document is currently
being converted. :class:`CitationRegistry` (for :mod:`prodockit.citations`'
citation keys) and :class:`GlossaryRegistry` (for :mod:`prodockit.glossary`'s
terms) are the same idea for their own kind of id - each its own separate
registry/namespace, not merged with headings' ids or each other.
"""

from __future__ import annotations

import logging
import posixpath
from dataclasses import dataclass

_log = logging.getLogger("prodockit")


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
        self._preseeded: dict[str, HeadingRecord] = {}

    def register(
        self,
        source: str,
        id: str,
        level: int,
        text: str,
        number: str | None = None,
        strict: bool = True,
    ) -> None:
        """Registers a heading, keyed by id.

        A duplicate id from a *different* source is a `DuplicateIdError`
        when `strict` (the default) - the right behaviour for a registry
        a caller deliberately shares across pages, where an unexpected
        collision usually means two headings genuinely need distinguishing
        (e.g. via an explicit id). When `strict` is False, a collision is
        logged and the earlier registration wins instead of raising - used
        for registry sharing this package sets up automatically (see
        prodockit.headings' Zensical auto-detection), where crashing an entire
        site build over two unrelated pages both having, say, an "Overview"
        heading would be a worse outcome than an unresolved cross-reference.
        """
        existing = self._headings.get(id)
        if existing is not None and existing.source != source:
            if strict:
                raise DuplicateIdError(
                    f"heading id {id!r} is already registered from "
                    f"{existing.source!r}; cannot also register it from {source!r}"
                )
            _log.warning(
                "heading id %r from %r collides with an existing one from %r - "
                "keeping the first; give one of them an explicit id to disambiguate",
                id,
                source,
                existing.source,
            )
            return
        self._headings[id] = HeadingRecord(
            source=source, id=id, level=level, text=text, number=number
        )
        # A real registration always supersedes a provisional preseed()
        # for the same id - no collision check needed, since preseed data
        # was only ever a stand-in for this.
        self._preseeded.pop(id, None)

    def preseed(
        self,
        source: str,
        id: str,
        level: int,
        text: str,
        number: str | None = None,
    ) -> None:
        """Provisionally records a heading's id/number/defining page ahead
        of that page actually being converted - used by prodockit.headings'
        Zensical pre-scan so a `\\ref{id}` referencing a heading on a page
        not yet processed in this build pass (or a page whose real
        registration this rendering context never sees at all - Zensical
        doesn't guarantee every page renders in one shared Python context,
        see prodockit-extensions#54) still resolves to the right number and
        cross-page link.

        Doesn't participate in collision checking at all: it's advisory
        data, always superseded automatically once the real page registers
        this id via `register()`. A repeat `preseed()` call for an id
        that's already been preseeded is a no-op - the first scan wins,
        consistent with how a real duplicate is handled.
        """
        if id not in self._preseeded:
            self._preseeded[id] = HeadingRecord(
                source=source, id=id, level=level, text=text, number=number
            )

    def get(self, id: str) -> HeadingRecord | None:
        return self._headings.get(id) or self._preseeded.get(id)

    def __contains__(self, id: str) -> bool:
        return id in self._headings or id in self._preseeded

    def clear_source(self, source: str) -> None:
        """Drops every entry previously registered from source.

        Needed so re-converting the same document (e.g. a live-reload dev
        server) can't leave a stale id behind after a heading's text - and
        therefore its slug - changes between builds.
        """
        for stale_id in [k for k, v in self._headings.items() if v.source == source]:
            del self._headings[stale_id]

    def clear_preseeded(self) -> None:
        """Drops every provisional `preseed()` entry, leaving real
        registrations untouched.

        Needed because the numbers a pre-scan computes depend on the
        numbering configuration it was given, and prodockit.refs may trigger
        a first pre-scan through a *default* HeadingsExtension it creates
        itself (extension order isn't guaranteed - see
        prodockit.refs.RefsExtension.extendMarkdown) before the project's
        own configured instance gets to run. The configured instance then
        needs to replace those provisional numbers, not be blocked by
        them, since `preseed()` itself is deliberately first-wins.
        """
        self._preseeded.clear()


@dataclass(frozen=True)
class CitationRecord:
    source: str
    id: str
    text: str


class CitationRegistry:
    """Registry of citation keys, defined once (e.g. on a references page)
    and looked up by :mod:`prodockit.citations`' ``\\citeref{id}`` syntax from
    anywhere in a build. Same shape and collision semantics as
    :class:`IdRegistry`, kept as a separate registry/id-namespace rather
    than merged with it - a citation key isn't a heading, and the two
    shouldn't collide with each other just because they happen to share a
    string, the same way LaTeX keeps \\label/\\ref and \\bibitem/\\cite in
    separate namespaces.
    """

    def __init__(self) -> None:
        self._citations: dict[str, CitationRecord] = {}
        self._preseeded: dict[str, CitationRecord] = {}

    def register(self, source: str, id: str, text: str, strict: bool = True) -> None:
        existing = self._citations.get(id)
        if existing is not None and existing.source != source:
            if strict:
                raise DuplicateIdError(
                    f"citation key {id!r} is already registered from "
                    f"{existing.source!r}; cannot also register it from {source!r}"
                )
            _log.warning(
                "citation key %r from %r collides with an existing one from %r - "
                "keeping the first; give one of them a distinct key to disambiguate",
                id,
                source,
                existing.source,
            )
            return
        self._citations[id] = CitationRecord(source=source, id=id, text=text)
        # A real registration always supersedes a provisional preseed()
        # for the same id - no collision check needed, since preseed data
        # was only ever a stand-in for this.
        self._preseeded.pop(id, None)

    def preseed(self, source: str, id: str, text: str) -> None:
        """Provisionally records a citation's display text and defining
        page ahead of that page actually being converted - used by
        prodockit.citations' Zensical pre-scan to unblock a `\\citeref{id}` that
        cites a source defined on a page not yet processed in this build
        pass (e.g. a references page at the end of nav, cited from an early
        chapter - the classic "cited before defined" ordering problem
        `zensical build`'s single, one-shot process can't otherwise
        resolve). `source` matters here, not just `text`: it's what lets a
        citation resolve to the correct cross-page link before the real
        page has registered anything.

        Doesn't participate in collision checking at all: it's advisory
        data, always superseded automatically once the real page registers
        this id via `register()`. A repeat `preseed()` call for an id
        that's already been preseeded is a no-op - the first scan wins,
        consistent with how a real duplicate is handled.
        """
        if id not in self._preseeded:
            self._preseeded[id] = CitationRecord(source=source, id=id, text=text)

    def clear_preseeded(self) -> None:
        """Drops every provisional `preseed()` entry, leaving real
        registrations untouched.

        Lets a re-scan rebuild the provisional set from scratch rather than
        being blocked by its own previous results - `preseed()` is
        deliberately first-wins, so without this a definition edited (or
        deleted) on disk would keep resolving to its original value for the
        life of the process, which is exactly what goes wrong under
        `zensical serve`'s live-reload (see issue #99).
        """
        self._preseeded.clear()

    def get(self, id: str) -> CitationRecord | None:
        return self._citations.get(id) or self._preseeded.get(id)

    def __contains__(self, id: str) -> bool:
        return id in self._citations or id in self._preseeded

    def clear_source(self, source: str) -> None:
        """Drops every entry previously registered from source - see
        IdRegistry.clear_source for why this matters."""
        for stale_id in [k for k, v in self._citations.items() if v.source == source]:
            del self._citations[stale_id]


@dataclass(frozen=True)
class GlossaryRecord:
    source: str
    id: str
    text: str


class GlossaryRegistry:
    """Registry of glossary/acronym terms, defined once (e.g. on an
    Acronyms or Glossary page) and looked up by :mod:`prodockit.glossary`'s
    ``\\gls{id}`` syntax from anywhere in a build. Same shape, collision
    semantics, and preseed behaviour as :class:`CitationRegistry` - kept as
    its own separate registry/id-namespace rather than merged with it, the
    same way a citation key and a glossary term aren't the same kind of
    thing even though both are just "an id with some text attached".
    """

    def __init__(self) -> None:
        self._terms: dict[str, GlossaryRecord] = {}
        self._preseeded: dict[str, GlossaryRecord] = {}

    def register(self, source: str, id: str, text: str, strict: bool = True) -> None:
        existing = self._terms.get(id)
        if existing is not None and existing.source != source:
            if strict:
                raise DuplicateIdError(
                    f"glossary term {id!r} is already registered from "
                    f"{existing.source!r}; cannot also register it from {source!r}"
                )
            _log.warning(
                "glossary term %r from %r collides with an existing one from %r - "
                "keeping the first; give one of them a distinct id to disambiguate",
                id,
                source,
                existing.source,
            )
            return
        self._terms[id] = GlossaryRecord(source=source, id=id, text=text)
        # A real registration always supersedes a provisional preseed()
        # for the same id - no collision check needed, since preseed data
        # was only ever a stand-in for this.
        self._preseeded.pop(id, None)

    def preseed(self, source: str, id: str, text: str) -> None:
        """Provisionally records a term's display text and defining page
        ahead of that page actually being converted - see
        CitationRegistry.preseed for why this matters."""
        if id not in self._preseeded:
            self._preseeded[id] = GlossaryRecord(source=source, id=id, text=text)

    def clear_preseeded(self) -> None:
        """Drops every provisional `preseed()` entry, leaving real
        registrations untouched - see CitationRegistry.clear_preseeded."""
        self._preseeded.clear()

    def get(self, id: str) -> GlossaryRecord | None:
        return self._terms.get(id) or self._preseeded.get(id)

    def __contains__(self, id: str) -> bool:
        return id in self._terms or id in self._preseeded

    def clear_source(self, source: str) -> None:
        """Drops every entry previously registered from source - see
        IdRegistry.clear_source for why this matters."""
        for stale_id in [k for k, v in self._terms.items() if v.source == source]:
            del self._terms[stale_id]


def cross_page_href(record_source: str, current_source: str, id: str) -> str:
    """Builds the href for a resolved prodockit.refs/prodockit.citations link.

    A bare ``#id`` fragment only navigates within the *current* page - on a
    multi-page site, a link to a heading/citation defined on a *different*
    page needs a real relative link to that page, e.g. ``other.md#id``.
    Zensical (``zensical.extensions.links.LinksTreeprocessor``, always
    present on every page it builds) already rewrites a relative ``.md``
    link with a fragment into the correct clean URL for the *current*
    page - the same rewriting a hand-typed ``[text](other.md#id)`` link
    already gets - so emitting that same relative form here, rather than a
    bare fragment, is what makes a cross-page reference/citation actually
    resolve on the built website (not just in a single-document PDF, where
    every id lives on the same page once every source is concatenated).

    `record_source`/`current_source` are both docs-dir-relative paths (e.g.
    ``"references.md"``, ``"starthere/customise.md"``) - a relative link
    written on the current page must be relative to *its own* directory,
    not to the docs root, so a ``record_source`` of ``"references.md"``
    needs `posixpath.relpath`'d into ``"../references.md"`` when
    `current_source` is one directory deeper (e.g.
    ``"starthere/customise.md"``) - exactly the adjustment a hand-typed
    relative link between the same two pages would need too.
    """
    if record_source == current_source:
        return f"#{id}"
    current_dir = posixpath.dirname(current_source)
    relative_source = (
        posixpath.relpath(record_source, current_dir) if current_dir else record_source
    )
    return f"{relative_source}#{id}"

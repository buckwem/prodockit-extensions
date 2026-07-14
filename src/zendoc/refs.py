# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc.refs: ``\\ref{id}`` section cross-reference syntax, resolving to
the referenced heading's current section number - similar in spirit to
LaTeX's ``\\ref``. Builds on the id registry from :mod:`zendoc.headings`,
which is auto-enabled with matching defaults if not already present.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from zendoc.headings import HeadingsExtension, _share_registry
from zendoc.util import IdRegistry

REF_RE = r"\\ref\{([^}\s]+)\}"


class RefInlineProcessor(InlineProcessor):
    """Matches ``\\ref{id}`` and emits an unresolved placeholder ``<a>``
    carrying the referenced id in a ``data-zendoc-ref`` attribute.

    Registered at a low inline-pattern priority so it runs after 'backtick'
    (190) and 'escape' (180) - meaning inline code spans are already stashed
    out of reach by the time this pattern runs, so ``\\ref{...}`` shown as
    literal example syntax inside `` `code` `` survives untouched, the same
    protection fenced code blocks already get from being stashed even
    earlier, during preprocessing.

    The placeholder can't be resolved to a real section number here: inline
    patterns run before the current document's own headings have been
    numbered (see HeadingsTreeprocessor, priority 4, which runs after this
    pattern's containing 'inline' treeprocessor, priority 20) - resolution
    happens later, in RefResolverTreeprocessor.
    """

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("a")
        el.set("data-zendoc-ref", m.group(1))
        el.set("class", "zendoc-ref")
        return el, m.start(0), m.end(0)


class RefResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder ``<a data-zendoc-ref="id">`` elements left by
    :class:`RefInlineProcessor` to the referenced heading's section number,
    once the current document's own headings have been numbered.

    Runs at a lower priority than 'zendoc-headings' (4) so every heading in
    *this* document - including one defined further down the page than
    where it's referenced - is already registered by the time resolution
    happens. A reference to a heading in a document not yet processed in
    this build (e.g. a later page in a multi-page site) can't be resolved
    yet either; both cases fall back to `unresolved`, the same way an
    undefined LaTeX \\ref shows "??" until a later compilation pass.
    """

    def __init__(self, md: Markdown, registry: IdRegistry, unresolved: str = "??") -> None:
        super().__init__(md)
        self.registry = registry
        self.unresolved = unresolved

    def run(self, root: etree.Element) -> None:
        for el in root.iter("a"):
            ref_id = el.get("data-zendoc-ref")
            if ref_id is None:
                continue
            del el.attrib["data-zendoc-ref"]
            record = self.registry.get(ref_id)
            if record is None or record.number is None:
                el.text = self.unresolved
                el.set("class", "zendoc-ref zendoc-ref-unresolved")
                if record is not None:
                    # Known heading, just unnumbered (e.g. {: .unnumbered }) -
                    # still a valid link target, unlike a genuinely unknown id.
                    el.set("href", f"#{ref_id}")
            else:
                el.text = record.number
                el.set("href", f"#{ref_id}")


class RefsExtension(Extension):
    """Python-Markdown extension providing the ``\\ref{id}`` syntax."""

    def __init__(self, **kwargs: object) -> None:
        # See HeadingsExtension for why this is popped rather than run
        # through Extension's own config/setConfig machinery. None here
        # means "discover the registry from a sibling HeadingsExtension",
        # not "use an empty registry" - that distinction can't be made once
        # a value has round-tripped through setConfig.
        registry = kwargs.pop("registry", None)
        self.registry: IdRegistry | None = registry if isinstance(registry, IdRegistry) else None
        self.config = {
            "unresolved": [
                "??",
                "Text rendered by \\ref{id} when id doesn't resolve to a "
                "numbered heading - unknown id, or a heading marked "
                "unnumbered.",
            ],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        registry = self.registry
        if registry is None:
            # Order-independent: if zendoc.headings already ran on this page
            # (in either list order), it stashed its registry on md - reuse
            # that directly rather than searching md.registeredExtensions,
            # which only works if headings happened to run first.
            existing = getattr(md, "zendoc_registry", None)
            if isinstance(existing, IdRegistry):
                registry = existing
            else:
                headings_ext = next(
                    (ext for ext in md.registeredExtensions if isinstance(ext, HeadingsExtension)),
                    None,
                )
                if headings_ext is None:
                    headings_ext = HeadingsExtension()
                    headings_ext.extendMarkdown(md)
                registry = headings_ext.registry
        registry = _share_registry(md, registry)
        unresolved: str = self.getConfig("unresolved")
        md.inlinePatterns.register(
            RefInlineProcessor(REF_RE, md),
            "zendoc-ref",
            45,
        )
        md.treeprocessors.register(
            RefResolverTreeprocessor(md, registry, unresolved),
            "zendoc-ref-resolver",
            2,
        )


def makeExtension(**kwargs: object) -> RefsExtension:
    return RefsExtension(**kwargs)

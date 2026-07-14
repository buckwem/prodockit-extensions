# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc.headings: gives every heading an id and a hierarchical section
number, recorded in a shared :class:`~zendoc.util.IdRegistry` that other
zendoc extensions (currently :mod:`zendoc.refs`) look entries up in.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.toc import TocExtension
from markdown.treeprocessors import Treeprocessor

from zendoc._zensical import page_source, share
from zendoc.util import IdRegistry

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _slugify(text: str) -> str:
    """Minimal fallback slug, used only when 'toc' hasn't already assigned an
    id. Enable Python-Markdown's own 'toc' extension for slugs that match the
    rest of a 'toc'-rendered document exactly (unicode handling, custom
    separators, etc.) - this fallback exists only so the registry still works
    if a caller genuinely doesn't want a table of contents.
    """
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", slug)


# Shared across every page of a single Zensical build (one Python process per
# `zensical build`/`zensical serve` invocation) - see zendoc._zensical and
# HeadingsExtension.extendMarkdown. Never touched unless Zensical's per-page
# context is actually detected, so it has no effect under any other tool, or
# on a caller who passes their own explicit registry/source.
_ZENSICAL_SHARED_REGISTRY = IdRegistry()


class HeadingsTreeprocessor(Treeprocessor):
    """Records every h1-h6 element's id, and its hierarchical section number,
    in a shared :class:`IdRegistry`, keyed by the current document's source
    name.

    Numbering is per-document: h1 is a top-level counter, h2 nests under the
    nearest preceding h1 ("1.1", "1.2", ...), and so on through h6 - reset
    from scratch on every call, so reordering headings within a document
    always produces correct numbers on the next build. A heading with an
    ``unnumbered`` class (e.g. via ``# Title {: .unnumbered }``) is still
    given an id but excluded from numbering - its counter position is
    skipped entirely - so its registered ``number`` is ``None``.

    Runs at a lower priority than 'toc' (registered at 5) so it always reads
    the final id 'toc' assigned - including one already set explicitly via
    'attr_list' - rather than racing it.
    """

    def __init__(
        self, md: Markdown, registry: IdRegistry, source: str, strict: bool = True
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.strict = strict

    def run(self, root: etree.Element) -> None:
        self.registry.clear_source(self.source)
        counters = [0] * 6
        for el in root.iter():
            if el.tag not in HEADING_TAGS:
                continue
            text = "".join(el.itertext())
            heading_id = el.get("id")
            if not heading_id:
                heading_id = _slugify(text)
                el.set("id", heading_id)

            level = int(el.tag[1])
            classes = (el.get("class") or "").split()
            if "unnumbered" in classes:
                number = None
            else:
                counters[level - 1] += 1
                for deeper in range(level, 6):
                    counters[deeper] = 0
                number = ".".join(str(c) for c in counters[:level])

            self.registry.register(
                source=self.source,
                id=heading_id,
                level=level,
                text=text,
                number=number,
                strict=self.strict,
            )


class HeadingsExtension(Extension):
    """Python-Markdown extension assigning ids and section numbers to headings."""

    def __init__(self, **kwargs: object) -> None:
        # Popped rather than run through Extension's own config/setConfig:
        # that machinery bool-coerces any config value whose *current*
        # default is None (see markdown.util.parseBoolValue), which would
        # silently corrupt a real IdRegistry object passed in explicitly.
        registry = kwargs.pop("registry", None)
        self._registry_explicit = isinstance(registry, IdRegistry)
        self.registry: IdRegistry = (
            registry if isinstance(registry, IdRegistry) else IdRegistry()
        )
        self.config = {
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to scope this document's own entries in the registry.",
            ],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        # Heading ids are 'toc''s job (including respecting one 'attr_list'
        # already set) - reuse it rather than re-deriving slugs here, but
        # don't clobber a caller's own 'toc' config (e.g. permalink=True) if
        # they've already enabled it themselves.
        if "toc" not in md.treeprocessors:
            TocExtension().extendMarkdown(md)
        source: str = self.getConfig("source")
        registry = self.registry
        strict = True
        # Only kick in when the caller hasn't configured anything themselves
        # (an explicit registry and/or source means a deliberate multi-page
        # setup - see the docs - which should keep raising on a genuine
        # collision, not silently paper over it).
        if not self._registry_explicit and not source:
            detected_source = page_source(md)
            if detected_source is not None:
                source = detected_source
                registry = _ZENSICAL_SHARED_REGISTRY
                strict = False
        registry = share(md, "zendoc_registry", registry)
        self.registry = registry
        md.treeprocessors.register(
            HeadingsTreeprocessor(md, registry, source, strict=strict),
            "zendoc-headings",
            4,
        )


def makeExtension(**kwargs: object) -> HeadingsExtension:
    return HeadingsExtension(**kwargs)

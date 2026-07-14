# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.treeprocessors import Treeprocessor

from zendoc.registry import IdRegistry

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


class RegistryTreeprocessor(Treeprocessor):
    """Records every h1-h6 element's id, and its hierarchical section number,
    in a shared :class:`IdRegistry`, keyed by the current document's source
    name.

    Numbering is per-document: h1 is a top-level counter, h2 nests under the
    nearest preceding h1 ("1.1", "1.2", ...), and so on through h6 - reset
    from scratch on every call, so reordering headings within a document
    always produces correct numbers on the next build (see the ``\\ref{id}``
    syntax in :mod:`zendoc.inlinepatterns`, which depends on this). A heading
    with an ``unnumbered`` class (e.g. via ``# Title {: .unnumbered }``) is
    still given an id but excluded from numbering - its counter position is
    skipped entirely, matching zendoc-template's own cover-page convention -
    so its registered ``number`` is ``None``.

    Runs at a lower priority than 'toc' (registered at 5) so it always reads
    the final id 'toc' assigned - including one already set explicitly via
    'attr_list' - rather than racing it.
    """

    def __init__(self, md: Markdown, registry: IdRegistry, source: str) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source

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
            )


class RefResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder ``<a data-zendoc-ref="id">`` elements left by
    :class:`zendoc.inlinepatterns.RefInlineProcessor` to the referenced
    heading's section number, once the current document's own headings have
    been numbered.

    Runs at a lower priority than RegistryTreeprocessor (4) so every heading
    in *this* document - including one defined further down the page than
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

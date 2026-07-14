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
    """Records every h1-h6 element's id in a shared :class:`IdRegistry`,
    keyed by the current document's source name.

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
        for el in root.iter():
            if el.tag not in HEADING_TAGS:
                continue
            text = "".join(el.itertext())
            heading_id = el.get("id")
            if not heading_id:
                heading_id = _slugify(text)
                el.set("id", heading_id)
            self.registry.register(
                source=self.source,
                id=heading_id,
                level=int(el.tag[1]),
                text=text,
            )

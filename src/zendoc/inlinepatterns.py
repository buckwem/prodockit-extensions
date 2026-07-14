# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown.inlinepatterns import InlineProcessor

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
    numbered (see RegistryTreeprocessor, priority 4, which runs after this
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

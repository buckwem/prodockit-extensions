# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Python-Markdown extension entry point for zendoc.

Currently provides the id/anchor registry only (see zendoc-template#25):
every heading is given an id and recorded in a shared IdRegistry keyed by
`source`, so a later cross-reference/citation feature can resolve an id to
the document that defines it. The cross-reference and citation syntax itself
will be added as further Preprocessor/Treeprocessor/Postprocessor subclasses
registered here.
"""

from __future__ import annotations

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.toc import TocExtension

from zendoc.registry import IdRegistry
from zendoc.treeprocessors import RegistryTreeprocessor


class ZendocExtension(Extension):
    """Python-Markdown extension for section cross-references and citations."""

    def __init__(self, **kwargs: object) -> None:
        self.config = {
            "registry": [
                IdRegistry(),
                "Shared IdRegistry instance across every source document in a "
                "build. Defaults to a new, single-document registry.",
            ],
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
        registry: IdRegistry = self.getConfig("registry")
        source: str = self.getConfig("source")
        md.treeprocessors.register(
            RegistryTreeprocessor(md, registry, source),
            "zendoc-registry",
            4,
        )


def makeExtension(**kwargs: object) -> ZendocExtension:
    return ZendocExtension(**kwargs)

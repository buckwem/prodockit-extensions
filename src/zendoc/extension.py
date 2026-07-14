# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Python-Markdown extension entry point for zendoc.

Provides the id/anchor registry (see zendoc-template#25): every heading is
given an id and hierarchical section number, recorded in a shared
IdRegistry keyed by `source`; and the ``\\ref{id}`` cross-reference syntax
built on top of it, which resolves to the referenced heading's current
section number - similar in spirit to LaTeX's ``\\ref``. A future citation
feature will build on the same registry.
"""

from __future__ import annotations

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.toc import TocExtension

from zendoc.inlinepatterns import REF_RE, RefInlineProcessor
from zendoc.registry import IdRegistry
from zendoc.treeprocessors import RefResolverTreeprocessor, RegistryTreeprocessor


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
        # Heading ids are 'toc''s job (including respecting one 'attr_list'
        # already set) - reuse it rather than re-deriving slugs here, but
        # don't clobber a caller's own 'toc' config (e.g. permalink=True) if
        # they've already enabled it themselves.
        if "toc" not in md.treeprocessors:
            TocExtension().extendMarkdown(md)
        registry: IdRegistry = self.getConfig("registry")
        source: str = self.getConfig("source")
        unresolved: str = self.getConfig("unresolved")
        md.treeprocessors.register(
            RegistryTreeprocessor(md, registry, source),
            "zendoc-registry",
            4,
        )
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


def makeExtension(**kwargs: object) -> ZendocExtension:
    return ZendocExtension(**kwargs)

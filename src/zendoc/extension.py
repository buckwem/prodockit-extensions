# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Python-Markdown extension entry point for zendoc.

This module currently only wires up the standard Python-Markdown
``Extension`` scaffolding (see issue #25 in zendoc-template). The actual
cross-reference and citation processors will be added as
Preprocessor/Treeprocessor/Postprocessor subclasses registered here.
"""

from __future__ import annotations

from markdown import Markdown
from markdown.extensions import Extension


class ZendocExtension(Extension):
    """Python-Markdown extension for section cross-references and citations."""

    def __init__(self, **kwargs: object) -> None:
        self.config: dict[str, list[object]] = {}
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)


def makeExtension(**kwargs: object) -> ZendocExtension:
    return ZendocExtension(**kwargs)

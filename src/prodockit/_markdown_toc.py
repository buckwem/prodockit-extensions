# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Compatibility boundary for Python-Markdown's active TOC settings.

Python-Markdown documents its extension registries and the TOC extension's
``slugify`` and ``separator`` configuration, but it does not expose a public
method for another extension to retrieve the *resolved* values from an
already-configured TOC extension.  The current implementation stores them as
``slugify`` and ``sep`` on the registered TOC treeprocessor.

Prodockit needs those exact values when it pre-scans pages: deriving heading
ids with its own defaults would make cross-page references disagree with a
project that configured a custom TOC slugifier.  Keep that small translation
here so feature extensions consume the interface Prodockit actually needs and
do not understand Python-Markdown's processor representation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from markdown import Markdown


class MarkdownTocAPIError(RuntimeError):
    """The registered TOC processor no longer exposes its resolved settings."""


@dataclass(frozen=True)
class TocSlugging:
    """The resolved heading-id function and separator used by the TOC."""

    slugify: Callable[[str, str], str]
    separator: str


def toc_slugging(md: Markdown) -> TocSlugging | None:
    """Return the active TOC's resolved slugging settings.

    ``None`` means that no TOC processor is registered.  A registered
    processor with a changed representation is different: it raises
    :class:`MarkdownTocAPIError`, so callers cannot silently pre-scan pages
    with ids that differ from the ids created during conversion.
    """
    if "toc" not in md.treeprocessors:
        return None

    try:
        processor = md.treeprocessors["toc"]
        # The registry is typed as holding the public Treeprocessor base
        # class, which deliberately has neither TOC-specific attribute. The
        # getattr calls are the compatibility translation this module exists
        # to contain, not a typing workaround scattered through feature code.
        slugify = getattr(processor, "slugify")  # noqa: B009
        separator = getattr(processor, "sep")  # noqa: B009
    except (AttributeError, KeyError, TypeError) as error:
        raise MarkdownTocAPIError(
            "Python-Markdown's active TOC settings are no longer available "
            "as md.treeprocessors['toc'].slugify and .sep"
        ) from error

    if not callable(slugify) or not isinstance(separator, str):
        raise MarkdownTocAPIError(
            "Python-Markdown's active TOC slugify/sep values have an "
            "unexpected type"
        )
    return TocSlugging(slugify=slugify, separator=separator)

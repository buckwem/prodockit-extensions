# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Contract tests for the isolated Python-Markdown TOC adapter."""

from __future__ import annotations

import pytest
from markdown import Markdown
from markdown.extensions.toc import TocExtension

import prodockit.headings as headings
from prodockit._markdown_toc import MarkdownTocAPIError, toc_slugging


def test_toc_slugging_returns_none_without_a_toc_processor() -> None:
    assert toc_slugging(Markdown()) is None


def test_toc_slugging_exposes_the_resolved_settings_prodockit_needs() -> None:
    def custom_slugify(value: str, separator: str) -> str:
        return separator.join(value.lower().split())

    md = Markdown(extensions=[TocExtension(slugify=custom_slugify, separator="_")])

    settings = toc_slugging(md)

    assert settings is not None
    assert settings.slugify is custom_slugify
    assert settings.separator == "_"


@pytest.mark.parametrize(
    "processor",
    [
        object(),
        type("NoSeparator", (), {"slugify": staticmethod(lambda value, separator: value)})(),
        type("BadSlugify", (), {"slugify": "not callable", "sep": "-"})(),
        type("BadSeparator", (), {"slugify": staticmethod(lambda value, separator: value), "sep": 1})(),
    ],
)
def test_toc_slugging_reports_a_changed_processor_contract(processor: object) -> None:
    md = Markdown()
    md.treeprocessors.register(processor, "toc", 5)

    with pytest.raises(MarkdownTocAPIError, match=r"TOC|slugify/sep"):
        toc_slugging(md)


def test_heading_prescan_warns_once_when_the_toc_contract_moves(monkeypatch) -> None:
    extension = headings.HeadingsExtension()
    md = Markdown(extensions=[TocExtension()])
    headings._ZENSICAL_PRESEED_STATE = None
    headings._MARKDOWN_TOC_API_WARNED = False
    monkeypatch.setattr(headings, "nav_signature", lambda: None)

    def moved(_md: Markdown):
        raise MarkdownTocAPIError("changed representation")

    monkeypatch.setattr(headings, "toc_slugging", moved)

    with pytest.warns(RuntimeWarning, match=r"active TOC slugging.*Markdown") as caught:
        extension._preseed_from_nav(md, extension.registry)
        extension._preseed_from_nav(md, extension.registry)

    assert len(caught) == 1
    headings._MARKDOWN_TOC_API_WARNED = False

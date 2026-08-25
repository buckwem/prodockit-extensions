# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Contract tests for the isolated Zensical current-page adapter."""

from __future__ import annotations

import warnings

import pytest

from prodockit import _zensical_page_context as page_context
from prodockit._zensical_page_context import (
    ZensicalPageContextAPIError,
    current_page_path,
)


class _Page:
    path = "guide/intro.md"


class _Context:
    page = _Page()


def _install_context(monkeypatch: pytest.MonkeyPatch, replacement: object) -> None:
    module = pytest.importorskip("zensical.extensions.context")
    monkeypatch.setattr(module, "ContextPreprocessor", replacement, raising=False)


def test_current_page_path_exposes_the_api_prodockit_needs(monkeypatch) -> None:
    class ContextPreprocessor:
        @staticmethod
        def from_markdown(md):
            return _Context()

    _install_context(monkeypatch, ContextPreprocessor)

    assert current_page_path(object()) == "guide/intro.md"


def test_current_page_path_returns_none_without_a_page_context(monkeypatch) -> None:
    class ContextPreprocessor:
        @staticmethod
        def from_markdown(md):
            return None

    _install_context(monkeypatch, ContextPreprocessor)

    assert current_page_path(object()) is None


def test_current_page_path_reports_a_removed_context_preprocessor(monkeypatch) -> None:
    module = pytest.importorskip("zensical.extensions.context")
    monkeypatch.delattr(module, "ContextPreprocessor")

    with pytest.raises(
        ZensicalPageContextAPIError,
        match=r"ContextPreprocessor\.from_markdown\(md\)\.page\.path",
    ):
        current_page_path(object())


def test_current_page_path_reports_a_none_page_path(monkeypatch) -> None:
    class ContextPreprocessor:
        @staticmethod
        def from_markdown(md):
            page = type("Page", (), {"path": None})()
            return type("Context", (), {"page": page})()

    _install_context(monkeypatch, ContextPreprocessor)

    with pytest.raises(
        ZensicalPageContextAPIError,
        match=r"ContextPreprocessor\.from_markdown\(md\)\.page\.path",
    ):
        current_page_path(object())


def test_current_page_path_reports_an_unusable_path_representation(monkeypatch) -> None:
    class UnusablePath:
        def __str__(self):
            raise TypeError("path cannot be represented as text")

    class ContextPreprocessor:
        @staticmethod
        def from_markdown(md):
            page = type("Page", (), {"path": UnusablePath()})()
            return type("Context", (), {"page": page})()

    _install_context(monkeypatch, ContextPreprocessor)

    with pytest.raises(
        ZensicalPageContextAPIError,
        match=r"ContextPreprocessor\.from_markdown\(md\)\.page\.path",
    ):
        current_page_path(object())


@pytest.mark.parametrize(
    "replacement",
    [
        type("NoFactory", (), {}),
        type(
            "ChangedSignature",
            (),
            {"from_markdown": staticmethod(lambda md, new_argument: None)},
        ),
        type(
            "NoPagePath",
            (),
            {"from_markdown": staticmethod(lambda md: type("Context", (), {"page": object()})())},
        ),
    ],
)
def test_current_page_path_reports_a_changed_zensical_contract(monkeypatch, replacement) -> None:
    _install_context(monkeypatch, replacement)

    with pytest.raises(
        ZensicalPageContextAPIError,
        match=r"ContextPreprocessor\.from_markdown\(md\)\.page\.path",
    ):
        current_page_path(object())


def test_current_page_path_is_silent_when_zensical_is_absent(monkeypatch) -> None:
    def no_zensical(name):
        raise ModuleNotFoundError("No module named 'zensical'", name="zensical")

    monkeypatch.setattr(page_context, "import_module", no_zensical)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert current_page_path(object()) is None


def test_current_page_path_reports_an_import_failure_inside_zensical(
    monkeypatch,
) -> None:
    def broken_context(name):
        raise ModuleNotFoundError("No module named 'zensical.internal'", name="zensical.internal")

    monkeypatch.setattr(page_context, "import_module", broken_context)

    with pytest.raises(
        ZensicalPageContextAPIError,
        match=r"ContextPreprocessor\.from_markdown\(md\)\.page\.path",
    ):
        current_page_path(object())

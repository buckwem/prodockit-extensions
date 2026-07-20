# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Direct unit tests for prodockit.util - the shared IdRegistry/
CitationRegistry/GlossaryRegistry/cross_page_href machinery every
extension-specific test suite (test_headings.py, test_refs.py,
test_citations.py, test_glossary.py) otherwise only exercises indirectly,
through its own Markdown extension."""

import pytest

from prodockit.util import (
    CitationRegistry,
    DuplicateIdError,
    GlossaryRegistry,
    IdRegistry,
    cross_page_href,
)

# ---------------------------------------------------------------------------
# cross_page_href
# ---------------------------------------------------------------------------


def test_cross_page_href_same_source_is_a_bare_fragment() -> None:
    assert cross_page_href("intro.md", "intro.md", "setup") == "#setup"


def test_cross_page_href_different_top_level_source() -> None:
    assert cross_page_href("references.md", "intro.md", "skou2023") == "references.md#skou2023"


def test_cross_page_href_from_a_nested_page_to_a_top_level_source() -> None:
    assert (
        cross_page_href("references.md", "starthere/customise.md", "skou2023")
        == "../references.md#skou2023"
    )


def test_cross_page_href_from_a_top_level_page_to_a_nested_source() -> None:
    assert (
        cross_page_href("starthere/customise.md", "intro.md", "setup")
        == "starthere/customise.md#setup"
    )


def test_cross_page_href_between_two_pages_in_the_same_subdirectory() -> None:
    assert (
        cross_page_href("starthere/install.md", "starthere/customise.md", "step-1")
        == "install.md#step-1"
    )


def test_cross_page_href_from_a_doubly_nested_page() -> None:
    assert (
        cross_page_href("references.md", "appendix/tools/setup.md", "skou2023")
        == "../../references.md#skou2023"
    )


# ---------------------------------------------------------------------------
# IdRegistry
# ---------------------------------------------------------------------------


def test_id_registry_register_and_get() -> None:
    registry = IdRegistry()
    registry.register(source="intro.md", id="setup", level=1, text="Setup", number="1")
    record = registry.get("setup")
    assert record is not None
    assert record.source == "intro.md"
    assert record.level == 1
    assert record.text == "Setup"
    assert record.number == "1"


def test_id_registry_get_returns_none_for_an_unknown_id() -> None:
    assert IdRegistry().get("does-not-exist") is None


def test_id_registry_contains() -> None:
    registry = IdRegistry()
    registry.register(source="intro.md", id="setup", level=1, text="Setup")
    assert "setup" in registry
    assert "other" not in registry


def test_id_registry_duplicate_from_a_different_source_raises_when_strict() -> None:
    registry = IdRegistry()
    registry.register(source="intro.md", id="setup", level=1, text="Setup")
    with pytest.raises(DuplicateIdError):
        registry.register(source="other.md", id="setup", level=1, text="Setup")


def test_id_registry_duplicate_from_a_different_source_keeps_the_first_when_not_strict() -> None:
    registry = IdRegistry()
    registry.register(source="intro.md", id="setup", level=1, text="Setup")
    # Must not raise:
    registry.register(source="other.md", id="setup", level=1, text="Different Setup", strict=False)
    assert registry.get("setup").source == "intro.md"  # type: ignore[union-attr]
    assert registry.get("setup").text == "Setup"  # type: ignore[union-attr]


def test_id_registry_re_registering_from_the_same_source_updates_the_record() -> None:
    """Same source re-registering (e.g. a live-reload rebuild after a
    heading's text changed) always just overwrites - no collision at
    all, regardless of `strict`."""
    registry = IdRegistry()
    registry.register(source="intro.md", id="setup", level=1, text="Setup")
    registry.register(source="intro.md", id="setup", level=2, text="Setup Again")
    record = registry.get("setup")
    assert record is not None
    assert record.level == 2
    assert record.text == "Setup Again"


def test_id_registry_clear_source_only_drops_that_sources_entries() -> None:
    registry = IdRegistry()
    registry.register(source="intro.md", id="setup", level=1, text="Setup")
    registry.register(source="other.md", id="usage", level=1, text="Usage")
    registry.clear_source("intro.md")
    assert registry.get("setup") is None
    assert registry.get("usage") is not None


# ---------------------------------------------------------------------------
# CitationRegistry
# ---------------------------------------------------------------------------


def test_citation_registry_register_and_get() -> None:
    registry = CitationRegistry()
    registry.register(source="references.md", id="skou2023", text="Skoulikari, 2023")
    record = registry.get("skou2023")
    assert record is not None
    assert record.source == "references.md"
    assert record.text == "Skoulikari, 2023"


def test_citation_registry_duplicate_from_a_different_source_raises_when_strict() -> None:
    registry = CitationRegistry()
    registry.register(source="references.md", id="skou2023", text="Skoulikari, 2023")
    with pytest.raises(DuplicateIdError):
        registry.register(source="other.md", id="skou2023", text="Skoulikari, 2023")


def test_citation_registry_preseed_is_used_before_the_real_registration() -> None:
    registry = CitationRegistry()
    registry.preseed(source="references.md", id="skou2023", text="Skoulikari, 2023")
    assert "skou2023" in registry
    record = registry.get("skou2023")
    assert record is not None
    assert record.source == "references.md"


def test_citation_registry_real_registration_supersedes_the_preseeded_stub() -> None:
    registry = CitationRegistry()
    registry.preseed(source="references.md", id="skou2023", text="stub text")
    registry.register(source="references.md", id="skou2023", text="Skoulikari, 2023")
    assert registry.get("skou2023").text == "Skoulikari, 2023"  # type: ignore[union-attr]


def test_citation_registry_repeat_preseed_keeps_the_first_scan() -> None:
    registry = CitationRegistry()
    registry.preseed(source="references.md", id="skou2023", text="first scan")
    registry.preseed(source="references.md", id="skou2023", text="second scan")
    assert registry.get("skou2023").text == "first scan"  # type: ignore[union-attr]


def test_citation_registry_clear_source_only_drops_that_sources_entries() -> None:
    registry = CitationRegistry()
    registry.register(source="references.md", id="skou2023", text="Skoulikari, 2023")
    registry.register(source="other.md", id="other-key", text="Other")
    registry.clear_source("references.md")
    assert registry.get("skou2023") is None
    assert registry.get("other-key") is not None


# ---------------------------------------------------------------------------
# GlossaryRegistry
# ---------------------------------------------------------------------------


def test_glossary_registry_register_and_get() -> None:
    registry = GlossaryRegistry()
    registry.register(source="acronyms.md", id="css", text="CSS")
    record = registry.get("css")
    assert record is not None
    assert record.source == "acronyms.md"
    assert record.text == "CSS"


def test_glossary_registry_duplicate_from_a_different_source_raises_when_strict() -> None:
    registry = GlossaryRegistry()
    registry.register(source="acronyms.md", id="css", text="CSS")
    with pytest.raises(DuplicateIdError):
        registry.register(source="other.md", id="css", text="CSS")


def test_glossary_registry_real_registration_supersedes_the_preseeded_stub() -> None:
    registry = GlossaryRegistry()
    registry.preseed(source="acronyms.md", id="css", text="stub text")
    registry.register(source="acronyms.md", id="css", text="CSS")
    assert registry.get("css").text == "CSS"  # type: ignore[union-attr]

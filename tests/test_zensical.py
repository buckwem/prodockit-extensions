# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Direct unit tests for prodockit._zensical's internal helpers - the pieces
prescan_headings() is built from, and prescan_headings() itself, kept
separate from the full markdown-conversion integration tests in
test_zensical_integration.py so a regression here (e.g. in the fence/comment
skipping) points straight at the broken primitive."""

import warnings
from pathlib import Path

import pytest

import prodockit._zensical as prodockit_zensical
from prodockit._zensical import (
    _count_top_level_headings,
    _front_matter_flag,
    nav_signature,
    prescan_headings,
    preseed_attr_from_nav,
)
from prodockit.util import CitationRegistry


def test_front_matter_flag_true_when_set() -> None:
    text = "---\nis_appendix: true\n---\n\n# Heading\n"
    assert _front_matter_flag(text, "is_appendix") is True


def test_front_matter_flag_false_when_absent() -> None:
    text = "---\nicon: lucide/book-open\n---\n\n# Heading\n"
    assert _front_matter_flag(text, "is_appendix") is False


def test_front_matter_flag_false_without_front_matter() -> None:
    assert _front_matter_flag("# Heading\n", "is_appendix") is False


def test_front_matter_flag_is_case_insensitive() -> None:
    text = "---\nis_appendix: TRUE\n---\n\n# Heading\n"
    assert _front_matter_flag(text, "is_appendix") is True


def test_count_top_level_headings_counts_only_h1() -> None:
    text = "# One\n\n## Sub\n\n# Two\n"
    assert _count_top_level_headings(text) == 2


def test_count_top_level_headings_skips_fenced_examples() -> None:
    text = "# Real\n\n```markdown\n# Not a heading\n```\n"
    assert _count_top_level_headings(text) == 1


def test_count_top_level_headings_skips_html_comments() -> None:
    text = "<!--\n# Not a heading\n-->\n\n# Real\n"
    assert _count_top_level_headings(text) == 1


def test_count_top_level_headings_skips_unnumbered() -> None:
    text = "# Cover {.unnumbered}\n\n# Real\n"
    assert _count_top_level_headings(text) == 1


# ---------------------------------------------------------------------------
# Setext h1s (#106)
#
# Nothing else in either pipeline distinguishes setext from ATX - Zensical's
# renderer and Pandoc both produce a real h1 either way - so an uncounted
# setext heading silently desynchronised continuous chapter numbering:
# later pages' start counts came out short, duplicating a chapter number on
# the website and leaving it one behind the PDF. Each expectation below was
# checked against the real renderer's own output rather than assumed.
# ---------------------------------------------------------------------------

def test_count_top_level_headings_counts_setext_h1() -> None:
    assert _count_top_level_headings("Title\n=====\n") == 1


def test_count_top_level_headings_counts_a_single_equals_underline() -> None:
    """One "=" is enough for the real renderer, so it has to be enough here."""
    assert _count_top_level_headings("Title\n=\n") == 1


def test_count_top_level_headings_allows_trailing_space_after_the_underline() -> None:
    assert _count_top_level_headings("Title\n=====   \n") == 1


def test_count_top_level_headings_ignores_a_dash_underline() -> None:
    """A "-" underline is a setext *h2*, not an h1."""
    assert _count_top_level_headings("Title\n-----\n") == 0


def test_count_top_level_headings_ignores_an_underline_after_a_two_line_paragraph() -> None:
    """The renderer produces no heading at all here - a setext underline
    only applies to a single text line - so neither should this."""
    assert _count_top_level_headings("Line one\nLine two\n========\n") == 0


def test_count_top_level_headings_ignores_an_underline_split_from_its_text() -> None:
    assert _count_top_level_headings("Title\n\n=====\n") == 0


def test_count_top_level_headings_ignores_an_indented_setext_block() -> None:
    """Four spaces makes it an indented code block, not a heading."""
    assert _count_top_level_headings("    Title\n    =====\n") == 0


def test_count_top_level_headings_skips_setext_inside_a_fence() -> None:
    assert _count_top_level_headings("```\nTitle\n=====\n```\n") == 0


def test_count_top_level_headings_skips_setext_inside_an_html_comment() -> None:
    assert _count_top_level_headings("<!--\nTitle\n=====\n-->\n") == 0


def test_count_top_level_headings_skips_unnumbered_setext() -> None:
    """attr_list attaches a setext heading's own attributes to the *text*
    line, not the line after the underline."""
    assert _count_top_level_headings("Title {: .unnumbered }\n=====\n") == 0


def test_count_top_level_headings_does_not_double_count_an_atx_heading() -> None:
    """A "=====" line under an ATX heading is a paragraph to the renderer,
    not a second heading - the ATX line has already counted itself."""
    assert _count_top_level_headings("# Title\n=====\n") == 1


def test_count_top_level_headings_counts_mixed_atx_and_setext() -> None:
    assert _count_top_level_headings("# One\n\nTwo\n===\n\n# Three\n") == 3


def test_prescan_headings_returns_none_outside_zensical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: None)
    assert prescan_headings("is_appendix") is None


def test_prescan_headings_computes_cumulative_start_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n\n## Sub\n", encoding="utf-8")
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    (docs_dir / "page3.md").write_text("# Three\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page1.md", "page2.md", "page3.md"]),
    )
    result = prescan_headings("is_appendix")
    assert result is not None
    start_counts, appendix_letters = result
    assert start_counts == {"page1.md": 0, "page2.md": 1, "page3.md": 2}
    assert appendix_letters == {}


def test_prescan_headings_letters_appendix_pages_and_skips_them_from_the_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n", encoding="utf-8")
    (docs_dir / "acronyms.md").write_text(
        "---\nis_appendix: true\n---\n\n# Acronyms\n", encoding="utf-8"
    )
    (docs_dir / "glossary.md").write_text(
        "---\nis_appendix: true\n---\n\n# Glossary\n", encoding="utf-8"
    )
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page1.md", "acronyms.md", "glossary.md", "page2.md"]),
    )
    result = prescan_headings("is_appendix")
    assert result is not None
    start_counts, appendix_letters = result
    # page2 continues the numeric sequence as if the two appendix pages
    # were never there - "1" (from page1), not "3".
    assert start_counts == {"page1.md": 0, "page2.md": 1}
    assert appendix_letters == {"acronyms.md": "A", "glossary.md": "B"}


def test_prescan_headings_respects_a_custom_appendix_attr_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "appendix.md").write_text(
        "---\ncustom_flag: true\n---\n\n# Appendix\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["appendix.md"])
    )
    result = prescan_headings("custom_flag")
    assert result is not None
    _, appendix_letters = result
    assert appendix_letters == {"appendix.md": "A"}


# ---------------------------------------------------------------------------
# Stale pre-scan under a long-lived process (#99)
#
# preseed() is deliberately first-wins so a genuine duplicate id resolves to
# the first page in nav order. Under `zensical build` (short-lived, files
# immutable) that's all it has to do. Under `zensical serve` the process
# outlives the files: the scan re-runs on every page render and re-reads
# from disk, but first-wins silently discarded the fresh values, so an
# edited definition kept its original text - and a deleted one stayed
# resolvable - until the dev server restarted.
# ---------------------------------------------------------------------------

def _nav(monkeypatch: pytest.MonkeyPatch, docs_dir: Path, pages: list[str]) -> None:
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: (str(docs_dir), pages))


def test_preseed_attr_from_nav_picks_up_an_edited_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page = docs_dir / "refs.md"
    page.write_text('Ref\n{: #r1 data-cite-text="ORIGINAL (2020)" }\n', encoding="utf-8")
    _nav(monkeypatch, docs_dir, ["refs.md"])
    registry = CitationRegistry()

    preseed_attr_from_nav(registry, "data-cite-text")
    assert registry.get("r1").text == "ORIGINAL (2020)"

    # The author edits the defining page while the dev server keeps running.
    page.write_text('Ref\n{: #r1 data-cite-text="EDITED (2026)" }\n', encoding="utf-8")
    preseed_attr_from_nav(registry, "data-cite-text")
    assert registry.get("r1").text == "EDITED (2026)"


def test_preseed_attr_from_nav_drops_a_deleted_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A definition removed from the page has to stop resolving, not linger
    as a provisional entry nothing will ever overwrite."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page = docs_dir / "refs.md"
    page.write_text('Ref\n{: #r1 data-cite-text="Gone soon" }\n', encoding="utf-8")
    _nav(monkeypatch, docs_dir, ["refs.md"])
    registry = CitationRegistry()

    preseed_attr_from_nav(registry, "data-cite-text")
    assert "r1" in registry

    page.write_text("Ref with no definition any more.\n", encoding="utf-8")
    preseed_attr_from_nav(registry, "data-cite-text")
    assert "r1" not in registry


def test_preseed_attr_from_nav_keeps_first_in_nav_order_across_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The constraint the rebuild must not break: when two different pages
    define the same id, the first in nav order still wins - re-scanning in
    nav order restores that, it isn't relying on entries left behind."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text('A\n{: #dup data-cite-text="FROM A" }\n', encoding="utf-8")
    (docs_dir / "b.md").write_text('B\n{: #dup data-cite-text="FROM B" }\n', encoding="utf-8")
    _nav(monkeypatch, docs_dir, ["a.md", "b.md"])
    registry = CitationRegistry()

    for _ in range(3):  # repeated renders must not flip the winner
        preseed_attr_from_nav(registry, "data-cite-text")
        record = registry.get("dup")
        assert (record.text, record.source) == ("FROM A", "a.md")


def test_preseed_attr_from_nav_leaves_real_registrations_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing provisional entries must not touch what a really-rendered
    page registered - that always supersedes a pre-scan."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "refs.md").write_text(
        'Ref\n{: #r1 data-cite-text="Preseeded" }\n', encoding="utf-8"
    )
    _nav(monkeypatch, docs_dir, ["refs.md"])
    registry = CitationRegistry()
    registry.register("refs.md", "r1", "Really registered")

    preseed_attr_from_nav(registry, "data-cite-text")

    assert registry.get("r1").text == "Really registered"


def test_nav_signature_changes_when_a_page_is_edited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What lets prodockit.headings cache its much heavier scan without going
    stale: one stat() per page, rather than re-reading them all to find out
    whether anything changed."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page = docs_dir / "page.md"
    page.write_text("# One\n", encoding="utf-8")
    _nav(monkeypatch, docs_dir, ["page.md"])

    before = nav_signature()
    assert before == nav_signature()  # stable while nothing changes

    page.write_text("# One\n\n# Two\n", encoding="utf-8")
    assert nav_signature() != before


def test_nav_signature_is_none_outside_zensical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: None)
    assert nav_signature() is None


def test_nav_signature_still_moves_when_a_page_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable page contributes a zeroed entry rather than being
    skipped, so its removal is still visible in the signature."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page = docs_dir / "page.md"
    page.write_text("# One\n", encoding="utf-8")
    _nav(monkeypatch, docs_dir, ["page.md"])

    before = nav_signature()
    page.unlink()
    assert nav_signature() != before
    assert nav_signature() == (("page.md", 0, 0),)


class _StubPage:
    def __init__(self, path: str) -> None:
        self.path = path


class _StubContext:
    def __init__(self, page: object) -> None:
        self.page = page


@pytest.fixture(autouse=True)
def _reset_api_warnings():
    """`_warn_api_moved` reports each API once per process, so a test that
    relies on the warning firing has to start from a clean slate."""
    prodockit_zensical._warned_apis.clear()
    yield
    prodockit_zensical._warned_apis.clear()


def _install_context(monkeypatch, cls: object) -> None:
    """Puts a stand-in ContextPreprocessor where page_source() imports it
    from, so the failure modes below can be provoked without a real
    Zensical."""
    module = pytest.importorskip("zensical.extensions.context")
    monkeypatch.setattr(module, "ContextPreprocessor", cls, raising=False)


def test_page_source_returns_the_page_path(monkeypatch) -> None:
    class Ok:
        @staticmethod
        def from_markdown(md):
            return _StubContext(_StubPage("guide/intro.md"))

    _install_context(monkeypatch, Ok)

    assert prodockit_zensical.page_source(object()) == "guide/intro.md"


def test_page_source_warns_when_from_markdown_has_been_renamed(monkeypatch) -> None:
    """prodockit-extensions#167: the guard used to cover only the import, so
    a rename surfaced as a stack trace from deep inside `zensical build`
    with nothing pointing at the version bump that caused it."""

    class Renamed:
        pass  # no from_markdown at all -> AttributeError

    _install_context(monkeypatch, Renamed)

    with pytest.warns(RuntimeWarning, match="from_markdown"):
        assert prodockit_zensical.page_source(object()) is None


def test_page_source_warns_when_the_signature_changed(monkeypatch) -> None:
    class Resignatured:
        @staticmethod
        def from_markdown(md, required_new_argument):
            return None

    _install_context(monkeypatch, Resignatured)

    with pytest.warns(RuntimeWarning, match="moved it"):
        assert prodockit_zensical.page_source(object()) is None


def test_page_source_warns_when_page_path_has_been_renamed(monkeypatch) -> None:
    """A `Page.path` -> `Page.src_path` rename is invisible to an import
    guard: everything imports, and the attribute access is what fails."""

    class RenamedPath:
        @staticmethod
        def from_markdown(md):
            return _StubContext(object())  # a page with no .path

    _install_context(monkeypatch, RenamedPath)

    with pytest.warns(RuntimeWarning):
        assert prodockit_zensical.page_source(object()) is None


def test_the_api_warning_names_the_api_and_the_installed_version(monkeypatch) -> None:
    """The reader has to be able to connect a degraded build to the Zensical
    upgrade that caused it - none of these APIs is public, so a rename can
    arrive in a patch release."""

    class Renamed:
        pass

    _install_context(monkeypatch, Renamed)

    with pytest.warns(RuntimeWarning) as recorded:
        prodockit_zensical.page_source(object())

    message = str(recorded[0].message)
    assert "ContextPreprocessor.from_markdown(md).page.path" in message
    assert "Zensical" in message
    # Says what actually degrades, not just that something broke.
    assert "cross-page" in message


def test_the_api_warning_fires_once_per_process_not_once_per_page(monkeypatch) -> None:
    """`page_source()` runs on every render; a per-page warning would bury
    the rest of the build log in copies of itself."""

    class Renamed:
        pass

    _install_context(monkeypatch, Renamed)

    with pytest.warns(RuntimeWarning) as recorded:
        for _ in range(5):
            prodockit_zensical.page_source(object())

    assert len(recorded) == 1


def test_page_source_is_silent_when_zensical_is_absent(monkeypatch) -> None:
    """"Not running under Zensical" is a legitimate, expected state for any
    other Python-Markdown consumer - warning there would cry wolf."""
    import builtins

    real_import = builtins.__import__

    def no_zensical(name, *args, **kwargs):
        if name.startswith("zensical"):
            raise ImportError("no zensical")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_zensical)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning becomes a failure
        assert prodockit_zensical.page_source(object()) is None


def test_nav_pages_warns_when_get_config_stops_behaving_like_a_mapping(monkeypatch) -> None:
    module = pytest.importorskip("zensical.config")
    monkeypatch.setattr(module, "get_config", lambda: object(), raising=False)

    with pytest.warns(RuntimeWarning, match="get_config"):
        assert prodockit_zensical.nav_pages() is None

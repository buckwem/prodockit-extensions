# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Offline tests for the scheduled Zensical capability drift report."""

from __future__ import annotations

from pathlib import Path

from tools import rendering_catalogue_drift as drift


def test_supported_extension_heading_extraction_stops_at_the_next_section() -> None:
    document = """
    <article><h2 id="supported-extensions">Supported extensions</h2>
    <h3 id="first">First</h3><h4 id="option">Option</h4>
    <h3 id="second">Second</h3><h2 id="other">Other</h2>
    <h3 id="excluded">Excluded</h3></article>
    """
    assert drift.extract_supported_extension_headings(document) == ["first", "option", "second"]


def test_authoring_page_extraction_is_unique_and_scoped() -> None:
    document = """
    <article>
      <a href="/docs/authoring/buttons/">Buttons</a>
      <a href="https://zensical.org/docs/authoring/buttons/">Buttons again</a>
      <a href="/docs/authoring/grids/">Grids</a>
      <a href="/docs/authoring/grids/example/">Nested page</a>
      <a href="/docs/compatibility/">Elsewhere</a>
    </article>
    """
    assert drift.extract_authoring_pages(document) == ["buttons", "grids"]


def test_upstream_baseline_is_bound_to_the_catalogue_ledger() -> None:
    sources = drift.validate_baseline()
    assert [source["name"] for source in sources] == [
        "Python-Markdown extensions",
        "PyMdown Extensions",
        "Zensical authoring",
    ]
    assert sum(len(source["item"]) for source in sources) == 58


def test_comparison_reports_additions_removals_and_order() -> None:
    assert drift.compare(["a", "b"], ["a", "c"]) == (["c"], ["b"], False)
    assert drift.compare(["a", "b"], ["b", "a"]) == ([], [], True)
    assert drift.compare(["a", "b"], ["a", "b"]) == ([], [], False)


def test_report_records_drift_without_rewriting_the_baseline(
    monkeypatch, tmp_path: Path
) -> None:
    baseline_before = drift.BASELINE.read_bytes()
    sources = drift.validate_baseline()
    documents: dict[str, str] = {}
    for source in sources:
        keys = [item["key"] for item in source["item"]]
        if source["extractor"] == "authoring-pages":
            documents[source["url"]] = "<article>" + "".join(
                f'<a href="/docs/authoring/{key}/">{key}</a>' for key in keys
            ) + "</article>"
        else:
            documents[source["url"]] = (
                '<article><h2 id="supported-extensions">Supported extensions</h2>'
                + "".join(f'<h3 id="{key}">{key}</h3>' for key in keys)
                + '<h2 id="other">Other</h2></article>'
            )
    first_url = sources[0]["url"]
    documents[first_url] = documents[first_url].replace(
        '<h2 id="other">', '<h3 id="new-upstream-capability">New</h3><h2 id="other">'
    )
    monkeypatch.setattr(drift, "fetch", lambda url: documents[url])
    report = tmp_path / "upstream-drift.md"

    assert drift.check(report) is False
    assert "`new-upstream-capability`" in report.read_text(encoding="utf-8")
    assert drift.BASELINE.read_bytes() == baseline_before


def test_drift_workflow_retains_and_reports_the_review_artifact() -> None:
    workflow = (drift.ROOT / ".github" / "workflows" / "drift.yml").read_text(
        encoding="utf-8"
    )
    assert "tools/rendering_catalogue_drift.py" in workflow
    assert "upstream-inventory-drift" in workflow
    assert "if: always()" in workflow
    assert "Upstream rendering capability drift" in workflow

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
_SPEC = importlib.util.spec_from_file_location(
    "zensical_compatibility", TOOLS / "zensical_compatibility.py"
)
assert _SPEC and _SPEC.loader
_GATE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GATE)
sys.path.pop(0)
checks = sys.modules["compatibility.checks"]


@pytest.mark.parametrize(
    "version,code,text,status",
    [
        ("0.0.61", 1, "Error: unknown mike option: version_selector", "xfail"),
        ("0.0.61", 1, "ImportError", "failed"),
        ("0.0.61", None, "unknown mike option: version_selector", "failed"),
        ("0.0.61", 0, "No issues found", "xpass"),
        ("0.0.59", 1, "unknown mike option: version_selector", "failed"),
        ("0.0.62", 1, "unknown mike option: version_selector", "failed"),
        ("0.0.62", 0, "No issues found", "passed"),
    ],
)
def test_mike_exception_is_strict_and_version_bounded(version, code, text, status):
    assert checks.classify(code, text, version=version, name="mike") == status


def test_invalid_input_rejection_is_distinct_from_build_success():
    assert (
        checks.classify(1, "bad mapping", version="0.0.61", name="invalid", reject=True) == "passed"
    )
    assert checks.classify(0, "", version="0.0.61", name="invalid", reject=True) == "failed"
    assert (
        checks.classify(None, "timeout", version="0.0.61", name="invalid", reject=True) == "error"
    )


def test_junit_counts_do_not_count_skips_as_executed(tmp_path):
    p = tmp_path / "tests.xml"
    p.write_text(
        "<testsuites><testsuite><testcase/><testcase><failure/></testcase>"
        "<testcase><error/></testcase><testcase><skipped/></testcase></testsuite></testsuites>"
    )
    assert checks.junit_counts(p) == {
        "status": "executed",
        "executed": 3,
        "passed": 1,
        "failed": 1,
        "error": 1,
        "skipped": 1,
    }
    assert checks.junit_counts(tmp_path / "missing.xml")["status"] == "not-run"


def make_snapshot(pages):
    return {
        "inventory": {},
        "articles": {},
        "pdfs": {
            "book.pdf": {
                "page_count": len(pages),
                "pages": pages,
                "bookmarks": [],
                "sha256": "hash",
            }
        },
    }


def test_comparator_does_not_truncate_added_pages():
    page = {"text": "Page", "pixels": "hash", "dimensions": [0, 0, 10, 10], "links": []}
    result = checks.compare_snapshots(make_snapshot([page]), make_snapshot([page, page]))
    assert result["pdfs"]["book.pdf"]["page_counts"] == [1, 2]
    assert result["pdfs"]["book.pdf"]["differences"] == {
        "text": [2],
        "pixels": [2],
        "dimensions": [2],
        "links": [2],
    }


def test_identical_pixels_do_not_hide_bad_links():
    a = {"text": "Page", "pixels": "hash", "dimensions": [0, 0, 10, 10], "links": []}
    b = {**a, "links": [{"uri": "https://example.com/broken"}]}
    diff = checks.compare_snapshots(make_snapshot([a]), make_snapshot([b]))["pdfs"]["book.pdf"][
        "differences"
    ]
    assert diff["pixels"] == []
    assert diff["links"] == [1]


def test_pdf_snapshot_checks_real_annotations_on_all_pages(tmp_path):
    import pymupdf

    p = tmp_path / "book.pdf"
    with pymupdf.open() as pdf:
        for _ in range(2):
            page = pdf.new_page()
            page.insert_text((30, 30), "Page")
        pdf[1].insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(10, 10, 40, 40),
                "uri": "https://github.com/example/repo/blob/main/" + str(tmp_path / "docs/a"),
            }
        )
        pdf.save(p)
    result = checks.pdf_snapshot(p, tmp_path)
    assert result["scope"] == "complete-document"
    assert len(result["pages"]) == 2
    assert result["problems"][0]["page"] == 2


def record(tmp_path, side, packages=None, status="passed"):
    checks.write_json(
        tmp_path / side / "result.json",
        {
            "environment": {
                "packages": packages or {"zensical": "0.0.61"},
                "platform": "test",
                "python": "3.14",
            },
            "scope": "consumer-configurations",
            "status": status,
            "projects": {},
            "probes": [{"name": "mike", "status": "xfail"}],
            "counts": {"xfail": 1},
        },
    )


def test_missing_candidate_is_not_a_passing_report(tmp_path):
    record(tmp_path, "baseline")
    assert _GATE.report(tmp_path) == 1


def test_changed_transitive_dependency_fails_isolation(tmp_path):
    record(tmp_path, "baseline", {"zensical": "0.0.59", "markdown": "3.10.3"})
    record(tmp_path, "candidate", {"zensical": "0.0.61", "markdown": "3.11"})
    assert _GATE.report(tmp_path) == 1
    assert "Dependency isolation FAILED" in (tmp_path / "analysis.md").read_text()


def test_config_only_report_explicitly_excludes_full_qualification(tmp_path):
    record(tmp_path, "baseline", {"zensical": "0.0.59"})
    record(tmp_path, "candidate", {"zensical": "0.0.61"})
    assert _GATE.report(tmp_path) == 0
    report = (tmp_path / "analysis.md").read_text()
    assert "**not run**" in report
    assert "XFAIL is a known upstream limitation, not a passing test" in report


def test_full_project_stops_on_failed_build(tmp_path, monkeypatch):
    monkeypatch.setattr(_GATE, "command", lambda *a, **k: {"exit": 1})
    monkeypatch.setattr(
        _GATE, "site_snapshot", lambda *a: pytest.fail("must not inspect stale output")
    )
    result = _GATE.full_project(tmp_path, tmp_path / "logs", template=False)
    assert result["status"] == "failed"
    assert result["incomplete_after"] == "mathjax"


def test_workflow_matrix_covers_supported_python_and_os():
    import yaml

    workflow = yaml.safe_load(
        (TOOLS.parent / ".github/workflows/zensical-compatibility.yml").read_text()
    )
    jobs = workflow["jobs"]
    matrix = jobs["configurations"]["strategy"]["matrix"]
    assert set(matrix["python-version"]) == {"3.10", "3.11", "3.12", "3.13", "3.14"}
    assert len(matrix["os"]) == 3
    assert "inputs.full" in jobs["complete-documents"]["if"]
    for job in jobs.values():
        upload = next(
            s for s in job["steps"] if s.get("uses", "").startswith("actions/upload-artifact")
        )
        assert upload["if"] == "always()"


def test_rejection_checks_do_not_accept_an_unrelated_crash():
    for name in ("invalid-mapping", "redirect-cycle"):
        assert (
            checks.classify(
                1, "ImportError: broken dependency", version="0.0.61", name=name, reject=True
            )
            == "failed"
        )


def test_timeout_is_reported_as_an_error(tmp_path):
    result = checks.command(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        tmp_path,
        tmp_path / "timeout.log",
        timeout=1,
    )
    assert result["exit"] is None
    assert "timed out" in result["error"]


def test_disposable_copy_includes_tracked_edits_and_deletions(tmp_path):
    import subprocess

    source, target = tmp_path / "source", tmp_path / "copy"
    source.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.com"],
        ["remote", "add", "origin", "https://github.com/example/repo"],
    ):
        subprocess.run(["git", *args], cwd=source, check=True)
    (source / "keep.txt").write_text("old")
    (source / "delete.txt").write_text("delete")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=source, check=True)
    (source / "keep.txt").write_text("edited")
    (source / "delete.txt").unlink()
    _GATE.copy_project(source, target)
    assert (target / "keep.txt").read_text() == "edited"
    assert not (target / "delete.txt").exists()


def test_asset_audit_understands_a_site_url_mount(tmp_path):
    (tmp_path / "zensical.toml").write_text(
        '[project]\nsite_name="Test"\nsite_url="https://example.com/project/"\nnav=[{Home="index.md"}]\n'
    )
    (tmp_path / "docs").mkdir()
    site = tmp_path / "site"
    (site / "assets").mkdir(parents=True)
    (site / "assets/main.css").write_text("body {}")
    html = '<link rel="stylesheet" href="/project/assets/main.css"><article class="md-content__inner">Home</article>'
    (site / "index.html").write_text(html)
    (site / "404.html").write_text(html)
    assert checks.site_snapshot(tmp_path)["missing_assets"] == []
    (site / "assets/main.css").unlink()
    assert len(checks.site_snapshot(tmp_path)["missing_assets"]) == 2


def test_historical_baseline_changes_only_zensical_and_separates_local_project():
    frozen = "prodockit @ file:///local/release\nzensical==0.0.61\nMarkdown==3.10.3\npytest==8.4.0\n"
    assert _GATE.baseline_requirements(frozen, "0.0.59") == (
        "zensical==0.0.59\nMarkdown==3.10.3\npytest==8.4.0\n"
    )
    assert _GATE.baseline_requirements("prodockit==0.65.2\nzensical==0.0.61\n", "0.0.59") == "zensical==0.0.59\n"


@pytest.mark.parametrize("extra_failure", [False, True])
def test_historical_floor_exception_is_exact_and_does_not_hide_other_failures(tmp_path, monkeypatch, extra_failure):
    import importlib.metadata
    import json

    from prodockit.pins import TESTED_VERSIONS

    monkeypatch.setattr(importlib.metadata, "version", lambda name: "0.65.2" if name == "prodockit" else "0.0.59")
    expected = f"prodockit 0.65.2 has requirement zensical>={TESTED_VERSIONS['zensical']}, but you have zensical 0.0.59."
    failed = {"id": "installation.dependencies", "status": "fail", "details": [expected]}
    log = tmp_path / "diagnostics.log"
    checks = [failed]
    if extra_failure:
        checks.append({"id": "renderer.mathjax", "status": "fail", "details": ["unavailable"]})
    log.write_text(json.dumps({"checks": checks}))
    assert _GATE.historical_floor_mismatch(log) is (not extra_failure)
    failed["details"].append("another package is missing")
    log.write_text(json.dumps({"checks": [failed]}))
    assert not _GATE.historical_floor_mismatch(log)
    log.write_text("broken JSON")
    assert not _GATE.historical_floor_mismatch(log)


@pytest.mark.parametrize("historical", [False, True])
def test_only_historical_worker_can_continue_after_expected_floor_mismatch(tmp_path, monkeypatch, historical):
    def run(args, root, log):
        return {"exit": int(log.stem in {"diagnostics", "source-bundle"})}

    monkeypatch.setattr(_GATE, "command", run)
    monkeypatch.setattr(_GATE, "historical_floor_mismatch", lambda log: True)
    result = _GATE.full_project(tmp_path, tmp_path / "logs", template=True, historical_baseline=historical)
    assert result["status"] == "failed"
    assert result["incomplete_after"] == ("source-bundle" if historical else "diagnostics")
    diagnostic = next(step for step in result["steps"] if step["name"] == "diagnostics")
    assert diagnostic["exit"] == 1
    assert ("expected_failure" in diagnostic) is historical

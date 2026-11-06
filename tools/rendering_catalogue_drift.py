# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Report upstream Zensical capability drift without rewriting the catalogue."""

from __future__ import annotations

import argparse
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "tests" / "rendering_catalogue"
BASELINE = CATALOGUE / "upstream-inventory.toml"
LEDGER = CATALOGUE / "catalogue.toml"
DEFAULT_REPORT = CATALOGUE / "build" / "upstream-drift.md"
USER_AGENT = "prodockit-rendering-catalogue-drift/1.0"


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        return tomllib.load(source)


def extract_supported_extension_headings(document: str) -> list[str]:
    """Extract supported extension and option heading IDs from one compatibility page."""
    soup = BeautifulSoup(document, "html.parser")
    article = soup.select_one("article")
    if article is None:
        raise ValueError("upstream page has no article")
    start = article.find(id="supported-extensions")
    if not isinstance(start, Tag) or start.name != "h2":
        raise ValueError("upstream page has no Supported extensions section")
    result: list[str] = []
    for heading in start.find_all_next(["h2", "h3", "h4"]):
        if heading.name == "h2":
            break
        identifier = heading.get("id")
        if isinstance(identifier, str) and identifier:
            result.append(identifier)
    if not result:
        raise ValueError("Supported extensions section is empty")
    return result


def extract_authoring_pages(document: str) -> list[str]:
    """Extract the unique authoring page slugs from the Zensical authoring index."""
    soup = BeautifulSoup(document, "html.parser")
    result: list[str] = []
    page_url = "https://zensical.org/docs/authoring/markdown/"
    for link in soup.select("a[href]"):
        path = urlparse(urljoin(page_url, str(link["href"]))).path
        prefix = "/docs/authoring/"
        if not path.startswith(prefix):
            continue
        remainder = path[len(prefix) :].strip("/")
        if remainder and "/" not in remainder and remainder not in result:
            result.append(remainder)
    if not result:
        raise ValueError("authoring index contains no authoring page links")
    return result


EXTRACTORS: dict[str, Callable[[str], list[str]]] = {
    "supported-extension-headings": extract_supported_extension_headings,
    "authoring-pages": extract_authoring_pages,
}


def validate_baseline() -> list[dict[str, Any]]:
    """Validate the checked-in baseline against the reviewed capability ledger."""
    baseline = _load(BASELINE)
    ledger = _load(LEDGER)
    if baseline["inventory"]["reviewed_zensical"] != ledger["catalogue"]["reviewed_zensical"]:
        raise ValueError("upstream baseline and catalogue use different Zensical versions")
    sources = baseline["source"]
    names = [source["name"] for source in sources]
    if len(names) != len(set(names)):
        raise ValueError("upstream inventory has duplicate source names")
    expected_ids = {
        item["id"]
        for item in ledger["capability"]
        if item["category"] in {"python-markdown", "pymdown", "zensical-authoring"}
    }
    assigned = [
        capability
        for source in sources
        for item in source["item"]
        for capability in item["capabilities"]
    ]
    duplicate_ids = sorted({item for item in assigned if assigned.count(item) > 1})
    if duplicate_ids:
        raise ValueError(
            "upstream capabilities assigned more than once: " + ", ".join(duplicate_ids)
        )
    if set(assigned) != expected_ids:
        missing = sorted(expected_ids - set(assigned))
        unknown = sorted(set(assigned) - expected_ids)
        raise ValueError(
            "upstream capability mapping differs from ledger; "
            f"missing={missing}, unknown={unknown}"
        )
    for source in sources:
        if source["extractor"] not in EXTRACTORS:
            raise ValueError(f"unknown upstream extractor: {source['extractor']}")
        keys = [item["key"] for item in source["item"]]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate keys in upstream source {source['name']}")
    return sources


def fetch(url: str, *, attempts: int = 3, timeout: int = 30) -> str:
    """Fetch one upstream page with bounded retries for transient failures."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except (OSError, UnicodeError, urllib.error.URLError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"could not fetch {url} after {attempts} attempts: {last_error}")


def compare(expected: list[str], actual: list[str]) -> tuple[list[str], list[str], bool]:
    """Return added, removed and order-changed results."""
    added = [item for item in actual if item not in expected]
    removed = [item for item in expected if item not in actual]
    return added, removed, not added and not removed and expected != actual


def check(report_path: Path) -> bool:
    """Write a review report; return True only when every source matches."""
    sources = validate_baseline()
    lines = [
        "# Zensical rendering catalogue upstream drift",
        "",
        "This scheduled check compares official Zensical capability pages with the reviewed",
        "catalogue baseline. It never rewrites the baseline or capability ledger.",
        "",
    ]
    clean = True
    for source in sources:
        expected = [item["key"] for item in source["item"]]
        lines.extend((f"## {source['name']}", "", f"Source: {source['url']}", ""))
        try:
            document = fetch(source["url"])
            actual = EXTRACTORS[source["extractor"]](document)
            added, removed, reordered = compare(expected, actual)
        except Exception as error:  # Report source outages as reviewable drift evidence.
            clean = False
            lines.extend(("**Result: fetch or extraction failed**", "", f"- {error}", ""))
            continue
        if not added and not removed and not reordered:
            lines.extend((f"**Result: current** ({len(actual)} upstream entries)", ""))
            continue
        clean = False
        lines.extend(("**Result: review required**", ""))
        if added:
            lines.append("- Added upstream: " + ", ".join(f"`{item}`" for item in added))
        if removed:
            lines.append("- Removed upstream: " + ", ".join(f"`{item}`" for item in removed))
        if reordered:
            lines.append("- The same entries now appear in a different order.")
        lines.append("")
    lines.extend(
        (
            "## Outcome",
            "",
            (
                "No upstream inventory drift detected."
                if clean
                else "Upstream inventory needs maintainer review."
            ),
            "",
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return clean


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        clean = check(args.report)
    except Exception as error:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            "# Zensical rendering catalogue upstream drift\n\n"
            "**Result: the drift check could not run**\n\n"
            f"- {error}\n",
            encoding="utf-8",
        )
        clean = False
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())

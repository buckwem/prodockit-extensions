# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Build, verify and publish the hidden rendering-review catalogue bundle."""

from __future__ import annotations

import argparse
import ast
import html
import json
import shutil
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "tests" / "rendering_catalogue"
CONFIG = CATALOGUE / "zensical.toml"
LEDGER = CATALOGUE / "catalogue.toml"
LAYERS = CATALOGUE / "test-layers.toml"
DOCS = CATALOGUE / "docs"
BUILT_SITE = CATALOGUE / "site"
BUILD = CATALOGUE / "build"
BUNDLE = BUILD / "review-bundle"
COMPLETE_PDF = BUILD / "rendering-catalogue.pdf"
ROUTE = "rendering-review"
ROBOTS_CONTENT = "noindex, nofollow, noarchive, nosnippet, noimageindex"


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        return tomllib.load(source)


def _nav_sources(items: list[Any]) -> list[str]:
    sources: list[str] = []
    for item in items:
        value = next(iter(item.values()))
        if isinstance(value, list):
            sources.extend(_nav_sources(value))
        else:
            source = PurePosixPath(value)
            if source.is_absolute() or ".." in source.parts or source.suffix != ".md":
                raise ValueError(f"Invalid catalogue page: {value}")
            sources.append(value)
    if len(sources) != len(set(sources)):
        raise ValueError("The catalogue navigation contains duplicate pages")
    return sources


def catalogue_sources() -> list[str]:
    return _nav_sources(_load(CONFIG)["project"]["nav"])


def page_url(source: str) -> str:
    path = PurePosixPath(source)
    target = path.parent if path.name == "index.md" else path.with_suffix("")
    return "" if str(target) == "." else f"{target.as_posix()}/"


def page_pdf(source: str) -> PurePosixPath:
    return PurePosixPath("page-pdfs") / PurePosixPath(source).with_suffix(".pdf")


def _run(*command: str) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=CATALOGUE, check=True)


def _copy_pdf(source: Path, destination: Path) -> None:
    if not source.is_file() or not source.read_bytes().startswith(b"%PDF-"):
        raise ValueError(f"Expected PDF was not produced: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _write_status(status: str) -> None:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    (BUNDLE / "bundle-status.json").write_text(
        json.dumps({"status": status}, indent=2) + "\n",
        encoding="utf-8",
    )


def _clear_intermediate_pdfs() -> None:
    for path in DOCS.glob("*.pdf"):
        path.unlink()


def _copy_catalogue_site() -> None:
    excluded = {"search.json", "sitemap.xml", "sitemap.xml.gz"}
    for source in BUILT_SITE.rglob("*"):
        relative = source.relative_to(BUILT_SITE)
        if any(part in excluded for part in relative.parts):
            continue
        destination = BUNDLE / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def _render_thumbnails() -> int:
    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - CI installs the testing extra.
        raise RuntimeError("Install Prodockit's testing extra to render PDF thumbnails") from error

    destination = BUNDLE / "thumbnails"
    destination.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(COMPLETE_PDF) as document:
        for number, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(0.35, 0.35), alpha=False)
            pixmap.save(destination / f"page-{number:03d}.png")
        return document.page_count


def _head(title: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="{ROBOTS_CONTENT}">
  <title>{html.escape(title)}</title>
  <style>
    body {{ color: #222; font: 16px/1.5 system-ui, sans-serif; margin: 2rem auto;
      max-width: 96rem; padding: 0 1rem; }}
    a {{ color: #4051b5; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d7d7d7; padding: .45rem; text-align: left;
      vertical-align: top; }}
    th {{ background: #f3f4f7; position: sticky; top: 0; }}
    .passed {{ color: #087f23; font-weight: 700; }}
    .waived {{ color: #8a4b08; font-weight: 700; }}
    .contact-sheet {{ display: grid; gap: 1rem;
      grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr)); }}
    .contact-sheet figure {{ margin: 0; }}
    .contact-sheet img {{ border: 1px solid #bbb; box-shadow: 0 2px 8px #0002;
      height: auto; width: 100%; }}
  </style>
</head>
<body>
"""


def _write_contact_sheet(page_count: int) -> None:
    cards = []
    for number in range(1, page_count + 1):
        image = f"thumbnails/page-{number:03d}.png"
        cards.append(
            f'<figure><a href="{image}"><img src="{image}" '
            f'alt="Catalogue PDF page {number}"></a><figcaption>Page {number}</figcaption></figure>'
        )
    content = (
        _head("Rendering catalogue PDF contact sheet")
        + "<h1>Rendering catalogue PDF contact sheet</h1>\n"
        + '<p><a href="rendering-catalogue.pdf">Open the complete catalogue PDF</a>.</p>\n'
        + '<div class="contact-sheet">\n'
        + "\n".join(cards)
        + "\n</div>\n</body>\n</html>\n"
    )
    (BUNDLE / "contact-sheet.html").write_text(content, encoding="utf-8")


def _coverage_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for capability in _load(LEDGER)["capability"]:
        source = capability.get("page", "")
        anchor = capability.get("anchor", "")
        status = capability["status"]
        test_status = "waived" if status == "waived" else "passed"
        rows.append(
            {
                "id": capability["id"],
                "title": capability["title"],
                "category": capability["category"],
                "status": status,
                "test_status": test_status,
                "source": source,
                "source_url": (
                    "https://github.com/buckwem/prodockit-extensions/blob/main/"
                    f"tests/rendering_catalogue/docs/{source}#{anchor}"
                    if source
                    else capability.get("reference", "")
                ),
                "website_url": f"{page_url(source)}#{anchor}" if source else "",
                "complete_pdf": "rendering-catalogue.pdf",
                "page_pdf": page_pdf(source).as_posix() if source else "",
                "reference": capability["reference"],
            }
        )
    return rows


def _write_coverage_report() -> None:
    rows = _coverage_rows()
    (BUNDLE / "coverage-report.json").write_text(
        json.dumps({"capabilities": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    rendered = []
    for row in rows:
        test_class = "waived" if row["test_status"] == "waived" else "passed"
        links = []
        for label, key in (
            ("Source", "source_url"),
            ("Website", "website_url"),
            ("Complete PDF", "complete_pdf"),
            ("Page PDF", "page_pdf"),
            ("Reference", "reference"),
        ):
            if row[key]:
                links.append(f'<a href="{html.escape(row[key])}">{label}</a>')
        rendered.append(
            "<tr>"
            f"<td><code>{html.escape(row['id'])}</code></td>"
            f"<td>{html.escape(row['title'])}</td>"
            f"<td>{html.escape(row['category'])}</td>"
            f'<td class="{test_class}">{html.escape(row["test_status"])}</td>'
            f"<td>{' · '.join(links)}</td>"
            "</tr>"
        )
    report = (
        _head("Rendering catalogue capability coverage")
        + "<h1>Rendering catalogue capability coverage</h1>\n"
        + f"<p>{len(rows)} reviewed capabilities. Automated status reflects the source and "
        "built-output assertions; visual acceptance still requires human review.</p>\n"
        + "<table><thead><tr><th>ID</th><th>Capability</th><th>Category</th>"
        + "<th>Test status</th><th>Evidence</th></tr></thead><tbody>\n"
        + "\n".join(rendered)
        + "\n</tbody></table>\n</body>\n</html>\n"
    )
    (BUNDLE / "coverage-report.html").write_text(report, encoding="utf-8")


def catalogue_test_functions() -> set[str]:
    """Return the catalogue test node IDs declared in the two test modules."""
    result: set[str] = set()
    for relative in (
        "tests/test_rendering_catalogue.py",
        "tests/test_rendering_catalogue_built.py",
    ):
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                result.add(f"{relative}::{node.name}")
    return result


def test_layers() -> list[dict[str, Any]]:
    """Load and validate the six-layer catalogue test ownership contract."""
    layers = _load(LAYERS)["layer"]
    expected_names = [
        "inventory",
        "source/config",
        "strict build",
        "website semantics",
        "PDF semantics",
        "visual review",
    ]
    if [layer["name"] for layer in layers] != expected_names:
        raise ValueError("The catalogue test layers are missing or out of order")
    assigned = [test for layer in layers for test in layer["tests"]]
    duplicates = sorted({test for test in assigned if assigned.count(test) > 1})
    if duplicates:
        raise ValueError("Catalogue tests assigned more than once: " + ", ".join(duplicates))
    discovered = catalogue_test_functions()
    missing = sorted(discovered - set(assigned))
    unknown = sorted(set(assigned) - discovered)
    if missing or unknown:
        details = []
        if missing:
            details.append("unassigned: " + ", ".join(missing))
        if unknown:
            details.append("unknown: " + ", ".join(unknown))
        raise ValueError("Invalid catalogue test-layer contract (" + "; ".join(details) + ")")
    return layers


def _write_test_layer_report() -> None:
    layers = test_layers()
    (BUNDLE / "test-layers.json").write_text(
        json.dumps({"layers": layers}, indent=2) + "\n", encoding="utf-8"
    )
    rendered = []
    for layer in layers:
        tests = "".join(f"<li><code>{html.escape(test)}</code></li>" for test in layer["tests"])
        rendered.append(
            f"<section><h2>{html.escape(layer['name'])}</h2>"
            f"<p>{html.escape(layer['purpose'])}</p><ul>{tests}</ul></section>"
        )
    report = (
        _head("Rendering catalogue test layers")
        + "<h1>Rendering catalogue test layers</h1>\n"
        + "<p>Every catalogue assertion belongs to exactly one reviewed layer.</p>\n"
        + "\n".join(rendered)
        + "\n</body>\n</html>\n"
    )
    (BUNDLE / "test-layers.html").write_text(report, encoding="utf-8")


def build() -> None:
    """Build the website, complete PDF, page PDFs and review aids."""
    if BUILD.exists():
        shutil.rmtree(BUILD)
    _clear_intermediate_pdfs()
    _write_status("building")
    _run("zensical", "build", "--clean", "--strict")
    _copy_catalogue_site()

    _run("pdk", "pdf")
    generated_complete = DOCS / "site_documentation.pdf"
    _copy_pdf(generated_complete, COMPLETE_PDF)
    _copy_pdf(COMPLETE_PDF, BUNDLE / "rendering-catalogue.pdf")
    generated_complete.unlink()

    for source in catalogue_sources():
        print(f"Building catalogue page PDF: {source}", flush=True)
        _run("pdk", "pdf", "-m", source)
        generated = DOCS / f"{PurePosixPath(source).stem}.pdf"
        _copy_pdf(generated, BUNDLE / page_pdf(source))
        generated.unlink()

    page_count = _render_thumbnails()
    _write_contact_sheet(page_count)
    _write_coverage_report()
    _write_test_layer_report()
    _write_status("built")
    print(f"Built review bundle: {BUNDLE}")


def _assert_meta_robots(path: Path) -> None:
    source = path.read_text(encoding="utf-8").lower()
    expected = f'<meta name="robots" content="{ROBOTS_CONTENT}">'
    if expected not in source:
        raise ValueError(f"Missing crawler metadata: {path}")


def verify() -> None:
    """Verify the complete local review bundle."""
    if json.loads((BUNDLE / "bundle-status.json").read_text(encoding="utf-8"))["status"] != "built":
        raise ValueError("The rendering-review bundle did not finish building")
    if not (BUNDLE / "rendering-catalogue.pdf").read_bytes().startswith(b"%PDF-"):
        raise ValueError("The complete catalogue PDF is missing")
    for source in catalogue_sources():
        output = BUNDLE / page_pdf(source)
        if not output.is_file() or not output.read_bytes().startswith(b"%PDF-"):
            raise ValueError(f"Missing page PDF: {output}")
    for excluded in ("search.json", "sitemap.xml", "sitemap.xml.gz"):
        if list(BUNDLE.rglob(excluded)):
            raise ValueError(f"Crawler-discovery file present in bundle: {excluded}")
    for page in BUNDLE.rglob("*.html"):
        _assert_meta_robots(page)

    report = json.loads((BUNDLE / "coverage-report.json").read_text(encoding="utf-8"))
    expected_ids = {item["id"] for item in _load(LEDGER)["capability"]}
    if {item["id"] for item in report["capabilities"]} != expected_ids:
        raise ValueError("The coverage report does not match catalogue.toml")
    test_layers()
    if not (BUNDLE / "test-layers.html").is_file():
        raise ValueError("The catalogue test-layer report is missing")

    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - CI installs the testing extra.
        raise RuntimeError("Install Prodockit's testing extra to verify the PDF") from error
    with pymupdf.open(BUNDLE / "rendering-catalogue.pdf") as document:
        thumbnails = list((BUNDLE / "thumbnails").glob("page-*.png"))
        if len(thumbnails) != document.page_count:
            raise ValueError("The PDF thumbnail count does not match the complete PDF")
    print(f"Verified review bundle: {BUNDLE}")


def publish(public_site: Path) -> None:
    """Copy the verified bundle beneath the stable hidden Pages route."""
    verify()
    destination = public_site.resolve() / ROUTE
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(BUNDLE, destination)
    print(f"Published rendering catalogue into {destination}")


def verify_publication(public_site: Path) -> None:
    """Verify crawler controls and deployed paths in the public-site tree."""
    public_site = public_site.resolve()
    route = public_site / ROUTE
    if not route.is_dir():
        raise ValueError(f"Missing published route: {route}")
    for page in route.rglob("*.html"):
        _assert_meta_robots(page)
    for filename in ("sitemap.xml", "search.json"):
        path = public_site / filename
        if path.is_file() and f"/{ROUTE}/" in path.read_text(encoding="utf-8"):
            raise ValueError(f"Hidden route leaked into {filename}")
    robots = (public_site / "robots.txt").read_text(encoding="utf-8")
    if f"Disallow: /{ROUTE}/" not in robots or "User-agent: *" not in robots:
        raise ValueError("robots.txt does not disallow the rendering-review route")
    for required in (
        route / "index.html",
        route / "rendering-catalogue.pdf",
        route / "contact-sheet.html",
        route / "coverage-report.html",
        route / "test-layers.html",
    ):
        if not required.is_file():
            raise ValueError(f"Missing published review artifact: {required}")
    print(f"Verified hidden publication route: {route}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify", "publish", "verify-publication"))
    parser.add_argument("--public-site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "verify":
        verify()
    elif args.action == "publish":
        publish(args.public_site)
    else:
        verify_publication(args.public_site)


if __name__ == "__main__":
    main()

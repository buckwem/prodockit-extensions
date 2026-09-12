# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Keep documentation PDF actions and published artifacts in step with the matrix.

The ``covered`` entries are test coverage, not downloadable documents. Only
``build`` entries get actions. Keep the CLI's flat outputs for existing consumers,
but snapshot each build under its full source path before another can overwrite it.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = "overrides/partials/page-pdf.html"


def targets(root: Path) -> dict[str, str]:
    with (root / ".github/docs-single-page-pdfs.toml").open("rb") as source:
        matrix = tomllib.load(source)
    result = {}
    urls: set[str] = set()
    for paths in matrix["build"].values():
        for source in paths:
            path = PurePosixPath(source)
            if path.is_absolute() or ".." in path.parts or path.suffix != ".md":
                raise ValueError(f"Invalid PDF source: {source}")
            if source in result or page_url(source) in urls:
                raise ValueError(f"Duplicate PDF page: {source}")
            urls.add(page_url(source))
            result[source] = f"page-pdfs/{path.with_suffix('.pdf')}"
    return result


def page_url(source: str) -> str:
    path = PurePosixPath(source)
    stem = path.parent if path.name == "index.md" else path.with_suffix("")
    return "" if str(stem) == "." else f"{stem}/"


def partial(root: Path) -> str:
    lines = [
        "{# Generated from .github/docs-single-page-pdfs.toml; see tools/docs_page_pdfs.py. #}"
    ]
    for source, target in targets(root).items():
        lines.extend([
            '{% if page.url == "' + page_url(source) + '" %}',
            '<a href="{{ "' + target + '" | url }}" title="Download this page as PDF"'
            ' class="md-content__button md-icon">',
            '  {% include ".icons/material/file-pdf-box.svg" %}',
            "</a>",
            "{% endif %}",
        ])
    return "\n".join(lines) + "\n"


def check_partial(root: Path) -> None:
    if (root / PARTIAL).read_text(encoding="utf-8") != partial(root):
        raise ValueError("PDF action partial is stale; run python tools/docs_page_pdfs.py generate")


def publish(source: str, root: Path = ROOT) -> None:
    target = targets(root)[source]
    built = root / "docs" / f"{PurePosixPath(source).stem}.pdf"
    if not built.read_bytes().startswith(b"%PDF-"):
        raise ValueError(f"Not a PDF: {built}")
    # docs survives the later clean canonical-site rebuild; site supports the
    # earlier build checks. Copy immediately after this source's successful build.
    for directory in ("docs", "site"):
        destination = root / directory / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built, destination)


class Actions(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("title") == "Download this page as PDF":
            self.links.append(values.get("href") or "")


def verify(root: Path = ROOT) -> None:
    """Check every emitted action, including absence on non-matrix pages."""
    check_partial(root)
    expected = {page_url(source) + "index.html": target
                for source, target in targets(root).items()}
    seen = set()
    for html in (root / "site").rglob("*.html"):
        relative = html.relative_to(root / "site").as_posix()
        parser = Actions()
        parser.feed(html.read_text(encoding="utf-8"))
        target = expected.get(relative)
        if target is None:
            if parser.links:
                raise ValueError(f"Unexpected PDF action on {relative}")
            continue
        seen.add(relative)
        resolved = [unquote(urlsplit(urljoin('/' + relative, href)).path).lstrip('/')
                    for href in parser.links]
        if resolved != [target] or any(urlsplit(href).netloc for href in parser.links):
            raise ValueError(f"Incorrect PDF action on {relative}: {parser.links}")
        artifact = root / "site" / target
        if not artifact.is_file() or not artifact.read_bytes().startswith(b"%PDF-"):
            raise ValueError(f"Missing PDF artifact for {relative}: {target}")
    if missing := set(expected) - seen:
        raise ValueError(f"Missing PDF pages: {sorted(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("generate", "check", "verify"))
    args = parser.parse_args()
    if args.action == "generate":
        (ROOT / PARTIAL).write_text(partial(ROOT), encoding="utf-8")
    elif args.action == "check":
        check_partial(ROOT)
    else:
        verify()


if __name__ == "__main__":
    main()

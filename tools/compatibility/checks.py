# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT
"""Evidence collection for the Zensical CLI compatibility gate."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def command(args: list[str], cwd: Path, log: Path, timeout: int = 1200) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                args, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, timeout=timeout, check=False
            )
        return {"command": args, "exit": result.returncode, "log": str(log)}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": args, "exit": None, "log": str(log), "error": str(error)}


def classify(
    exit_code: int | None, output: str, *, version: str, name: str, reject: bool = False
) -> str:
    # Exact version and diagnostic: an unrelated crash must never become XFAIL.
    if name == "mike" and version == "0.0.61":
        if exit_code == 0:
            return "xpass"
        if exit_code == 1 and "unknown mike option: version_selector" in output:
            return "xfail"
        return "failed"
    if exit_code is None:
        return "error"
    if reject and name == "invalid-mapping":
        return (
            "passed" if exit_code == 1 and "configurations must be mappings" in output else "failed"
        )
    if reject and name == "redirect-cycle":
        diagnosed = "cycle" in output.lower() or (
            "Redirect target" in output and "Aborted because --strict" in output
        )
        return "passed" if exit_code == 1 and diagnosed else "failed"
    return "passed" if (exit_code != 0 if reject else exit_code == 0) else "failed"


def junit_counts(path: Path) -> dict:
    if not path.exists():
        return {"status": "not-run", "executed": 0}
    cases = list(ET.parse(path).getroot().iter("testcase"))
    counts = Counter(
        "error"
        if c.find("error") is not None
        else "failed"
        if c.find("failure") is not None
        else "skipped"
        if c.find("skipped") is not None
        else "passed"
        for c in cases
    )
    return {"status": "executed", "executed": len(cases) - counts["skipped"], **counts}


def probes(
    root: Path, version: str, browser_script: Path | None = None, *, full: bool = False
) -> list[dict]:
    import yaml
    from bs4 import BeautifulSoup
    from packaging.version import Version

    current = Version(version)
    cases = {
        "defaults": {},
        "mike": {"plugins": {"mike": {"version_selector": False}}},
        "search": {"plugins": {"search": {"lang": ["en"], "indexing": "full"}}},
        "autorefs": {"plugins": {"autorefs": {"resolve_closest": True}}},
        "invalid-mapping": {"markdown_extensions": {"admonition": False}},
        "page-redirect": {"plugins": {"redirects": {"redirect_maps": {"old.md": "index.md"}}}},
        "anchor-redirect": {
            "plugins": {"redirects": {"redirect_maps": {"index.md#old": "index.md#new"}}}
        },
        "redirect-chain": {
            "plugins": {
                "redirects": {"redirect_maps": {"old.md": "middle.md", "middle.md": "index.md"}}
            }
        },
        "redirect-cycle": {
            "plugins": {
                "redirects": {"redirect_maps": {"old.md": "middle.md", "middle.md": "old.md"}}
            }
        },
        "table-reader": {"plugins": {"table-reader": {}}},
        "macro-include": {"plugins": {"macros": {"module_name": "", "include_dir": "includes"}}},
    }
    cases["windows-macro-include"] = {
        "plugins": {"macros": {"module_name": "", "include_dir": "includes"}}
    }
    results = []
    exe = str(Path(sys.executable).with_name("zensical.exe" if os.name == "nt" else "zensical"))
    for name, extra in cases.items():
        if name == "windows-macro-include" and os.name != "nt":
            results.append(
                {"name": name, "status": "not-applicable", "reason": "Windows-only path"}
            )
            continue
        if name == "windows-macro-include" and current < Version("0.0.60"):
            results.append({"name": name, "status": "not-supported", "since": "0.0.60"})
            continue
        minimum = "0.0.60" if name == "table-reader" else "0.0.61"
        if name in {"anchor-redirect", "redirect-chain", "table-reader"} and current < Version(
            minimum
        ):
            results.append({"name": name, "status": "not-supported", "since": minimum})
            continue
        folder = root / name
        (folder / "docs").mkdir(parents=True)
        content = "# Home\n\n## New {#new}\n"
        if name == "table-reader":
            (folder / "data.csv").write_text("Name,Count\nGateMarker,7\n", encoding="utf-8")
            content += '\n{{ read_csv("data.csv") }}\n'
        if name in {"macro-include", "windows-macro-include"}:
            content = "# Home\n"
            extra["plugins"]["macros"]["on_error_fail"] = True
            # On Windows exercise the actual extended-length loader path.
            include = folder / "includes"
            if name == "windows-macro-include":
                include = include / ("long-directory-" * 12) / ("nested-" * 12)
                include = Path("\\\\?\\" + str(include.resolve()))
            include.mkdir(parents=True)
            (include / "part.md").write_text("IncludedGateMarker", encoding="utf-8")
            extra["plugins"]["macros"]["include_dir"] = str(include)
            content += '\n{% include "part.md" %}\n'
        (folder / "docs/index.md").write_text(content, encoding="utf-8")
        (folder / "mkdocs.yml").write_text(
            yaml.safe_dump({"site_name": "Compatibility", "nav": [{"Home": "index.md"}], **extra}),
            encoding="utf-8",
        )
        result = command([exe, "build", "--clean", "--strict"], folder, folder / "build.log", 90)
        output = (folder / "build.log").read_text(encoding="utf-8")
        reject = name == "redirect-cycle" or (
            name == "invalid-mapping" and current >= Version("0.0.60")
        )
        status = classify(result["exit"], output, version=version, name=name, reject=reject)
        row = {
            "name": name,
            "status": status,
            "expectation": "reject-invalid-input" if reject else "build",
            **result,
        }
        if name == "invalid-mapping":
            if not reject:
                row["expectation"] = "tolerated-invalid-input"
            row["classification"] = (
                "invalid input; baseline tolerance is not a compatibility promise"
            )
        if name == "mike":
            row["limitation"] = "https://github.com/buckwem/prodockit-extensions/issues/799"
        if status == "passed" and not reject:
            html = (folder / "site/index.html").read_text(encoding="utf-8")
            if name == "table-reader":
                table = BeautifulSoup(html, "html.parser").select_one("article table")
                if table is None or "GateMarker" not in table.get_text():
                    row.update(status="failed", error="CSV table did not render")
            if (
                name in {"macro-include", "windows-macro-include"}
                and "IncludedGateMarker" not in html
            ):
                row.update(status="failed", error="Include did not render")
            if name == "anchor-redirect":
                manifest = json.loads((folder / "site/redirect.json").read_text())
                if manifest.get("#old") != "#new":
                    row.update(status="failed", error="Anchor manifest is incorrect")
            if name in {"redirect-chain", "page-redirect"}:
                redirect = (folder / "site/old/index.html").read_text(encoding="utf-8")
                if "../" not in redirect or "middle" in redirect:
                    row.update(status="failed", error="Redirect did not resolve to final target")
        results.append(row)
        if name in {"anchor-redirect", "redirect-chain", "page-redirect"} and status == "passed":
            browser = {"name": name + "-browser", "status": "not-run"}
            if browser_script:
                start = "#old" if name == "anchor-redirect" else "old/"
                end = "/#new" if name == "anchor-redirect" else "/"
                run = command(
                    ["node", str(browser_script), str(folder / "site"), start, end],
                    folder,
                    folder / "browser.log",
                    90,
                )
                browser.update(run, status="passed" if run["exit"] == 0 else "failed")
            results.append(browser)
        if name in {"table-reader", "anchor-redirect"} and row["status"] == "passed":
            pdf_result = {"name": name + "-pdf", "status": "not-run"}
            if full:
                pdk = str(
                    Path(sys.executable).with_name(
                        "prodockit.exe" if os.name == "nt" else "prodockit"
                    )
                )
                run = command([pdk, "pdf", "-f", "mkdocs.yml"], folder, folder / "pdf.log")
                pdf_result.update(run, status="passed" if run["exit"] == 0 else "failed")
                if run["exit"] == 0:
                    import pymupdf

                    with pymupdf.open(folder / "docs/site_documentation.pdf") as pdf:
                        text = "".join(page.get_text() for page in pdf)
                        marker = "GateMarker" if name == "table-reader" else "New"
                        if marker not in text or "read_csv(" in text:
                            pdf_result.update(
                                status="failed", error="Feature PDF content missing or raw"
                            )
                    pdf_result["scope"] = "feature fixture only; not whole-document qualification"
                    if name == "anchor-redirect":
                        pdf_result["limitation"] = (
                            "Target content renders; JavaScript alias navigation is website-only"
                        )
            results.append(pdf_result)
    return results


def pdf_snapshot(path: Path, project: Path) -> dict:
    import pymupdf

    with pymupdf.open(path) as doc:
        pages = []
        problems = []
        for number, page in enumerate(doc, 1):
            links = [
                {
                    k: str(v) if isinstance(v, (pymupdf.Rect, pymupdf.Point)) else v
                    for k, v in link.items()
                    if k not in {"xref", "id"}
                }
                for link in page.get_links()
            ]
            for link in links:
                uri = link.get("uri", "")
                if str(project) in uri or "/blob/main//" in uri or uri.startswith("file:"):
                    problems.append({"page": number, "invalid_uri": uri})
            pix = page.get_pixmap(dpi=144)
            pages.append(
                {
                    "page": number,
                    "dimensions": list(page.rect),
                    "text": page.get_text(),
                    "pixels": hashlib.sha256(pix.samples).hexdigest(),
                    "links": links,
                }
            )
        return {
            "scope": "complete-document",
            "page_count": len(doc),
            "bookmarks": doc.get_toc(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pages": pages,
            "problems": problems,
            "raster_dpi": 144,
        }


def site_snapshot(root: Path) -> dict:
    from bs4 import BeautifulSoup

    from prodockit.pdf.site import output_path, published_pdf_path
    from prodockit.project_config import load_project_config
    from prodockit.settings import flatten_nav

    config = load_project_config(
        str(next(p for p in (root / "zensical.toml", root / "mkdocs.yml") if p.exists()))
    )
    nav = flatten_nav(config.project.get("nav") or [])
    paths = [
        output_path(
            p["url"], config.site_dir, directory_urls=config.project.get("use_directory_urls", True)
        )
        for p in nav
    ]
    inventory = {
        str(p.relative_to(config.site_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in config.site_dir.rglob("*")
        if p.is_file()
    }
    articles = {}
    missing_assets = []
    for p in config.site_dir.rglob("*.html"):
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        article = soup.select_one("article.md-content__inner")
        for asset in soup.select("script[src], link[rel=stylesheet][href]"):
            link = urlsplit(asset.get("src") or asset["href"])
            if not link.scheme and not link.netloc:
                asset_path = unquote(link.path)
                if asset_path.startswith("/"):
                    mount = urlsplit(config.project.get("site_url", "")).path.rstrip("/") + "/"
                    if asset_path.startswith(mount):
                        asset_path = asset_path[len(mount) :]
                    base = config.site_dir
                else:
                    base = p.parent
                if not (base / asset_path.lstrip("/")).is_file():
                    missing_assets.append(
                        {"page": str(p.relative_to(config.site_dir)), "asset": link.path}
                    )
        if article:
            articles[str(p.relative_to(config.site_dir))] = hashlib.sha256(
                str(article).encode()
            ).hexdigest()
    pdfs, publications = {}, {}
    for p in config.docs_dir.glob("*.pdf"):
        # Generated outputs only: do not treat an embedded author PDF as a complete build.
        if p.name not in {"site_documentation.pdf", "source_bundle.pdf"}:
            continue
        pdfs[p.name] = pdf_snapshot(p, root)
        published = published_pdf_path(config, p)
        publications[p.name] = bool(
            published and published.exists() and published.read_bytes() == p.read_bytes()
        )
    return {
        "nav_total": len(paths),
        "nav_missing": [str(p) for p in paths if not p.exists()],
        "inventory": inventory,
        "missing_assets": missing_assets,
        "articles": articles,
        "pdfs": pdfs,
        "publications": publications,
    }


def compare_snapshots(a: dict, b: dict) -> dict:
    result = {
        "inventory_equal": a["inventory"] == b["inventory"],
        "articles_equal": a["articles"] == b["articles"],
        "pdfs": {},
    }
    for name in sorted(a["pdfs"].keys() | b["pdfs"].keys()):
        x, y = a["pdfs"].get(name), b["pdfs"].get(name)
        if x is None or y is None:
            result["pdfs"][name] = {"missing": True}
            continue
        result["pdfs"][name] = {
            "page_counts": [x["page_count"], y["page_count"]],
            "bookmarks_equal": x["bookmarks"] == y["bookmarks"],
            "byte_equal": x["sha256"] == y["sha256"],
            "differences": {
                field: [
                    n + 1
                    for n in range(max(len(x["pages"]), len(y["pages"])))
                    if n >= len(x["pages"])
                    or n >= len(y["pages"])
                    or x["pages"][n][field] != y["pages"][n][field]
                ]
                for field in ("text", "pixels", "dimensions", "links")
            },
        }
    return result


def environment() -> dict:
    from importlib.metadata import distributions

    binaries = {}
    for name in ("node", "npm", "pandoc"):
        executable = shutil.which(name)
        if executable:
            try:
                run = subprocess.run(
                    [executable, "--version"], capture_output=True, text=True, timeout=10
                )
                binaries[name] = (
                    run.stdout.splitlines()[0]
                    if run.returncode == 0 and run.stdout
                    else "unavailable"
                )
            except (OSError, subprocess.TimeoutExpired):
                binaries[name] = "unavailable"
        else:
            binaries[name] = "not installed"
    return {
        "binaries": binaries,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {
            d.metadata["Name"].lower().replace("_", "-"): d.version for d in distributions()
        },
    }

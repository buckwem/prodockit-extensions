# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Read and publish document content around Zensical's built output.

Zensical remains responsible for Markdown rendering. Prodockit validates and
extracts the already-rendered articles from a completed website; it neither
invokes Zensical nor imports its Python package internals.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]
from bs4 import BeautifulSoup

from prodockit.project_config import ProjectConfig


class BuiltSiteError(RuntimeError):
    """A documented Zensical build or its output cannot be consumed."""


def validate_built_site(config: ProjectConfig, source_paths: list[str]) -> None:
    """Validate the completed Zensical output needed by a PDF build.

    This deliberately checks existence and structure, not freshness. A macro
    may depend on Git or external state, so source/output mtimes cannot prove
    that an arbitrary static build is current.
    """
    instruction = "run `zensical build --clean --strict` first"
    if not config.site_dir.is_dir():
        raise BuiltSiteError(f"built site not found: {config.site_dir}; {instruction}")
    index = config.site_dir / "index.html"
    if not index.is_file():
        raise BuiltSiteError(f"built site has no index page: {index}; {instruction}")

    directory_urls = bool(config.project.get("use_directory_urls", True))
    missing = []
    for source in source_paths:
        generated = output_path(source, config.site_dir, directory_urls=directory_urls)
        if not generated.is_file():
            missing.append(generated)
    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise BuiltSiteError(f"built site is incomplete; missing {rendered}; {instruction}")


def published_pdf_path(config: ProjectConfig, pdf_path: str | Path) -> Path | None:
    """Return the matching built-site path for an author PDF, if any.

    Only files inside ``docs_dir`` are website assets. An explicitly
    configured output elsewhere remains outside the built website.
    """
    source = Path(pdf_path)
    source = source.resolve() if source.is_absolute() else (config.root / source).resolve()
    try:
        relative = source.relative_to(config.docs_dir)
    except ValueError:
        return None
    return (config.site_dir / relative).resolve()


def publish_pdf_to_built_site(config: ProjectConfig, pdf_path: str | Path) -> Path | None:
    """Atomically mirror an author PDF below ``docs_dir`` into ``site_dir``."""
    source = Path(pdf_path)
    source = source.resolve() if source.is_absolute() else (config.root / source).resolve()
    destination = published_pdf_path(config, source)
    if destination is None or destination == source:
        return destination
    if not source.is_file():
        raise BuiltSiteError(f"PDF renderer did not create the expected output: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def output_path(source_path: str, site_dir: Path, *, directory_urls: bool = True) -> Path:
    """Map one nav Markdown path to its documented generated HTML path."""
    source = PurePosixPath(source_path)
    if source.suffix.lower() != ".md":
        raise BuiltSiteError(f"navigation target is not a Markdown page: {source_path}")
    if source.name.lower() == "index.md":
        relative = source.with_suffix(".html")
    elif directory_urls:
        relative = source.with_suffix("") / "index.html"
    else:
        relative = source.with_suffix(".html")
    return site_dir.joinpath(*relative.parts)


def page_html(
    config: ProjectConfig,
    source_path: str,
    *,
    directory_urls: bool | None = None,
) -> str:
    """Extract only the rendered document article for ``source_path``."""
    if directory_urls is None:
        directory_urls = bool(config.project.get("use_directory_urls", True))
    path = output_path(source_path, config.site_dir, directory_urls=directory_urls)
    if not path.is_file():
        raise BuiltSiteError(f"zensical build did not create the expected page: {path}")
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    article = soup.select_one("article.md-content__inner.md-typeset")
    if article is None:
        raise BuiltSiteError(
            f"could not find the document article in {path}; the generated HTML layout changed"
        )
    for website_only in article.select(":scope > a, :scope > footer, nav.md-tags, .md-feedback"):
        website_only.decompose()
    # ``str(Comment(...))`` returns only the comment body, without ``<!--``
    # and ``-->``. Joining the children therefore turns source comments into
    # visible PDF prose. Encoding the article's inner HTML preserves node
    # types while still excluding the outer website-only article wrapper.
    return article.decode_contents().strip()


def page_metadata(source_file: Path) -> dict[str, Any]:
    """Read a page's YAML front matter without invoking Zensical."""
    text = source_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise BuiltSiteError(f"unterminated YAML front matter in {source_file}") from None
    try:
        value = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as error:
        raise BuiltSiteError(f"invalid YAML front matter in {source_file}: {error}") from error
    if not isinstance(value, dict):
        raise BuiltSiteError(f"YAML front matter in {source_file} must be a mapping")
    return value

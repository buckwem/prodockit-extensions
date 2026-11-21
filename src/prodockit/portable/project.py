# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Managed generations and public Zensical CLI orchestration for the prototype."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import tomlkit
from bs4 import BeautifulSoup

from prodockit import __version__
from prodockit._zensical_defaults import DOCUMENTED_MARKDOWN_DEFAULTS
from prodockit.pdf.site import output_path
from prodockit.portable import PortableError
from prodockit.portable.compiler import compile_pages, scan
from prodockit.project_config import CONFIG_OVERRIDE_ENV, ProjectConfig, load_project_config

MIGRATED = {"prodockit.headings", "prodockit.refs", "prodockit.bibliography"}
PENDING = {"prodockit.citations", "prodockit.glossary", "prodockit.tables"}


@dataclass(frozen=True)
class Prepared:
    config: Path
    manifest: Path
    site: Path


def _workspace(config: ProjectConfig) -> Path:
    return config.root / ".pdk" / "portable"


@contextmanager
def workspace_lock(config: ProjectConfig) -> Iterator[None]:
    root = _workspace(config)
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("*\n", encoding="utf-8")
    lock = root / "lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise PortableError(
            f"portable workspace is in use; if no process is running, remove {lock}"
        ) from error
    try:
        (lock / "pid").write_text(str(os.getpid()), encoding="utf-8")
        yield
    finally:
        shutil.rmtree(lock)


def _check_config(config: ProjectConfig) -> None:
    if config.path.suffix != ".toml":
        raise PortableError("the feasibility prototype currently accepts zensical.toml only")
    if not config.docs_dir.is_dir() or config.docs_dir == config.root:
        raise PortableError("the prototype needs an existing docs directory below the project root")
    if not config.docs_dir.is_relative_to(config.root):
        raise PortableError("the prototype needs docs_dir inside the original project")
    if _workspace(config).is_relative_to(config.docs_dir):
        raise PortableError("docs_dir must not contain the portable workspace")
    for key in ("plugins", "watch", "draft_docs", "exclude_docs", "not_in_nav"):
        if config.project.get(key):
            raise PortableError(
                f"{key} is outside the feasibility prototype; use the existing mode"
            )
    if (config.project.get("theme") or {}).get("custom_dir"):
        raise PortableError("custom theme directories are outside the feasibility prototype")
    for name, options in config.markdown_extensions.items():
        if name in PENDING or name.startswith(
            ("zensical.extensions.macros", "pymdownx.snippets", "pymdownx.blocks.")
        ):
            raise PortableError(
                f"{name} is outside the feasibility prototype; use the existing mode"
            )
        if name in MIGRATED and options.get("source"):
            raise PortableError(f"explicit {name}.source is outside the feasibility prototype")
        if name == "prodockit.headings":
            unknown = set(options) - {"numbering", "appendix_attr"}
            if unknown or options.get("numbering", "per-document") not in {
                "continuous",
                "per-document",
            }:
                raise PortableError("unsupported heading settings in the feasibility prototype")
        if name == "toc" and (options.get("slugify") or options.get("separator", "-") != "-"):
            raise PortableError("custom slugging is outside the feasibility prototype")
    if MIGRATED & config.markdown_extensions.keys() and not {"attr_list", "toc"}.issubset(
        config.markdown_extensions
    ):
        raise PortableError("the prototype requires explicit attr_list and toc configuration")


def input_snapshot(config: ProjectConfig) -> tuple[dict[str, str], dict[str, str]]:
    """Content hashes include all copied assets and bibliography inputs."""
    _check_config(config)
    files = {config.path}
    sources: dict[str, str] = {}
    for path in sorted(config.docs_dir.rglob("*")):
        if path.is_symlink():
            raise PortableError(f"symlinked source is outside the feasibility prototype: {path}")
        if path.is_file():
            files.add(path)
            if path.suffix.lower() == ".md":
                sources[path.relative_to(config.docs_dir).as_posix()] = path.read_text(
                    encoding="utf-8"
                )
    bib_options = config.markdown_extensions.get("prodockit.bibliography", {})
    for name in ("bib_file", "csl_style"):
        value = bib_options.get(name)
        if value:
            files.add((config.root / str(value)).resolve())
    for source, text in sources.items():
        for edit in scan(source, text).edits:
            if edit.kind in {"cite", "bibliography"}:
                files.add(
                    (config.root / str(bib_options.get("bib_file", "references.bib"))).resolve()
                )
            if edit.kind == "bibliography" and edit.key:
                files.add((config.root / edit.key).resolve())
    try:
        hashes = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)
        }
    except OSError as error:
        raise PortableError(f"cannot read build input: {error}") from error
    return hashes, sources


def _generated_config(config: ProjectConfig) -> dict[str, Any]:
    project = copy.deepcopy(config.project)
    project.update(docs_dir="docs", site_dir="site")
    extensions = copy.deepcopy(config.markdown_extensions)
    if "markdown_extensions" not in project:
        extensions = copy.deepcopy(DOCUMENTED_MARKDOWN_DEFAULTS)
    for name in MIGRATED:
        extensions.pop(name, None)
    # Only the migrated custom formatter is removed; Mermaid and other fences stay.
    superfences = extensions.get("pymdownx.superfences", {})
    if "custom_fences" in superfences:
        superfences["custom_fences"] = [
            fence
            for fence in superfences["custom_fences"]
            if fence.get("format") != "prodockit.image_hotspots.format_hotspots"
        ]
    project["markdown_extensions"] = extensions
    return {"project": project}


def _prepare(config: ProjectConfig, *, pandoc: Path | None = None) -> Prepared:
    before, sources = input_snapshot(config)
    pandoc = pandoc.resolve() if pandoc is not None else None
    output, pages, _dependencies = compile_pages(config, sources, pandoc=pandoc)
    directory = _workspace(config) / "generations"
    directory.mkdir(exist_ok=True)
    generation = Path(tempfile.mkdtemp(prefix="generation-", dir=directory))
    try:
        shutil.copytree(config.docs_dir, generation / "docs")
        for name, text in output.items():
            (generation / "docs" / name).write_text(text, encoding="utf-8")
        generated_config = generation / "zensical.toml"
        generated_config.write_text(tomlkit.dumps(_generated_config(config)), encoding="utf-8")
        after, _ = input_snapshot(load_project_config(str(config.path)))
        if before != after:
            raise PortableError(
                "source inputs changed during preparation; retry with a stable snapshot"
            )
        manifest = {
            "schema": 1,
            "mode": "portable",
            "prodockit": __version__,
            "original_config": str(config.path),
            "input_hashes": before,
            "generation": generation.name,
            "directory_urls": bool(config.project.get("use_directory_urls", True)),
            "pages": pages,
            "generated_hashes": {
                str(path.relative_to(generation)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(generation.rglob("*"))
                if path.is_file()
            },
        }
        manifest_path = generation / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return Prepared(generated_config, manifest_path, generation / "site")
    except BaseException:
        shutil.rmtree(generation)
        raise


def prepare(config_file: str, *, pandoc: Path | None = None) -> Prepared:
    config = load_project_config(config_file)
    with workspace_lock(config):
        return _prepare(config, pandoc=pandoc)


def command(config: Path, action: str, *options: str) -> list[str]:
    return [sys.executable, "-m", "zensical", action, "--config-file", str(config), *options]


def _environment(config: Path) -> dict[str, str]:
    return {**os.environ, CONFIG_OVERRIDE_ENV: str(config)}


def validate(prepared: Prepared, *, fresh: bool = True) -> None:
    manifest = json.loads(prepared.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("mode") != "portable":
        raise PortableError("not a supported portable generation manifest")
    if fresh:
        hashes, _ = input_snapshot(load_project_config(manifest["original_config"]))
        if hashes != manifest["input_hashes"]:
            raise PortableError("portable output is stale; prepare and build again")
    root = prepared.config.parent
    for name, digest in manifest["generated_hashes"].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise PortableError(f"prepared input changed: {name}; prepare and build again")
    soups: dict[str, BeautifulSoup] = {}
    for source, details in manifest["pages"].items():
        path = output_path(source, prepared.site, directory_urls=manifest["directory_urls"])
        if not path.is_file():
            raise PortableError(f"build is incomplete: missing {path}")
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        article = soup.select_one("article.md-content__inner.md-typeset")
        if article is None:
            raise PortableError(f"{source}: cannot find the built article")
        for target in details["targets"]:
            heading = article.find(id=target["id"])
            if heading is None or heading.name not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                raise PortableError(
                    f"{source}: heading anchor {target['id']!r} did not survive rendering"
                )
            visible = copy.copy(heading)
            for permalink in visible.select("a.headerlink"):
                permalink.decompose()
            if visible.get_text().strip() != target["text"]:
                raise PortableError(
                    f"{source}: rendered heading {target['id']!r} differs from its collected text; "
                    "this heading syntax is not yet qualified for portable preparation"
                )
        soups[source] = soup
    for source, details in manifest["pages"].items():
        current = output_path(source, prepared.site, directory_urls=manifest["directory_urls"])
        actual: Counter[tuple[Path, str, str]] = Counter()
        for anchor in soups[source].select(
            "a.prodockit-ref, a.prodockit-autoref, .prodockit-bib-cite a, a.pdk-hotspots-region"
        ):
            parts = urlsplit(str(anchor.get("href", "")))
            if parts.scheme or parts.netloc:
                continue
            target_path = (
                (current.parent / unquote(parts.path)).resolve() if parts.path else current
            )
            if target_path.is_dir():
                target_path /= "index.html"
            if not target_path.is_file():
                raise PortableError(
                    f"{source}: generated link does not exist: {anchor.get('href')}"
                )
            target_soup = BeautifulSoup(target_path.read_text(encoding="utf-8"), "html.parser")
            if parts.fragment and target_soup.find(id=unquote(parts.fragment)) is None:
                raise PortableError(
                    f"{source}: generated link has no target anchor: {anchor.get('href')}"
                )
            actual[(target_path, unquote(parts.fragment), anchor.get_text(" ", strip=True))] += 1
        for link in details["links"]:
            expected = output_path(
                link["page"], prepared.site, directory_urls=manifest["directory_urls"]
            )
            key = (expected, link["id"], link["text"])
            if actual[key] < 1:
                raise PortableError(
                    f"{source}: expected reference to {link['page']}#{link['id']} "
                    "is missing or its label changed"
                )
            actual[key] -= 1
        for image in soups[source].select(".pdk-hotspots img"):
            target = (current.parent / unquote(urlsplit(str(image.get("src", ""))).path)).resolve()
            if not target.is_file():
                raise PortableError(f"{source}: hotspot image did not survive the build")


def _build(prepared: Prepared, *, clean: bool = False, strict: bool = True) -> None:
    options = (["--clean"] if clean else []) + (["--strict"] if strict else [])
    result = subprocess.run(
        command(prepared.config, "build", *options),
        env=_environment(prepared.config),
        cwd=prepared.config.parent,
        check=False,
    )
    if result.returncode:
        raise PortableError(f"Zensical build failed with status {result.returncode}")
    validate(prepared)
    version = subprocess.run(
        [sys.executable, "-m", "zensical", "--version"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    (prepared.site / ".pdk-build.json").write_text(
        json.dumps(
            {
                "mode": "portable",
                "generation": prepared.config.parent.name,
                "zensical": version,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def build(
    config_file: str, *, pandoc: Path | None = None, clean: bool = False, strict: bool = True
) -> Prepared:
    config = load_project_config(config_file)
    with workspace_lock(config):
        prepared = _prepare(config, pandoc=pandoc)
        _build(prepared, clean=clean, strict=strict)
        return prepared


def _stop(process: subprocess.Popen[Any]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _start(prepared: Prepared, address: str) -> subprocess.Popen[Any]:
    try:
        host, port = address.rsplit(":", 1)
        if host not in {"localhost", "127.0.0.1"}:
            raise ValueError("use localhost or 127.0.0.1 for this prototype")
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, int(port)))
    except (OSError, ValueError) as error:
        raise PortableError(f"preview address is unavailable: {address}: {error}") from error
    process = subprocess.Popen(
        command(prepared.config, "serve", "--dev-addr", address),
        env=_environment(prepared.config),
        cwd=prepared.config.parent,
    )
    try:
        deadline = time.monotonic() + 20
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise PortableError(f"Zensical preview exited with status {process.returncode}")
            try:
                with opener.open(f"http://{address}/", timeout=0.25) as response:
                    if response.status == 200:
                        return process
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        raise PortableError("Zensical preview did not become ready within 20 seconds")
    except BaseException:
        _stop(process)
        raise


def serve(
    config_file: str,
    *,
    pandoc: Path | None = None,
    address: str = "127.0.0.1:8000",
    report: Callable[[str], None] = print,
) -> None:
    config = load_project_config(config_file)
    if not (config.docs_dir / "index.md").is_file():
        raise PortableError("supervised preview currently requires docs/index.md")
    with workspace_lock(config):
        prepared = _prepare(config, pandoc=pandoc)
        _build(prepared)
        process = _start(prepared, address)
        try:
            report(f"Portable preview: http://{address}/ (watching original sources)")
            # A source edit while the server starts must trigger the next build.
            last = json.loads(prepared.manifest.read_text(encoding="utf-8"))["input_hashes"]
            last_error = ""
            while True:
                time.sleep(0.5)
                if process.poll() is not None:
                    raise PortableError(
                        f"Zensical preview stopped with status {process.returncode}"
                    )
                try:
                    current = load_project_config(config_file)
                    fingerprint = input_snapshot(current)[0]
                    if fingerprint == last:
                        continue
                    last = fingerprint
                    candidate = _prepare(current, pandoc=pandoc)
                    _build(candidate)
                    _stop(process)
                    try:
                        process = _start(candidate, address)
                    except PortableError:
                        process = _start(prepared, address)
                        raise
                    prepared = candidate
                    report("Portable preview updated from a complete source generation.")
                    last_error = ""
                except (OSError, ValueError, RuntimeError) as error:
                    if str(error) != last_error:
                        report(f"Keeping the previous preview: {error}")
                        last_error = str(error)
        finally:
            _stop(process)

# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Managed generations and public Zensical CLI orchestration for the prototype."""

from __future__ import annotations

import copy
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
from types import MappingProxyType
from typing import Any
from urllib.parse import unquote, urlsplit

import tomlkit
from bs4 import BeautifulSoup

from prodockit import __version__
from prodockit._zensical_defaults import DOCUMENTED_MARKDOWN_DEFAULTS
from prodockit.headings import PREPARED_CAPTION_NUMBER_ATTR, PREPARED_CAPTION_PREFIX
from prodockit.pdf.site import output_path
from prodockit.portable import PortableError, macros, snippets
from prodockit.portable.captions import CAPTION_EXTENSION
from prodockit.portable.compiler import (
    BIBLIOGRAPHY_MARKERS,
    DEFINITION_EXTENSIONS,
    compile_pages,
    scan,
)
from prodockit.portable.inputs import SNIPPETS_DIRECTORY, InputSnapshot, digest
from prodockit.portable.manifest import (
    SCHEMA,
    generated_hashes,
    read_manifest,
    toolchain,
    validate_inputs,
    write_manifest,
)
from prodockit.project_config import (
    CONFIG_OVERRIDE_ENV,
    ProjectConfig,
    load_project_config,
    parse_project_config,
)

HEADING_AND_BIBLIOGRAPHY = {"prodockit.headings", "prodockit.refs", "prodockit.bibliography"}
MIGRATED = HEADING_AND_BIBLIOGRAPHY | set(DEFINITION_EXTENSIONS.values())
_PREVIEW_ERRORS = (OSError, ValueError, RuntimeError)
_PREVIEW_RETRY_SECONDS = 5.0


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
    for name, options in config.markdown_extensions.items():
        if name not in {CAPTION_EXTENSION, macros.EXTENSION} and name.startswith(
            ("pymdownx.blocks.", macros.EXTENSION)
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
    snippet_options = config.markdown_extensions.get(snippets.EXTENSION, {})
    if snippet_options.get("base_path", ["."]) not in (".", ["."]) or (
        snippet_options.keys() - {"base_path", "check_paths", "restrict_base_path", "encoding"}
    ) or not snippet_options.get("restrict_base_path", True) or (
        snippet_options.get("encoding", "utf-8") != "utf-8"
    ):
        raise PortableError("portable snippets require local UTF-8 files at the project root")
    names = config.markdown_extensions.keys()
    if names & DEFINITION_EXTENSIONS.values() and "attr_list" not in names:
        raise PortableError("portable glossary and citation definitions require explicit attr_list")
    if HEADING_AND_BIBLIOGRAPHY & names and not {"attr_list", "toc"} <= names:
        raise PortableError("the prototype requires explicit attr_list and toc configuration")


def _theme_directory(config: ProjectConfig) -> Path | None:
    value = (config.project.get("theme") or {}).get("custom_dir")
    if not value:
        return None
    if not isinstance(value, str):
        raise PortableError("portable theme.custom_dir must be a path")
    directory = config.root / value
    resolved = directory.resolve()
    if (
        not resolved.is_relative_to(config.root)
        or (config.docs_dir.is_relative_to(resolved) and resolved != config.docs_dir)
        or resolved.is_relative_to(config.root / ".git")
        or resolved.is_relative_to(_workspace(config))
        or _workspace(config).is_relative_to(resolved)
        or resolved.is_relative_to(config.site_dir)
        or config.site_dir.is_relative_to(resolved)
        or not resolved.is_dir()
    ):
        raise PortableError("portable theme.custom_dir must be a project source directory")
    if any(
        path.is_symlink()
        for path in (directory, *directory.parents)
        if path.is_relative_to(config.root)
    ):
        raise PortableError(f"symlinked theme directory: {directory}")
    return resolved


def _capture_tree(directory: Path, files: dict[Path, bytes]) -> None:
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise PortableError(f"symlinked source is outside the feasibility prototype: {path}")
        if path.is_file() and path not in files:
            files[path] = path.read_bytes()


def _decode(path: Path, data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        line = data.count(b"\n", 0, error.start) + 1
        raise PortableError(f"{path}:{line}: invalid UTF-8 input") from error


def capture_inputs(config_file: Path) -> InputSnapshot:
    """Parse and compile the same captured bytes, including configuration."""
    config_file = config_file.resolve()
    files = {config_file: config_file.read_bytes()}
    config = parse_project_config(config_file, _decode(config_file, files[config_file]))
    _check_config(config)
    theme = _theme_directory(config)
    macro_module = None
    if macros.EXTENSION in config.markdown_extensions:
        macro_module = macros.capture_module(
            config.root, config.markdown_extensions[macros.EXTENSION], files
        )
    _capture_tree(config.docs_dir, files)
    sources = {
        path.relative_to(config.docs_dir).as_posix(): _decode(path, data)
        for path, data in files.items()
        if path.is_relative_to(config.docs_dir) and path.suffix.lower() == ".md"
    }
    if theme is not None:
        _capture_tree(theme, files)
    bib_options = config.markdown_extensions.get("prodockit.bibliography", {})
    dependencies: set[Path] = set()
    for name in ("bib_file", "csl_style"):
        value = bib_options.get(name)
        if value:
            dependencies.add((config.root / str(value)).resolve())
    extensions = (
        config.markdown_extensions if "markdown_extensions" in config.project
        else DOCUMENTED_MARKDOWN_DEFAULTS
    ).keys()
    caption_options = config.markdown_extensions.get(CAPTION_EXTENSION)
    snippet_paths: set[Path] = set()
    macro_context = macros.ConditionalContext.from_config(
        config.project, config.markdown_extensions
    )
    for source, text in sources.items():
        page = scan(
            source, text, extensions=extensions, caption_options=caption_options,
            macro_context=macro_context,
        )
        for line, snippet_name in page.snippets.items():
            snippet_paths.add(
                snippets.capture(
                    config.root, snippet_name, location=f"{source}:{line}", files=files
                )
            )
        for edit in page.edits:
            if edit.kind == "cite" or edit.kind in BIBLIOGRAPHY_MARKERS:
                dependencies.add(
                    (config.root / str(bib_options.get("bib_file", "references.bib"))).resolve()
                )
            if edit.kind in BIBLIOGRAPHY_MARKERS and edit.key.strip():
                dependencies.add((config.root / edit.key.strip()).resolve())
    try:
        for path in sorted(dependencies - files.keys()):
            files[path] = path.read_bytes()
    except OSError as error:
        raise PortableError(f"cannot read build input: {error}") from error
    return InputSnapshot(
        config, MappingProxyType(files), theme, frozenset(snippet_paths), macro_module
    )


def _generated_config(config: ProjectConfig, theme: Path | None) -> dict[str, Any]:
    project = copy.deepcopy(config.project)
    project.update(docs_dir="docs", site_dir="site")
    if theme is not None:
        project["theme"]["custom_dir"] = theme.as_posix()
    extensions = copy.deepcopy(config.markdown_extensions)
    if "markdown_extensions" not in project:
        extensions = copy.deepcopy(DOCUMENTED_MARKDOWN_DEFAULTS)
    for name in MIGRATED:
        extensions.pop(name, None)
    if snippets.EXTENSION in extensions:
        extensions[snippets.EXTENSION]["base_path"] = [SNIPPETS_DIRECTORY]
    if macros.EXTENSION in extensions:
        extensions[macros.EXTENSION]["module_name"] = Path(macros.MODULE_FILENAME).stem
    if CAPTION_EXTENSION in extensions:
        extensions["prodockit.headings:PreparedCaptionExtension"] = {}
    # Source diagnostics run before generation. Keep the table renderer and
    # the checks that operate on parsed tables and do not need the source path.
    old = "prodockit.tables"
    if old in extensions:
        new = "prodockit.tables:PreparedTablesExtension"
        extensions = {
            new if name == old else name: options for name, options in extensions.items()
        }
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


def _prepare(snapshot: InputSnapshot, *, pandoc: Path | None = None) -> Prepared:
    config = snapshot.config
    pandoc = pandoc.resolve() if pandoc is not None else None
    compiler_toolchain = toolchain(pandoc)
    directory = _workspace(config) / "generations"
    directory.mkdir(exist_ok=True)
    generation = Path(tempfile.mkdtemp(prefix="generation-", dir=directory))
    try:
        inputs = snapshot.materialize(generation)
        output, pages, _dependencies = compile_pages(
            config, snapshot.sources, inputs=inputs, pandoc=pandoc,
        )
        (generation / "docs").mkdir()
        for name, data in snapshot.documents.items():
            target = generation / "docs" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(output[name].encode("utf-8") if name in output else data)
        if snapshot.macro_module is not None:
            (generation / macros.MODULE_FILENAME).write_bytes(
                snapshot.files[snapshot.macro_module]
            )
        generated_config = generation / "zensical.toml"
        generated_config.write_bytes(
            tomlkit.dumps(_generated_config(config, inputs.theme_dir)).encode("utf-8")
        )
        if snapshot.hashes != capture_inputs(config.path).hashes:
            raise PortableError(
                "source inputs changed during preparation; retry with a stable snapshot"
            )
        manifest = {
            "schema": SCHEMA,
            "mode": "portable",
            "prodockit": __version__,
            "original_config": str(config.path),
            "original_docs_dir": str(config.docs_dir),
            "input_hashes": snapshot.hashes,
            "generation": generation.name,
            "toolchain": compiler_toolchain,
            "directory_urls": bool(config.project.get("use_directory_urls", True)),
            "pages": pages,
            "source_paths": {
                source: {
                    "original": str(config.docs_dir / source),
                    "captured": f".inputs/docs/{source}", "generated": f"docs/{source}",
                } for source in pages
            },
            "captured_inputs": {
                str(original): captured.relative_to(generation).as_posix()
                for original, captured in sorted(inputs.paths.items())
            },
            "generated_hashes": generated_hashes(generation),
        }
        manifest_path = generation / "manifest.json"
        write_manifest(manifest_path, manifest)
        validate_inputs(generation, read_manifest(manifest_path))
        return Prepared(generated_config, manifest_path, generation / "site")
    except BaseException:
        shutil.rmtree(generation)
        raise


def prepare(config_file: str, *, pandoc: Path | None = None) -> Prepared:
    config = load_project_config(config_file)
    with workspace_lock(config):
        return _prepare(capture_inputs(config.path), pandoc=pandoc)


def command(config: Path, action: str, *options: str) -> list[str]:
    return [sys.executable, "-m", "zensical", action, "--config-file", str(config), *options]


def _environment(config: Path) -> dict[str, str]:
    return {**os.environ, CONFIG_OVERRIDE_ENV: str(config)}


def _validate_prepared(prepared: Prepared, *, fresh: bool = True) -> dict[str, Any]:
    root = prepared.manifest.parent.resolve()
    if (
        prepared.config.resolve() != root / "zensical.toml"
        or prepared.site.resolve() != root / "site"
    ):
        raise PortableError("configuration, manifest and site must belong to the same generation")
    manifest = read_manifest(prepared.manifest.resolve())
    validate_inputs(root, manifest)
    if fresh and (
        capture_inputs(Path(manifest["original_config"])).hashes != manifest["input_hashes"]
    ):
        raise PortableError("portable output is stale; prepare and build again")
    return manifest


_BUILD_RECEIPT = ".pdk-build.json"


def _site_hash(site: Path) -> str:
    files = {}
    for path in sorted(site.rglob("*")):
        relative = path.relative_to(site).as_posix()
        if path.is_symlink():
            raise PortableError(f"symlinked portable site output: {relative}")
        if path.is_file() and relative != _BUILD_RECEIPT:
            files[relative] = digest(path.read_bytes())
    return digest(json.dumps(files, sort_keys=True).encode("utf-8"))


def validate(
    prepared: Prepared, *, fresh: bool = True, require_receipt: bool = False
) -> None:
    manifest = _validate_prepared(prepared, fresh=fresh)
    receipt = prepared.site / _BUILD_RECEIPT
    if receipt.exists():
        try:
            provenance = json.loads(receipt.read_text(encoding="utf-8"))
            if any(
                provenance[key] != manifest[key] for key in ("mode", "generation", "content_id")
            ):
                raise ValueError("build identity differs")
        except (KeyError, TypeError, ValueError) as error:
            raise PortableError("site receipt does not match its prepared generation") from error
        site_hash = provenance.get("site_hash")
        if require_receipt and not isinstance(site_hash, str):
            raise PortableError("portable PDF requires a site fingerprint; run pdk -p build")
    elif require_receipt:
        raise PortableError("portable PDF requires a completed pdk -p build")
    else:
        site_hash = None
    soups: dict[str, BeautifulSoup] = {}
    for source, details in manifest["pages"].items():
        path = output_path(source, prepared.site, directory_urls=manifest["directory_urls"])
        if not path.is_file():
            raise PortableError(f"build is incomplete: missing {path}")
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        article = soup.select_one("article.md-content__inner.md-typeset")
        if article is None:
            raise PortableError(f"{source}: cannot find the built article")
        expected_captions = details.get("captions", [])
        rendered_captions = article.select(f"figure[{PREPARED_CAPTION_NUMBER_ATTR}]")
        if len(rendered_captions) != len(expected_captions):
            raise PortableError(f"{source}: prepared captions did not survive rendering")
        for caption, expected in zip(rendered_captions, expected_captions, strict=True):
            prefix = caption.select_one(f"figcaption .{PREPARED_CAPTION_PREFIX}")
            if (
                prefix is None or prefix.get_text() != expected["number"] + "."
                or (expected["id"] and caption.get("id") != expected["id"])
            ):
                raise PortableError(f"{source}: prepared caption anchor or number changed")
            content = "table" if expected["kind"] == "table-caption" else "img"
            if caption.select_one(content) is None:
                raise PortableError(f"{source}: prepared caption could not attach to its {content}")
        if article.select_one(".prodockit-page-bibliography"):
            entries = Counter(str(entry["id"]) for entry in article.select(".csl-entry[id]"))
            collision = next((key for key, count in entries.items() if count > 1), None)
            if collision is not None:
                raise PortableError(f"{source}: duplicate bibliography entry anchor {collision!r}")
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
            "a.prodockit-ref, a.prodockit-autoref, a.prodockit-gls, "
            ".prodockit-cite a, .prodockit-bib-cite a, "
            "a.prodockit-bib-backlink, a.pdk-hotspots-region"
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
    if site_hash is not None and site_hash != _site_hash(prepared.site):
        raise PortableError("portable site files changed after build; run pdk -p build")


def _build(prepared: Prepared, *, clean: bool = False, strict: bool = True) -> None:
    manifest = _validate_prepared(prepared)
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
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if version.returncode:
        raise PortableError(f"Zensical version check failed with status {version.returncode}")
    (prepared.site / _BUILD_RECEIPT).write_text(
        json.dumps(
            {
                "mode": "portable",
                "generation": prepared.config.parent.name,
                "content_id": manifest["content_id"],
                "zensical": version.stdout.strip(),
                "site_hash": _site_hash(prepared.site),
            }
        )
        + "\n",
        encoding="utf-8",
    )


@contextmanager
def portable_pdf_generation(
    manifest_file: Path, config_file: str | None, markdown_file: str | None
) -> Iterator[tuple[Path, Prepared]]:
    """Select an explicit, current generation and hold its project lock."""
    manifest_file = manifest_file.resolve()
    manifest = read_manifest(manifest_file)
    original = Path(manifest["original_config"]).resolve()
    if config_file is not None and Path(config_file).resolve() != original:
        raise PortableError("portable manifest belongs to a different original configuration")
    config = load_project_config(original)
    generation = manifest_file.parent
    if generation.parent != _workspace(config) / "generations":
        raise PortableError("portable PDF requires a generation in its original project workspace")
    prepared = Prepared(generation / "zensical.toml", manifest_file, generation / "site")
    with workspace_lock(config):
        validate(prepared, require_receipt=True)
        if markdown_file is not None and markdown_file not in manifest["pages"]:
            raise PortableError(f"page is absent from the portable manifest: {markdown_file}")
        yield original, prepared


def render_portable_pdf(
    config_file: str,
    prepared: Prepared,
    *,
    markdown_file: str | None,
    on_stage: Callable[[int, int, str], None],
) -> str:
    """Render into scratch space and publish beside the selected site."""
    from prodockit.pdf.config import build_pdf_from_built_site

    generation = prepared.manifest.parent
    with tempfile.TemporaryDirectory(prefix=".pdf-", dir=generation) as work:
        output = Path(
            build_pdf_from_built_site(
                config_file,
                markdown_file=markdown_file,
                on_stage=on_stage,
                portable_site=prepared.site,
                output_directory=Path(work),
            )
        )
        validate(prepared, require_receipt=True)
        directory = generation / "pdf"
        if directory.is_symlink():
            raise PortableError("portable PDF output directory must not be symlinked")
        directory.mkdir(exist_ok=True)
        destination = directory / output.name
        os.replace(output, destination)
        return str(destination)


@contextmanager
def _built_candidate(
    snapshot: InputSnapshot, *, pandoc: Path | None, clean: bool = False, strict: bool = True
) -> Iterator[Prepared]:
    """Keep a generation only once its build and any caller's startup succeed."""
    prepared = _prepare(snapshot, pandoc=pandoc)
    try:
        _build(prepared, clean=clean, strict=strict)
        yield prepared
    except BaseException:
        shutil.rmtree(prepared.config.parent)
        raise


def build(
    config_file: str, *, pandoc: Path | None = None, clean: bool = False, strict: bool = True
) -> Prepared:
    config = load_project_config(config_file)
    with workspace_lock(config), _built_candidate(
        capture_inputs(config.path), pandoc=pandoc, clean=clean, strict=strict
    ) as prepared:
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
    _validate_prepared(prepared, fresh=False)
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
        snapshot = capture_inputs(config.path)
        active = snapshot.hashes
        with _built_candidate(snapshot, pandoc=pandoc) as prepared:
            process = _start(prepared, address)
        try:
            report(f"Portable preview: http://{address}/ (watching original sources)")
            rejected: dict[str, str] | None = None
            retry_at = 0.0
            last_error = ""
            while True:
                time.sleep(0.5)
                if process.poll() is not None:
                    raise PortableError(
                        f"Zensical preview stopped with status {process.returncode}"
                    )
                observed = None
                try:
                    snapshot = capture_inputs(config.path)
                    observed = snapshot.hashes
                    if observed == active:
                        rejected = None
                        last_error = ""
                        continue
                    if observed == rejected and time.monotonic() < retry_at:
                        continue
                    with _built_candidate(snapshot, pandoc=pandoc) as candidate:
                        _stop(process)
                        try:
                            process = _start(candidate, address)
                        except _PREVIEW_ERRORS:
                            process = _start(prepared, address)
                            raise
                except _PREVIEW_ERRORS as error:
                    if process.poll() is not None:
                        raise PortableError(
                            f"Could not restart the previous portable preview: {error}"
                        ) from error
                    rejected = observed
                    retry_at = time.monotonic() + _PREVIEW_RETRY_SECONDS
                    if str(error) != last_error:
                        report(f"Keeping the previous preview: {error}")
                        last_error = str(error)
                else:
                    prepared = candidate
                    active = observed
                    rejected = None
                    report("Portable preview updated from a complete source generation.")
                    last_error = ""
        finally:
            _stop(process)

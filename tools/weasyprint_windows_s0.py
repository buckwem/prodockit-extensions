# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Collect S0 evidence for the official WeasyPrint Windows x64 bundle.

This is a prototype acceptance harness, not a production installer.  It keeps
all state beneath ``--work-dir``, invokes the downloaded executable by its
absolute path, and records cold and warm preparation/render timings.  It does
not edit PATH, the registry, or the host Python environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class AcceptanceError(RuntimeError):
    """The upstream artifact failed an S0 acceptance condition."""


@dataclass(frozen=True)
class ArtifactSpec:
    version: str
    release_url: str
    asset_url: str
    asset_name: str
    sha256: str
    archive_bytes: int
    executable: str = "onedir/weasyprint/weasyprint.exe"
    licence: str = "LICENSE"


@dataclass(frozen=True)
class PrepareResult:
    executable: Path
    downloaded: bool
    extracted: bool
    download_seconds: float
    extraction_seconds: float
    total_seconds: float


SPEC = ArtifactSpec(
    version="70.0",
    release_url="https://github.com/Kozea/WeasyPrint/releases/tag/v70.0",
    asset_url=(
        "https://github.com/Kozea/WeasyPrint/releases/download/v70.0/weasyprint-windows-onedir.zip"
    ),
    asset_name="weasyprint-windows-onedir.zip",
    sha256="ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53",
    archive_bytes=32_271_073,
)

FIXTURE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WeasyPrint S0 acceptance</title>
<style>
  @page { size: A4; margin: 20mm; @bottom-center { content: counter(page); } }
  body { font-family: Arial, sans-serif; font-size: 12pt; }
  code { font-family: "Courier New", monospace; }
  h1, h2 { bookmark-level: 1; }
  .next { break-before: page; }
  svg { width: 240px; height: 90px; }
</style>
</head>
<body>
<h1 id="start">Standalone renderer acceptance</h1>
<p>S0 text marker: Résumé — Ω.</p>
<p><a href="#details">Internal destination</a> and
<a href="https://example.com/prodockit-s0">external destination</a>.</p>
<svg viewBox="0 0 240 90" role="img" aria-label="S0 inline SVG">
  <title>S0 inline SVG</title>
  <rect x="2" y="2" width="236" height="86" rx="12" fill="#dbeafe" stroke="#2563eb"/>
  <path d="M30 55 L85 20 L140 55 L205 20" fill="none" stroke="#7c3aed" stroke-width="6"/>
</svg>
<section class="next">
<h2 id="details">Second-page destination</h2>
<p>S0 second-page marker. <code>project-local runtime</code></p>
</section>
</body>
</html>
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_members(archive: zipfile.ZipFile, spec: ArtifactSpec) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    names = {member.filename.rstrip("/") for member in members}
    required = {spec.executable, spec.licence}
    missing = required - names
    if missing:
        raise AcceptanceError(f"archive is missing required paths: {sorted(missing)}")
    normalised_names: set[str] = set()
    for member in members:
        if "\\" in member.filename:
            raise AcceptanceError(f"unsafe archive path: {member.filename!r}")
        path = PurePosixPath(member.filename)
        if (
            not path.parts
            or path.is_absolute()
            or ".." in path.parts
            or any(":" in part for part in path.parts)
            or path.parts[0] not in {"onedir", "README.rst", "LICENSE"}
        ):
            raise AcceptanceError(f"unsafe archive path: {member.filename!r}")
        normalised = path.as_posix().rstrip("/").casefold()
        if normalised in normalised_names:
            raise AcceptanceError(f"duplicate archive path: {member.filename!r}")
        normalised_names.add(normalised)
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise AcceptanceError(f"archive contains a symbolic link: {member.filename!r}")
    return members


def _extract(archive_path: Path, destination: Path, spec: ArtifactSpec) -> tuple[int, int]:
    staging = destination.with_name(f"{destination.name}.staging-{uuid.uuid4().hex}")
    previous = destination.with_name(f"{destination.name}.previous-{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_members(archive, spec)
            for member in members:
                target = staging.joinpath(*PurePosixPath(member.filename).parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        extracted_bytes = sum(path.stat().st_size for path in staging.rglob("*") if path.is_file())
        file_count = sum(1 for path in staging.rglob("*") if path.is_file())
        marker = {
            "version": spec.version,
            "asset_url": spec.asset_url,
            "sha256": spec.sha256,
            "file_count": file_count,
            "extracted_bytes": extracted_bytes,
        }
        (staging / ".s0-artifact.json").write_text(
            json.dumps(marker, indent=2) + "\n", encoding="utf-8"
        )
        had_previous = destination.exists()
        if had_previous:
            os.replace(destination, previous)
        try:
            os.replace(staging, destination)
        except OSError:
            if had_previous and previous.exists() and not destination.exists():
                os.replace(previous, destination)
            raise
        else:
            if previous.exists():
                shutil.rmtree(previous)
        return file_count, extracted_bytes
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if previous.exists():
            if not destination.exists():
                os.replace(previous, destination)
            else:
                shutil.rmtree(previous)


def _download(url: str, destination: Path) -> float:
    partial = destination.with_suffix(f"{destination.suffix}.partial-{os.getpid()}")
    request = urllib.request.Request(url, headers={"User-Agent": "Prodockit-S0/1"})
    started = time.perf_counter()
    try:
        for attempt in range(3):
            try:
                with (
                    urllib.request.urlopen(request, timeout=45) as response,
                    partial.open("wb") as output,
                ):
                    shutil.copyfileobj(response, output)
                os.replace(partial, destination)
                return time.perf_counter() - started
            except (OSError, urllib.error.URLError) as error:
                if partial.exists():
                    partial.unlink()
                if attempt == 2:
                    raise AcceptanceError(f"could not download {url}: {error}") from error
                time.sleep(2**attempt)
    finally:
        if partial.exists():
            partial.unlink()
    raise AssertionError("unreachable")


def _runtime_is_current(runtime: Path, spec: ArtifactSpec) -> bool:
    marker = runtime / ".s0-artifact.json"
    executable = runtime / spec.executable
    licence = runtime / spec.licence
    if not marker.is_file() or not executable.is_file() or not licence.is_file():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return data.get("version") == spec.version and data.get("sha256") == spec.sha256


def prepare_artifact(
    work_dir: Path,
    spec: ArtifactSpec = SPEC,
    *,
    archive_override: Path | None = None,
) -> PrepareResult:
    """Download, verify and atomically extract the pinned artifact."""

    started = time.perf_counter()
    downloads = work_dir / "downloads"
    runtime = work_dir / "runtime"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = archive_override or downloads / spec.asset_name
    downloaded = False
    download_seconds = 0.0
    if not archive.is_file() or sha256_file(archive) != spec.sha256:
        if archive_override is not None:
            raise AcceptanceError(f"archive override failed SHA-256 verification: {archive}")
        download_seconds = _download(spec.asset_url, archive)
        downloaded = True
    if archive.stat().st_size != spec.archive_bytes:
        raise AcceptanceError(
            f"archive size mismatch: expected {spec.archive_bytes}, got {archive.stat().st_size}"
        )
    actual_digest = sha256_file(archive)
    if actual_digest != spec.sha256:
        raise AcceptanceError(
            f"archive digest mismatch: expected {spec.sha256}, got {actual_digest}"
        )

    extracted = False
    extraction_seconds = 0.0
    if not _runtime_is_current(runtime, spec):
        extraction_started = time.perf_counter()
        _extract(archive, runtime, spec)
        extraction_seconds = time.perf_counter() - extraction_started
        extracted = True
    return PrepareResult(
        executable=runtime / spec.executable,
        downloaded=downloaded,
        extracted=extracted,
        download_seconds=round(download_seconds, 3),
        extraction_seconds=round(extraction_seconds, 3),
        total_seconds=round(time.perf_counter() - started, 3),
    )


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise AcceptanceError(
            f"command failed ({' '.join(command)}):\n{result.stdout}\n{result.stderr}"
        )
    return result


def _resolved(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def _font_descriptors(font: Any) -> list[Any]:
    resolved = _resolved(font)
    descriptors: list[Any] = []
    descriptor = resolved.get("/FontDescriptor")
    if descriptor is not None:
        descriptors.append(_resolved(descriptor))
    for descendant in resolved.get("/DescendantFonts", []):
        descendant_descriptor = _resolved(descendant).get("/FontDescriptor")
        if descendant_descriptor is not None:
            descriptors.append(_resolved(descendant_descriptor))
    return descriptors


def inspect_pdf(path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - the Windows workflow installs pypdf
        raise AcceptanceError("pypdf is required to inspect the S0 output") from error

    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    external_links = 0
    internal_links = 0
    embedded_fonts = 0
    for page in reader.pages:
        resources = _resolved(page.get("/Resources", {}))
        fonts = _resolved(resources.get("/Font", {}))
        for font in fonts.values():
            for descriptor in _font_descriptors(font):
                if any(name in descriptor for name in ("/FontFile", "/FontFile2", "/FontFile3")):
                    embedded_fonts += 1
                    break
        for annotation in page.get("/Annots", []):
            annotation = _resolved(annotation)
            if annotation.get("/Subtype") != "/Link":
                continue
            action = _resolved(annotation.get("/A", {}))
            if action.get("/S") == "/URI":
                external_links += 1
            elif annotation.get("/Dest") is not None or action.get("/S") == "/GoTo":
                internal_links += 1

    def outline_count(items: list[Any]) -> int:
        return sum(outline_count(item) if isinstance(item, list) else 1 for item in items)

    metadata = reader.metadata
    text_markers = {
        "first_page": "Standalone renderer acceptance" in text,
        "second_page": "S0 second-page marker" in text,
    }
    page_count = len(reader.pages)
    outlines = outline_count(reader.outline)
    findings: dict[str, Any] = {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "pages": page_count,
        "outline_entries": outlines,
        "external_links": external_links,
        "internal_links": internal_links,
        "embedded_fonts": embedded_fonts,
        "producer": str(metadata.get("/Producer", "") if metadata is not None else ""),
        "text_markers": text_markers,
    }
    if page_count != 2:
        raise AcceptanceError(f"expected two PDF pages, got {page_count}")
    if outlines < 2:
        raise AcceptanceError("PDF did not retain the expected heading bookmarks")
    if external_links < 1 or internal_links < 1:
        raise AcceptanceError("PDF did not retain both external and internal links")
    if embedded_fonts < 1:
        raise AcceptanceError("PDF did not contain an embedded font")
    if not all(text_markers.values()):
        raise AcceptanceError("PDF text layer did not retain the fixture markers")
    return findings


def render_fixture(executable: Path, work_dir: Path, label: str) -> dict[str, Any]:
    outputs = work_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    html = outputs / "fixture.html"
    html.write_text(FIXTURE, encoding="utf-8")
    pdf = outputs / f"{label}.pdf"
    started = time.perf_counter()
    _run([str(executable.resolve()), "--quiet", str(html.resolve()), str(pdf.resolve())])
    elapsed = time.perf_counter() - started
    findings = inspect_pdf(pdf)
    findings["render_seconds"] = round(elapsed, 3)
    findings["path"] = str(pdf)
    return findings


def _archive_inventory(runtime: Path) -> dict[str, Any]:
    marker = json.loads((runtime / ".s0-artifact.json").read_text(encoding="utf-8"))
    licence_files = [
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file()
        and path.name.lower().startswith(("license", "licence", "copying", "notice"))
    ]
    return {
        "file_count": marker["file_count"],
        "extracted_bytes": marker["extracted_bytes"],
        "licence_files": sorted(licence_files),
    }


def collect_evidence(work_dir: Path, *, archive_override: Path | None = None) -> dict[str, Any]:
    if platform.system() != "Windows" or platform.machine().lower() not in {
        "amd64",
        "x86_64",
    }:
        raise AcceptanceError("S0 execution requires a Windows x64 host")

    original_path = os.environ.get("PATH")
    cold = prepare_artifact(work_dir, archive_override=archive_override)
    version = _run([str(cold.executable.resolve()), "--version"]).stdout.strip()
    if SPEC.version not in version:
        raise AcceptanceError(f"unexpected WeasyPrint version output: {version!r}")
    cold_render = render_fixture(cold.executable, work_dir, "cold")
    warm = prepare_artifact(work_dir, archive_override=archive_override)
    if warm.downloaded or warm.extracted:
        raise AcceptanceError("healthy warm preparation downloaded or extracted the artifact")
    warm_render = render_fixture(warm.executable, work_dir, "warm")
    if cold_render["pages"] != warm_render["pages"]:
        raise AcceptanceError("cold and warm renders produced different page counts")
    if cold_render["text_markers"] != warm_render["text_markers"]:
        raise AcceptanceError("cold and warm renders produced different text evidence")
    if os.environ.get("PATH") != original_path:
        raise AcceptanceError("acceptance harness changed PATH")

    runtime = work_dir / "runtime"
    return {
        "status": "passed",
        "scope": "S0 evidence only; no production runtime selection changed",
        "artifact": asdict(SPEC),
        "provenance": {
            "publisher": "Kozea/WeasyPrint",
            "official_release": SPEC.release_url,
            "upstream_digest_verified": True,
            "upstream_build": (
                "GitHub-hosted Windows runner, Python 3.14, PyInstaller onedir; "
                "Pango closure supplied from upstream's MSYS2 UCRT64 build environment"
            ),
            "end_user_msys2_required": False,
        },
        "licensing": {
            "weasyprint": "BSD-3-Clause",
            "archive_licence_retained": (runtime / SPEC.licence).is_file(),
            "inventory": _archive_inventory(runtime)["licence_files"],
            "third_party_notice_status": (
                "The official archive contains no separate bundled-dependency notice inventory; "
                "use direct upstream download and resolve notice closure before redistribution."
            ),
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "path_unchanged": os.environ.get("PATH") == original_path,
            "registry_changes_requested": False,
            "administrator_rights_requested": False,
        },
        "inventory": _archive_inventory(runtime),
        "cold_prepare": asdict(cold) | {"executable": str(cold.executable)},
        "warm_prepare": asdict(warm) | {"executable": str(warm.executable)},
        "cli_version": version,
        "cold_render": cold_render,
        "warm_render": warm_render,
        "cold_warm_byte_identical": cold_render["sha256"] == warm_render["sha256"],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--work-dir", type=Path, required=True)
    result.add_argument("--archive", type=Path, help="use a pre-downloaded official artifact")
    result.add_argument("--report", type=Path, default=Path("weasyprint-windows-s0.json"))
    return result


def main() -> int:
    args = parser().parse_args()
    report: dict[str, Any]
    try:
        report = collect_evidence(args.work_dir.resolve(), archive_override=args.archive)
    except (AcceptanceError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        report = {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        result = 1
    else:
        result = 0
    args.report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return result


if __name__ == "__main__":
    raise SystemExit(main())

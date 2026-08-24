# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Clone, adopt and visually compare a real documentation site.

Every operation is confined to pytest's temporary directory. The clone's push
URL is disabled before prodockit runs, providing a second safety boundary on
top of ``prodockit adopt`` never invoking Git itself.
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageChops, ImageDraw

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


@dataclass(frozen=True)
class RealSite:
    name: str
    repository: str
    revision: str
    config: str
    output: str
    build: tuple[str, ...]
    pages: tuple[str, ...]
    expected_changes: tuple[str, ...]
    working_directory: str = "."
    python_packages: tuple[str, ...] = ()
    mermaid: bool = False
    maths: bool = False
    ignore_rectangles: tuple[tuple[int, int, int, int], ...] = ()
    max_changed_pixel_ratio: float = 0.0


@dataclass(frozen=True)
class Comparison:
    page: str
    changed_pixels: int
    total_pixels: int
    ratio: float
    diff: Path | None = None


def load_sites(path: Path) -> tuple[RealSite, ...]:
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    return tuple(RealSite(**_normalise(item)) for item in parsed.get("site", []))


def _normalise(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    result["build"] = tuple(result["build"])
    result["pages"] = tuple(result["pages"])
    result["expected_changes"] = tuple(result["expected_changes"])
    result["python_packages"] = tuple(result.get("python_packages", []))
    result["ignore_rectangles"] = tuple(
        tuple(rectangle) for rectangle in result.get("ignore_rectangles", [])
    )
    return result


def _run(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    timeout: int = 900,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        env={**os.environ, "PYTHONUTF8": "1", **(environment or {})},
    )
    if completed.returncode:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise AssertionError(f"command failed ({' '.join(command)}):\n{output}")
    return completed


def clone(site: RealSite, destination: Path) -> Path:
    destination.mkdir(parents=True)
    _run(["git", "init", "--quiet"], cwd=destination)
    _run(["git", "remote", "add", "origin", site.repository], cwd=destination)
    _run(["git", "fetch", "--quiet", "--depth", "1", "origin", site.revision], cwd=destination)
    _run(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=destination)
    _run(
        ["git", "remote", "set-url", "--push", "origin", "DISABLED_BY_REAL_SITE_HARNESS"],
        cwd=destination,
    )
    head = _run(["git", "rev-parse", "HEAD"], cwd=destination).stdout.strip()
    assert head == site.revision
    assert not _run(["git", "status", "--porcelain"], cwd=destination).stdout
    return destination


def prepare(site: RealSite, destination: Path, project: Path) -> dict[str, str]:
    paths = [str(project)]
    if site.python_packages:
        destination.mkdir(parents=True)
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--target",
                str(destination),
                *site.python_packages,
            ],
            cwd=destination,
        )
        paths.insert(0, str(destination))
    existing = os.environ.get("PYTHONPATH")
    if existing:
        paths.append(existing)
    value = os.pathsep.join(paths)
    return {"PYTHONPATH": value}


def site_root(site: RealSite, project: Path) -> Path:
    return project / site.working_directory


def build(
    site: RealSite,
    project: Path,
    environment: Mapping[str, str] | None = None,
) -> None:
    command = [sys.executable if value == "{python}" else value for value in site.build]
    _run(command, cwd=site_root(site, project), environment=environment)


def adopt(site: RealSite, project: Path) -> str:
    command = [sys.executable, "-m", "prodockit", "adopt", "--apply"]
    command.append("--mermaid" if site.mermaid else "--no-mermaid")
    command.append("--maths" if site.maths else "--no-maths")
    completed = _run(command, cwd=site_root(site, project), input_text="y\ny\n")
    return completed.stdout


def chrome() -> str | None:
    candidates = (
        os.environ.get("PRODOCKIT_TEST_CHROME"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    return next((value for value in candidates if value and Path(value).is_file()), None)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        pass


@contextmanager
def serve(directory: Path) -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def capture(
    executable: str,
    base_url: str,
    pages: tuple[str, ...],
    destination: Path,
    *,
    label: str,
    profile: Path,
) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    captured: dict[str, Path] = {}
    for number, page in enumerate(pages, start=1):
        output = destination / f"{number:02d}-{Path(page).parent.name or 'home'}.png"
        url = f"{base_url}/{page}?prodockit-snapshot={label}"
        command = [
            executable,
            "--headless=new",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-gpu",
            "--disable-sync",
            "--hide-scrollbars",
            "--no-default-browser-check",
            "--no-first-run",
            "--force-color-profile=srgb",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            "--window-size=1440,1200",
            f"--user-data-dir={profile}",
            f"--screenshot={output}",
            url,
        ]
        _capture_page(command, output, destination)
        assert output.is_file(), f"Chrome did not capture {page}"
        captured[page] = output
    return captured


def _capture_page(command: list[str], output: Path, cwd: Path) -> None:
    """Wait for Chrome's output, not for its unrelated background services."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    deadline = time.monotonic() + 45
    previous_size = -1
    stable = 0
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None and not output.is_file():
                raise AssertionError(f"Chrome exited before writing {output}")
            if output.is_file():
                size = output.stat().st_size
                stable = stable + 1 if size == previous_size and size > 0 else 0
                previous_size = size
                if stable >= 2:
                    return
            time.sleep(0.2)
        raise AssertionError(f"Chrome did not finish writing {output} within 45 seconds")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def compare(
    before: dict[str, Path],
    after: dict[str, Path],
    destination: Path,
    *,
    ignore_rectangles: tuple[tuple[int, int, int, int], ...] = (),
) -> tuple[Comparison, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    comparisons: list[Comparison] = []
    for number, page in enumerate(before, start=1):
        first = Image.open(before[page]).convert("RGB")
        second = Image.open(after[page]).convert("RGB")
        assert first.size == second.size
        for rectangle in ignore_rectangles:
            ImageDraw.Draw(first).rectangle(rectangle, fill=(0, 0, 0))
            ImageDraw.Draw(second).rectangle(rectangle, fill=(0, 0, 0))
        difference = ImageChops.difference(first, second)
        pixels = cast(Iterable[tuple[int, int, int]], difference.get_flattened_data())
        changed = sum(1 for pixel in pixels if max(pixel) > 2)
        total = first.width * first.height
        diff_path: Path | None = None
        if changed:
            diff_path = destination / f"{number:02d}-diff.png"
            difference.save(diff_path)
        comparisons.append(Comparison(page, changed, total, changed / total, diff_path))
    return tuple(comparisons)

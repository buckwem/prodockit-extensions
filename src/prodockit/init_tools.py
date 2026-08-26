# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Scaffold the Node tooling `prodockit.pdf` needs for Mermaid diagrams and
TeX maths in a PDF.

WeasyPrint has no JS engine, so neither can be rendered the way the live
website renders them - `prodockit.pdf` shells out to `mermaid-cli` and a
`tex2svg` script to turn both into static images before Pandoc sees them.
`prodockit.pdf.config` looks for those in a specific place
(`tools/mermaid/node_modules/.bin/mmdc` and `tools/mathjax/tex2svg.js`),
and until now the library required that layout without providing it - every
consuming project hand-wrote the same two `package.json` files, their
lockfiles, and the same `tex2svg.js`.

That went wrong independently in all three projects using it: one had no
`tools/` directory at all and shipped PDFs full of raw `flowchart LR ...`
source, two set the pre-rename `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD` (which
puppeteer 25.x, what mermaid-cli 11.x resolves to, ignores - so every CI
run downloaded a Chrome build it then discarded), and one committed two
config files nothing reads. Hence `prodockit init-tools`: the canonical
copies live here, pinned in one place. Shipping the matching lockfiles lets
callers use deterministic `npm ci` installs and reuse npm's download cache.

The scaffold stops at writing files. Running `npm ci` is left to the
caller - it is the step that needs the network, and a build tool silently
reaching for a package registry is not a good surprise. `next_steps()`
returns the exact commands, including the CI environment variables that
are easy to get wrong.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

#: Files copied for each component, relative to that component's directory.
COMPONENT_FILES: dict[str, tuple[str, ...]] = {
    "mermaid": ("package.json", "package-lock.json"),
    "mathjax": ("package.json", "package-lock.json", "tex2svg.js"),
}

#: What each component is for, in the words the CLI reports.
COMPONENT_PURPOSE: dict[str, str] = {
    "mermaid": "Mermaid diagrams (```mermaid fences)",
    "mathjax": "TeX maths ($...$ / $$...$$)",
}

TEMPLATE_DIR = Path(__file__).parent / "_tools_template"


class InitToolsError(Exception):
    """Raised when the scaffold can't be written."""


@dataclass
class InitToolsResult:
    """What `init_tools()` wrote, and what it deliberately didn't."""

    tools_dir: Path
    components: list[str]
    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)

    @property
    def wrote_anything(self) -> bool:
        return bool(self.written)


def init_tools(
    tools_dir: str | Path = "tools",
    *,
    components: tuple[str, ...] = ("mermaid", "mathjax"),
    force: bool = False,
) -> InitToolsResult:
    """Copies the packaged tooling templates into `tools_dir`.

    An existing file is left alone and reported as skipped unless `force`
    is set - a project will have run `npm ci` against its own committed
    lockfile, and quietly replacing a `package.json` out from under it
    would be a genuinely nasty thing to do.
    """
    unknown = [name for name in components if name not in COMPONENT_FILES]
    if unknown:
        raise InitToolsError(
            f"unknown component(s): {', '.join(unknown)} "
            f"(known: {', '.join(sorted(COMPONENT_FILES))})"
        )

    root = Path(tools_dir)
    result = InitToolsResult(tools_dir=root, components=list(components))

    for component in components:
        source_dir = TEMPLATE_DIR / component
        target_dir = root / component
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise InitToolsError(f"could not create {target_dir}: {exc}") from exc

        package_source = source_dir / "package.json"
        package_target = target_dir / "package.json"
        package_is_canonical = (
            not package_target.exists()
            or package_target.read_bytes() == package_source.read_bytes()
        )
        for filename in COMPONENT_FILES[component]:
            source = source_dir / filename
            target = target_dir / filename
            # A lockfile is coupled to package.json.  Do not put prodockit's
            # canonical lock beside an author's customised manifest: npm ci
            # would quite correctly reject that mismatched pair.  A new
            # scaffold, or an existing unmodified scaffold left by a partial
            # run, can safely receive both files.
            if filename == "package-lock.json" and not package_is_canonical and not force:
                result.skipped.append(target)
                continue
            if target.exists() and not force:
                result.skipped.append(target)
                continue
            try:
                shutil.copyfile(source, target)
            except OSError as exc:
                raise InitToolsError(f"could not write {target}: {exc}") from exc
            result.written.append(target)

    return result


def gitignore_lines(result: InitToolsResult) -> list[str]:
    """The `.gitignore` entries a project wants for this scaffold - the
    `node_modules` trees, not the manifests, which should be committed
    along with the lockfiles `npm ci` needs."""
    return [
        f"{result.tools_dir.as_posix()}/{component}/node_modules/"
        for component in result.components
    ]


def install_commands(result: InitToolsResult) -> list[str]:
    """The `npm` commands that turn the scaffold into a working install."""
    return [
        f"npm --prefix {result.tools_dir.as_posix()}/{component} "
        "ci --no-audit --no-fund --prefer-offline"
        for component in result.components
    ]


def ci_environment() -> dict[str, str]:
    """Environment variables a CI run wants when installing mermaid-cli.

    `PUPPETEER_SKIP_DOWNLOAD` is deliberately spelled out here because the
    older `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD` is what everyone reaches for
    and puppeteer 25.x - what mermaid-cli 11.x resolves to - silently
    ignores it, downloading a full Chrome build on every run before falling
    back to whatever `PUPPETEER_EXECUTABLE_PATH` points at anyway.
    """
    return {
        "PUPPETEER_SKIP_DOWNLOAD": "true",
        "PUPPETEER_EXECUTABLE_PATH": "/usr/bin/google-chrome-stable",
    }

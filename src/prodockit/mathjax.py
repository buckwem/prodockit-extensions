# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Install MathJax for the *website*, from the copy the PDF already uses.

Three things needed this and had two copies of it between them:
`prodockit bootstrap`'s stage 18, and a template's CI, which never runs
bootstrap. Two copies of a configuration whose whole failure mode is
being subtly wrong - both produce a valid file, so nothing fails; the
site simply typesets one way locally and another when published
(prodockit-extensions#276).

The escaping is the reason it matters. `inlineMath: [["\\\\(", "\\\\)"]]`
carries four layers of it, and a copy that looks right can be wrong.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

#: Where `npm ci --prefix tools/mathjax` leaves the browser bundle, and
#: where the site loads it from. The same install `prodockit pdf`
#: pre-renders through, so the website and the PDF typeset through
#: byte-identical MathJax rather than whatever a CDN serves today.
BUNDLE = "tex-svg-full.js"
SOURCE = ("tools", "mathjax", "node_modules", "mathjax-full", "es5", BUNDLE)
LICENSE = "LICENSE"
LICENSE_SOURCE = ("tools", "mathjax", "node_modules", "mathjax-full", LICENSE)
DEST = ("docs", "javascripts", "vendor", "mathjax")
CONFIG = ("docs", "javascripts", "mathjax.js")

#: Installed rather than committed, so both are ignored - the bundle is
#: third-party code and does not belong in a project's repository.
IGNORED = ("docs/javascripts/vendor/", "docs/javascripts/mathjax.js")

#: The configuration MathJax reads once at startup. Its absence is what
#: leaves arithmatex's markup on the page as raw TeX (#263), and its
#: *lateness* does the same: a config loaded after the bundle is ignored.
CONFIG_SOURCE = """\
// Written by `prodockit init-mathjax`. Loaded *before* the MathJax
// bundle, because MathJax reads `window.MathJax` once at startup - a
// config that arrives afterwards is ignored, and the page shows raw TeX.
window.MathJax = {
  tex: {
    // pymdownx.arithmatex's `generic = true` has already turned every
    // `$...$` / `$$...$$` into explicit delimiters server-side, which is
    // also the only form prodockit.pdf's Lua filter can pre-render.
    inlineMath: [["\\\\(", "\\\\)"]],
    displayMath: [["\\\\[", "\\\\]"]],
    processEscapes: true,
    processEnvironments: true,
  },
  options: {
    // Typeset only inside the wrappers arithmatex emitted, rather than
    // scanning the page - documentation is full of `$HOME` and `$1`, and
    // none of it is maths.
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex",
  },
};
"""


class MathJaxError(Exception):
    """Raised when the bundle it copies from is not there."""


@dataclass
class InstallResult:
    """What was written, for a caller that wants to report it."""

    bundle: Path
    license: Path
    config: Path
    ignored: list[str] = field(default_factory=list)


def install_mathjax(root: str | Path = ".", *, update_gitignore: bool = True) -> InstallResult:
    """Copies the bundle beside a freshly written config, under `root`.

    Raises `MathJaxError` when `tools/mathjax` has not been installed -
    the bundle is copied from there rather than downloaded, so `npm ci
    --prefix tools/mathjax` has to have run first. Saying so is more use
    than fetching a different MathJax and leaving the website and the PDF
    to disagree.
    """
    project = Path(root)
    source = project.joinpath(*SOURCE)
    license_source = project.joinpath(*LICENSE_SOURCE)
    missing = [path for path in (source, license_source) if not path.is_file()]
    if missing:
        raise MathJaxError(
            f"{missing[0]} is not there - run `npm ci --prefix tools/mathjax` first, "
            "so the website and the PDF use the same MathJax"
        )

    bundle = project.joinpath(*DEST, BUNDLE)
    bundle.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, bundle)
    license_path = project.joinpath(*DEST, LICENSE)
    shutil.copyfile(license_source, license_path)

    config = project.joinpath(*CONFIG)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(CONFIG_SOURCE, encoding="utf-8")

    added: list[str] = []
    if update_gitignore:
        added = _ignore(project / ".gitignore")
    return InstallResult(bundle=bundle, license=license_path, config=config, ignored=added)


def _ignore(path: Path) -> list[str]:
    """Adds the two entries, once. A rerun must not stack them."""
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        current = ""
    missing = [line for line in IGNORED if line not in current.splitlines()]
    if not missing:
        return []
    lead = "" if current.endswith("\n") or not current else "\n"
    note = "# Installed by `prodockit init-mathjax` - not committed"
    body = "\n".join(missing)
    path.write_text(f"{current}{lead}\n{note}\n{body}\n", encoding="utf-8")
    return missing

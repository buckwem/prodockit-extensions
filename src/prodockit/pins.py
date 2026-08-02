# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Finds every place a build-input version is declared across a project,
and moves them all together.

A project that pins its build inputs ends up declaring the same version in
several files at once - a floor in ``pyproject.toml``, an exact pin in each
CI workflow that builds the docs, another in whatever job checks for drift.
They have to agree, nothing enforces that they do, and the failure when
they disagree is quiet: CI builds with one version while the declared
floor says another, and the published output stops matching what anyone
tested.

This module reads them all, so raising a version is one answer rather than
a hunt through four files.

**Operators are preserved per site.** A library declares a floor
(``zensical>=0.0.52``) because an exact pin in package metadata propagates
to every consumer; a build pins exactly (``zensical==0.0.52``) because its
output is an artifact. Both are correct, and setting a new version keeps
each as it was rather than flattening them to one form.

**Both hosts.** GitHub Actions keeps its jobs in ``.github/workflows/``;
GitLab CI keeps them in ``.gitlab-ci.yml`` (or ``.gitlab/``). Both are
scanned, along with ``pyproject.toml`` and any ``requirements``/
``constraints`` files, so the same command works whichever a project uses.

The versions themselves are matched textually rather than by parsing each
file format, because the point is to rewrite them in place without
reformatting the file around them - the same approach
:mod:`prodockit.sync_repo` takes to ``zensical.toml``.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

#: Build inputs whose version a prodockit project normally pins. Zensical
#: renders the site prodockit builds from, and WeasyPrint decides
#: pagination - which is content here, since page numbers resolve into the
#: back-of-book index and the Table of Contents. Override with
#: `packages=` for a project that pins something else too.
DEFAULT_PACKAGES = ("zensical", "weasyprint")

#: Directories never worth scanning - build output, virtualenvs, caches.
#: A stale copy of a workflow inside one of these would otherwise be
#: reported as a real declaration site.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "site",
        "public",
        "dist",
        "build",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

#: Files scanned by name, relative to the project root.
ROOT_FILES = ("pyproject.toml", ".gitlab-ci.yml", ".gitlab-ci.yaml", "setup.cfg")

#: Directories scanned wholesale for CI job definitions - GitHub Actions
#: and GitLab's own `include:` layout respectively.
CI_DIRS = (os.path.join(".github", "workflows"), ".gitlab")

#: A version specifier for one of the managed packages, anywhere in a line:
#: `zensical==0.0.52`, `"weasyprint >= 69.0"`, `zensical~=0.0.52`. The
#: package name must not be preceded by a word character, so
#: `my-zensical-fork==1.0` is left alone.
_SPEC_RE_TEMPLATE = (
    r"(?<![\w.-])(?P<name>{names})"
    # Optional extras, as in `prodockit[index]==0.17.4`. Captured rather
    # than skipped: they have to be written back on rewrite, or the pin
    # silently stops installing an optional dependency - for
    # `prodockit[index]` that means the back-of-book index stops being
    # generated, with no error anywhere.
    r"(?P<extras>\[[\w.,\s-]*\])?\s*"
    r"(?P<op>==|>=|~=|<=|!=|>|<)\s*"
    r"(?P<version>[0-9][\w.*+!-]*)"
)

#: A GitHub Actions runner label - `runs-on: ubuntu-24.04`. Not a pip
#: specifier: there is no operator, the version is joined to the name by a
#: hyphen, and it names an image rather than a package. It is pinned for
#: the same reason all the same, because it carries `pandoc`, the fonts a
#: PDF embeds and the Chrome that rasterises diagrams - none of which pip
#: can reach - so it belongs in the same inventory.
_RUNNER_RE_TEMPLATE = r"runs-on:\s*[\"']?(?P<name>{names})(?P<extras>)(?P<op>-)(?P<version>[\w.]+)"

#: A container image tag - GitLab CI's `image: python:3.13`, and the same
#: shape in any workflow that names one. An optional registry/namespace
#: prefix is skipped so `image: docker.io/library/python:3.13` matches on
#: `python`.
_IMAGE_RE_TEMPLATE = (
    r"image:\s*[\"']?(?:[\w.-]+(?:/[\w.-]+)*/)?(?P<name>{names})(?P<extras>)(?P<op>:)(?P<version>[\w.-]+)"
)

#: PyPI's own JSON metadata endpoint - no dependency needed to read it.
PYPI_URL = "https://pypi.org/pypi/{package}/json"


class PinError(Exception):
    """Raised when a declaration site cannot be read or written."""


@dataclass(frozen=True)
class PinSite:
    """One place a managed package's version is declared.

    `path` is relative to the project root, `line` is 1-based, and `op` is
    the comparison operator as written - preserved on rewrite, so a floor
    stays a floor and an exact pin stays exact.
    """

    path: str
    line: int
    package: str
    op: str
    version: str
    #: Extras as written, brackets included (`"[index]"`), or `""`. Kept
    #: verbatim so a rewrite reproduces the declaration rather than a
    #: reconstruction of it.
    extras: str = ""
    #: How this declaration is written: a pip specifier (`zensical==0.0.52`),
    #: a GitHub runner label (`runs-on: ubuntu-24.04`), or a container image
    #: tag (`image: python:3.13`). Decides whether PyPI can say what the
    #: newest release is - for the last two, nothing can.
    kind: str = "pip"

    @property
    def spec(self) -> str:
        return f"{self.package}{self.extras}{self.op}{self.version}"


@dataclass
class PackageState:
    """Every declaration of one package, and what is available for it.

    `versions` is the distinct set currently declared - more than one entry
    means the project already disagrees with itself, which is worth saying
    out loud rather than quietly resolving.
    """

    package: str
    sites: list[PinSite] = field(default_factory=list)
    latest: str | None = None
    latest_error: str | None = None

    @property
    def versions(self) -> list[str]:
        seen = []
        for site in self.sites:
            if site.version not in seen:
                seen.append(site.version)
        return seen

    @property
    def is_consistent(self) -> bool:
        return len(self.versions) <= 1

    @property
    def current(self) -> str | None:
        """The version to treat as current - the highest declared, so a
        project whose files disagree is nudged forward rather than back."""
        if not self.versions:
            return None
        return max(self.versions, key=version_key)

    @property
    def is_behind(self) -> bool:
        if self.latest is None or self.current is None:
            return False
        return version_key(self.latest) > version_key(self.current)

    @property
    def on_pypi(self) -> bool:
        """Whether PyPI can answer what the newest release is. A runner
        label or an image tag is still worth inventorying and rewriting -
        it is a build input like any other - but there is no package index
        to ask, so the current value is the only sensible default."""
        return any(site.kind == "pip" for site in self.sites) or not self.sites


def version_key(version: str) -> tuple[object, ...]:
    """Orders versions numerically segment by segment, so 0.0.9 sorts
    below 0.0.52 (a plain string compare puts it above). Non-numeric
    segments compare as strings after any numeric one, which is enough to
    keep a pre-release below its own release without implementing PEP 440
    in full - this only ever decides "is there something newer", never
    what to install."""
    parts: list[object] = []
    for chunk in re.split(r"[.\-+]", version):
        head = re.match(r"(\d*)(.*)", chunk)
        assert head is not None  # the pattern matches any string
        digits, suffix = head.groups()
        # A suffix marks a pre-release, which sorts *below* the same
        # numeric segment with none - 1.0.0rc1 before 1.0.0. Ranking the
        # suffix rather than comparing it directly is what makes that
        # work: plain string order puts "rc1" above "", i.e. the release
        # candidate above the release it precedes.
        parts.append((int(digits or 0), 0 if suffix else 1, suffix))
    return tuple(parts)


def _candidate_files(root: str) -> list[str]:
    """Every file worth scanning, root-relative, in a stable order."""
    found: list[str] = []
    for name in ROOT_FILES:
        if os.path.isfile(os.path.join(root, name)):
            found.append(name)

    for rel_dir in CI_DIRS:
        abs_dir = os.path.join(root, rel_dir)
        if not os.path.isdir(abs_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(abs_dir):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for filename in sorted(filenames):
                if filename.endswith((".yml", ".yaml")):
                    found.append(os.path.relpath(os.path.join(dirpath, filename), root))

    # requirements.txt / requirements-dev.txt / constraints.txt, top level
    # only - deeper ones belong to something else (a docs example, a
    # vendored package) more often than to this project's own build.
    for filename in sorted(os.listdir(root)):
        if re.fullmatch(r"(requirements|constraints)[\w.-]*\.txt", filename):
            found.append(filename)

    return found


def discover(
    root: str = ".", packages: tuple[str, ...] | list[str] = DEFAULT_PACKAGES
) -> dict[str, PackageState]:
    """Finds every declaration of `packages` under `root`.

    Returns one `PackageState` per package, in the order given, including
    packages with no declaration at all - a project that does not pin
    WeasyPrint yet should still see it listed rather than silently
    omitted.
    """
    states = {package: PackageState(package=package) for package in packages}
    names = "|".join(re.escape(p) for p in packages)
    # Three shapes, because a build input is not always a pip specifier -
    # see each template for what it matches and why it counts.
    patterns = [
        ("pip", re.compile(_SPEC_RE_TEMPLATE.format(names=names), re.IGNORECASE)),
        ("runner", re.compile(_RUNNER_RE_TEMPLATE.format(names=names), re.IGNORECASE)),
        ("image", re.compile(_IMAGE_RE_TEMPLATE.format(names=names), re.IGNORECASE)),
    ]

    for rel_path in _candidate_files(root):
        try:
            with open(os.path.join(root, rel_path), encoding="utf-8") as handle:
                lines = handle.read().split("\n")
        except (OSError, UnicodeDecodeError):
            # Unreadable or binary - not a declaration site anyone edits.
            continue
        for number, text in enumerate(lines, start=1):
            for kind, pattern in patterns:
                for match in pattern.finditer(text):
                    package = match.group("name").lower()
                    if package not in states:
                        continue
                    states[package].sites.append(
                        PinSite(
                            path=rel_path,
                            line=number,
                            package=package,
                            op=match.group("op"),
                            version=match.group("version"),
                            extras=match.group("extras") or "",
                            kind=kind,
                        )
                    )
    return states


def fetch_latest(package: str, *, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """Asks PyPI for `package`'s newest release.

    Returns `(version, error)` - exactly one is set. Network failure is
    normal rather than exceptional here (offline, proxied, rate-limited),
    and it should degrade to "you tell me the version" instead of
    aborting, so the caller gets a message to show rather than a
    traceback.
    """
    try:
        with urllib.request.urlopen(PYPI_URL.format(package=package), timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return None, f"could not reach PyPI ({error})"
    except json.JSONDecodeError as error:
        return None, f"PyPI returned something unreadable ({error})"

    version = (payload.get("info") or {}).get("version")
    if not isinstance(version, str) or not version:
        return None, "PyPI returned no version for this package"
    return version, None


def resolve_latest(
    states: dict[str, PackageState], *, offline: bool = False, timeout: float = 10.0
) -> None:
    """Fills in each state's `latest`/`latest_error` in place. `offline`
    skips the lookup entirely, for a run that only reports what the files
    already say."""
    for state in states.values():
        if not state.on_pypi:
            # A runner label or image tag. Asking PyPI for "ubuntu" would
            # either miss or, worse, find an unrelated package of that name
            # and report a nonsense upgrade.
            state.latest_error = "not a PyPI package - set the version yourself"
            continue
        if offline:
            state.latest_error = "skipped (offline)"
            continue
        state.latest, state.latest_error = fetch_latest(state.package, timeout=timeout)


def apply_version(root: str, state: PackageState, version: str) -> list[PinSite]:
    """Rewrites every site of `state` to `version`, preserving each site's
    own operator, and returns the sites that actually changed.

    Rewrites by line and by exact specifier text, never by a whole-file
    regex - a file may legitimately mention the same package elsewhere (a
    changelog entry, a comment, a documentation example), and only the
    lines `discover()` identified should move.
    """
    changed: list[PinSite] = []
    by_path: dict[str, list[PinSite]] = {}
    for site in state.sites:
        if site.version != version:
            by_path.setdefault(site.path, []).append(site)

    for rel_path, sites in by_path.items():
        abs_path = os.path.join(root, rel_path)
        try:
            with open(abs_path, encoding="utf-8") as handle:
                lines = handle.read().split("\n")
        except OSError as error:
            raise PinError(f"could not read {rel_path}: {error}") from error

        for site in sites:
            index = site.line - 1
            if index >= len(lines):
                raise PinError(f"{rel_path}:{site.line} no longer exists - re-run discovery")
            old = site.spec
            new = f"{site.package}{site.extras}{site.op}{version}"
            # Tolerate whitespace around the operator as written, and carry
            # any extras through untouched.
            spaced = re.compile(
                rf"(?<![\w.-]){re.escape(site.package)}{re.escape(site.extras)}\s*"
                rf"{re.escape(site.op)}\s*{re.escape(site.version)}(?![\w.])",
                re.IGNORECASE,
            )
            replaced, count = spaced.subn(new, lines[index])
            if not count:
                raise PinError(
                    f"{rel_path}:{site.line} no longer contains {old!r} - re-run discovery"
                )
            lines[index] = replaced
            changed.append(site)

        try:
            with open(abs_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
        except OSError as error:
            raise PinError(f"could not write {rel_path}: {error}") from error

    return changed

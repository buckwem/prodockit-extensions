# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.template_sync: bringing a project back into step with the
template it was generated from, without touching the work in it.

A project generated from `prodockit-template` diverges the moment
somebody starts writing. Most of that divergence is theirs and must be
left alone; a smaller part is the template's - stylesheets, CI, the
Node tooling - and goes stale silently. This finds the second kind and
nothing else (prodockit-template#188).

The rules live in a manifest shipped *with the template*, not here, so a
file added to the template arrives with the commit that adds it rather
than waiting for a prodockit release. This module reads that manifest,
works out which template version a project came from, and says what
would change.

Nothing in here writes. The stages that do come later; these are the
three that decide whether writing is safe at all:

1. resolve the template a project should track, from its own remote
2. read and validate the manifest
3. work out the baseline version, and with it which files were edited
"""

from __future__ import annotations

import fnmatch
import os
import pathlib
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

if sys.version_info >= (3, 11):  # pragma: no cover - one branch per interpreter
    import tomllib
else:  # pragma: no cover - `tomllib` is 3.11+, and this package supports 3.10
    import tomli as tomllib

#: Where each host's template lives. A project on Surrey's GitLab tracks
#: Surrey's mirror, because a student there may have no GitHub access at
#: all; everyone else tracks the canonical copy. So this is a lookup with
#: a default, not "the same host as the project".
TEMPLATE_REMOTES = {
    "gitlab.surrey.ac.uk": "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git",
    "gitlab.com": "git@github.com:buckwem/prodockit-template.git",
    "github.com": "git@github.com:buckwem/prodockit-template.git",
}

#: The host each override flag names, and how a slug becomes a remote.
OVERRIDE_HOSTS = {
    "github": ("github.com", "git@github.com:{slug}.git"),
    "surrey": ("gitlab.surrey.ac.uk", "git@gitlab.surrey.ac.uk:{slug}.git"),
}

#: The file a project records its baseline in, once one is established.
STAMP_FILE = ".prodockit-template"

#: The manifest, in the template.
MANIFEST_FILE = ".prodockit-template.toml"

#: Where every run appends its full account of itself. Kept out of git by
#: `missing_ignores` below: it is a diagnostic, not part of the project.
LOG_FILE = ".prodockit-template.log"


class TemplateSyncError(ValueError):
    """A sync that cannot be run as asked.

    Raised rather than worked around. Every failure here is one where
    guessing produces a plausible wrong answer - the wrong template, an
    unclassified file, a baseline nobody confirmed - and a plausible
    wrong answer is what this tool exists to avoid.
    """


@dataclass(frozen=True)
class Manifest:
    """Who owns what, read from the template it applies to.

    Read from the *new* version, at a tag: a working copy carries
    untracked local artefacts, and delivering those as though they were
    part of a release is how a spike directory ends up in somebody's
    report.
    """

    template_owns: tuple[str, ...] = ()
    project_owns: tuple[str, ...] = ()
    seed: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    take: tuple[str, ...] = ()
    never: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    renames: dict[str, str] = field(default_factory=dict)

    def rename(self, path: str) -> str:
        """The template's path, as the project spells it.

        A project generated before a directory was renamed still has the
        old name. Comparing before renaming gives it a second copy of
        every file in that directory rather than an update to the one it
        has.

        For locating the project's copy only. Ownership is decided on the
        template's own spelling, because that is how the manifest is
        written - classifying the renamed path asks whether
        `docs/javascript/extra.js` matches `docs/javascripts/**`, which
        it does not, and reports a file the manifest plainly claims as
        unclassified.
        """
        for old, new in self.renames.items():
            if path == new:
                return old
            if path.startswith(new + "/"):
                return old + path[len(new) :]
        return path

    def owner(self, path: str) -> str:
        """Which rule claims this path: template, project, shared,
        excluded - or `unclassified`, which is an error rather than a
        default."""
        for name, globs in (
            ("template", self.template_owns),
            ("project", self.project_owns),
            ("shared", self.shared),
            ("excluded", self.excluded),
        ):
            if _matches(path, globs):
                return name
        return "unclassified"


def _matches(path: str, globs: Iterable[str]) -> bool:
    """Whether a path matches any of these globs.

    `dir/**` needs no special case: `fnmatch`'s `*` crosses `/`, so the
    pattern already matches every depth below `dir`. A branch for it was
    written here first and removed - it only ever answered for the bare
    directory entry, which nothing classifies, and code that looks
    load-bearing and is not costs more than the line it saves.
    """
    return any(fnmatch.fnmatch(path, glob) for glob in globs)


def load_manifest(text: str) -> Manifest:
    """Reads a manifest, or says why it cannot."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise TemplateSyncError(f"{MANIFEST_FILE} is not valid TOML: {error}") from error

    def strings(section: str, key: str) -> tuple[str, ...]:
        value = data.get(section, {}).get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise TemplateSyncError(f"{section}.{key} must be a list of strings")
        return tuple(value)

    renames = data.get("renames", {})
    if not isinstance(renames, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in renames.items()
    ):
        raise TemplateSyncError("renames must be a table of old = new strings")

    manifest = Manifest(
        template_owns=strings("template", "owns"),
        project_owns=strings("project", "owns"),
        seed=strings("project", "seed"),
        ignore=strings("project", "ignore"),
        shared=strings("shared", "files"),
        take=tuple(data.get("shared", {}).get("zensical_toml", {}).get("take", [])),
        never=tuple(data.get("shared", {}).get("zensical_toml", {}).get("never", [])),
        excluded=strings("excluded", "paths"),
        renames=dict(renames),
    )

    # A seed is a project-owned file the template writes once. One that
    # is not project-owned would be updated by the very rule it exists to
    # be exempt from.
    stray = [s for s in manifest.seed if not _matches(s, manifest.project_owns)]
    if stray:
        raise TemplateSyncError(
            f"seeded but not project-owned: {', '.join(stray)} - a seed is written "
            "once and then belongs to the project, so it has to be project-owned"
        )
    return manifest


def unclassified(manifest: Manifest, paths: Sequence[str]) -> list[str]:
    """Files in the template that no rule claims.

    Checked rather than defaulted, because both defaults are wrong:
    treating an unknown file as the template's overwrites somebody's
    work, and treating it as the project's silently stops delivering it.
    A manifest that does not classify its own tree is a bug in the
    manifest, and this is how it is found.
    """
    return [p for p in paths if manifest.owner(p) == "unclassified"]


def resolve_template(
    origin: str | None,
    *,
    github: str | None = None,
    surrey: str | None = None,
    explicit: bool = False,
) -> str:
    """Which template a project should be brought into step with.

    Derived from the project's own remote, so neither a student nor a
    maintainer has to know the answer. `--github`/`--surrey` override it,
    bare for that host's usual template or with `group/repo` for another.

    `explicit` says a flag was given at all, which is what separates
    `--github` (that host's default) from no flag (derive).
    """
    if github is not None and surrey is not None:
        raise TemplateSyncError(
            "--github and --surrey name two different templates; give one"
        )
    for flag, slug in (("github", github), ("surrey", surrey)):
        if slug is None:
            continue
        host, shape = OVERRIDE_HOSTS[flag]
        if not slug:  # bare flag: that host's usual template
            return TEMPLATE_REMOTES[host]
        if slug.count("/") < 1:
            raise TemplateSyncError(
                f"--{flag} takes group-or-name/repo, e.g. --{flag} buckwem/prodockit-template"
            )
        return shape.format(slug=slug.removesuffix(".git"))
    if explicit:  # a flag was given with no value and no host matched
        raise TemplateSyncError("no template named")

    if not origin:
        raise TemplateSyncError(
            "this project has no `origin` remote, so the template it came from "
            "cannot be derived - name one with --github or --surrey"
        )
    host = _host_of(origin)
    if host not in TEMPLATE_REMOTES:
        raise TemplateSyncError(
            f"no template is known for {host} - name one with --github or --surrey"
        )
    return TEMPLATE_REMOTES[host]


def cache_root(
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> pathlib.Path:
    """Where fetched templates are kept, per platform convention.

    `env` and `platform` are arguments rather than reads of the live
    process so a test can ask about a platform it is not running on. A
    check that reads `os.environ` or `sys.platform` directly passes or
    fails for reasons that have nothing to do with the code.
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform

    if override := env.get("PRODOCKIT_CACHE"):
        return pathlib.Path(override)
    if platform == "win32":
        if local := env.get("LOCALAPPDATA"):
            return pathlib.Path(local) / "prodockit" / "cache"
    elif platform == "darwin":
        return pathlib.Path(env.get("HOME", "~")).expanduser() / "Library" / "Caches" / "prodockit"
    if xdg := env.get("XDG_CACHE_HOME"):
        return pathlib.Path(xdg) / "prodockit"
    return pathlib.Path(env.get("HOME", "~")).expanduser() / ".cache" / "prodockit"


def cache_path_for(remote: str, root: pathlib.Path) -> pathlib.Path:
    """Where one template's checkout belongs under the cache root.

    Keyed by host *and* namespace, because a project on Surrey's GitLab
    and one on GitHub track different templates that share a repository
    name - caching them at the same path would hand a project the other
    one's files.
    """
    from prodockit.sync_repo import SyncRepoError, parse_remote

    try:
        host, namespace, repo = parse_remote(remote)
    except SyncRepoError as error:
        raise TemplateSyncError(
            f"cannot work out where to cache the template for {remote!r}"
        ) from error
    parts = [host, *namespace.split("/"), repo]
    safe = ["".join(c if c.isalnum() or c in "._-" else "-" for c in part) for part in parts]
    return root.joinpath("templates", *safe)


def ensure_template(remote: str, path: pathlib.Path, run: GitRunner) -> str:
    """Makes sure a checkout of the template is at `path`, and returns
    which of three things happened: `cloned`, `updated` or `offline`.

    Three, not two. A fetch that cannot reach the host is not the same
    answer as one that found nothing new, and it is not a failure either
    - a student on a train should still be able to see what their project
    would do. It has to be *said*, though, because the alternative is
    syncing against a template that is quietly months old.

    The hard reset is safe only because this path is the tool's own cache,
    never a checkout anybody works in; `--template-path` exists for that.
    """
    if (path / ".git").exists():
        if not run(["git", "-C", str(path), "fetch", "--quiet", "origin"]):
            return "offline"
        if not run(["git", "-C", str(path), "reset", "--hard", "--quiet", "FETCH_HEAD"]):
            raise TemplateSyncError(
                f"the cached template at {path} could not be moved to the fetched "
                "version - delete that directory and run this again"
            )
        return "updated"

    path.parent.mkdir(parents=True, exist_ok=True)
    if not run(["git", "clone", "--quiet", remote, str(path)]):
        raise TemplateSyncError(
            f"could not fetch the template from {remote} - check the network, and "
            "that you can reach that host (a Surrey template needs your GitLab "
            "access), or point this at a checkout with --template-path"
        )
    return "cloned"


def _host_of(remote: str) -> str:
    """The hostname in a git remote, SSH or HTTPS.

    Deliberately small: `prodockit.sync_repo.parse_remote` already does
    the full job including GitLab's nested groups, and is used where the
    namespace matters. Here only the host decides anything.
    """
    from prodockit.sync_repo import SyncRepoError, parse_remote

    try:
        host, _namespace, _repo = parse_remote(remote)
    except SyncRepoError as error:
        raise TemplateSyncError(
            f"the `origin` remote is not one this can read a host from ({remote!r}) "
            "- name the template with --github or --surrey"
        ) from error
    return host


@dataclass(frozen=True)
class Baseline:
    """Which template version a project matches, and what it has edited.

    The two answers come from one calculation, which is why they are one
    result: a file that matches no version of the template is exactly a
    file somebody has changed.
    """

    version: str | None
    matched: int
    total: int
    edited: tuple[str, ...] = ()
    agreeing: tuple[str, ...] = ()

    @property
    def derived(self) -> bool:
        """Whether this came from scanning rather than from a stamp."""
        return self.version is not None and self.matched < self.total


def derive_baseline(
    template_owned: Sequence[str],
    project_blob: Callable[[str], str | None],
    versions: Sequence[str],
    template_blob: Callable[[str, str], str | None],
) -> Baseline:
    """The newest template version the project's files agree with.

    Content, not dates: a project records nothing about where it came
    from until this tool writes a stamp, and asking the reader to
    remember is asking for a guess. Every template-owned file is compared
    by blob hash against each version, newest first, and the best
    agreement wins.

    The files that still disagree at that version are the edited ones -
    the same scan answers both questions, and neither answer is
    trustworthy without the other. Being behind and having edited a file
    look identical until the baseline is known.
    """
    present = {path: blob for path in template_owned if (blob := project_blob(path))}
    if not present:
        return Baseline(version=None, matched=0, total=0)

    best = Baseline(version=None, matched=-1, total=len(present))
    for version in versions:
        disagree = tuple(
            path for path, blob in present.items() if template_blob(version, path) != blob
        )
        agreed = len(present) - len(disagree)
        if agreed > best.matched:
            best = Baseline(
                version=version,
                matched=agreed,
                total=len(present),
                edited=disagree,
                agreeing=tuple(p for p in present if p not in set(disagree)),
            )
        if agreed == len(present):
            break  # nothing will beat a complete match
    return best


#: Groups in the order a report reads best: what will be touched, what
#: will not, what needs deciding, what is not delivered at all.
REPORT_ORDER = ("template", "project", "shared", "excluded", "unclassified")

#: What each group means an update will *do*, said in the report rather
#: than left to be inferred from the group's name. "project" and
#: "excluded" both mean untouched, for entirely different reasons, and a
#: reader should not have to know the manifest to tell them apart.
GROUP_ACTIONS = {
    "template": "replace where unedited",
    "project": "never written",
    "shared": "merge",
    "excluded": "not delivered",
    "unclassified": "error - the manifest must classify every file",
}


def classification_report(
    manifest: Manifest, paths: Sequence[str], *, verbose: bool = False
) -> list[str]:
    """What the manifest makes of a template's files.

    Counts by default, because the point of the summary is that the
    numbers add up to the whole tree - a reader can see nothing has been
    missed without reading 69 lines.

    `verbose` lists every file under its group. That is the form worth
    having when the question is "why is *this* file being replaced",
    which a count cannot answer.
    """
    groups: dict[str, list[str]] = {name: [] for name in REPORT_ORDER}
    for path in paths:
        groups[manifest.owner(path)].append(path)

    lines: list[str] = []
    for name in REPORT_ORDER:
        members = groups[name]
        if name == "unclassified" and not members:
            continue  # nothing to say, and saying it invites a shrug
        lines.append(f"{name:12} {len(members):3} files  ({GROUP_ACTIONS[name]})")
        if verbose:
            lines.extend(f"    {path}" for path in sorted(members))
    return lines


def baseline_report(baseline: Baseline, *, verbose: bool = False) -> list[str]:
    """What was concluded about where a project came from.

    The edited files are always listed, however long the list: they are
    the reason the tool will leave something alone, and a count of them
    is not actionable. `verbose` adds the files that agreed, which is how
    somebody checks the conclusion rather than taking it.
    """
    if baseline.version is None:
        return ["no template-owned files found - nothing to compare"]

    lines = [
        f"baseline     {baseline.version}",
        f"agreeing     {baseline.matched} of {baseline.total}",
        f"edited       {len(baseline.edited)}",
    ]
    lines.extend(f"    {path}" for path in baseline.edited)
    if verbose:
        lines.append("agreeing files")
        lines.extend(f"    {path}" for path in sorted(baseline.agreeing))
    return lines


#: What an update would do to one file, and why. The reason is carried
#: rather than re-derived for the report: "differs" is not a reason, and
#: a reader deciding whether to pass `--force` needs to know whether the
#: difference is theirs or the template's.
@dataclass(frozen=True)
class FileAction:
    path: str
    project_path: str
    action: str
    reason: str


#: Every action a file can be given, and what it means for the project.
FILE_ACTIONS = {
    "same": "already matches the template",
    "add": "absent here - the template has gained it",
    "update": "behind - not edited here",
    "keep": "edited here - yours kept, template's written alongside as .new",
    "forced": "edited here - overwritten on request",
}


def blocking_changes(manifest: Manifest, dirty: Iterable[str]) -> list[str]:
    """Uncommitted changes that must be dealt with before an update runs.

    Only template-owned paths block. A project being written always has
    a dirty tree - the report itself, its figures, its bibliography - and
    refusing on any of that refuses always, which is the same as not
    having the tool (prodockit-template#188).

    The point is narrower than tidiness: this is what makes `--force`
    safe. Anything an update can overwrite is committed, so `git
    checkout` gets it back. Widen this and that guarantee goes with it.
    """
    return sorted(p for p in dirty if manifest.owner(p) == "template")


def plan_template_files(
    manifest: Manifest,
    template_files: Sequence[str],
    project_blob: Callable[[str], str | None],
    template_blob: Callable[[str], str | None],
    baseline: Baseline,
    *,
    force: Iterable[str] = (),
) -> list[FileAction]:
    """What an update would do to each template-owned file.

    Three inputs decide it, and all three are needed: what the project
    has, what the template has now, and which files the project edited.
    Without the last, "differs" cannot tell being behind from having
    changed something, and the tool would either overwrite work or never
    update anything.
    """
    forced = {f.removeprefix("./") for f in force}
    edited = set(baseline.edited)
    actions: list[FileAction] = []

    for path in template_files:
        if manifest.owner(path) != "template":
            continue
        here = manifest.rename(path)
        mine, theirs = project_blob(here), template_blob(path)
        if mine is None:
            actions.append(FileAction(path, here, "add", FILE_ACTIONS["add"]))
        elif mine == theirs:
            actions.append(FileAction(path, here, "same", FILE_ACTIONS["same"]))
        elif path in edited or here in edited:
            forced_here = path in forced or here in forced
            name = "forced" if forced_here else "keep"
            actions.append(FileAction(path, here, name, FILE_ACTIONS[name]))
        else:
            actions.append(FileAction(path, here, "update", FILE_ACTIONS["update"]))
    return actions


def update_report(
    actions: Sequence[FileAction], *, verbose: bool = False
) -> list[str]:
    """What the update would do, grouped by action.

    `same` is counted and never listed even in verbose: it is almost
    every file, it is the uninteresting case, and burying the five that
    matter under sixty that do not is how a report stops being read.
    """
    grouped: dict[str, list[FileAction]] = {name: [] for name in FILE_ACTIONS}
    for action in actions:
        grouped[action.action].append(action)

    lines: list[str] = []
    for name, description in FILE_ACTIONS.items():
        members = grouped[name]
        if not members:
            continue
        lines.append(f"{name:8} {len(members):3}  ({description})")
        if name == "same" and not verbose:
            continue
        if name == "same":
            continue
        for action in sorted(members, key=lambda a: a.project_path):
            suffix = "" if action.project_path == action.path else f"   <- {action.path}"
            lines.append(f"    {action.project_path}{suffix}")
    return lines


def missing_seeds(manifest: Manifest, exists: Callable[[str], bool]) -> list[str]:
    """Seeded files the project does not have, under either name.

    Only absence matters. A seed is written once and then belongs to the
    project - `LICENSE.md` being the case that makes it obvious, since a
    project may rightly change its licence and an update that restored
    the template's would be wrong rather than helpful.

    Both spellings are checked. A project generated before `LICENSE`
    became `LICENSE.md` has the old one, and a newer project has the new
    one; looking for only one of them seeds a second licence beside the
    first.
    """
    return [
        s for s in manifest.seed if not exists(s) and not exists(manifest.rename(s))
    ]


def _dotted(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Every leaf in a parsed TOML document, by dotted path.

    Tables are walked; anything else is a value. `prodockit.tables` is a
    table *name* containing a dot, which is exactly why the manifest
    quotes it - the quoting is preserved here so a pattern can match the
    whole name rather than treating it as two levels.
    """
    out: dict[str, Any] = {}
    for key, value in data.items():
        name = f'"{key}"' if "." in key else key
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            nested = _dotted(value, path)
            out.update(nested or {path: value})
        else:
            out[path] = value
    return out


def _taken(key: str, patterns: Sequence[str]) -> bool:
    """Whether a dotted key is one the template may set.

    A pattern naming a *table* claims what is inside it:
    `project.markdown_extensions."prodockit.*"` has to reach
    `...tables".x`, or every extension's settings would be missed while
    the bare, empty tables matched. So each ancestor is tested too.
    """
    parts = key.split(".")
    # Quoted names contain dots; rebuild them before walking prefixes.
    rebuilt: list[str] = []
    for part in parts:
        if rebuilt and rebuilt[-1].startswith('"') and not rebuilt[-1].endswith('"'):
            rebuilt[-1] += "." + part
        else:
            rebuilt.append(part)
    return any(
        _matches(".".join(rebuilt[: i + 1]), patterns) for i in range(len(rebuilt))
    )


def read_config(text: str) -> dict[str, Any]:
    """Parses a project's or template's `zensical.toml`.

    Here rather than in the caller so the 3.10 shim above is the only one
    - `tomllib` arrived in 3.11, and a second conditional import is a
    second place to get it wrong.
    """
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise TemplateSyncError(f"zensical.toml is not valid TOML: {error}") from error


def config_changes(
    manifest: Manifest, template_config: dict[str, Any], project_config: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Which of the template's own config keys a project is missing or
    has differently: `(added, updated)`.

    Nothing is ever removed. A reader who switched `prodockit.bibliography`
    off has made a choice, and a tool that turns it back on because the
    template has it is not updating anything - it is reverting them.

    `never` is the other half of that. A pattern broad enough to be
    useful catches keys that hold the project's *content* rather than its
    settings: `project.extra.pdf_*` covers the margins and the page size,
    and also `pdf_copyright`, which on a real assignment reads
    `Author: 123456` against the template's own name. Overwriting that
    would put the template author's name on somebody else's report, which
    is precisely what this tool exists not to do.
    """
    take, never = manifest.take, manifest.never
    theirs = {
        k: v
        for k, v in _dotted(template_config).items()
        if _taken(k, take) and not _matches(k, never)
    }
    mine = _dotted(project_config)
    added = sorted(k for k in theirs if k not in mine)
    updated = sorted(k for k in theirs if k in mine and mine[k] != theirs[k])
    return added, updated


def missing_ignores(manifest: Manifest, current: Sequence[str]) -> list[str]:
    """Ignore lines the template has and the project lacks.

    Append-only: a project's own ignores are its own, and there is no way
    to tell a stale template line from a deliberate local one.
    """
    have = {line.strip() for line in current}
    wanted = [*manifest.ignore, LOG_FILE]
    return [line for line in wanted if line.strip() not in have]


def leftovers(manifest: Manifest, project_files: Iterable[str]) -> list[str]:
    """Files the project has that are no longer delivered.

    Reported, never deleted. Removing files from somebody's repository
    because a manifest changed its mind is a different and more dangerous
    operation than updating a file the template owns.
    """
    return sorted(p for p in project_files if manifest.owner(p) == "excluded")


# ---------------------------------------------------------------------------
# Applying: the writing half
# ---------------------------------------------------------------------------


def _table_header(dotted: str) -> tuple[str, str] | None:
    """Split a dotted key into `(table, key)`, or None if it names a table.

    `project.extra.pdf_page_size` is a key in `[project.extra]`;
    `project.markdown_extensions."prodockit.tree"` is a table with no key
    of its own. The difference decides whether a value is edited or a
    header inserted.
    """
    parts: list[str] = []
    for part in dotted.split("."):
        if parts and parts[-1].startswith('"') and not parts[-1].endswith('"'):
            parts[-1] += "." + part
        else:
            parts.append(part)
    if parts[-1].startswith('"'):
        return None  # a quoted name is a table, not a key
    return ".".join(parts[:-1]), parts[-1]


def set_config_value(text: str, dotted: str, rendered: str) -> str:
    """Sets one key in a TOML document, leaving every other line alone.

    Surgical rather than a parse-and-dump round trip. This project's
    `zensical.toml` is 604 lines of which 367 are comments explaining why
    each setting is what it is; re-emitting the document would discard
    all of them and reorder the rest, turning a one-line change into a
    diff nobody can review (prodockit-template#188).

    Raises rather than guessing when the table is not found. Appending a
    key to the end of a file lands it in whatever table happens to be
    last, which is a wrong answer that looks like a right one.
    """
    split = _table_header(dotted)
    if split is None:
        raise TemplateSyncError(f"{dotted} names a table, not a key")
    table, key = split

    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"[{table}]":
            start = index
            break
    if start is None:
        raise TemplateSyncError(f"no [{table}] table in this file")

    for index in range(start + 1, len(lines)):
        stripped = lines[index].lstrip()
        if stripped.startswith("["):
            break  # the next table began; the key is absent
        name = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if name == key:
            lines[index] = f"{key} = {rendered}\n"
            return "".join(lines)

    # Absent: insert directly under the header, before the table's own
    # comments so the new line is not attributed to the wrong setting.
    lines.insert(start + 1, f"{key} = {rendered}\n")
    return "".join(lines)


def add_config_table(text: str, dotted: str) -> str:
    """Adds an empty table, if the document does not already have it.

    Appended at the end of the document rather than beside its siblings:
    TOML has no requirement that tables be grouped, and inserting into
    the middle of a heavily commented file risks attaching the new header
    to a comment written about the setting above it.
    """
    header = f"[{dotted}]"
    if any(line.strip() == header for line in text.splitlines()):
        return text
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return f"{text}{separator}{header}\n"


def append_ignores(text: str, lines: Sequence[str]) -> str:
    """Adds ignore lines the file does not have, at the end.

    Append-only, and never reordered: a `.gitignore` is read top to
    bottom by people as well as by git, and shuffling somebody's own
    entries to make room is not an update.
    """
    if not lines:
        return text
    have = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines if line.strip() not in have]
    if not missing:
        return text
    prefix = text if text.endswith("\n") or not text else text + "\n"
    return prefix + "\n".join(missing) + "\n"


#: Written beside a file the project has edited, rather than over it.
SIDECAR_SUFFIX = ".new"


@dataclass(frozen=True)
class Written:
    """One file an apply actually touched, and what it did.

    Reported from what was written rather than from what was planned:
    the two agreeing is the thing worth checking, and a report generated
    from the plan cannot notice them disagreeing.
    """

    path: str
    action: str


def pending_writes(
    actions: Sequence[FileAction],
    project_root: pathlib.Path,
    read_template: Callable[[str], bytes],
    *,
    sidecar: str = SIDECAR_SUFFIX,
) -> list[FileAction]:
    """The actions in a plan that would actually change something.

    `same` is not the only action that can amount to nothing. A `keep`
    writes the template's copy to a `.new` sidecar, and on the second run
    against the same template version that sidecar is already there with
    exactly those bytes - so the run has nothing to do and should not say
    otherwise.

    That mattered more than it sounds. A run with nothing to write still
    branched, still announced "staged, not committed", and left a student
    looking for a change that did not exist - and the empty branch it left
    behind then blocked the *next* run.
    """
    pending = []
    for action in actions:
        if action.action == "same":
            continue
        target = project_root / action.project_path
        if action.action == "keep":
            target = target.with_name(target.name + sidecar)
        if target.exists() and target.read_bytes() == read_template(action.path):
            continue
        pending.append(action)
    return pending


def apply_file_actions(
    actions: Sequence[FileAction],
    project_root: pathlib.Path,
    read_template: Callable[[str], bytes],
    *,
    sidecar: str = SIDECAR_SUFFIX,
) -> list[Written]:
    """Carries out a plan, and writes nothing it was not asked to.

    Only `add`, `update` and `forced` replace a file the project has.
    `keep` writes the template's copy *beside* the project's, under
    `sidecar`, so the two can be compared without either being lost -
    which is the whole reason an edited file is not simply skipped.

    `same` writes nothing at all. It is most of the tree, and a tool that
    rewrites identical bytes makes every update look like a change to
    anyone reading `git status` afterwards.
    """
    written: list[Written] = []
    for action in pending_writes(actions, project_root, read_template, sidecar=sidecar):
        target = project_root / action.project_path
        if action.action == "keep":
            target = target.with_name(target.name + sidecar)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_template(action.path))
        written.append(Written(str(target.relative_to(project_root)), action.action))
    return written


def written_report(written: Sequence[Written]) -> list[str]:
    """What an apply did, grouped the way the plan was reported.

    Deliberately built from `Written` rather than from the plan: if the
    two ever disagree, this is where it shows.
    """
    if not written:
        return ["nothing to write - this project is already in step"]
    grouped: dict[str, list[str]] = {}
    for item in written:
        grouped.setdefault(item.action, []).append(item.path)
    lines = []
    for action, paths in grouped.items():
        lines.append(f"{action:8} {len(paths):3}  ({FILE_ACTIONS[action]})")
        lines.extend(f"    {path}" for path in sorted(paths))
    return lines


def _render(value: object) -> str:
    """A TOML literal for a value taken from the template.

    Only the shapes a settings file actually holds. Anything else raises
    rather than being guessed at: a wrongly quoted value produces a
    config that parses and means something different, which is worse
    than a refusal.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return "[" + ", ".join(_render(v) for v in value) + "]"
    raise TemplateSyncError(
        f"cannot write {type(value).__name__} into TOML - "
        "this setting has to be copied by hand"
    )


def apply_config_changes(
    text: str,
    template_config: dict[str, Any],
    added: Sequence[str],
    updated: Sequence[str],
) -> str:
    """Puts the template's own settings into a project's config.

    Tables first, then values: a key cannot be written into a table that
    is not there yet, and a project that has never had an extension has
    neither.
    """
    values = _dotted(template_config)
    for key in added:
        if _table_header(key) is None:
            text = add_config_table(text, key)
    for key in [*added, *updated]:
        split = _table_header(key)
        if split is None:
            continue  # a bare table, already added above
        table, _name = split
        if not any(line.strip() == f"[{table}]" for line in text.splitlines()):
            text = add_config_table(text, table)
        text = set_config_value(text, key, _render(values[key]))
    return text


def apply_seeds(
    manifest: Manifest,
    project_root: pathlib.Path,
    read_template: Callable[[str], bytes],
) -> list[Written]:
    """Writes seeded files the project does not have.

    Absence is the whole test. A seed that is present is never touched,
    however far it has diverged - `LICENSE.md` being the case that makes
    it obvious, since a project may rightly change its licence.
    """
    written: list[Written] = []
    for seed in missing_seeds(manifest, lambda p: (project_root / p).exists()):
        # Under the template's own name. The rename table says what an
        # *existing* file may be called here, which is a different
        # question from what a new one should be called - writing
        # `LICENSE` into a project that has neither would seed the name
        # the template has already moved away from.
        target = project_root / seed
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_template(seed))
        written.append(Written(str(target.relative_to(project_root)), "add"))
    return written


#: What stage 8 hands to another command rather than writing itself.
#: `prodockit pins` owns every version declaration in a project and knows
#: each site's own operator; `prodockit sync-repo` owns the README badge
#: block. Two tools writing the same lines would fight, and the loser
#: would be whichever ran last.
DELEGATED = {
    "requirements.txt": ["prodockit", "pins", "--check"],
    "README.md": ["prodockit", "sync-repo"],
}


#: What a run does to git, as a command it could have typed. Injected so
#: the tests never touch a real repository, and so the report can show a
#: reader exactly what was run on their behalf.
GitRunner = Callable[[Sequence[str]], bool]


def branch_name(version: str) -> str:
    """The branch a run puts its work on.

    Short and legible: `git describe` on a template whose tags belong to
    something else produces `0.0.26-12-g2ae6640`, which names a branch
    nobody can read or type. A tag is used as it stands; anything else is
    cut to a short hash.
    """
    label = version.strip()
    if not label:
        raise TemplateSyncError("no template version to name a branch after")
    if len(label) == 40 and all(c in "0123456789abcdef" for c in label):
        label = label[:9]
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in label)
    return f"template-update-{safe.strip('-')}"


def start_branch(run: GitRunner, name: str) -> bool:
    """Puts the working tree on its own branch, *before* anything is
    written.

    Deliberately first rather than last. An update adds files as well as
    changing them, and `git checkout .` does not remove what it never
    tracked - so a reader who wants to undo a run cannot simply revert
    the tracked half. Branching first makes the whole run one thing to
    abandon.

    Returns whether the branch was created. An existing branch of that
    name is resumed rather than replaced - a second run against the same
    template version belongs on the same branch, and deleting it would
    throw away whatever the first run left - but only if it already
    contains the commit you are on, or holds nothing that is not already
    in it.

    That condition is the whole point. The name is derived from the
    template version, so a project that syncs from the same baseline
    twice wants the same branch name both times; checking it out
    unconditionally silently moves the run, and the reader, onto older
    work. Found doing exactly that in a test clone: the run reported
    success on a branch two commits behind the one it started from.

    Refusing outright is too blunt, though. A branch left behind by an
    earlier run is usually either merged or empty, and over a term that
    is the ordinary case - a student who had done nothing wrong was
    blocked on every run by a branch a previous run had created and left
    with nothing in it. So a branch that is merely *behind* is moved
    forward, and only one holding commits of its own is refused.
    """
    if not run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"]):
        return run(["git", "checkout", "-b", name])

    if run(["git", "merge-base", "--is-ancestor", "HEAD", name]):
        return run(["git", "checkout", name])

    # The other safe case, and the common one over a term: the branch is
    # *behind*, holding nothing the project does not already have. Either
    # its run was merged, or it was created by a run that turned out to
    # have nothing to write. Moving it forward loses nothing.
    if run(["git", "merge-base", "--is-ancestor", name, "HEAD"]):
        return run(["git", "checkout", "-B", name])

    # False in both directions means either genuine divergence or a
    # question that could not be put at all. Told apart here, so a
    # repository that cannot be read does not report as a stale branch.
    if not run(["git", "rev-parse", "--verify", "--quiet", "HEAD"]):
        raise TemplateSyncError(
            f"cannot tell whether the branch {name} is safe to continue on, "
            "because this repository's HEAD could not be read"
        )
    raise TemplateSyncError(
        f"the branch {name} already exists and holds commits this project does "
        "not, so continuing would run this against work that has diverged. Merge "
        f"it, or delete it with `git branch -D {name}`, and run this again"
    )


def now() -> str:
    """The current local time, ISO 8601, with the offset kept.

    Local because whoever reads the log is usually the person who ran it;
    with the offset because the person diagnosing it often is not.
    """
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ignore_the_log(project_root: pathlib.Path) -> bool:
    """Makes sure `.gitignore` covers the log. True if a line was added.

    Done whenever the log is written, rather than left to the `.gitignore`
    stage, because that stage only runs under `--apply` - and a dry run
    would otherwise leave an untracked diagnostic file for the next
    `git add -A` to sweep into the project.
    """
    path = project_root / ".gitignore"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if LOG_FILE in {line.strip() for line in current.splitlines()}:
        return False
    path.write_text(append_ignores(current, [LOG_FILE]), encoding="utf-8")
    return True


def append_log(
    project_root: pathlib.Path,
    lines: Sequence[str],
    started: str,
    command: Sequence[str] | None = None,
) -> pathlib.Path:
    """Appends one run's full account to the project's log.

    Appended, never truncated: the run worth diagnosing is usually not
    the last one. Written whether or not `--apply` was passed and whether
    or not the terminal asked for `--verbose`, because the run a student
    reports is the one they ran without either.
    """
    path = project_root / LOG_FILE
    argv = list(command if command is not None else sys.argv)
    body = "\n".join(lines)
    entry = (
        f"=== {started}  started  {' '.join(argv)}\n"
        f"{body}\n"
        f"=== {now()}  finished\n\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return path


def write_stamp(project_root: pathlib.Path, version: str) -> pathlib.Path:
    """Records which template version this project now matches.

    Written last, so it describes a state that exists. Written at all so
    the next run reads it instead of deriving the answer again - the
    derivation is sound, but it is a scan of every version in the
    template's history, and it cannot tell a file somebody edited from
    one the template never had.
    """
    path = project_root / STAMP_FILE
    path.write_text(f"{version.strip()}\n", encoding="utf-8")
    return path


def read_stamp(project_root: pathlib.Path) -> str | None:
    """The recorded version, or None when there is none to read."""
    path = project_root / STAMP_FILE
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def stage_changes(run: GitRunner, paths: Sequence[str]) -> bool:
    """Stages what the run wrote, and stops there.

    The commit is the reader's. It is their history, and a message
    written by a tool about somebody else's project is worth less than
    the thirty seconds it saves - they are the ones who will read it in
    six months.
    """
    if not paths:
        return True
    return run(["git", "add", "--", *paths])


def git_runner(project_root: pathlib.Path) -> GitRunner:
    """A `GitRunner` that runs git in a project, quietly.

    Success or failure only. Every call this module makes is one whose
    output nobody needs and whose failure is handled by the caller -
    asking for a branch that is not there is how `start_branch` decides
    to create it, so a non-zero exit is an answer rather than an error.

    `git` is found the way the rest of prodockit finds it, so a Windows
    reader whose PATH has not caught up still gets a working command
    (prodockit-extensions#451).
    """
    from prodockit.tools import find

    def run(command: Sequence[str]) -> bool:
        binary = find("git") if command and command[0] == "git" else command[0]
        try:
            completed = subprocess.run(
                [binary, *command[1:]],
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        except OSError:  # git missing entirely
            return False
        return completed.returncode == 0

    return run

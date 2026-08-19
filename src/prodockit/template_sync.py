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
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
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


def _host_of(remote: str) -> str:
    """The hostname in a git remote, SSH or HTTPS.

    Deliberately small: `prodockit.sync_repo.parse_remote` already does
    the full job including GitLab's nested groups, and is used where the
    namespace matters. Here only the host decides anything.
    """
    from prodockit.sync_repo import parse_remote

    host, _namespace, _repo = parse_remote(remote)
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
    """Seeded files the project does not have.

    Only absence matters. A seed is written once and then belongs to the
    project - `LICENSE.md` being the case that makes it obvious, since a
    project may rightly change its licence and an update that restored
    the template's would be wrong rather than helpful.
    """
    return [s for s in manifest.seed if not exists(manifest.rename(s))]


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
    return [line for line in manifest.ignore if line.strip() not in have]


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

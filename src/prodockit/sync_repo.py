# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Keep repo-hosting-specific metadata in step with the git remote a
checkout actually uses, so forking or mirroring a project between GitHub,
GitLab and Bitbucket doesn't leave stale links, the wrong brand icon, or
README badges pointing at somebody else's repository.

Two things are synced, both derived from `git remote get-url origin`:

- In the Zensical config: `repo_url`, `repo_name`, `[project.theme.icon]
  repo`, and `edit_uri`.
- In the README: the badge row between `<!-- repo-badges:start -->` and
  `<!-- repo-badges:end -->` markers, if those markers are present.
  GitHub and GitLab each get badges pointing at their own APIs; any other
  host is left alone rather than guessed at.

Run it via `prodockit sync-repo` after changing a remote, or as a build
step before `zensical build`.

`edit_uri` gets particular attention because Zensical's own default is
`f"edit/master/{docs_dir}"` - hardcoding the `master` branch name whatever
the repo's default actually is, and applied only on an exact
`github.com`/`gitlab.com` host match, so a self-hosted GitLab gets no
default at all. This sets it explicitly instead, from the real default
branch and matched by host *kind*, which covers the self-hosted case too.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from urllib.parse import urlparse

#: Host substring -> (kind, FontAwesome brand icon, display label).
HOST_ICON_MAP: list[tuple[str, str, str, str]] = [
    ("github.com", "github", "fontawesome/brands/github", "GitHub"),
    ("gitlab", "gitlab", "fontawesome/brands/gitlab", "GitLab"),
    ("bitbucket.org", "bitbucket", "fontawesome/brands/bitbucket", "Bitbucket"),
]
DEFAULT_ICON = "fontawesome/brands/git-alt"

README_BADGE_BLOCK_RE = re.compile(
    r"(<!-- repo-badges:start.*?-->\n).*?(\n<!-- repo-badges:end -->)",
    re.DOTALL,
)


class SyncRepoError(Exception):
    """Raised when the remote can't be read or parsed, or the config is
    missing a setting this needs to rewrite."""


@dataclass
class SyncResult:
    """What `sync_repo_metadata()` did, or would do under `check`."""

    host: str
    label: str
    repo_url: str
    changes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def get_remote_url(remote: str = "origin", *, cwd: str | None = None) -> str:
    """The configured URL for `remote`."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
    except subprocess.CalledProcessError as exc:
        raise SyncRepoError(f"no '{remote}' git remote configured") from exc
    except OSError as exc:  # git not installed
        raise SyncRepoError(f"could not run git: {exc}") from exc
    return result.stdout.strip()


def detect_default_branch(remote: str = "origin", *, cwd: str | None = None) -> str:
    """The remote's own default branch, falling back to `"main"`.

    Read from the local `refs/remotes/<remote>/HEAD` symbolic ref, which a
    normal clone sets up. A checkout without it (a bare `git init` plus a
    manually added remote, or a fetch that never resolved HEAD) simply gets
    the fallback rather than an error - `edit_uri` pointing at `main` is a
    far better failure mode than the build stopping.
    """
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
    except (subprocess.CalledProcessError, OSError):
        return "main"
    ref = result.stdout.strip()
    return ref.split("/", 1)[1] if "/" in ref else (ref or "main")


def parse_remote(url: str) -> tuple[str, str, str]:
    """`(host, owner, repo_name)` from an SSH or HTTPS git remote URL."""
    ssh_match = re.match(r"^[\w.-]+@(?P<host>[\w.-]+):(?P<path>.+)$", url)
    if ssh_match:
        host = ssh_match.group("host")
        path = ssh_match.group("path")
    else:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")

    path = path.removesuffix(".git")
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or not host:
        raise SyncRepoError(f"could not parse owner/repo from remote URL: {url!r}")
    return host, parts[0], parts[-1]


def icon_for_host(host: str) -> tuple[str, str, str]:
    """`(kind, icon, label)` for a git remote host."""
    host_lower = host.lower()
    for needle, kind, icon, label in HOST_ICON_MAP:
        if needle in host_lower:
            return kind, icon, label
    return "other", DEFAULT_ICON, host


def edit_uri_for_host(kind: str, docs_dir: str, default_branch: str) -> str | None:
    """The `edit_uri` to set for a host kind, or `None` for a host this
    doesn't know how to link into - in which case `edit_uri` is left alone
    and Zensical's "edit this page" button simply doesn't appear, matching
    its own behaviour for an unrecognised host."""
    if kind in ("github", "gitlab"):
        return f"edit/{default_branch}/{docs_dir.strip('/')}/"
    return None


def _replace_setting(text: str, pattern: str, replacement: str, label: str) -> tuple[str, bool]:
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count == 0:
        raise SyncRepoError(f"could not find {label} to update in the config file")
    return new_text, new_text != text


def repo_name_matching_existing(text: str, owner: str, repo_name: str) -> str:
    """`owner/repo` or bare `repo`, whichever shape the config already uses.

    Zensical shows `repo_name` verbatim in the site header, and both forms
    are in legitimate use - this project's own config says
    `buckwem/prodockit-extensions`, while the template it came from says
    just the repository name. Rewriting to a fixed shape would silently
    restyle the header of every project that chose the other one, so the
    existing value decides and only the owner/repo *values* are updated.
    """
    current = re.search(r'^repo_name = "(.*)"$', text, flags=re.MULTILINE)
    if current and "/" in current.group(1):
        return f"{owner}/{repo_name}"
    return repo_name


def update_config(
    text: str,
    *,
    repo_url: str,
    owner: str,
    repo_name: str,
    icon: str,
    edit_uri: str | None,
) -> tuple[str, list[str]]:
    """Rewrites `repo_url`/`repo_name`/`theme.icon.repo`/`edit_uri` in a
    Zensical config, returning the new text and which settings changed.

    Deliberately a line-level regex rewrite rather than a parse-and-dump:
    round-tripping TOML through a writer would reformat the whole file and
    discard its comments, which in these projects carry most of the
    explanation for why each setting is what it is.
    """
    changes: list[str] = []
    display_name = repo_name_matching_existing(text, owner, repo_name)
    for pattern, replacement, label in (
        (r'^repo_url = ".*"$', f'repo_url = "{repo_url}"', "repo_url"),
        (r'^repo_name = ".*"$', f'repo_name = "{display_name}"', "repo_name"),
        (r'^repo = ".*"$', f'repo = "{icon}"', "theme.icon.repo"),
    ):
        text, did_change = _replace_setting(text, pattern, replacement, label)
        if did_change:
            changes.append(label)

    if edit_uri is not None:
        edit_uri_line = f'edit_uri = "{edit_uri}"'
        if re.search(r'^edit_uri = ".*"$', text, flags=re.MULTILINE):
            text, did_change = _replace_setting(
                text, r'^edit_uri = ".*"$', edit_uri_line, "edit_uri"
            )
        else:
            # A config predating this setting - insert it after repo_name
            # rather than requiring it to already be there.
            text, count = re.subn(
                r'^(repo_name = ".*")$',
                r"\1\n" + edit_uri_line,
                text,
                count=1,
                flags=re.MULTILINE,
            )
            if count == 0:
                raise SyncRepoError("could not find repo_name to insert edit_uri after")
            did_change = True
        if did_change:
            changes.append("edit_uri")

    return text, changes


def badges_for_host(kind: str, owner: str, repo_name: str, default_branch: str) -> str | None:
    """The README badge-row markup for a host kind, or `None` for a host
    with no known badge set (left untouched in that case)."""
    if kind == "github":
        base = f"https://github.com/{owner}/{repo_name}"
        return (
            '<p align="center">\n'
            f'  <a href="{base}/actions"><img\n'
            f'    src="{base}/actions/workflows/docs.yml/badge.svg"\n'
            '    alt="Build"\n'
            "  /></a>\n"
            f'  <a href="{base}/stargazers"><img\n'
            f'    src="https://img.shields.io/github/stars/{owner}/{repo_name}?style=flat&logo=github&label=Stars"\n'
            '    alt="GitHub Stars"\n'
            "  /></a>\n"
            f'  <a href="{base}/forks"><img\n'
            f'    src="https://img.shields.io/github/forks/{owner}/{repo_name}?style=flat&logo=github&label=Forks"\n'
            '    alt="GitHub Forks"\n'
            "  /></a>\n"
            "</p>"
        )
    if kind == "gitlab":
        path = f"{owner}/{repo_name}"
        encoded = f"{owner}%2F{repo_name}"
        return (
            '<p align="center">\n'
            f'  <a href="https://gitlab.com/{path}/-/pipelines"><img\n'
            f'    src="https://img.shields.io/gitlab/pipeline-status/{encoded}?branch={default_branch}&label=Build"\n'
            '    alt="Build"\n'
            "  /></a>\n"
            f'  <a href="https://gitlab.com/{path}"><img\n'
            f'    src="https://img.shields.io/gitlab/stars/{encoded}?style=flat&logo=gitlab&label=Stars"\n'
            '    alt="GitLab Stars"\n'
            "  /></a>\n"
            f'  <a href="https://gitlab.com/{path}/-/forks"><img\n'
            f'    src="https://img.shields.io/gitlab/forks/{encoded}?style=flat&logo=gitlab&label=Forks"\n'
            '    alt="GitLab Forks"\n'
            "  /></a>\n"
            "</p>"
        )
    return None


def update_readme(text: str, badges: str) -> tuple[str, bool]:
    """Replaces whatever sits between the `repo-badges` markers with
    `badges`. Returns the text unchanged, and `False`, if the markers
    aren't there - a project that doesn't want managed badges simply omits
    them, so their absence is a valid state rather than an error."""
    if not README_BADGE_BLOCK_RE.search(text):
        return text, False
    new_text = README_BADGE_BLOCK_RE.sub(lambda m: m.group(1) + badges + m.group(2), text)
    return new_text, new_text != text


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        raise SyncRepoError(f"could not read {path}: {exc}") from exc


def _write(path: str, text: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as exc:
        raise SyncRepoError(f"could not write {path}: {exc}") from exc


def sync_repo_metadata(
    config_path: str = "zensical.toml",
    *,
    readme_path: str | None = "README.md",
    remote: str = "origin",
    default_branch: str | None = None,
    check: bool = False,
    cwd: str | None = None,
) -> SyncResult:
    """Brings `config_path` (and `readme_path`, if it has badge markers)
    into line with `remote`'s URL, and returns what changed.

    With `check`, nothing is written - the returned result still lists
    everything that *would* change, which is what makes it usable as a CI
    guard against a config that has drifted from the remote it is served
    from.

    `default_branch` is detected from the remote when not given.
    """
    remote_url = get_remote_url(remote, cwd=cwd)
    host, owner, repo_name = parse_remote(remote_url)
    kind, icon, label = icon_for_host(host)
    repo_url = f"https://{host}/{owner}/{repo_name}"
    branch = default_branch or detect_default_branch(remote, cwd=cwd)

    result = SyncResult(host=host, label=label, repo_url=repo_url)

    original_config = _read(config_path)
    docs_dir_match = re.search(r'^docs_dir\s*=\s*"([^"]*)"', original_config, re.MULTILINE)
    docs_dir = docs_dir_match.group(1) if docs_dir_match else "docs"
    updated_config, config_changes = update_config(
        original_config,
        repo_url=repo_url,
        owner=owner,
        repo_name=repo_name,
        icon=icon,
        edit_uri=edit_uri_for_host(kind, docs_dir, branch),
    )
    result.changes.extend(config_changes)
    if config_changes and not check:
        _write(config_path, updated_config)

    if readme_path is not None:
        badges = badges_for_host(kind, owner, repo_name, branch)
        if badges is None:
            result.notes.append(f"no known README badge set for {label}; README left unchanged")
        else:
            original_readme = _read(readme_path)
            updated_readme, readme_changed = update_readme(original_readme, badges)
            if readme_changed:
                result.changes.append("README badges")
                if not check:
                    _write(readme_path, updated_readme)
            elif not README_BADGE_BLOCK_RE.search(original_readme):
                result.notes.append(
                    f"no repo-badges markers in {readme_path}; badge row left unchanged"
                )

    return result

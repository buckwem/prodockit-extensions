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
  `<!-- repo-badges:end -->` markers, if those markers are present -
  including an empty pair, which is how a template ships a row for this to
  fill in. GitHub and GitLab each get badges pointing at their own host;
  any other host is left alone rather than guessed at.

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
from urllib.parse import quote, urlparse

#: Host substring -> (kind, FontAwesome brand icon, display label).
HOST_ICON_MAP: list[tuple[str, str, str, str]] = [
    ("github.com", "github", "fontawesome/brands/github", "GitHub"),
    ("gitlab", "gitlab", "fontawesome/brands/gitlab", "GitLab"),
    ("bitbucket.org", "bitbucket", "fontawesome/brands/bitbucket", "Bitbucket"),
]
DEFAULT_ICON = "fontawesome/brands/git-alt"

# The body between the markers is optional. An empty pair - the two
# markers on consecutive lines, which is how a template ships a badge row
# it expects `sync-repo` to fill in - is the one shape that has to work,
# and requiring a newline *before* the end marker meant it was the one
# shape that could not match: the start group had already consumed the
# only newline there was.
README_BADGE_BLOCK_RE = re.compile(
    r"(<!-- repo-badges:start.*?-->\n)(?:.*?\n)?(<!-- repo-badges:end -->)",
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
            encoding="utf-8",
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
            encoding="utf-8",
            check=True,
            cwd=cwd,
        )
    except (subprocess.CalledProcessError, OSError):
        return "main"
    ref = result.stdout.strip()
    return ref.split("/", 1)[1] if "/" in ref else (ref or "main")


def parse_remote(url: str) -> tuple[str, str, str]:
    """`(host, namespace, repo_name)` from an SSH or HTTPS git remote URL.

    `namespace` is the *whole* owner path, not just its first segment.
    GitLab nests groups - `cs-dept/year3/report` is a project in the
    `year3` subgroup of `cs-dept` - and keeping only `cs-dept` produced a
    `cs-dept/report` that does not exist, which then propagated into
    `repo_url`, the edit links and the badges alike
    (prodockit-extensions#201). GitHub has no such nesting, so its
    namespace is always the single owner segment.
    """
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
    return host, "/".join(parts[:-1]), parts[-1]


def icon_for_host(host: str) -> tuple[str, str, str]:
    """`(kind, icon, label)` for a git remote host."""
    host_lower = host.lower()
    for needle, kind, icon, label in HOST_ICON_MAP:
        if needle in host_lower:
            return kind, icon, label
    return "other", DEFAULT_ICON, host


#: Hosts that serve repositories rather than published sites. A `site_url`
#: pointing at one of these is always wrong - it is what the template used
#: to ship - so it is safe to replace rather than treat as deliberate.
_CODE_HOST_NEEDLES = ("github.com", "gitlab", "bitbucket.org")

#: Hostnames that published Pages sites live on. A `site_url` already on one
#: of these was managed by whoever set it up, so following the remote to a
#: new one is what they would want.
_PAGES_HOST_SUFFIXES = (".github.io", ".gitlab.io")


def site_url_for(
    kind: str, namespace: str, repo_name: str, pages_base: str | None
) -> str | None:
    """The published site URL for a remote, or `None` when it cannot be
    known - in which case `site_url` is left alone.

    Only GitHub Pages is derived. Its shape is fixed and public:
    `https://<owner>.github.io/<repo>/`, or the bare origin when the
    repository is itself named `<owner>.github.io`. Hostnames are
    lowercased, which is what GitHub serves regardless of how the owner
    name is capitalised.

    GitLab is deliberately not guessed at. A self-hosted instance serves
    Pages from `pages_external_url`, an instance setting nothing in the
    remote URL reveals, and gitlab.com now gives new projects a unique
    domain with a random suffix rather than the old
    `<group>.gitlab.io/<project>` path. A confidently wrong canonical URL
    is worse than none at all - it tells search engines to index somewhere
    that does not exist - so those projects set `pages_base` instead, and
    the repository name is appended to it.
    """
    if pages_base:
        return f"{pages_base.rstrip('/')}/{repo_name}/"
    if kind == "github":
        owner = namespace.lower()
        if repo_name.lower() == f"{owner}.github.io":
            return f"https://{owner}.github.io/"
        return f"https://{owner}.github.io/{repo_name}/"
    return None


def site_url_is_ours_to_replace(current: str) -> bool:
    """Whether an existing `site_url` may be rewritten.

    Two things are replaceable. One already on a Pages hostname was set up
    to follow the repository, so it should keep following it. One pointing
    at a *code* host is not a site address at all - the project template
    shipped `https://github.com/<owner>/<repo>/` as its `site_url` for a
    long time, which put a repository page in every `<link rel="canonical">`
    and every `sitemap.xml` entry.

    Anything else is a custom domain, and is left alone. That matters more
    than it looks: `--check` is wired into CI as a gate, so rewriting a
    deliberate value would not just lose it once - it would report drift on
    every run afterwards and redden builds for a correct config.
    """
    host = (urlparse(current).hostname or "").lower()
    if not host:
        return False
    if any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _PAGES_HOST_SUFFIXES):
        return True
    return any(needle in host for needle in _CODE_HOST_NEEDLES)


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


def repo_name_matching_existing(text: str, namespace: str, repo_name: str) -> str:
    """`owner/repo` or bare `repo`, whichever shape the config already uses.

    Zensical shows `repo_name` verbatim in the site header, and both forms
    are in legitimate use - this project's own config says
    `buckwem/prodockit-extensions`, while the template it came from says
    just the repository name. Rewriting to a fixed shape would silently
    restyle the header of every project that chose the other one, so the
    existing value decides and only the owner/repo *values* are updated.

    This is a label, not a link - the header's target is `repo_url`, which
    carries the full namespace. So a deeply nested GitLab project shows
    its immediate parent rather than the entire path: `year3/report`, not
    `cs-dept/year3/report`, which would crowd the header for no gain. For
    the single-segment namespace GitHub always has, and GitLab usually
    has, the two are the same string.
    """
    current = re.search(r'^repo_name = "(.*)"$', text, flags=re.MULTILINE)
    if current and "/" in current.group(1):
        return f"{namespace.rsplit('/', 1)[-1]}/{repo_name}"
    return repo_name


def update_config(
    text: str,
    *,
    repo_url: str,
    namespace: str,
    repo_name: str,
    icon: str,
    edit_uri: str | None,
    site_url: str | None = None,
) -> tuple[str, list[str]]:
    """Rewrites `repo_url`/`repo_name`/`theme.icon.repo`/`edit_uri`, and
    `site_url` when one is supplied, in a Zensical config - returning the
    new text and which settings changed.

    Deliberately a line-level regex rewrite rather than a parse-and-dump:
    round-tripping TOML through a writer would reformat the whole file and
    discard its comments, which in these projects carry most of the
    explanation for why each setting is what it is.
    """
    changes: list[str] = []
    display_name = repo_name_matching_existing(text, namespace, repo_name)
    for pattern, replacement, label in (
        (r'^repo_url = ".*"$', f'repo_url = "{repo_url}"', "repo_url"),
        (r'^repo_name = ".*"$', f'repo_name = "{display_name}"', "repo_name"),
        (r'^repo = ".*"$', f'repo = "{icon}"', "theme.icon.repo"),
    ):
        text, did_change = _replace_setting(text, pattern, replacement, label)
        if did_change:
            changes.append(label)

    # Unlike the settings above, a missing `site_url` is not inserted. It
    # is optional in Zensical, and a project that has deliberately left it
    # out has no canonical URL by choice - adding one silently would change
    # what the site publishes rather than keeping it in step.
    if site_url is not None and re.search(r'^site_url = ".*"$', text, flags=re.MULTILINE):
        text, did_change = _replace_setting(
            text, r'^site_url = ".*"$', f'site_url = "{site_url}"', "site_url"
        )
        if did_change:
            changes.append("site_url")

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


def badges_for_host(
    kind: str, host: str, namespace: str, repo_name: str, default_branch: str
) -> str | None:
    """The README badge-row markup for a host, or `None` for a host with no
    known badge set (left untouched in that case).

    The `host` matters as much as the `kind`. GitLab is routinely
    self-hosted, and a badge row built from the kind alone sent every link
    to `gitlab.com` - for a university or company instance, a repository
    that does not exist. The badges looked plausible and pointed at nothing.

    So the pipeline badge is the one GitLab serves from the instance itself
    rather than shields.io's. It is correct on any install, and on a
    private one it is the only version that can work at all: the reader is
    already authenticated against the very instance that would refuse
    shields.io. The star and fork badges have no such native form, and are
    emitted only for `gitlab.com`, where shields can actually read them.
    """
    if kind == "github":
        base = f"https://{host}/{namespace}/{repo_name}"
        return (
            '<p align="center">\n'
            f'  <a href="{base}/actions"><img\n'
            f'    src="{base}/actions/workflows/docs.yml/badge.svg"\n'
            '    alt="Build"\n'
            "  /></a>\n"
            f'  <a href="{base}/stargazers"><img\n'
            f'    src="https://img.shields.io/github/stars/{namespace}/{repo_name}?style=flat&logo=github&label=Stars"\n'
            '    alt="GitHub Stars"\n'
            "  /></a>\n"
            f'  <a href="{base}/forks"><img\n'
            f'    src="https://img.shields.io/github/forks/{namespace}/{repo_name}?style=flat&logo=github&label=Forks"\n'
            '    alt="GitHub Forks"\n'
            "  /></a>\n"
            "</p>"
        )
    if kind == "gitlab":
        base = f"https://{host}/{namespace}/{repo_name}"
        rows = [
            f'  <a href="{base}/-/pipelines"><img\n'
            f'    src="{base}/badges/{default_branch}/pipeline.svg"\n'
            '    alt="Build"\n'
            "  /></a>\n"
        ]
        if host.lower() == "gitlab.com":
            # shields.io takes the project as one percent-encoded path, so
            # every separator in a nested namespace needs encoding too.
            encoded = quote(f"{namespace}/{repo_name}", safe="")
            rows.append(
                f'  <a href="{base}"><img\n'
                f'    src="https://img.shields.io/gitlab/stars/{encoded}?style=flat&logo=gitlab&label=Stars"\n'
                '    alt="GitLab Stars"\n'
                "  /></a>\n"
            )
            rows.append(
                f'  <a href="{base}/-/forks"><img\n'
                f'    src="https://img.shields.io/gitlab/forks/{encoded}?style=flat&logo=gitlab&label=Forks"\n'
                '    alt="GitLab Forks"\n'
                "  /></a>\n"
            )
        return '<p align="center">\n' + "".join(rows) + "</p>"
    return None


def update_readme(text: str, badges: str) -> tuple[str, bool]:
    """Replaces whatever sits between the `repo-badges` markers with
    `badges`. Returns the text unchanged, and `False`, if the markers
    aren't there - a project that doesn't want managed badges simply omits
    them, so their absence is a valid state rather than an error."""
    if not README_BADGE_BLOCK_RE.search(text):
        return text, False
    new_text = README_BADGE_BLOCK_RE.sub(lambda m: m.group(1) + badges + "\n" + m.group(2), text)
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


def _site_url_to_write(
    config: str,
    kind: str,
    namespace: str,
    repo_name: str,
    pages_base: str | None,
    result: SyncResult,
) -> str | None:
    """The `site_url` to write, or `None` to leave the config's alone -
    recording on `result` why, when the answer is None for a reason worth
    telling the user about."""
    current_match = re.search(r'^site_url = "(.*)"$', config, flags=re.MULTILINE)
    if current_match is None:
        return None
    desired = site_url_for(kind, namespace, repo_name, pages_base)
    if desired is None:
        result.notes.append(
            f"cannot derive a published URL for {result.label}; site_url left unchanged "
            "(set pages_base in your config to have it managed)"
        )
        return None
    current = current_match.group(1)
    if current != desired and not site_url_is_ours_to_replace(current):
        result.notes.append(
            f"site_url is a custom domain ({current}); left unchanged"
        )
        return None
    return desired


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
    host, namespace, repo_name = parse_remote(remote_url)
    kind, icon, label = icon_for_host(host)
    repo_url = f"https://{host}/{namespace}/{repo_name}"
    branch = default_branch or detect_default_branch(remote, cwd=cwd)

    result = SyncResult(host=host, label=label, repo_url=repo_url)

    original_config = _read(config_path)
    docs_dir_match = re.search(r'^docs_dir\s*=\s*"([^"]*)"', original_config, re.MULTILINE)
    docs_dir = docs_dir_match.group(1) if docs_dir_match else "docs"

    pages_base_match = re.search(r'^pages_base\s*=\s*"([^"]*)"', original_config, re.MULTILINE)
    pages_base = pages_base_match.group(1) if pages_base_match else None
    site_url = _site_url_to_write(original_config, kind, namespace, repo_name, pages_base, result)

    updated_config, config_changes = update_config(
        original_config,
        repo_url=repo_url,
        namespace=namespace,
        repo_name=repo_name,
        icon=icon,
        edit_uri=edit_uri_for_host(kind, docs_dir, branch),
        site_url=site_url,
    )
    result.changes.extend(config_changes)
    if config_changes and not check:
        _write(config_path, updated_config)

    if readme_path is not None:
        badges = badges_for_host(kind, host, namespace, repo_name, branch)
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

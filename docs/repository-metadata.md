# Repository metadata {: #sync-repo-repository-metadata }

\index{`prodockit sync-repo`} keeps the repo-hosting-specific parts of your project
in step with the git remote the checkout actually uses, so forking or
mirroring it between GitHub, GitLab and Bitbucket doesn't leave stale links,
the wrong brand icon, or README badges pointing at somebody else's
repository.

Everything it writes is derived from one thing - `git remote get-url origin`:

- In `zensical.toml`: `repo_url`, `repo_name`, `[project.theme.icon] repo`
  and `edit_uri`.
- In `README.md`: the badge row between the `repo-badges` markers, if you
  have them.

## Quick start {: #sync-repo-quick-start }

Run it from your project root, wherever `zensical.toml` lives:

```bash
prodockit sync-repo
```

It reports only what it actually changed:

```
Detected GitHub remote (https://github.com/you/your-repo); updated: repo_url, repo_name, edit_uri
```

Run it after changing a remote, or as a build step before `zensical build`.
Running it twice does nothing the second time.

## In CI {: #sync-repo-in-ci }

`--check` writes nothing and exits non-zero if anything is out of date -
enough to fail a build when a config has drifted from the remote it's
actually served from:

```bash
prodockit sync-repo --check
```

## Options {: #sync-repo-options }

| Option | Default | What it does |
| --- | --- | --- |
| `-f`, `--config-file` | `zensical.toml` | Which Zensical config to update. |
| \index{prodockit sync-repo!`--readme`} | `README.md` | README to update the badge block in. Pass an empty value to skip it. |
| \index{prodockit sync-repo!`--remote`} | `origin` | Which git remote to read the repository URL from. |
| \index{prodockit sync-repo!`--branch`} | detected | Default branch for `edit_uri` and GitLab build-badge links. |
| \index{prodockit sync-repo!`--check`} | off | Report what would change, write nothing, exit non-zero if anything would. |

## What it does, and why {: #sync-repo-what-it-does }

### `edit_uri` {: #sync-repo-edit-uri }

Zensical falls back to `edit/master/<docs_dir>` when `edit_uri` isn't set -
hardcoding the `master` branch name whatever your repository's default
actually is, and only for an exact `github.com`/`gitlab.com` host match, so
a self-hosted GitLab gets no default at all and its "edit this page" button
simply never appears.

`sync-repo` sets it explicitly instead, from your remote's real default
branch and matched by *kind* of host rather than exact hostname - so
`gitlab.your-institution.ac.uk` is recognised as GitLab and gets a working
edit link. A host it has no edit-URL convention for is left alone rather
than guessed at.

### `repo_name` keeps the shape you chose {: #sync-repo-repo-name }

Zensical prints `repo_name` verbatim in the site header, and both
`owner/repo` and a bare `repo` are in legitimate use. `sync-repo` looks at
what your config already says and keeps that shape, updating only the
values - so syncing never silently restyles your header.

### README badges {: #sync-repo-readme-badges }

If your README contains these markers, the block between them is replaced
with a badge row (build status, stars, forks) pointing at whichever host
your remote is on:

```markdown
<!-- repo-badges:start -->
<!-- repo-badges:end -->
```

GitHub and GitLab have known badge sets. Any other host is reported and
left untouched rather than given invented URLs. If you don't want managed
badges, leave the markers out - their absence is a normal state, not an
error, and `sync-repo` just says so and moves on.

## Using it from Python {: #sync-repo-from-python }

The command is a thin wrapper around
[`prodockit.sync_repo`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/sync_repo.py),
whose `sync_repo_metadata()` returns what changed rather than printing it:

```python
from prodockit.sync_repo import sync_repo_metadata

result = sync_repo_metadata(check=True)
if result.changed:
    print("out of date:", ", ".join(result.changes))
```

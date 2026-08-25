---
icon: lucide/git-fork
---

{{ heading_counter_reset(page) }}

# Repository metadata {: #sync-repo-repository-metadata }

\index{commands!`prodockit sync-repo`} keeps the repo-hosting-specific parts of your project
in step with the git remote the checkout actually uses, so forking or
mirroring it between GitHub, GitLab and Bitbucket doesn't leave stale links,
the wrong brand icon, or README badges pointing at somebody else's
repository.

Everything it writes is derived from one authority: the selected git remote,
`origin` by default.

- In `zensical.toml`: `repo_url`, `repo_name`, `[project.theme.icon] repo`,
  `edit_uri`, and `site_url` where it can be known.
- In `README.md`: the badge row between the `repo-badges` markers, if you
  have them.

## When to run it

Run `sync-repo` after:

- creating a repository from a template;
- forking or transferring a repository;
- renaming a repository or its default branch;
- changing `origin` from GitHub to GitLab, or the reverse;
- adding managed README badge markers;
- noticing that “Edit this page”, canonical URLs, or badges point elsewhere.

It is safe to include the check form in every pull request. The writing form is
a maintenance action: run it on a branch and review the resulting metadata as
you would any other source change.

## Check, update, and verify {: #sync-repo-quick-start }

Run it from your project root, wherever `zensical.toml` lives:

/// steps

//// step | Check without writing

```bash
prodockit sync-repo --check
```

Exit zero means the managed values already match the remote. A non-zero result
lists what would change, making this form suitable for CI.

////

//// step | Update the managed values

```bash
prodockit sync-repo
```

The command reports only what it actually changed:

```
Detected GitHub remote (https://github.com/you/your-repo); updated: repo_url, repo_name, edit_uri
```

////

//// step | Review the source diff

```bash
git diff -- zensical.toml README.md
```

Confirm that the detected host, namespace, repository, default branch, and
public site address are the ones you intend. A syntactically valid URL can
still identify the wrong repository.

////

//// step | Repeat the check and build

```bash
prodockit sync-repo --check
zensical build --clean --strict
```

Running the write command twice should do nothing the second time. The strict
build then checks the links within the site; inspect the header repository link,
an “Edit this page” link, the canonical URL, and README badges in the rendered
or hosted result.

////

///

## In CI {: #sync-repo-in-ci }

Place the non-writing check before the build. It catches a fork whose config
still names its source repository before those stale links are published:

```yaml
- name: Verify repository metadata
  run: prodockit sync-repo --check
- run: zensical build --clean --strict
```

Do not run the writing form in an ordinary pull-request job. CI would modify
its disposable checkout, hide the source drift, and still leave the repository
unchanged for the next run.

## Options {: #sync-repo-options }

| Option | Default | What it does |
| --- | --- | --- |
| `-f`, `--config-file` | `zensical.toml` | Which Zensical config to update. |
| \index{commands!prodockit sync-repo!`--readme`} | `README.md` | README to update the badge block in. Pass an empty value to skip it. |
| \index{commands!prodockit sync-repo!`--remote`} | `origin` | Which git remote to read the repository URL from. |
| \index{commands!prodockit sync-repo!`--branch`} | detected | Default branch for `edit_uri` and GitLab build-badge links. |
| \index{commands!prodockit sync-repo!`--check`} | off | Report what would change, write nothing, exit non-zero if anything would. |

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

### `site_url`, and when it is left alone {: #sync-repo-site-url }

`site_url` is the address your site is *published* at, which is not the
address of the repository. Zensical puts it in every page's
`<link rel="canonical">` and in every `sitemap.xml` entry, so a wrong one
tells search engines the real home of your documentation is somewhere
else - quietly, since the site builds and looks perfect either way.

Only GitHub Pages is derived, because only its shape is knowable from the
remote: `https://<owner>.github.io/<repo>/`, or the bare origin when the
repository is itself named `<owner>.github.io`.

GitLab is not guessed at. A self-hosted instance serves Pages from
`pages_external_url`, an instance setting the remote URL says nothing
about, and gitlab.com now gives new projects a unique domain with a random
suffix rather than the old `<group>.gitlab.io/<project>` path. Set
`pages_base` and the repository name is appended to it:

```toml
pages_base = "https://mb0105.pages.gitlab.surrey.ac.uk"
```

!!! info "What it will not touch"
    An existing `site_url` is only replaced when it is already a Pages URL
    - one set up to follow the repository, so it keeps following it - or
    when it points at a code host, which is never a published site and is
    what the project template used to ship.

    Any other value is treated as a custom domain and left alone, with a
    note saying so. That matters because `--check` is wired into CI as a
    gate: rewriting a deliberate value would not merely lose it once, it
    would report drift on every run afterwards and redden builds for a
    config that was right all along.

    A `site_url` that is absent stays absent. It is optional in Zensical,
    and a project that left it out has no canonical URL by choice.

### Nested GitLab groups {: #sync-repo-nested-groups }

GitLab nests groups, so a project can live several levels down -
`cs-dept/year3/report` is the `report` project in the `year3` subgroup of
`cs-dept`. The whole path is kept, and every generated URL uses it:
`repo_url`, the edit links, and the badges all address the real project
rather than a `cs-dept/report` that does not exist.

The one exception is the `repo_name` label described below, which shows
the immediate parent (`year3/report`). It is a caption, not a link - the
header's target is `repo_url` - and printing a deep path verbatim would
crowd the header for no gain.

GitHub has no equivalent nesting, so nothing changes there.

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

An empty pair, exactly as above, is the normal starting state: a template
ships the markers and the first `sync-repo` fills them in.

GitHub and GitLab have known badge sets. Any other host is reported and
left untouched rather than given invented URLs. If you don't want managed
badges, leave the markers out - their absence is a normal state, not an
error, and `sync-repo` just says so and moves on.

!!! note "Self-hosted GitLab gets a build badge only"
    The badge set is chosen by host *kind*, and `gitlab` matches any
    instance - a university or company GitLab as readily as `gitlab.com`.
    The links are built from your actual host, so they point at your own
    instance rather than at a `gitlab.com` project that does not exist.

    The build badge is the one GitLab serves itself, at
    `<your-instance>/<owner>/<repo>/badges/<branch>/pipeline.svg`. That
    works on a private instance, where the reader is already authenticated
    against it - which an external badge service can never be.

    Stars and forks have no instance-served equivalent, and shields.io
    resolves its GitLab endpoints against `gitlab.com` only, so those two
    are emitted for `gitlab.com` alone. On a self-hosted instance they
    could render nothing but a broken image.

The Python API used by the command is documented for contributors under
[Development and code map](development.md#call-maintenance-logic-from-python).

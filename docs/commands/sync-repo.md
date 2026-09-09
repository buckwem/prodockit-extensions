---
icon: lucide/git-compare-arrows
---

{{ heading_counter_reset(page) }}

# `pdk sync-repo`

`pdk sync-repo` aligns repository URLs, edit links, repository branding, and
managed README badges with the selected Git remote.

Use the [repository metadata task guide](../devcons/repo-metadata.md) when
moving, forking, or renaming a repository.

## Synopsis {: #cmd-sync-repo-synopsis }

Use check mode to preview repository-derived changes before writing them.

```text
pdk sync-repo [OPTIONS]
pdk sync-repo --check
```

## Working directory {: #cmd-sync-repo-working-directory }

Run this command from the **project repository root**. The configuration,
README, and selected Git remote must belong to the same checkout. Although
`--config-file` and `--readme` can name other files, Git still reads the remote
from the current repository.

From outside the repository it normally exits with `Error: no 'origin' git
remote configured`; a wrong project may instead have a valid but unintended
`origin`. Confirm `git remote -v` before applying changes when there is any
doubt.

## Options {: #cmd-sync-repo-options }

\ref{tab-cmd-sync-repo-options} lists repository and destination controls.

| Option {: width="34%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Update another Zensical configuration; defaults to `zensical.toml`. |
| `--readme PATH` | Update another README badge block; defaults to `README.md`. Pass an empty value to skip it. |
| `--remote NAME` | Read another Git remote; defaults to `origin`. |
| `--branch NAME` | Use an explicit default branch instead of detecting it. |
| `--check` | Report drift and exit non-zero without writing. |
| `--site-name TEXT` | Set the website title without opening an editor. |
| `--site-url URL` | Set the full website address; this does not enable or verify hosting. |
| `--create-readme` | Create a minimal README only if it is missing. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-sync-repo-options}

Repository metadata options
///

## Effects {: #cmd-sync-repo-effects }

Without `--check`, the command updates the relevant repository settings in the
configuration and the managed README badge block when present. It preserves
unrelated configuration and README content. It does not change the Git remote,
create a repository, commit, or push.

For a fresh Zensical project, run `pdk sync-repo --create-readme` in a terminal.
When details are missing or still use starter placeholders, it asks you to confirm
the repository, title and suggested website address. Missing TOML tables and
settings are created using a comment-preserving TOML editor. An absent README is
optional, not an error. Existing README content is never replaced.

Without a terminal, use `--site-name` and `--site-url` for explicit values.
Check mode never prompts or writes. A suggested Pages address is not proof of a
successful deployment; custom domains are preserved unless explicitly changed.

## Related commands {: #cmd-sync-repo-related-commands }

Use these commands to verify metadata or coordinate a later template update:

- [`pdk diag`](diag.md) verifies that a repository is available and its
  metadata can be inspected.
- [`pdk template-sync`](template-sync.md) uses the project host when sending a
  template update for review.

# Machine bootstrap {: #bootstrap-machine-bootstrap }

\index{`prodockit bootstrap`} turns the User Guide's install sequence into
ten stages that can be checked individually and repaired one at a time,
rather than followed top to bottom and hoped over.

The install is long, sequential, and easy to get half-right in ways that
only surface much later - a missing Pango that looks fine until the first
`prodockit pdf`, a Node without `npm` that fails in an apparently
unrelated step two sections on. Every stage here answers "is this
actually set up?", which is the question a written instruction cannot
answer for its reader.

!!! warning "This cannot be the first thing you run"
    `prodockit bootstrap` is a prodockit subcommand, so Python and
    `pip install prodockit` necessarily come first - it cannot install the
    interpreter it is running on. That is the boundary: **you** install
    Python, **bootstrap** does the rest.

    ```bash
    pip install prodockit
    prodockit bootstrap --check
    ```

## What it covers {: #bootstrap-stages }

| # | Stage | Automated? |
| --- | --- | --- |
| 1 | Visual Studio Code | yes |
| 2 | Git, installed **and** configured | yes |
| 3 | SSH keypair | yes |
| 4 | Public key on the host | **guide and verify** |
| 5 | Template cloned | yes |
| 6 | Your own project on the host | **guide and verify** |
| 7 | Clone pointed at your project | yes |
| 8 | Pandoc and WeasyPrint's libraries | yes |
| 9 | Node.js and the render toolchains | yes |
| 10 | VS Code extensions | yes |

Stages 3, 5, 7 and 10 are platform-independent - over half the work is
the same on every operating system.

### The two stages that cannot be automated {: #bootstrap-guide-and-verify }

Uploading an SSH public key and creating your own project both need an
authenticated human in a browser. They could in principle be done through
the host's API, but only with a Personal Access Token - which you would
create through the same web interface we were trying to avoid, and which
bootstrap would then have to receive and hold.

For a tool aimed at people setting up their first project, that trades
two well-signposted clicks for a credential-handling problem. So
bootstrap **guides and then verifies** instead: it tells you exactly what
to do and where, and then checks whether it worked - `ssh -T` for the key,
`git ls-remote` for the project.

The verification is the valuable half. "I clicked something" and
"authentication works" are different states, and only one of them lets
you push.

## Checking without changing anything {: #bootstrap-check }

```bash
prodockit bootstrap --check
```

```text
 1  MISS  Visual Studio Code - the `code` command is not on PATH
 2  ok    Git, installed and configured - Ada Lovelace <al01234@surrey.ac.uk>
 3  ok    SSH keypair - /Users/al01234/.ssh/id_ed25519_gitlab
 4  ok    SSH key on the host - authenticated to gitlab.surrey.ac.uk
 5  ?     Template cloned - needs project_name
 ...
5 of 10 stages need work.
```

Four states, and the difference between them matters:

| | Meaning |
| --- | --- |
| `ok` | Set up correctly. A rerun leaves it alone. |
| `MISS` | Not there at all. |
| `WRONG` | Present but not usable - git installed with no `user.email`, Node installed without `npm`. **Not** the same as missing, and telling you to install something you already have would send you the wrong way. |
| `?` | Cannot be judged yet, because it needs a configuration answer you have not given. |

Exits non-zero when anything needs work, so it is usable as a check in a
script - the same convention as
[`prodockit sync-repo --check`](repo-metadata.md#sync-repo-in-ci) and
`prodockit pins --check`.

## Seeing what it would do {: #bootstrap-dry-run }

```bash
prodockit bootstrap --dry-run
```

Prints the exact commands each unsatisfied stage would run, and the
instructions for the two that need you. Nothing is executed.

This is worth running before trusting any install tool with your machine,
and it is also how a stage is reviewed here: the commands are the thing
under test.

## Configuration {: #bootstrap-configuration }

Stored per **user**, not per project - it is needed before a project
exists:

| Platform | Path |
| --- | --- |
| macOS / Linux | `~/.config/prodockit/bootstrap.toml` |
| Windows | `%APPDATA%\prodockit\bootstrap.toml` |

```toml
full_name    = "Ada Lovelace"
email        = "al01234@surrey.ac.uk"
username     = "al01234"
host         = "surrey"
namespace    = "comm058-2026"
project_name = "report-al01234"
project_dir  = "~/GitLab/report-al01234"
```

!!! danger "Never put a secret in this file"
    There is no field here for a password, token or passphrase, and that
    is a design constraint rather than an oversight - the guide-and-verify
    approach means bootstrap never needs one. A plain file in a synced
    home directory is the wrong place for a credential, so if a future
    version ever needs API access, the token belongs in your operating
    system's keychain and this file holds at most a reference to it.

A malformed line is an error naming the file and line number, not a
setting silently ignored - a config that quietly reverted to defaults
would re-prompt for everything with no explanation of why.

## Hosts {: #bootstrap-hosts }

Only the University of Surrey's GitLab (`gitlab.surrey.ac.uk`) is
supported today. `gitlab.com` and `github.com` are declared, so the shape
is right and adding them is filling in a record rather than rewriting the
stages - but they are refused with a clear message rather than
half-working against something nothing has tested.

Everything host-specific is a *value* rather than a branch: the hostname,
the greeting `ssh -T` prints on success, the settings and new-project
URLs, and the vocabulary (GitLab's *project* in a *group*, GitHub's
*repository* in an *organisation*).

## Status {: #bootstrap-status }

Phase 1 implements `--check` and `--dry-run` only. **Nothing installs
anything yet** - running either against a real machine is safe, which is
the point of shipping this half first.

Applying stages automatically follows in phases: macOS, then Ubuntu, then
Windows. Windows is deliberately last: it is the hardest (MSYS2, `PATH`
edits, the Administrator split for `ssh-agent`) and it is the one platform
this project has [no automated coverage for at all](limitations.md#limitations-platforms).

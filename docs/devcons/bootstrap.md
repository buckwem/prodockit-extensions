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
    prodockit bootstrap
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

### Nothing bootstrap runs can ask you a question {: #bootstrap-no-prompts }

Every command bootstrap runs - checking or applying - runs in an
environment that cannot prompt: `BatchMode=yes` for `ssh`,
`GIT_TERMINAL_PROMPT=0` for git, and both reaching `git clone` and
`git ls-remote` through `GIT_SSH_COMMAND`.

This is not tidiness. Before a key is uploaded, `ssh` falls back to
password authentication - and it reads that password from `/dev/tty`
directly, bypassing whatever the calling program did with stdin. A
read-only check sat at a `git@gitlab.surrey.ac.uk's password:` prompt
with no way out. Failing fast is the point: "could not authenticate" is
a finding bootstrap can report and act on, and a blinking cursor is not.

If you have set `GIT_SSH_COMMAND` yourself, it is left alone.

One consequence is deliberate. The first time a machine connects to a
host, ssh asks whether to trust its fingerprint - and bootstrap will not
answer that for you:

```text
 4  WRONG  SSH key on the host - gitlab.surrey.ac.uk is not a known host
           yet - run `ssh -T git@gitlab.surrey.ac.uk` once and accept the
           fingerprint
```

Trusting a host key is a security decision. A tool that makes it
silently on your behalf has taken something from you that you did not
know you had, so this one hands it back with the exact command.

## Checking without changing anything {: #bootstrap-check }

Checking is what you get by default - run it with no options at all:

```bash
prodockit bootstrap
```

`--check` is accepted too, and does the same thing. The read-only
behaviour is the default deliberately: the alternative, once applying is
implemented, is a command that starts installing software because
somebody typed it to see what it did.

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

## Setting it up {: #bootstrap-apply }

```bash
prodockit bootstrap --configure   # answer the questions, then stop
prodockit bootstrap --apply       # set up what needs it, asking first
```

`--apply` walks the stages that need work, showing what it will run
before it runs it, and asks each time. The defaults differ by state, and
deliberately:

| Stage state | Prompt |
| --- | --- |
| `MISS` - not there at all | `Apply? [Y/n]` |
| `WRONG` - present but not usable | `Apply? [y/N]` |

Reapplying over something that already exists is the case that can
destroy work, so it is the case you have to ask for rather than get by
pressing Enter.

**Every stage is re-checked after it is applied.** A command exiting zero
says the installer ran, not that the thing it installed works - which is
the distinction behind most of the failures this project has had. If a
stage runs but still does not check out, bootstrap says so and stops
rather than continuing on a broken foundation.

A failing command stops the run too. Later commands in a plan generally
depend on earlier ones, so pressing on turns one clear failure into
several confusing ones.

## Which repository gets cloned {: #bootstrap-source }

By default, this host's copy of the template - for Surrey that is
`gitlab.surrey.ac.uk:mb0105/prodockit-template.git`, its own mirror,
so you never need a GitHub account to start.

If you have already been given a repository - a taught module usually
issues one per student - put its URL in `source_url` and that is cloned
instead:

```toml
source_url = "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git"
```

The later stages follow on their own: a clone made from `source_url`
already has the right `origin`, so the repoint stage reports `ok` and
does nothing.

## Configuration {: #bootstrap-configuration }

You should not need to open this file. When a run finds an answer
missing it offers to ask for it, and only for the ones actually blank:

```text
Some details are not set yet: project_name, project_dir.
Answer them now? [Y/n]:
```

`prodockit bootstrap --configure` re-asks everything, with each current
value as the default, so pressing Enter through confirms an unchanged
setup.

A piped or scripted run never prompts - it reports what is missing and
carries on, rather than blocking on a question nobody is there to
answer.

The file itself is stored per **user**, not per project - it is needed
before a project exists:

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
source_url   = ""
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

Checking, `--dry-run`, `--configure` and `--apply` all work. macOS is
the platform this has been exercised on end to end - a real clone of the
Surrey template, applied and verified.

Ubuntu and Windows have their commands written and unit-tested, but
neither has been run on a real machine yet. Windows is deliberately last: it is the hardest (MSYS2, `PATH`
edits, the Administrator split for `ssh-agent`) and it is the one platform
this project has [no automated coverage for at all](limitations.md#limitations-platforms).

# Machine bootstrap {: #bootstrap-machine-bootstrap }

\index{`prodockit bootstrap`} turns the User Guide's install sequence into
eleven stages that can be checked individually and repaired one at a time,
rather than followed top to bottom and hoped over.

The install is long, sequential, and easy to get half-right in ways that
only surface much later - a missing Pango that looks fine until the first
`prodockit pdf`, a Node without `npm` that fails in an apparently
unrelated step two sections on. Every stage here answers "is this
actually set up?", which is the question a written instruction cannot
answer for its reader.

## Before you start {: #bootstrap-prerequisites }

!!! warning "This cannot be the first thing you run"
    `prodockit bootstrap` is a prodockit subcommand, so Python and
    `pip install prodockit` necessarily come first - it cannot install the
    interpreter it is running on. That is the boundary: **you** install
    Python, **bootstrap** does the rest.

Which is three steps, on any platform: install Python, make a virtual
environment, install prodockit into it.

The virtual environment is not optional on macOS and increasingly not on
Linux either. A Python installed by a package manager is marked
\index{PEP 668} *externally managed*, and `pip install` outside a virtual
environment is refused outright:

```text
error: externally-managed-environment
× This environment is externally managed
```

That message is correct and unhelpful in equal measure - it explains what
it will not do without saying what to do instead. A virtual environment
is what to do instead.

=== "macOS"

    Install [Homebrew](https://brew.sh) if you do not have it, then:

    ```bash
    brew install python
    ```

    Change to the directory you want to keep your projects in - the one
    you will later point bootstrap's `project_dir` at - and create the
    environment there:

    ```bash
    cd ~/GitLab
    /opt/homebrew/bin/python3 -m venv .venv
    source .venv/bin/activate
    pip3 install prodockit
    ```

    Homebrew's `python3` is named by its full path deliberately. macOS
    ships a `python3` of its own, and which one a bare `python3` finds
    depends on `PATH` ordering you did not choose - naming it explicitly
    makes the environment reproducible rather than dependent on how the
    shell happened to be configured. On an Intel Mac the prefix is
    `/usr/local` rather than `/opt/homebrew`; `brew --prefix` prints
    yours.

=== "Windows"

    Install Python from
    [python.org/downloads](https://www.python.org/downloads/), and on the
    installer's screens:

    - Tick **Add python.exe to PATH** on the first screen. Without it,
      `python` is not a command and nothing below works.
    - Click **Disable path length limit** on the final screen. Node's
      render toolchains in stage 10 nest deeply enough to hit the 260
      character limit.

    Then, in PowerShell, in the directory you want to keep your projects
    in:

    ```powershell
    cd ~\GitLab
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install prodockit
    ```

    !!! warning "Windows ships a `python` that is not Python"
        Typing `python` on a machine without it installed opens the
        Microsoft Store rather than reporting that nothing is there.
        That placeholder is still ahead of a real Python on `PATH` in
        some installs, so if `python --version` opens a shop window, the
        install did not take - repeat it with **Add python.exe to PATH**
        ticked.

=== "Ubuntu"

    ```bash
    sudo apt install python3 python3-venv python3-pip
    ```

    `python3-venv` is a separate package on Debian and Ubuntu, and its
    absence does not show up until `python3 -m venv` fails - by which
    point the error looks like a broken Python rather than a missing
    package.

    Then, in the directory you want to keep your projects in:

    ```bash
    cd ~/GitLab
    python3 -m venv .venv
    source .venv/bin/activate
    pip install prodockit
    ```

### Every new terminal needs the environment activated again {: #bootstrap-reactivate }

A virtual environment lasts as long as the shell it was activated in.
Open a new terminal window - or come back tomorrow - and `prodockit` is
an unknown command again until you activate it:

=== "macOS / Ubuntu"

    ```bash
    source .venv/bin/activate
    ```

=== "Windows"

    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

You can tell it worked because the prompt gains a `(.venv)` prefix. If it
is not there, nothing you install or run is going where you think it is.

### Check what you actually got {: #bootstrap-verify-install }

```bash
prodockit --version
which prodockit          # `where prodockit` on Windows
```

Worth the two seconds, because the failure this catches is silent. An
older `prodockit` already on `PATH` from a different Python shadows a
newer one completely: `pip install` reports success, `prodockit
--version` reports a version from two releases ago, and `prodockit
bootstrap` fails as an unknown command with nothing to suggest why. If
the version is not the one you just installed, `which` will show you
which Python is winning.

!!! tip "`pipx` is the other reasonable answer"
    For a command-line tool used across several projects rather than a
    library imported by one, [`pipx`](https://pipx.pypa.io/) is arguably
    the better fit - it gives each tool its own environment and puts the
    command on `PATH` without an activation step, so there is no
    `(.venv)` to forget. It is one more thing to install, which is why it
    is not the route above, but if you already have it,
    `pipx install prodockit` works and skips this whole section.

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
| 8 | Commit identity in the project | yes |
| 9 | Pandoc and WeasyPrint's libraries | yes |
| 10 | Node.js and the render toolchains | yes |
| 11 | VS Code extensions | yes |

Stages 3, 5, 7, 8 and 11 are platform-independent - nearly half the work
is the same on every operating system.

### Your commits, under your own name {: #bootstrap-identity }

Stage 8 sets `user.name` and `user.email` **on the clone**, not globally:

```bash
git config --local user.name  "Ada Lovelace"
git config --local user.email "al01234@surrey.ac.uk"
```

Per-repository is the right scope, and deliberately so. A global
`user.email` is a legitimate personal preference, and a tool that sets up
one university project has no business rewriting the identity you use for
everything else.

It also has to be *checked* per-repository, which is subtler than it
sounds. `git config user.email` inside a repository falls back to the
global value, so a check written that way passes on any machine with any
identity at all - which is how bootstrap once asked for an email, stored
it, reported every stage `ok`, and never applied it. Commits went out
under a GitHub noreply address instead.

That is worth more than tidiness here: on Surrey's GitLab, a commit whose
author address matches no known account is not linked to one, so
coursework can appear to be authored by an unrecognised user - and you
would have no reason to suspect it.

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

### Where your part comes in the order {: #bootstrap-manual-order }

Some stages are part automated and part yours, and *when* your part
happens is not cosmetic - it is whether the stage can work at all:

| | Example |
| --- | --- |
| **Before** the commands, because they depend on you | The keypair stage: the advice on choosing a passphrase is no use once `ssh-keygen` has already asked for one. |
| **After** them, because it depends on the commands | macOS's VS Code: the Command Palette you are asked to open belongs to the application `brew install` has just put there. |

Both orderings have been wrong in a shipped release - the install
skipped entirely in one direction (#230), and the run stopped dead at the
SSH key stage in the other (#234) - so each stage now states which it
needs rather than leaving it to be inferred.

The two guide-and-verify stages are wholly yours, and their verification
is the stage's own check rather than a command in the plan. That
distinction is what stopped the run in #234: a check is allowed to say
"not yet" and be asked again, whereas a command that exits non-zero is a
failure and ends the run - and `ssh -T` exits non-zero even when it
succeeds.

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

Ubuntu is being exercised now, on an ARM virtual machine, and the first
run found two things no unit test could have: a `.deb` installed from a
filename that never existed (#233), and the SSH stage ending the run on
the very state it exists to repair (#234). Both are fixed; the platform
should be treated as newly-trodden rather than proven.

Windows has its commands written and unit-tested but has not been run at
all. It is deliberately last: it is the hardest (MSYS2, `PATH` edits, the
Administrator split for `ssh-agent`) and it is the one platform this
project has [no automated coverage for at all](limitations.md#limitations-platforms).

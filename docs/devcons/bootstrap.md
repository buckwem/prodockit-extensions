# Machine bootstrap {: #bootstrap-machine-bootstrap }

\index{`prodockit bootstrap`} turns the User Guide's install sequence into
a list of stages that can be checked individually and repaired one at a
time, rather than followed top to bottom and hoped over. `prodockit
bootstrap` reports how many there are; the table below names them.

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
      render toolchains in stage 14 nest deeply enough to hit the 260
      character limit.

    Then allow PowerShell to run scripts. Windows blocks all of them by
    default, and activating a virtual environment *is* a script - so
    without this the very next step fails:

    ```powershell
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    ```

    Depending on your PowerShell version it may ask you to confirm;
    answer `Y`. Often it simply returns to the prompt, which means it
    worked.

    !!! info "What this changes, and what it does not"
        Without it, activating the environment fails with `... cannot be
        loaded because running scripts is disabled on this system` -
        which names the script rather than the policy blocking it, so it
        reads as a broken file. `RemoteSigned` allows scripts you wrote
        locally while still requiring a signature on anything downloaded;
        `-Scope CurrentUser` limits the change to your own account, so it
        needs no Administrator window and is done once.

        Rather not change it at all? Use classic **CMD** instead of
        PowerShell and run `.\.venv\Scripts\activate.bat` - `.bat`
        files are not covered by execution policy.

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
an unknown command again until you activate it.

A new terminal also starts in your home directory, so **change to the
directory holding `.venv` first** - the path below is relative to it, and
from anywhere else it simply is not there:

=== "macOS / Ubuntu"

    ```bash
    cd ~/GitLab
    source .venv/bin/activate
    ```

=== "Windows"

    ```powershell
    cd ~\GitLab
    .\.venv\Scripts\Activate.ps1
    ```

    Fails with `running scripts is disabled on this system`? The
    execution policy has not been set on this account - see
    [Before you start](#bootstrap-prerequisites).

Use whichever directory you made the environment in - `~/GitLab` here,
matching [Before you start](#bootstrap-prerequisites) above.

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

## Quick start {: #bootstrap-quick-start }

Six steps from a machine with nothing on it to a published site. Each one
is safe to repeat: bootstrap checks before it changes anything, and a
stage already done is left alone.

/// steps

//// step | Install Python
prodockit is a Python program, so this is the one thing that cannot be
automated - there is nothing to run it with yet. Any version from 3.10
works; 3.13 is what the template's CI uses.

=== "macOS"

    Install [Homebrew](https://brew.sh) if you do not have it, then:

    ```bash
    brew install python@3.13
    python3 --version
    ```

=== "Windows"

    ```powershell
    winget install --id Python.Python.3.13 -e
    py --version
    ```

    [python.org](https://www.python.org/downloads/) works equally well.
    Avoid the Microsoft Store build: it is a stub that cannot always
    create the virtual environment the next step needs.

=== "Ubuntu"

    `python3-venv` is a separate package on Debian and Ubuntu, and the
    next step will not work without it.

    ```bash
    sudo apt install python3 python3-venv
    python3 --version
    ```
////

//// step | Install prodockit in an environment of its own
In the directory you want to keep your projects in - the one you will
later point bootstrap's `project_dir` at - creating it if it is not there
yet. Not alongside your system Python: Debian and Ubuntu refuse
`pip install` outside a virtual environment, and the first stage checks
this before anything else, because the project's own environment is
built by whichever Python is running bootstrap.

=== "macOS"

    ```bash
    mkdir -p ~/GitLab
    cd ~/GitLab
    python3 -m venv .venv
    source .venv/bin/activate
    pip install prodockit
    ```

=== "Windows"

    ```powershell
    New-Item -ItemType Directory -Force ~\GitLab | Out-Null
    cd ~\GitLab
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install prodockit
    ```

=== "Ubuntu"

    ```bash
    mkdir -p ~/GitLab
    cd ~/GitLab
    python3 -m venv .venv
    source .venv/bin/activate
    pip install prodockit
    ```

`(.venv)` in your prompt means it is active. Every command below is run
from here, with it active - see [Before you start](#bootstrap-prerequisites)
for the longer version, including what to do when PowerShell refuses to
run the activation script.
////

//// step | Check what needs doing
```bash
pdk boot
```

The first run asks what it needs and saves the answers beside the project
as `.pdk-bootstrap.toml`. Then it stops, so what it tells you to note
down stays on the screen - run it again to see the stages.

On `gitlab.surrey.ac.uk` that is seven questions: your name, the ID you
log in with, your course code, and whether the work is assessed. Assessed
work is then asked which stage - first attempt, SRA or LSA - and which
year the module starts in, and its group and repository name follow from
those. Unassessed work is asked for its group and its repository name
instead, each offered as your own.

On any other host it is eight, since none of that can be derived there.

`pdk` is `prodockit` and `boot` is `bootstrap`, so
`prodockit bootstrap` is the same command typed in full.
////

//// step | Read the commands first
```bash
pdk boot --dry-run
```

Every command it would run, and every step it would ask you to do
yourself, without running any of them. Worth one read on a machine you
care about.
////

//// step | Apply it
```bash
pdk boot --apply
```

It asks before each stage and shows the commands first. Two steps need a
browser - uploading your SSH key, and creating the project on the host -
and those ask you to type `yes` when you have done them, because
pressing Enter through a browser step is how a run finishes with a stage
that never happened.

Stop whenever you like. The next run picks up from wherever it got to.
////

//// step | Confirm
```bash
pdk boot
```

Every stage `ok`, and the last one names the address your site is
published at. If a stage still reports work to do, its line says what
and why - and running `--apply` again does only that stage.
////

///

## What it covers {: #bootstrap-stages }

| # | Stage | Automated? |
| --- | --- | --- |
| 1 | prodockit runs in an environment of its own | yes, after a step of your own |
| 2 | Visual Studio Code | yes, after a step of your own |
| 3 | Git, installed **and** configured | yes |
| 4 | SSH keypair | yes, after a step of your own |
| 5 | SSH config points at the key | yes |
| 6 | Key loaded into the ssh agent | yes, after a step of your own |
| 7 | SSH key on the host | **guide and verify** |
| 8 | Where the project comes from | **a choice** |
| 9 | Project cloned | yes |
| 10 | A history of your own | yes |
| 11 | Your own project on the host | **guide and verify** |
| 12 | Pages switched on | **guide and verify** |
| 13 | Clone pointed at your project | yes |
| 14 | Commit identity in the project | yes |
| 15 | Pandoc, and the libraries WeasyPrint needs | yes |
| 16 | Project environment and its dependencies | yes |
| 17 | Node.js and the render toolchains | yes |
| 18 | VS Code extensions | yes |
| 19 | VS Code settings for the project | yes |
| 20 | Citation style for the first build | yes |
| 21 | MathJax for the website | yes |
| 22 | First commit pushed | yes, after a step of your own |
| 23 | Documentation site published | **guide and verify** |

Stages 8 to 14, 18, 19, 21 and 23 do the same thing on every operating
system - they are about your project and your host rather than about the
machine. The rest differ, because installing software does.

The list is longer than it was because it was wrong. Comparing it
against the User Guide step by step found six things it did not do at
all, from the PDF fonts' checker language down to the project's own
virtual environment - see [What "ready" means](#bootstrap-ready).

### A check must be able to see what its plan does {: #bootstrap-invariant }

The most persistent bug in this command has never been a wrong message.
It is a stage whose **check is narrower than its own plan**: the check
passes, the plan never runs, and the stage reports a state it is not in.
`ok` stops you looking, which is the whole cost.

It has happened seven times. Four were found by people running the tool;
three more were added *after* the pattern was written down, in the same
week - fonts added to a plan with no font check, Chromium and two shell
exports added with neither. The suite passed throughout, because it
asserted each half correctly and in isolation.

So there are now two gates across all stages, rather than an audit of
each:

1. **Every stage declares what its plan produces.** A stage added without
   an entry fails. Writing the entry is the point - it forces the
   question "can a check see this?" at the moment the plan grows.
2. **No stage whose plan installs something may report `ok` about a
   machine where nothing is installed.** This is the behavioural half,
   and it is what catches a declaration that was written without doing
   the work.

One refinement, learned from the case that nearly failed the rule while
being correct. Stage 12 installs Pango and **cannot** verify it -
importing WeasyPrint is the only real test, and WeasyPrint is not
installed until stage 13. That hand-off is right, so the invariant is
*some* stage's check must be able to observe what a plan changes, not
necessarily its own.

### What "ready" means {: #bootstrap-ready }

The bar is that **opening the project in VS Code is enough to start
writing**. Anything short of that is a stage, not a footnote - which is
why the list grew from thirteen to sixteen when it was compared against
the User Guide line by line.

Six things it did not do at all:

| | What was missing |
| --- | --- |
| **WeasyPrint was never verified** | Stage 12 was *named* "Pandoc and WeasyPrint's libraries" and only ever ran `pandoc --version`. It reported `ok` on a machine whose first PDF build would fail at `cannot load library`. Importing WeasyPrint is now the test, at stage 13 - a strict one, because the import loads Pango through the system linker, so success proves the package *and* the native libraries. `pip` exiting zero proves neither. |
| **Two required extensions, absent** | Even Better TOML and LTeX+ were missing, while Code Spell Checker - from the *optional* tooling page - was installed in their place. |
| **The project had no environment** | The clone ships a `requirements.txt` that nothing installed, so Zensical itself was absent from the project. |
| **The template's history was kept** | The guide resets it; the clone carried the template's whole log and branches into your project. |
| **Zensical Studio was unconfigured** | Markdown was not handed to its language mode. |
| **The grammar checker had no language** | LTeX+ was installed with nothing telling it what it was reading. |

Two of those deserve their own explanation, below: the project's own
virtual environment, and the history reset.

### Three things the first build needs {: #bootstrap-first-build }

The User Guide found these on a fresh Ubuntu ARM64 machine
(prodockit-userguide#101, #102 and #103), and all three were true here
too. Each fails in a way that does not point at itself.

**Mermaid's browser has to be the right architecture.** `npm ci` in
`tools/mermaid` triggers Puppeteer's own postinstall download, and that
download is not guaranteed to match the CPU it lands on. On ARM64 - an
Apple-silicon Linux VM, Graviton, a Raspberry Pi - it fetches an x86_64
Chrome that can never run. Nothing fails at install time. The symptom is
a diagram that will not render, much later, with nothing to connect it to
the install. So on Ubuntu the stage installs a system Chromium and
exports

```bash
PUPPETEER_EXECUTABLE_PATH=$(which chromium-browser || which chromium)
PUPPETEER_SKIP_DOWNLOAD=true
```

**before** `npm ci`, and appends them to `~/.bashrc` so later sessions
have them too - once, checked first, because a profile carrying the same
two exports four times over is the mark of a tool that assumed it would
only ever run once. macOS and Windows are left alone: Puppeteer's own
download is fine there.

**The PDF's fonts are not the website's fonts.** The site loads Inter and
JetBrains Mono from a CDN when a page is viewed; a PDF has to embed the
actual files. WeasyPrint **substitutes a fallback silently** rather than
failing, so the build succeeds, the PDF looks plausible, and the only
symptom is a test reporting `No 'Inter' font found`. They are installed
with the graphics stack now, per platform.

**The citation style is fetched, not committed.** `prodockit.bibliography`
is enabled by default and points `csl_style` at
`harvard-cite-them-right.csl`, which is not in the clone - so `zensical
serve`, `zensical build` and `prodockit pdf` all fail outright until it is
there. Stage 17 fetches it. An *empty* file counts as `WRONG` rather than
done: a failed download leaves one behind, and anything asking only
whether the path exists would call that finished. A project configured
for a different style is told to fetch its own rather than given Harvard.

### Two virtual environments, and only one of them is yours {: #bootstrap-project-env }

There are two, and confusing them is the whole difficulty of stage 13.

Bootstrap runs from one that **necessarily predates the project** -
`pip install prodockit` has to happen before there is anything to clone.
The User Guide's is a *second* environment, created inside the project
afterwards, and it is the one that matters day to day: the VS Code Python
extension finds `.venv` in your project folder and activates it in every
new terminal, which is why the guide's prompts read

```text
(.venv) yourname@Mac your-project %
```

So stage 13 creates `<project>/.venv` and installs `requirements.txt`
into **that**, naming the interpreter explicitly:

```bash
<project>/.venv/bin/python -m pip install -r <project>/requirements.txt
```

The explicitness is load-bearing. A bare `pip install -r
requirements.txt` finds whichever `pip` is on `PATH` - bootstrap's own -
and installs your project's dependencies into bootstrap's environment
instead. It exits zero, the stage re-checks, and your `.venv` is still
empty. You would find out at your first `zensical build`, with nothing
to suggest why.

### Deleting history is the one thing that asks first {: #bootstrap-fresh-history }

Stage 8 does what the guide's "Start with a fresh commit history" step
does - `rm -rf .git`, `git init -b main`, `git config core.fileMode
false` - and it is the only stage that destroys anything.

Two safeguards, both deliberate:

**It reports `WRONG`, not `MISSING`.** That is not a description of the
repository so much as a choice about the prompt: `MISSING` offers
`[Y/n]`, and deleting a repository's history should never happen by
pressing Enter.

**It is judged by `origin`, not by whether commits exist.** The obvious
test - "does this repository have history?" - would tell somebody who had
been writing for a month that theirs needed deleting. `origin` still
pointing at the template is the only state where discarding it is
unambiguously right, and it is one that cannot recur: resetting removes
the remote, repointing replaces it. A clone made from your own
`source_url` never matches it at all.

`core.fileMode false` comes along from the guide, and earns its place: git
treats a change to a file's executable bit as a change to the file, and
cloud-sync clients rewrite those bits as they sync - so a project in a
synced folder can show every file as modified without a byte of content
having changed.

### The key ssh never offers {: #bootstrap-ssh-config }

Stage 4 exists because of a failure that lies about its own cause. With
no `Host` stanza, ssh does not know that `id_ed25519_gitlab` has
anything to do with `gitlab.surrey.ac.uk`. It offers its own defaults -
`id_rsa`, `id_ed25519` - and when none of them is accepted, falls back
to asking for a password:

```text
git@gitlab.surrey.ac.uk's password:
```

Which is indistinguishable from a key the host has rejected. The reader
goes back to the upload step and re-pastes a key that was never the
problem, because the key was never offered.

So the stanza is written first, in the User Guide's own shape:

```text
Host gitlab.surrey.ac.uk
    HostName gitlab.surrey.ac.uk
    User git
    IdentityFile ~/.ssh/id_ed25519_gitlab
```

It is **appended**, never written over: an ssh config is your file and
may hold entries for hosts this knows nothing about. And if a stanza for
this host already exists pointing somewhere else, bootstrap explains the
edit rather than making it - ssh takes the first match, so a second entry
would be ignored anyway, and rewriting your ssh config underneath you is
not something an installer should do unasked.

Permissions come with it, for the same reason. ssh refuses a private key
that others can read:

```text
Permissions 0644 for '/Users/al01234/.ssh/id_ed25519_gitlab' are too open.
This private key will be ignored.
```

and then falls back to a password - the same symptom, from a different
cause. `chmod 600` on both the key and the config closes it. Windows has
no `chmod` and restricts a profile file to its owner already, so it gets
the stanza without the permission step.

### The key ssh cannot use {: #bootstrap-ssh-agent }

Stage 5 is the second half of the same trap, and it catches the machines
stage 4 does not.

Stage 3 tells you to give the key a passphrase, which is right. But every
ssh command bootstrap runs carries `BatchMode=yes`, so none of them may
ask you for it. Those two are only compatible if an **agent** is holding
the decrypted key.

Without one, the failure is subtle enough to be worth spelling out. `ssh
-T` reads the `.pub` file and offers the public half quite happily - that
needs no passphrase:

```text
debug1: Offering public key: ~/.ssh/id_ed25519_gitlab ED25519 SHA256:NXf+... explicit
```

The host recognises it and challenges ssh to prove it holds the private
half. *That* needs the passphrase, and there is nobody to ask:

```text
Load key "~/.ssh/id_ed25519_gitlab": incorrect passphrase supplied to decrypt private key
```

So authentication fails, and stage 6 reports `the host rejected the key`
about a key that is correct, uploaded, and simply locked.

`ssh-add` is run with **the terminal handed over** - the only command in
bootstrap that gets it - because the passphrase prompt has to appear
somewhere and ssh reads it from `/dev/tty` regardless of what the caller
does with stdin. Run captured, it would sit unanswerable until the
timeout, which is exactly what `sudo` did in #243.

Starting an agent, though, is genuinely not automatable:

```bash
eval "$(ssh-agent -s)"
```

works by exporting `SSH_AUTH_SOCK` into *the shell that runs it*, and a
subprocess cannot export anything into its parent. Bootstrap running that
would start an agent, set the variable in a shell that then exits, and
change nothing at all. So when no agent is running it says so and gives
you the line to run - and asks you to re-run bootstrap in that same
terminal. On Windows the agent is a service, and enabling it needs an
Administrator window, which is a different shell rather than a different
command.

### Your commits, under your own name {: #bootstrap-identity }

Stage 11 sets `user.name` and `user.email` **on the clone**, not globally:

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

Guiding well is the other half, and it is the part written instructions
usually get wrong. Three things the upload stage does deliberately:

**It prints the key, rather than naming the file it lives in.**

```text
    4. Click 'Add new key', then fill in:
       Title: any clear name, so you can tell this machine's key from another's later.
       Key: copy everything between the lines below - all of it, and nothing else - and paste it in:
       ======= PUBLIC KEY =======
       ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... al01234@surrey.ac.uk
       ======= PUBLIC KEY =======
```

"Paste the contents of `~/.ssh/id_ed25519_gitlab.pub`" asks you to find a
dotfile, open it in something, and copy the right one of two files whose
names differ by four characters - and the wrong one is your *private*
key. Only `.pub` is ever read. The markers earn their place too: the key
is one long line that wraps in a terminal, and a key pasted a character
short is rejected exactly like one never uploaded at all.

**It navigates by menu, not only by URL.** A pasted link is the quicker
route if you already know where you are going, and the worse one if you
do not - it gives you no way to tell whether you have arrived somewhere
sensible. The menu path comes first and the URL follows as a shortcut.

**It names the traps the host sets.** GitLab requires an expiry date,
fills it in a year ahead, and will not let you clear it - so accepting
the default locks you out mid-course, and the failure surfaces months
later as a permission error that reads exactly like a misconfigured key.
GitHub has no such field. That difference is a value on the host record
rather than a branch in the stage, which is what keeps adding a host to
filling in a record.

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

There is exactly one deliberate exception, and it is asked **before**
anything runs rather than during it:

```text
  Run 2 commands? [Y/n]: y
  These need administrator rights.
  Password:
```

`sudo` reads its password from `/dev/tty` too, so telling it not to ask
is not an option the way it is for ssh and git. Left alone, it asked from
*inside* a captured subprocess: the reader typed a password into a
command whose output was being swallowed, and their thinking time counted
against the install's own time limit, which then expired
([#243](https://github.com/buckwem/prodockit-extensions/issues/243)). So
`sudo -v` is run first, with the terminal attached and nothing captured,
purely to refresh the credential - it runs no command of its own. The
privileged commands then find a warm timestamp and never prompt. Plans
that need no privileges, such as macOS's `brew install`, are never asked.

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
 4  ok    SSH config points at the key - gitlab.surrey.ac.uk uses id_ed25519_gitlab
 5  ok    Key loaded into the ssh agent - id_ed25519_gitlab is loaded
 6  ok    SSH key on the host - authenticated to gitlab.surrey.ac.uk
 7  ?     Template cloned - needs project_name
 ...
5 of 18 stages need work.
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

| What the plan does | Prompt |
| --- | --- |
| Anything that can be undone | `Apply? [Y/n]` |
| Anything that cannot - stage 8, and only stage 8 | `Apply? [y/N]` |

One rule, and a visible one. The default used to follow the *check's
status* - `MISS` meant yes, `WRONG` meant no - which is a rule you cannot
see from the prompt, so the same key press meant different things at
different stages for reasons that were never on screen.

Now a plan says whether it destroys something, and only one does.

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

**The host is the first question**, and deliberately so. Everything else
is shaped by it: which URLs the browser steps send you to, which key file
is looked for, whether the thing you are creating is called a project or
a repository. Answering it sixth would mean five questions about a setup
that might not be buildable at all.

It is asked as a **hostname** - the thing in your address bar - rather
than a nickname, and it is judged twice before it is stored.

*Is it a GitLab?*

```text
The git host your project lives on [gitlab.surrey.ac.uk]: bitbucket.org
  'bitbucket.org' does not look like a GitLab host - bootstrap's stages
  are written around GitLab, so a hostname naming something else cannot
  be set up (e.g. gitlab.surrey.ac.uk)
```

*Is it one that works yet?*

```text
The git host your project lives on [gitlab.surrey.ac.uk]: github.com
  github.com is declared but not yet supported - prodockit bootstrap
  currently implements gitlab.surrey.ac.uk only
```

*Does it answer?*

```text
The git host your project lives on [gitlab.surrey.ac.uk]:
  could not reach gitlab.surrey.ac.uk on port 22 - Operation timed out.
  If this host is only reachable from your university network, connect
  the VPN and press Enter to try again.
```

That last one earns its place. Without it the first sign of an
unreachable host is stage 6 reporting that your key was rejected - after
you have made a key and pasted it into a web page - and "I cannot reach
this server" looks nothing like "this server refused you". These stages
have produced that confusion three times already (#234, #239, #246), so
it is worth one connection attempt to tell the two apart at the point the
host is named.

Re-asking with the same answer is a real retry, not a loop: connect the
VPN, press Enter, and the second attempt succeeds.

Port 22 rather than 443, because every URL bootstrap builds is
`git@host:path`, which is ssh.

A configuration written before this stored a key - `host = "surrey"` -
and those files are on real machines, so they still resolve. The prompt
stores a hostname from now on.

Press Enter and you get Surrey's GitLab, which is the only host
implemented today.

A piped or scripted run never prompts - it reports what is missing and
carries on, rather than blocking on a question nobody is there to
answer.

The file is stored per **directory**, beside whatever is being set up:

| Where | Path |
| --- | --- |
| This directory | `./.pdk-bootstrap.toml` |
| Older, per user (macOS / Linux) | `~/.config/prodockit/bootstrap.toml` |
| Older, per user (Windows) | `%APPDATA%\prodockit\bootstrap.toml` |

One config per directory is one per project. There was a single file per
user until 0.32.1, so setting up a second project overwrote the answers
for the first - its namespace, its name, the directory it lives in - and
the original could not be re-checked without answering everything again.

The per-user file is still read where a directory has none of its own, so
a setup already answered keeps working and nothing has to be moved. It is
never written to once a local file is possible.

Where the directory is a git repository, `.pdk-bootstrap.toml` is added
to `.gitignore`: it holds your name, email and username, and the first
push commits everything else in the project.

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
run found several things no unit test could have: a `.deb` installed from
a filename that never existed (#233), the SSH stage ending the run on the
very state it exists to repair (#234), and a Chrome downloaded for the
wrong architecture (#249). All are fixed; the platform should be treated
as newly-trodden rather than proven.

**Windows now has every stage automated, and none of it has been run on a
Windows machine.** Those two facts belong in the same sentence. All
seventeen stages produce commands or instructions there, MSYS2 and Pango
install unattended, and the checks are written - but the only evidence
any of it works is that the command lists are what the User Guide says
they should be, asserted from macOS. Treat the first real run as the
test, and expect it to find things, because every other platform's first
run did.

Two Windows-specific hazards are handled because they are the same
hazards seen elsewhere, not because anyone hit them here:

- **`winget` asks questions.** It wants agreement to its source terms the
  first time it is used, and to a package's terms when one carries them -
  on the terminal, so a captured, timed subprocess simply waits. That is
  [the `sudo` failure](#bootstrap-no-prompts) reached by a different
  route, and it would have met every Windows reader at stage 1. Every
  `winget install` carries `--accept-source-agreements`,
  `--accept-package-agreements` and `-e`, the last because an ambiguous
  package id is one more thing to be asked about.
- **Rerunning must not accumulate.** The `PATH` entry for MSYS2 is added
  only when absent, the same way the ssh config stanza and the Puppeteer
  exports are.

What is still yours to do on Windows: the `ssh-agent` service, which needs
an Administrator window, and the PDF's two fonts, which Windows has no
package manager for. Both are *checked* rather than merely suggested - an
instruction nobody verifies is how a font goes missing silently.

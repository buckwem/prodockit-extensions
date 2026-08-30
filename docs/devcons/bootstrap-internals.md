---
icon: lucide/list-checks
---

{{ heading_counter_reset(page) }}

# Bootstrap design

This \index{bootstrap design} page is for contributors changing `prodockit bootstrap`. The author guide
documents what to run; this page records the safety model behind its stages.

## Model every stage as evidence and a plan

Each stage has two independent parts:

1. A `check` observes the machine or repository and reports `ok`, `warning`,
   `missing`, `wrong`, `unknown`, or `blocked` with evidence. A warning is
   non-blocking and is reserved for an explicit compatibility risk that cannot
   be verified, such as an installed program whose version cannot be read.
2. A `plan` describes commands and human instructions that could reach the
   desired state.

`--apply` executes the approved plan and then runs the check again. A command
returning zero is not proof that Python imports WeasyPrint, SSH authenticates,
the correct remote exists, or a public site answers.

A check must be able to observe what its plan changes. Otherwise a successful
application is followed by the same failing result and bootstrap cannot be
safe to repeat.

## Keep commands non-interactive

Every subprocess is non-interactive. Package managers receive unattended
flags, Git and SSH disable credential prompts, and commands have bounded
timeouts. A blinking prompt cannot be represented as a finding or resumed
reliably by a later run.

Work requiring credentials uses **guide and verify** instead. Bootstrap tells
the reader how to upload an SSH public key or create an empty project, then
checks authentication or repository reachability. It never asks for or stores
a personal access token.

## Treat fresh history as destructive

The fresh history stage removes the template's Git records before creating the
reader's own repository history. It is offered only when `origin` still points
at the known template remote. A clone already pointing at the reader's project
must never qualify.

This stage reports `wrong`, not `missing`, so pressing Enter cannot accept the
destructive action. The plan explains exactly what is removed and requires an
explicit answer.

## Separate bootstrap and project environments

Bootstrap necessarily runs before the target project exists. After cloning,
it creates the project's own `.venv` and invokes that environment's Python
explicitly when installing `requirements.txt`. A bare `pip` could otherwise
install project dependencies into bootstrap's environment and leave the
checkout unable to build.

## Preserve stage order

Stage order is dependency order: Git must exist before SSH and cloning; the
clone must exist before its environment and Node tools; the remote must exist
before a push; the push must trigger a pipeline before the site can be
verified. A failure stops the run because later findings would be consequences
of the first failure rather than independent work.

Manual instructions also declare whether they occur before or after commands.
Passphrase advice must precede `ssh-keygen`; instructions for configuring an
installed editor must follow installation.

## Add or change a stage

When changing a stage, add tests for its complete state classification, plan,
non-interactive command arguments, re-check behaviour, platform/host branches,
and refusal boundaries. Test the real end-to-end path on supported operating
systems when the change touches installers, shells, SSH, browsers, or host
behaviour that a fake runner cannot reproduce.

The installed-wheel harness runs two routes with deliberately old versions of
every versioned prerequisite, including npm and Ubuntu's system Chromium. The
GitHub new-repository route represents a first Bootstrap pass and must upgrade
the tools before creating the project. The Surrey existing-repository route
must make the same upgrades without changing the repository's existing
history. Both routes must pass a second check and leave a second apply
unchanged.

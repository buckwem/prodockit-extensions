# Mistakes

Mistakes made while working on this project, and the rule each one leaves
behind. Not a changelog of bugs in the code - `docs/about/changelog.md`
is that. This is a record of mistakes in the *work*: things done wrong
while writing, testing, releasing or reporting on it.

It exists because several have been made more than once. A mistake that
repeats is not carelessness twice over, it is a missing rule.

Covers work across all three repositories - `prodockit-extensions`,
`prodockit-template` and `prodockit-userguide` - and lives here because
this is where the work is driven from.

## How to use it

**Read this file at the start of a session**, and again before any step
that resembles an entry below: reverting a file, claiming something is
verified, quoting an issue or PR number, or cutting a release.

**Add an entry as soon as a mistake is found**, before fixing it and
whether or not it reached anyone. The near-misses are the valuable ones -
they are the same mistake with a lucky catch, and the luck is not part of
the process.

Each entry:

- **What happened** - concretely, with the command or claim that did it.
- **Why it happened** - the reasoning that made it look right at the time.
  An entry that stops at "was careless" teaches nothing.
- **The rule** - what to do instead, phrased so it can be followed
  without re-reading the story.

Newest last, numbered so they can be cited: "MISTAKES.md #1".

---

## 1. `git checkout <file>` used to undo a temporary edit

**What happened.** To prove a new test could actually fail, the fix in
`src/prodockit/bootstrap/stages.py` was deliberately reverted, the test
was run and failed as intended, and the sabotage was then undone with:

```bash
git checkout src/prodockit/bootstrap/stages.py
```

That restores the file to `HEAD`. The sabotage went, and so did the fix -
`_prodockit_command` and all three of its call sites, none of which were
committed yet. It was caught by a grep that happened to follow.

The same thing happened in #339, and was not caught: the check for
`zensical.toml`/`README.md` on the remote was reset away and shipped
missing through 0.28.x and 0.29.0.

**Why it happened.** `git checkout <file>` was thought of as "undo the
thing I just did", because the sabotage was the most recent edit. It is
not an undo - it discards *everything* uncommitted in that file.
`stages.py` is long and usually carries a whole change in progress, so
that is the entire piece of work.

**The rule.** Never use `git checkout <file>`, `git restore <file>` or
`git reset --hard` to undo an edit made on purpose. Reverse the exact
edit instead - the same script that made the change, run backwards, or a
copy of the file taken into the scratchpad first.

After any revert, by any means, grep for something unique to the work in
progress before continuing. A green test suite does not prove the work
survived: the tests pass without the fix right up until they are re-run
against the reverted file.

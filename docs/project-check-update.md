---
icon: lucide/list-checks
---

{{ heading_counter_reset(page) }}

# Check and update a template project

Use this sequence for a project created from `prodockit-template`. It gives one
repeatable starting point whether you only want to confirm that the project is
healthy or you expect a template update. The
[Command reference](command-line.md) gives the complete interface of each
command without repeating these task steps.

/// steps

//// step | Activate the project's environment

Open a terminal in the folder containing `zensical.toml`, then activate that
project's `.venv`. Do not run the checks from the parent Bootstrap environment.

////

//// step | Establish the current health baseline

```bash
pdk diag
```

Resolve every `FAIL` before attempting a template update. If Diagnostics offers
a bounded repair, inspect it with `pdk diag --dry-run` before deciding whether
to run `pdk diag --apply`. A run containing only `PASS` results establishes that
the local project is healthy; it does not check whether the remote template has
changed.

////

//// step | Align the selected project components when requested

If Diagnostics reports that Adopt has integration stages to apply, preview
exactly those local changes:

```bash
pdk adopt --dry-run
```

Review the stages, then use `pdk adopt --apply` if they are correct. Adopt can
install or align the supported local toolchain and save the project's selected
components, but it never downloads or applies a template. Rerun `pdk diag`
afterward and resolve any remaining failure before continuing.

////

//// step | Check the dependency declarations

```bash
pdk pins --check --offline
```

If this passes and you only wanted to check the project, continue to the final
verification step. If Diagnostics or Pins says the declarations are outside
the supported combination, run `pdk pins`, review the versions, and accept only
the tested defaults. Then rerun both the offline Pins check and `pdk diag`.

////

//// step | Preview and apply a template update when one is needed

```bash
pdk template-sync
```

If the preview says the project is already up to date, no template action is
needed. Otherwise review the reported files, then run:

```bash
pdk template-sync --apply
```

Use `--review-all` when the preview lists several edited template files. For
each file, inspect the diff and choose overwrite, `.new`, or skip; skip is the
safe default. Review and merge the generated pull or merge request before
continuing.

////

//// step | Confirm the applied template and pins agree

After the update has been merged and your local project contains that merge,
run:

```bash
pdk template-sync
pdk pins --check --offline
```

The first command should report that no template file changes are needed. The
second should report that every dependency declaration agrees. Investigate any
remaining result rather than repeatedly applying the update.

////

//// step | Run the final health and output checks

```bash
pdk diag
zensical build --clean --strict
pdk pdf
```

The project is ready when Diagnostics passes, the website build reports no
issues, and the PDF is written successfully. Review the website and PDF before
submitting or publishing them.

////

///

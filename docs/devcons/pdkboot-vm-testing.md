---
icon: lucide/monitor-check
---

# Test the pdkboot preview in a VM

Use a disposable VM snapshot. The preview is deliberately isolated from
`prodockit bootstrap`: it installs the `pdkboot` command and writes
`.pdkboot.toml` plus `.pdkboot.last-run.json` in the directory where it runs.

The package under test is `prodockit 0.43.0a2`. Confirm the wheel against
`dist/SHA256SUMS` before copying it into a VM.

## Install from a Parallels shared folder

Create a dedicated environment so replacing or removing the preview does not
affect a project's Python environment.

=== "Windows PowerShell"

    ```powershell
    py -m venv "$env:USERPROFILE\pdkboot-preview"
    & "$env:USERPROFILE\pdkboot-preview\Scripts\python.exe" -m pip install --upgrade pip
    & "$env:USERPROFILE\pdkboot-preview\Scripts\python.exe" -m pip install --pre "Z:\path\to\prodockit-0.43.0a2-py3-none-any.whl"
    & "$env:USERPROFILE\pdkboot-preview\Scripts\pdkboot.exe" --version
    ```

=== "Ubuntu"

    ```bash
    python3 -m venv ~/pdkboot-preview
    ~/pdkboot-preview/bin/python -m pip install --upgrade pip
    ~/pdkboot-preview/bin/python -m pip install --pre /path/to/prodockit-0.43.0a2-py3-none-any.whl
    ~/pdkboot-preview/bin/pdkboot --version
    ```

=== "macOS"

    ```bash
    python3 -m venv ~/pdkboot-preview
    ~/pdkboot-preview/bin/python -m pip install --upgrade pip
    ~/pdkboot-preview/bin/python -m pip install --pre /path/to/prodockit-0.43.0a2-py3-none-any.whl
    ~/pdkboot-preview/bin/pdkboot --version
    ```

The version command must print `pdkboot, version 0.43.0a2`.

## Run one scenario per snapshot

Create an empty working directory, enter it, then use the preview environment's
`pdkboot` executable throughout:

```text
pdkboot --configure
pdkboot --check
pdkboot --dry-run
pdkboot --apply
pdkboot --check
```

Do not approve destructive history work unless the VM contains no work that
needs preserving. After each run, retain `.pdkboot.last-run.json` with the
terminal transcript.

| Scenario | Starting state | Expected result |
|---|---|---|
| Fresh machine | Python only | Every install is explicit; completed stages become `ok` on the final check |
| Existing current tools | Git, Node, npm and Pandoc already current | Tools are checked and skipped rather than reinstalled |
| Older tools | Old Node and Pandoc on Windows | An explicit upgrade is proposed with a default of No |
| Broken Node | `node` works but `npm` does not | A repair is proposed; later npm work does not start first |
| Installed outside PATH | Git installed but absent from the initial Windows PATH | pdkboot discovers or refreshes the path before proposing another install |
| Interrupted install | Stop one slow installer once | The report says `interrupted`; the exact resume command rechecks completed work |
| Package-manager failure | Disable networking or damage a disposable winget source | Output is revealed, recovery is classified, and later stages do not start |
| Partial project | Interrupt clone or environment creation | Existing data is never deleted; recovery asks for inspection or moving it aside |
| Conflicting modes (#540) | Any state | `pdkboot --check --apply` fails before reading configuration or changing anything |

## Exercise an upgrade installation

In another disposable preview environment, install the released package first,
then install the wheel over it:

```text
python -m pip install "prodockit==0.42.1"
python -m pip install --upgrade --pre /path/to/prodockit-0.43.0a2-py3-none-any.whl
pdkboot --version
```

The legacy `prodockit bootstrap` command must still exist. Its configuration is
not read or rewritten by `pdkboot`.

## Roll back

Remove the dedicated preview environment. If the test directory is disposable,
remove it or revert the VM snapshot. No system software installed during an
approved `--apply` run is removed automatically; use the operating system's
normal package manager if the scenario requires uninstalling it.

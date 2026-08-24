# Installed-wheel adoption acceptance

The automated workflow builds a wheel and runs `tools/adopt_acceptance.py` on
GitHub-hosted Ubuntu x64 and Windows 2025 x64 machines. It uses disposable TOML
and YAML projects and covers the core, Mermaid-only, maths-only and combined
paths.

## Test a real project manually

Change to the prodockit-extensions repository:

```bash
cd /path/to/prodockit-extensions
```

Activate its virtual environment as a separate step:

```bash
source .venv/bin/activate
```

Build the candidate wheel:

```bash
python -m build --wheel
```

Run the acceptance script, naming an existing source project and a new output
directory:

```bash
python tools/adopt_acceptance.py \
    --wheel dist \
    --project /path/to/existing-site \
    --output /path/to/adopt-test-copy \
    --report adopt-acceptance-report.json
```

On PowerShell, use one line or PowerShell's backtick continuation:

```powershell
python tools/adopt_acceptance.py --wheel dist --project C:\path\to\existing-site --output C:\path\to\adopt-test-copy --report adopt-acceptance-report.json
```

Add `--mermaid`, `--maths`, or both only when the project needs those optional
renderers.

The script:

1. Copies the source project without `.git`, `.venv`, `.cache`, `site`,
   `node_modules` or Python cache directories.
2. Creates a temporary clean virtual environment.
3. Installs the project's requirements, followed by the candidate wheel.
4. Builds the copy before adoption.
5. Confirms `--dry-run` writes nothing.
6. Applies adoption and builds again.
7. Checks that existing output is unchanged apart from the selected asset tags.
8. Applies adoption again and confirms it is idempotent.

The source project is never passed to `prodockit adopt`. The output directory
must not already exist, so the script cannot replace an earlier test or a real
project. After it passes, serve the disposable copy and inspect representative
pages yourself:

```bash
cd /path/to/adopt-test-copy
```

Create a fresh environment for the disposable copy if it does not already have
one:

```bash
python -m venv .venv
```

Activate it as a separate step:

```bash
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the requirements file used by the project. `prodockit adopt` checks
`requirements.txt`, `requirements/docs.txt`, then `docs/requirements.txt`, and
creates `requirements.txt` if the project did not already have one. For
example:

```bash
python -m pip install -r requirements.txt
```

Then run the preview:

```bash
zensical serve
```

If `dist` contains more than one prodockit wheel, pass the exact `.whl` path to
`--wheel` instead.

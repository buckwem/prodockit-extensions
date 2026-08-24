# Real-site adoption harness

This opt-in harness checks `prodockit adopt` against pinned public
documentation repositories. It proves that the existing site builds before
and after adoption and compares representative pages in headless Chrome.

It cannot change an upstream site:

- Each repository is fetched at the exact commit recorded in `sites.toml`.
- The checkout is created below pytest's temporary directory.
- Its Git push URL is replaced with `DISABLED_BY_REAL_SITE_HARNESS` before
    prodockit runs.
- The harness verifies that the commit did not move.
- `prodockit adopt` does not commit or push.

## Run the real-site checks

Change to the prodockit-extensions repository:

```bash
cd /path/to/prodockit-extensions
```

Activate its virtual environment as a separate step:

```bash
source .venv/bin/activate
```

Run the opt-in marker:

```bash
PRODOCKIT_REAL_SITE_TESTS=1 python -m pytest -m real_site tests/real_sites
```

Chrome or Chromium is required. Set `PRODOCKIT_TEST_CHROME` to its executable
when it is not on `PATH` or in a standard installation directory.

Site-specific, continuously animated regions may be listed as rectangles in
`sites.toml`. Every pixel outside those documented regions must remain
identical unless that site explicitly records a small tolerance.

## Backlog

`backlog.toml` is an inert planning list. The harness does not load it and no
command should browse, fetch, clone or test an entry from it without an
explicit request from the user. A site is executable only after a separately
approved test adds a pinned repository revision to `sites.toml`.

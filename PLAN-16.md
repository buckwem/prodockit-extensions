# Plan: rename `zendoc` → `prodockit` (zendoc-extensions#16)

**Done - all 5 phases complete, issue closed.** One manual step remains
outstanding on pypi.org: removing the old `zendoc` project (decision #1) -
not available via API, needs to be done by hand whenever convenient.

## What #16 actually asks for

> I want to remove the "zen" from the name of the extension. Change
> extension name to prodockit in prodockit-extensions repo.

Two renames, not one:
1. The **Python package/import name**: `zendoc` → `prodockit` (this repo's
   own `src/zendoc/*` code, PyPI project name, CLI command, entry points).
2. The **GitHub repo name**: `zendoc-extensions` → `prodockit-extensions`
   (this repo already went through one rename this month - `zendoc-extension`
   → `zendoc-extensions`, #11/#15 - so this is a second hop; see risks below).

This repo is not the only thing affected - `zendoc-template`
(github.com/buckwem/zendoc-template) depends on the `zendoc` PyPI package
directly (imports, `requirements.txt`, `zensical.toml` extension config)
and has **132 references to "zendoc"** across 20 files that would need
updating in lockstep. `zendoc-dev-dashboard` does **not** depend on the
`zendoc` package at all (checked - its dependencies are `zensical`,
`weasyprint`, etc., unrelated) - it just happens to share the naming
prefix, so it's out of scope here unless you want full branding
consistency later.

## Decisions (resolved)

1. **Existing `zendoc` PyPI releases**: remove the `zendoc` project from
   PyPI entirely. Note this is a manual step only you can do (full project
   deletion is a pypi.org web UI action, not available via API/CLI to an
   agent) - and PyPI's policy is that a deleted project's exact name
   generally can't be re-registered by anyone afterwards, so this is a
   one-way door. Sequencing: do this *after* `prodockit` is published and
   `zendoc-template` is cut over (Phase 4), so there's no gap where neither
   package installs.
2. **Version numbering for `prodockit`**: reset to `0.1.0`.
3. **`zendoc-template` renaming**: out of scope for now (bigger plans
   pending) - Phase 4 below only updates its *dependency* on the package,
   not the template repo's own name/branding.

## PyPI name check

`prodockit` is **available** on PyPI (confirmed - no existing project by
that name), so no squatting conflict to work around.

## Sequencing (each phase is a PR, tested before moving to the next)

### Phase 1 - `zendoc-extensions`: the package rename itself
- `src/zendoc/` → `src/prodockit/` (directory rename), all internal
  imports (`headings.py`, `refs.py`, `citations.py`, `glossary.py`,
  `settings.py`, `util.py`, `wordcount.py`, `zensical_macros.py`,
  `_zensical.py`, `pdf/__init__.py`, `pdf/build.py`, `pdf/cli.py`,
  `pdf/config.py`, `pdf/css.py`, `pdf/html.py`, `pdf/icons.py`,
  `pdf/lua.py`, `pdf/mermaid.py`) updated from `zendoc.X` to `prodockit.X`.
- `pyproject.toml`: `name = "zendoc"` → `"prodockit"`; entry points
  (`"zendoc.headings"` etc. → `"prodockit.headings"` etc.); `[project.scripts]
  zendoc = "zendoc.pdf.cli:main"` → `prodockit = "prodockit.pdf.cli:main"`
  (this is a CLI-breaking rename too - anyone running `zendoc` from a
  shell gets `prodockit` instead, worth a changelog line); `packages =
  ["src/zendoc"]` → `["src/prodockit"]`; ruff per-file-ignores paths;
  `[project.urls]` updated to the new repo name/Pages URL (see Phase 3 -
  these can be updated now even before the repo rename actually happens,
  same as #11 did).
- `tests/*.py` - update every `from zendoc...`/`import zendoc` to
  `prodockit`.
- `docs/*.md`, `README.md`, this repo's own `zensical.toml` (which
  showcases the extension on its own docs site) - every `zendoc.headings`/
  `zendoc.citations`/`pip install zendoc`/repo-URL reference updated.
- Verify: full test suite (`pytest`), `zensical build`, docs site builds
  clean.

### Phase 2 - cut a `prodockit` PyPI release
- `pyproject.toml` version reset to `0.1.0` (per decision #2).
- One-time manual step **you'll need to do yourself**: register
  `prodockit` as a pending trusted publisher on pypi.org for this repo's
  `publish.yml` workflow (trusted publishing is configured per-project-name
  on PyPI's side and requires your own PyPI login - I can't do this part).
- Then a normal GitHub Release triggers `publish.yml` as it already does.

### Phase 3 - rename the GitHub repo - done
- `zendoc-extensions` → `prodockit-extensions` via `gh repo rename`.
- Redirect-chaining risk checked and fine: `github.com/buckwem/zendoc-extensions`
  redirects (301 → 200) to the new URL.
- GitHub Pages: old `buckwem.github.io/zendoc-extensions/` 404s (expected -
  Pages doesn't redirect the way repo URLs do), new
  `buckwem.github.io/prodockit-extensions/` resolves (200).
- Local clone directory renamed to `~/GitHub/prodockit-extensions`, `origin`
  remote URL updated.
- All self-referential URLs in-repo (pyproject.toml, README, docs) were
  already updated ahead of time in Phase 1/#17, so no further code changes
  needed here.

### Phase 4 - `zendoc-template`: update the dependent repo
132 references across 20 files, roughly:
- `requirements.txt` - `zendoc>=0.10.0` → `prodockit>=<new version>`.
- `macros.py` - `from zendoc.zensical_macros import define_env` →
  `from prodockit.zensical_macros import define_env`; update the
  workaround comment (currently references `zendoc.zensical_macros` and
  `zensical/zensical#823`, the issue number stays the same, just the
  module name in the prose changes).
- `zensical.toml` - `[project.markdown_extensions."zendoc.headings"]` and
  siblings (`refs`, `citations`, `glossary`) → `"prodockit.headings"` etc.
- `build_pdf.py` - any `zendoc.pdf`/`zendoc.settings`/`zendoc.wordcount`
  references.
- `docs/starthere/customise.md`, `installtooling.md`, `startediting.md`,
  `testing.md` - prose references, install instructions, doc links
  (`buckwem.github.io/zendoc-extensions/...` → `.../prodockit-extensions/...`).
- `test/conftest.py`, `test_customisation.py`, `test_captions.py`,
  `test_fences.py`, `test_links.py`, `test_pdf_structure.py`,
  `test_word_count.py`, `test_zensical_basics.py`, `test/run_tests.py` -
  import statements and docstring/comment references.
- `README.md`, `CONTRIBUTING.md` - prose references.
- `spike/render-pipeline-92/fix_tabs.py` - this is old spike/scratch code
  from a past migration; worth checking whether it's still referenced by
  anything live or safe to leave/delete rather than update in place.
- Verify: `pip install -r requirements.txt`, `python build_pdf.py`,
  `zensical build --clean`, full `pytest` suite (157 tests currently) -
  all need to pass against `prodockit` before merging.

### Phase 5 - close out
- Close #16 (this repo) referencing the merged PRs.
- Remove the `zendoc` project from PyPI (decision #1 - manual, pypi.org,
  after `prodockit` is live and `zendoc-template` is cut over).
- Update memory/notes if anything here should persist beyond this
  conversation (e.g. the new repo name, PyPI package name).

## Effort/risk summary

This is bigger than #11 (that was a pure find-replace on self-referential
URLs/prose, ~15 lines across 5 files). This one is a real package rename:
directory move, import rewrites, entry-point/CLI renames, a PyPI release,
a second repo rename hop, and a 132-reference cleanup in the dependent
template repo - each phase independently testable, but the whole thing
only "works" end to end once `zendoc-template` is pointed at a published
`prodockit` release, so there's a window where the two repos are
intentionally out of sync (Phase 1-2 done, Phase 4 not yet) - not a
problem as long as `zendoc-template`'s `main` isn't touched until Phase 4
actually lands.

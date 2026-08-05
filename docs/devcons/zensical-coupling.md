# Zensical coupling {: #coupling-zensical-coupling }

prodockit imports several Zensical Python APIs that Zensical neither
documents nor treats as public. Nothing else in these docs says which, so
the coupling is invisible until a Zensical release breaks it. This page is
that list.

!!! info "Last verified against Zensical 0.0.53"
    Every call site and data shape below was checked against that version.
    A newer Zensical may have moved any of them - see
    [Regression testing a Zensical upgrade](#coupling-regression-testing).

## Why this page exists {: #coupling-why }

Zensical 0.0.53's `zensical/__init__.py` exports exactly three names:

```python
__all__ = ["build", "serve", "version"]
```

**prodockit uses none of them.** Everything it reaches for is a module-level
import from inside the package. Zensical's documentation site has no Python
API reference at all, and upstream's own position is that the module API is
not yet stable or generally available.

The practical consequence: any of these can be renamed or removed in a
**patch** release without that counting as a breaking change from
upstream's point of view. So a `zensical` bump needs a deliberate
regression pass, not just a green test run.

## Undocumented Python APIs {: #coupling-python-apis }

| API | Call site | Why prodockit needs it |
| --- | --- | --- |
| `zensical.config.get_config()` | [`_zensical.py:145`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/_zensical.py) | Reads the in-flight build's `docs_dir`/`nav` for the nav pre-scans |
| `zensical.config.parse_config()` | [`pdf/config.py:291`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/pdf/config.py), [`testing/plugin.py:139`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/testing/plugin.py) | Resolves `zensical.toml` the way a real build does, for the PDF pipeline and the pytest fixtures |
| `zensical.markdown.render.render()` and its `content`/`meta` result keys | [`pdf/config.py:289,344,348-351`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/pdf/config.py) | Renders each nav page to HTML for the PDF using the website's own pipeline |
| `zensical.extensions.context.ContextPreprocessor.from_markdown()` and `.page.path` | [`_zensical.py:91-104`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/_zensical.py) | Recovers the current page path under Zensical's per-page `render()` |
| `zensical.version()` | [`_zensical.py:60-62`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/_zensical.py) | Names the installed version when reporting that one of these APIs moved. The one documented name on the list |

Three more appear only in the test suite. They are no less coupled - a
rename breaks the build, it just breaks CI rather than a user's site:

| API | Call site | Why |
| --- | --- | --- |
| `zensical.extensions.context.ContextExtension`, `Page` | `tests/test_zensical_integration.py:14` | Simulates a per-page render, so cross-page resolution is tested the way Zensical actually drives it |
| `zensical.extensions.macros.MacroEnv` | `tests/test_zensical_macros.py:9` | Exercises `define_env()` against the real macro environment |
| `zensical.config` + `zensical.markdown.render` | `tests/test_docs_render_cleanly.py:41-45` | Renders every nav page to catch a page that only fails inside a real build |

## Undocumented data shapes {: #coupling-data-shapes }

Not imports, but just as breakable - prodockit reads structures whose keys
are nowhere documented.

**The resolved nav tree** — `{"url", "is_index", "children"}`, read by
[`settings.py:26-28`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/settings.py)
and `_zensical.py`'s own `_flatten_nav()`. `is_index` appears nowhere in
Zensical's documentation; it exists only in the loader's output.

**`env.conf`** inside `define_env(env)` —
[`zensical_macros.py:199`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/zensical_macros.py).
The Macros page documents `define_env(env)`, `env.variables`, `env.macro`
and `env.filter`, but not `env.conf`; the documented route to config from a
macro is the `config` *template* variable.

**The packaged icon directory layout** — `<site-packages>/zensical/
templates/.icons/...`, searched by
[`pdf/icons.py:66-79`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/pdf/icons.py).
The docs describe `.icons` under your own `custom_dir`, never the path
inside the installed package. This one degrades gently: the lookup already
tries `material` and `mkdocs_material` first and is wrapped in its own
`except`, so a layout change costs icons rather than the build.

## What is documented, and therefore fine {: #coupling-documented }

Worth listing so this page doubles as a triage aid - if something breaks
and it is on *this* list, a Zensical rename is unlikely to be the cause:

- `zensical.extensions.macros` with `module_name`, configured in
  `zensical.toml` — documented configuration, not an import.
- `zensical.extensions.emoji.twemoji` / `.to_svg`, likewise.
- `[project.theme.icon.admonition]` and the rest of the theme config
  prodockit's PDF pipeline reads.

These are strings in a config file that Zensical resolves itself. prodockit
never imports them.

## Robustness notes {: #coupling-robustness }

### Renames are guarded, and reported {: #coupling-rename-guard }

Both lookups in `_zensical.py` guard the attribute access and the call, not
just the import. A renamed `from_markdown`, a changed signature, or a
`Page.path` that becomes `Page.src_path` all import perfectly and then
raise `AttributeError`/`TypeError` - so guarding only the import left those
surfacing as a stack trace from inside `zensical build`, with nothing
pointing at the version bump.

prodockit now warns instead, naming the API, the installed Zensical version
and what degrades:

```text
prodockit expected Zensical's ContextPreprocessor.from_markdown(md).page.path,
which raised AttributeError: ... Zensical 0.0.52 appears to have moved it.
prodockit falls back to non-Zensical behaviour, so cross-page references,
citations and glossary terms may resolve to their unresolved marker instead
of the real target.
```

!!! warning "The guards do not silently swallow the failure, deliberately"
    Returning `None` quietly would be worse than the crash it replaces.
    `page_source()` returning `None` makes every page fall back to the same
    default source, so each render wipes the previous page's registry
    entries and cross-page references resolve to `??` — on a site that
    still builds and exits zero.

    A plain `ImportError` *is* silent, because "not running under Zensical"
    is a legitimate state for any other Python-Markdown consumer. Each API
    is reported once per process rather than once per page, since
    `page_source()` runs on every render.

### `parse_config()` writes a module-level global {: #coupling-parse-config-global }

`zensical.config.parse_config()` sets Zensical's module-level `_CONFIG` -
the same global `get_config()` reads.

Harmless today: `prodockit pdf` and the pytest fixtures each run in their
own process. But calling `build_pdf_from_zensical_config()` or using the
`prodockit_resolved_config` fixture *inside a live build process* would
silently rebind that build's config. Worth knowing before wiring the PDF
build into a Zensical plugin.

### The unguarded imports are correct {: #coupling-unguarded }

`pdf/config.py` and `testing/plugin.py` import Zensical without a guard.
That is deliberate - Zensical is a hard requirement for both, and failing
loudly is right. The same rename risk applies to `render()`'s
`result["content"]`/`["meta"]` keys, which would raise `KeyError` mid-build;
that has no friendlier message yet.

## Regression testing a Zensical upgrade {: #coupling-regression-testing }

None of the above is a documented interface, so **a green unit-test run is
not enough**. A Zensical bump needs a deliberate pass:

1. **Run the full suite**, `tests/test_zensical_integration.py` especially -
   it exercises the per-page render context directly.
2. **Build the site *and* the PDF, and diff the output** rather than
   checking both exit zero. Zensical 0.0.52 silently redrew the GitHub
   brand icon (Font Awesome 7.2.0 → 7.3.1) with no source change, which is
   exactly the drift a pass/fail check misses. The
   [drift job](pinning-drift.md#pinning-watching-for-drift) does
   this comparison automatically.
3. **Check cross-page `\ref` / `\citeref` / `\gls` resolution
   specifically.** These depend on the nav pre-scans and on
   `ContextPreprocessor` reporting the right page path, and they degrade to
   `??` rather than failing.
4. **Confirm the data shapes.** The resolved nav tree should still carry
   `url`/`is_index`/`children`, and `render()` should still return
   `content`/`meta`.

`zensical` is [pinned exactly in the build](pinning-drift.md#pinning-version-pinning-and-drift)
so an upgrade is a decision rather than something that happens overnight -
which is what makes a deliberate pass possible at all.

## Related {: #coupling-related }

- [Limitations and workarounds](limitations.md) covers the theme CSS-class
  coupling - `.md-typeset` targeting, glightbox wrappers, and Zensical's own
  `LinksTreeprocessor` URL rewriting. Those are HTML/CSS shapes rather than
  APIs, and equally undocumented.
- [Version pinning and drift](pinning-drift.md) covers pinning `zensical`
  and watching for a newer release.

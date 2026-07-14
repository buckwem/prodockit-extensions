# Release Notes

## 0.5.0 (2026-07-14)

- New `zendoc.glossary` extension: define a term once via `attr_list` (an
  id plus a `data-term` short display string), then insert it by id from
  anywhere with `\gls{id}`, which resolves to the term's own text, linked
  to its definition - e.g. `\gls{css}` → `CSS`. Unlike `zendoc.citations`'
  `\cite{id}` (which generates new bracketed citation text), `\gls{id}`
  inserts the term's own registered text in place - closer to LaTeX's
  `glossaries` package.
- One shared `GlossaryRegistry` covers both acronym-style and
  glossary-style entries - they're the same kind of thing (an id with a
  short display text), so acronym and glossary pages can reference each
  other, or be referenced from any other page, with no special wiring.
- Supports forward references within a document, an `unresolved` marker
  (`?` by default) for an unknown id, and the same automatic Zensical
  cross-page registry sharing and nav pre-scan (for citing/using a term
  before its defining page has been converted) that `zendoc.citations` got
  in 0.4.0.
- Refactored the nav pre-scan logic (previously private to
  `zendoc.citations`) into a shared, generic
  `zendoc._zensical.preseed_attr_from_nav` helper, since `zendoc.glossary`
  needed the identical scan.

## 0.4.0 (2026-07-14)

Fixes found migrating zendoc-template's own `references.md` to
`zendoc.citations` for real - all discovered by actually building a
real multi-page site, not just single-document tests:

- **Fixed a real correctness bug**: `zendoc.refs`/`zendoc.citations` were
  emitting a bare `#id` fragment for *every* resolved link, including a
  cross-page one - which only works by coincidence in a single concatenated
  PDF document, but 404s on an actual multi-page website (an `#id` fragment
  only navigates within the *current* page). Both now emit a real relative
  link (e.g. `references.md#id`, correctly adjusted for the citing page's
  own directory depth) when the target is on a different page, which
  Zensical and MkDocs already know how to rewrite into the right clean URL
  - the same way a hand-typed cross-page Markdown link already works.
- New: `zendoc.citations` pre-scans every page in a Zensical build's nav
  for citation definitions before any page is actually converted, so citing
  a source *before* it's defined - the common case, since a references page
  is usually kept at the end of nav as an appendix - resolves correctly in
  a single `zensical build` pass, rather than only working from
  `zensical serve`'s live-reload. New `CitationRegistry.preseed()` method
  backs this; a real registration always supersedes a preseeded stub.
- `RefsExtension` gained a `source` option (mirroring `HeadingsExtension`'s),
  needed for the same-page-vs-cross-page link decision above.
- Fixed the nav pre-scan (and, in zendoc-template, its `build_pdf.py`-side
  equivalent) matching a citation-definition attr_list example shown
  literally inside a fenced code block in documentation - it now skips
  fenced content, the same protection `CitationDefTreeprocessor` already
  gets for free from the real Python-Markdown parser.

## 0.3.0 (2026-07-14)

- New `zendoc.citations` extension: define a source once via `attr_list`
  (an id plus a `data-cite-text` short display string), then cite it by key
  from anywhere with `\cite{id}` (or `\cite{id1,id2,...}` for multiple),
  auto-generating a bracketed, linked citation - `[Skoulikari, 2023]` -
  instead of hand-typing the link and text at every citation site.
- Supports forward references within a document, an `unresolved` marker
  (`?` by default) for an unknown key, and the same automatic Zensical
  cross-page registry sharing (with soft-fail on key collisions) that
  `zendoc.headings`/`zendoc.refs` got in 0.2.0.
- Auto-generating the references page's own listing from structured
  bibliographic data isn't built yet - see the extension's docs for the
  current scope.
- Fixed the `zensical.toml` installation examples in the docs: nested
  `[project.markdown_extensions.zendoc.headings]` tables don't work
  (Zensical only hoists the `pymdownx`/`zensical` namespaces that way) -
  the quoted-key form (`[project.markdown_extensions."zendoc.headings"]`)
  is required, as zendoc-template's own `zensical.toml` already used
  correctly.

## 0.2.0 (2026-07-14)

- `zendoc.headings`/`zendoc.refs` now share their registry automatically
  under Zensical, without any explicit `registry`/`source` configuration:
  each extension detects Zensical's per-page rendering context and derives
  a stable `source` from the page's own path, fixing cross-page `\ref{id}`
  references not resolving (zendoc-template#85).
- A heading id collision across two different sources, when detected via
  this automatic Zensical sharing, now logs a warning and keeps the first
  registration instead of raising `DuplicateIdError` - so two unrelated
  pages that happen to share a heading title (e.g. both have an "Overview"
  section) no longer break the build. Explicitly-shared registries (the
  manual multi-page pattern) still raise on a collision, unchanged.
- Fixed an extension-ordering bug: `zendoc.headings` and `zendoc.refs` now
  find and share each other's registry regardless of which order they're
  listed in - previously, only `zendoc.headings`-then-`zendoc.refs` worked
  reliably, and Zensical's own TOML-to-extension-list conversion doesn't
  preserve list order at all.

## 0.1.0 (2026-07-14)

Initial release.

- `zendoc.headings`: heading ids and hierarchical section numbering,
  backed by a shared `IdRegistry`.
- `zendoc.refs`: `\ref{id}` section cross-references, resolving to the
  target's current section number, including forward references within a
  document and across a shared registry.
- Documentation site built with Zensical, published at
  [buckwem.github.io/zendoc-extension](https://buckwem.github.io/zendoc-extension/).

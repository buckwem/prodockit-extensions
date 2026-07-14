# Release Notes

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

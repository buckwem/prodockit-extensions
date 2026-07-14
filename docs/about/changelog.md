# Release Notes

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

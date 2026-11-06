# Zensical rendering review catalogue

This is a separate Zensical project for the reviewable rendering coverage
tracked by [issue #1051](https://github.com/buckwem/prodockit-extensions/issues/1051).
It is deliberately outside the public documentation project.

Phase 1 establishes the reviewed capability inventory, coverage contract and
catalogue navigation. Phase 2 adds reviewable base Markdown and built-in
Python-Markdown specimens. Phase 3 adds all supported PyMdown settings. Phase
4 adds configured integrations, Zensical authoring and every Prodockit
authoring extension; the early-access Directives feature has an explicit
waiver. Phase 5 adds the reviewed nested-content matrix and deterministic
page-boundary specimens. Phase 6 packages the navigable website, complete and
per-page PDFs, PDF thumbnails, contact sheet and capability coverage report as
one review bundle and publishes the same bundle at the stable hidden route
`/rendering-review/`. Phase 7 makes the catalogue a release qualification
input, assigns every assertion to one of six explicit test layers and reports
drift from the official Zensical capability pages without rewriting the
reviewed ledger.

Check the catalogue source contract from the repository root:

```bash
python -m pytest tests/test_rendering_catalogue.py -q
```

Build the complete Phase 6 review bundle from the repository root:

```bash
python tools/rendering_catalogue.py build
python tools/rendering_catalogue.py verify
```

The result is written to
`tests/rendering_catalogue/build/review-bundle/`. Open its `index.html` to
review the website, or open `contact-sheet.html` for a page-by-page overview
of the complete PDF. `coverage-report.html` links every reviewed capability to
its source, website specimen, PDF outputs and automated status.
`test-layers.html` lists the assertions owned by inventory, source/config,
strict build, website semantics, PDF semantics and visual review.

The website-only source project can still be built independently:

```bash
cd tests/rendering_catalogue
zensical build --clean --strict
```

After building both outputs, run the built-output semantic assertions from the
repository root:

```bash
python -m pytest tests/test_rendering_catalogue_built.py -m built -q
```

## Crawler controls and their limit

The public manual does not link to the catalogue and the route is excluded
from its navigation, search index and sitemap. The site sets `noindex`,
`nofollow`, `noarchive`, `nosnippet` and `noimageindex` on every review page;
the root `robots.txt` disallows the route for all crawlers and names common AI
crawlers explicitly. PDFs, thumbnails and reports stay beneath the same
disallowed route.

These controls are advisory. A crawler can ignore `robots.txt` or page
metadata, and GitHub Pages cannot add an `X-Robots-Tag` response header for
non-HTML assets. The catalogue is hidden from normal discovery, not protected
as confidential information.

## CI and downstream responsibilities

Relevant pull requests build and retain the complete catalogue before running
its semantic assertions. The same full build runs in the main documentation
workflow, which is a required successful input to release qualification.
Weekly drift checks compare the checked-in baseline with official Zensical
capability pages and open one review issue when the inventory changes; they do
not silently rewrite `catalogue.toml` or `upstream-inventory.toml`.

This repository owns the authoritative rendering catalogue. The template
tests generated-project and publication integration. The User Guide tests its
real document, content and Surrey publication overlay. Those downstream and
real-document tests remain because their purposes are not equivalent to an
isolated capability specimen; a test should be removed only after replacement
evidence and the responsibility transfer are explicit.

VENDORED MATHJAX
================

tex-svg-full.js is MathJax 3.2.2 (https://www.mathjax.org/), copied
verbatim from tools/mathjax/node_modules/mathjax-full/es5/. Apache-2.0,
licence text alongside it in LICENSE.

Plain text rather than Markdown on purpose: everything under docs/ is a
documentation source, so a README.md here is built into a real page on the
published site and indexed by its search. This is a note to whoever is
maintaining the file, not a page for readers.

Why vendored rather than a CDN

The website would otherwise fetch MathJax from a third-party CDN on every
page view. Vendoring keeps the site self-contained: no external request, no
dependency on someone else's uptime or retention policy, and the site
builds and works offline.

Why this particular bundle

- tex-... rather than tex-mml-...: pymdownx.arithmatex emits TeX,
  never MathML, so the MathML input processor would be dead weight.
- ...-svg... rather than -chtml: the SVG output processor carries
  its glyphs as paths inside the bundle. The CommonHTML one fetches around
  thirty .woff files from a sibling directory at runtime, which would
  mean vendoring those too and would reintroduce runtime fetches - the
  thing vendoring is meant to remove. SVG also matches what the PDF gets,
  since prodockit pdf pre-renders through the same MathJax to SVG.
- ...-full rather than the plain build: it bundles every TeX
  extension. The plain build loads an extension on demand from a sibling
  path the moment a formula uses one, which would fail here with nothing
  but a console error and an unrendered formula. 200 KB to remove a
  failure mode that only appears when someone writes a formula using an
  extension.

Replacing it

Bump mathjax-full in tools/mathjax/package.json, reinstall, then copy
the file across again:

    npm install --prefix tools/mathjax
    cp tools/mathjax/node_modules/mathjax-full/es5/tex-svg-full.js \
       docs/javascripts/vendor/mathjax/tex-svg-full.js

Keep the two in step. The PDF renders through tools/mathjax and the
website through this copy, so a mismatch means a formula can typeset one
way in print and another on screen - the reason this is copied from the
pinned install rather than downloaded separately.

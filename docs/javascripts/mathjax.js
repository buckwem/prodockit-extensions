// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT
//
// Client-side MathJax for the website only. The PDF never runs this:
// WeasyPrint has no JS engine, so `prodockit pdf` pre-renders the same
// formulas to static SVG through `tools/mathjax/tex2svg.js` instead (see
// docs/pdf.md). Both sides deliberately run the same MathJax build - the
// vendored bundle beside this file is copied verbatim from the very
// `mathjax-full` install tools/mathjax uses - so a formula cannot typeset
// one way on screen and another in print.
//
// Loaded *before* the MathJax bundle itself (order matters in
// zensical.toml's `extra_javascript`): MathJax reads `window.MathJax` once,
// at startup, so a config assigned afterwards is ignored.

window.MathJax = {
  tex: {
    // pymdownx.arithmatex's `generic = true` has already converted every
    // `$...$` / `$$...$$` into explicit `\(...\)` / `\[...\]` delimiters
    // server-side, which is also the only form prodockit.pdf's Lua filter
    // can pre-render. MathJax therefore never needs to hunt for `$` here,
    // and is not configured to.
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true,
  },
  options: {
    // Typeset *only* inside the wrappers arithmatex emitted, rather than
    // scanning the whole page. That matters more in this repository than
    // most: these docs are full of shell examples containing `$3`,
    // `$GITHUB_ENV` and `$pinned_zensical`, and none of it should ever be
    // mistaken for maths.
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex",
  },
};

// Re-typeset after client-side navigation. `navigation.instant` is enabled
// (see zensical.toml's theme features), so most page changes swap the DOM
// without a document load and MathJax's own startup typeset never runs
// again - formulas on every page after the first would stay as literal
// `\(...\)` without this. `document$` is the theme's own document
// observable; the guard keeps this harmless if a future theme drops it.
if (typeof document$ !== "undefined") {
  document$.subscribe(function () {
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.startup.output.clearCache();
      window.MathJax.typesetClear();
      window.MathJax.texReset();
      window.MathJax.typesetPromise();
    }
  });
}

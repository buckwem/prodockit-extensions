// Copyright (c) 2025-2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT

// Renders a single TeX formula (read from stdin) to a standalone SVG on
// stdout, using MathJax's pure Node component API (mathjax-full/js) - no
// browser/DOM required, unlike the Puppeteer-based mermaid rendering.
//
// Usage: node tex2svg.js <display|inline> < formula.tex > formula.svg
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const texInput = new TeX({ packages: AllPackages });
const svgOutput = new SVG({ fontCache: 'none' });
const doc = mathjax.document('', { InputJax: texInput, OutputJax: svgOutput });

const isDisplay = process.argv[2] === 'display';

let texSource = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { texSource += chunk; });
process.stdin.on('end', () => {
  try {
    const node = doc.convert(texSource, { display: isDisplay });
    const svgHtml = adaptor.outerHTML(node);
    const match = svgHtml.match(/<svg[\s\S]*?<\/svg>/);
    if (!match) {
      process.stderr.write('tex2svg: no <svg> produced for input\n');
      process.exit(1);
    }
    process.stdout.write(match[0]);
  } catch (err) {
    process.stderr.write(`tex2svg: ${err}\n`);
    process.exit(1);
  }
});

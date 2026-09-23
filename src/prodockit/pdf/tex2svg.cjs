// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT

// Promise-based adapter for the prebuilt MathJax 4 tex-svg component.
// Usage: node tex2svg.cjs <MathJax directory> <display|inline> < formula.tex

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(process.argv[2] || '');
const mode = process.argv[3];
const component = path.join(root, 'tex-svg.js');
const maximumInputBytes = 1024 * 1024;

if (!path.isAbsolute(root) || !fs.statSync(component, {throwIfNoEntry: false})?.isFile()) {
  process.stderr.write('tex2svg: the prepared MathJax runtime is incomplete\n');
  process.exit(2);
}
if (mode !== 'display' && mode !== 'inline') {
  process.stderr.write('tex2svg: mode must be display or inline\n');
  process.exit(2);
}

global.MathJax = {
  loader: {
    load: ['adaptors/liteDOM'],
    paths: {mathjax: root},
    require,
  },
  startup: {typeset: false},
  svg: {fontCache: 'none'},
};

let source = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  source += chunk;
  if (Buffer.byteLength(source, 'utf8') > maximumInputBytes) {
    process.stderr.write('tex2svg: input exceeds the 1 MiB limit\n');
    process.exit(2);
  }
});
process.stdin.on('end', async () => {
  try {
    require(component);
    await MathJax.startup.promise;
    const container = await MathJax.tex2svgPromise(source, {display: mode === 'display'});
    const html = MathJax.startup.adaptor.outerHTML(container);
    const svg = html.match(/<svg[\s\S]*<\/svg>/)?.[0];
    if (!svg) throw new Error('no SVG was produced');
    // MathJax's HTML serializer leaves SSML tags inside accessibility
    // attributes. An external SVG image must be well-formed XML for WeasyPrint.
    const xmlSvg = svg.replace(/="[^"]*"/g, (attribute) =>
      attribute.replaceAll('<', '&lt;').replaceAll('>', '&gt;'));
    process.stdout.write(xmlSvg);
    MathJax.done();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`tex2svg: ${message}\n`);
    process.exit(1);
  }
});

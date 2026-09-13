// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT

// Read one JSON request from Python, serve the completed site on loopback,
// and check the DOM after the site's own JavaScript has run.
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const puppeteer = require(request.puppeteerModule);
const siteDir = path.resolve(request.siteDir);
const timeoutMs = request.timeoutMs || 15000;
const types = {
  '.css': 'text/css',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.mjs': 'text/javascript',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

const server = http.createServer((incoming, outgoing) => {
  let requested;
  try {
    requested = decodeURIComponent(new URL(incoming.url, 'http://localhost').pathname);
  } catch (_) {
    outgoing.writeHead(400).end();
    return;
  }
  let file = path.resolve(siteDir, `.${requested}`);
  const relative = path.relative(siteDir, file);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    outgoing.writeHead(403).end();
    return;
  }
  try {
    if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    outgoing.writeHead(200, { 'content-type': types[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(outgoing);
  } catch (_) {
    outgoing.writeHead(404).end();
  }
});

function renderedCounts() {
  const article = document.querySelector('article.md-content__inner.md-typeset');
  if (!article) return { article: false, maths: [], mermaid: [], visibleMaths: [], visibleMermaid: [] };
  const visible = element => {
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return box.width > 0 && box.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const svgWithin = root => {
    if (!root) return false;
    for (const svg of root.querySelectorAll('svg')) {
      if (visible(svg)) return true;
    }
    for (const element of root.querySelectorAll('*')) {
      if (element.shadowRoot && svgWithin(element.shadowRoot)) return true;
    }
    return false;
  };
  const mathHosts = [...article.querySelectorAll('.arithmatex')];
  const mermaidHosts = [...article.querySelectorAll('.mermaid')];
  const visibleMaths = mathHosts.flatMap((host, index) => visible(host) ? [index] : []);
  const visibleMermaid = mermaidHosts.flatMap((host, index) => visible(host) ? [index] : []);
  const maths = mathHosts.flatMap((host, index) => {
      const mathjax = host.querySelector('mjx-container');
      if (mathjax && visible(mathjax) &&
          (svgWithin(mathjax) || mathjax.querySelector('mjx-math'))) return [index];
      const katex = host.querySelector('.katex');
      return katex && visible(katex) && katex.querySelector('.katex-html') ? [index] : [];
    });
  const mermaid = mermaidHosts.flatMap((host, index) => svgWithin(host) ? [index] : []);
  return { article: true, maths, mermaid, visibleMaths, visibleMermaid };
}

async function captureFailure(page, label, errors) {
  const safe = label.replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 80);
  fs.writeFileSync(path.join(request.diagnostics, `${safe}.errors.json`), JSON.stringify(errors, null, 2));
  if (!page) return;
  try {
    fs.writeFileSync(path.join(request.diagnostics, `${safe}.html`), await page.content());
    await page.screenshot({ path: path.join(request.diagnostics, `${safe}.png`), fullPage: true });
  } catch (error) {
    fs.writeFileSync(path.join(request.diagnostics, `${safe}.capture-error.txt`), String(error));
  }
}

async function checkPage(page, target, label, errors) {
  const seen = { maths: new Set(), mermaid: new Set() };
  const observe = async () => {
    await page.waitForFunction(
      () => {
        const state = window.__pdkRenderedCounts();
        return state.article &&
          state.visibleMaths.every(index => state.maths.includes(index)) &&
          state.visibleMermaid.every(index => state.mermaid.includes(index));
      },
      { timeout: timeoutMs, polling: 250 },
    );
    const state = await page.evaluate(renderedCounts);
    state.maths.forEach(index => seen.maths.add(index));
    state.mermaid.forEach(index => seen.mermaid.add(index));
  };
  try {
    await observe();
    const tabCount = await page.evaluate(() =>
      document.querySelectorAll('article.md-content__inner.md-typeset .tabbed-set .tabbed-labels label').length,
    );
    for (let index = 0; index < tabCount; index++) {
      await page.evaluate(index => {
        document.querySelectorAll('article.md-content__inner.md-typeset .tabbed-set .tabbed-labels label')[index].click();
      }, index);
      await observe();
    }
    if (seen.maths.size < target.maths || seen.mermaid.size < target.mermaid) {
      throw new Error('Some maths or Mermaid elements were never visibly rendered in any tab');
    }
  } catch (error) {
    const counts = await page.evaluate(renderedCounts).catch(() => ({}));
    await captureFailure(page, label, { target, counts, seen: {
      maths: [...seen.maths], mermaid: [...seen.mermaid],
    }, errors });
    throw new Error(
      `${target.source} (${label}): expected ${target.maths} rendered equation(s) and ` +
      `${target.mermaid} Mermaid SVG(s); found ${seen.maths.size} and ` +
      `${seen.mermaid.size} after checking visible content and tabs. ${error.message}`,
    );
  }
}

async function main() {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await puppeteer.launch({
      executablePath: request.browser,
      headless: true,
      args: ['--no-sandbox', '--disable-gpu'],
    });
    const page = await browser.newPage();
    await page.evaluateOnNewDocument(`window.__pdkRenderedCounts = ${renderedCounts.toString()};`);
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
    page.on('pageerror', error => errors.push(`page: ${error.message}`));
    page.on('requestfailed', failed => errors.push(`request: ${failed.url()} ${failed.failure()?.errorText}`));
    page.on('response', response => { if (response.status() >= 400) errors.push(`HTTP ${response.status()}: ${response.url()}`); });

    for (const target of request.targets) {
      try {
        await page.goto(`${base}${target.route}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
      } catch (error) {
        await captureFailure(page, `load-${target.source}`, errors);
        throw new Error(`${target.source}: the built page did not load: ${error.message}`);
      }
      await checkPage(page, target, `direct-${target.source}`, errors);
    }
    if (request.instantNavigation && request.startRoute) {
      const target = request.targets[0];
      try {
        await page.goto(`${base}${request.startRoute}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
      } catch (error) {
        await captureFailure(page, `navigation-start-${target.source}`, errors);
        throw new Error(`${target.source}: the instant-navigation start page did not load: ${error.message}`);
      }
      const clicked = await page.evaluate(route => {
        const link = [...document.querySelectorAll('a[href]')].find(candidate => {
          const url = new URL(candidate.href);
          return url.origin === location.origin && url.pathname === route;
        });
        if (!link) return false;
        link.click();
        return true;
      }, target.route);
      if (!clicked) {
        await captureFailure(page, `navigation-${target.source}`, errors);
        throw new Error(`${target.source}: no local navigation link found for instant-navigation check`);
      }
      try {
        await page.waitForFunction(route => location.pathname === route, { timeout: 15000 }, target.route);
      } catch (error) {
        await captureFailure(page, `navigation-${target.source}`, errors);
        throw new Error(`${target.source}: instant navigation did not reach the page: ${error.message}`);
      }
      await checkPage(page, target, `navigation-${target.source}`, errors);
    }
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});

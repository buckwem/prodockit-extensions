// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT
// NODE_PATH may point at an existing puppeteer-core installation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const puppeteer = require('puppeteer-core');
const script = fs.readFileSync('docs/javascripts/pdk.js', 'utf8');
const css = fs.readFileSync('docs/stylesheets/pdk.css', 'utf8');
const server = http.createServer((req, res) => {
  if (req.url === '/pdk-sleigh.png') {
    res.setHeader('Content-Type', 'image/png');
    return res.end(fs.readFileSync('docs/javascripts/pdk-sleigh.png'));
  }
  res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(
  '<meta charset="utf-8"><style>' + css + '</style><body data-md-color-scheme="default"><div data-md-component="palette"></div><a href="#target">Underlying link</a>' +
  '<div style="height:3000px"></div><h2 id="target">Target</h2><script>' +
  'window.document$={subscribe(f){window.refresh=f;f()}};</script><script>' + script + '</script>'
); });
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await puppeteer.launch({executablePath: process.argv[2], headless: true});
  try {
    const page = await browser.newPage();
    page.on("console", msg => { if (msg.type() === "warning") console.log(msg.text()); });
    page.on("pageerror", error => console.log(error.message));
    const base = 'http://127.0.0.1:' + server.address().port;
    async function load(time, width = 1000) {
      await page.setViewport({width, height: 800});
      await page.goto(base + '/?pdk-festive-test=1&pdk-festive-speed=0&pdk-festive-time=' + encodeURIComponent(time));
      await page.waitForSelector("canvas", {timeout: 5000});
    }
    async function state() { return page.$eval('canvas', c => JSON.parse(c.dataset.snapshot)); }
    for (const [time, expected] of [
      ['2026-12-24T09:59:59Z', undefined], ['2026-12-24T10:00:00Z', 'Kiritimati'],
      ['2026-12-24T18:15:00Z', 'Kathmandu'], ['2026-12-26T11:59:59Z', 'Baker'],
      ['2026-12-26T12:00:00Z', undefined]
    ]) {
      await load(time); assert.equal((await state()).destination, expected);
    }
    await load('2026-12-24T10:00:00Z', 390);
    await page.evaluate(() => { for(let i=0;i<5;i++) window.refresh(); });
    assert.equal(await page.$$eval('canvas', els => els.length), 1);
    assert.equal(await page.$eval('canvas', c => getComputedStyle(c).pointerEvents), 'none');
    await page.evaluate(() => document.body.setAttribute('data-md-color-scheme','slate'));
    await page.waitForFunction(() => JSON.parse(document.querySelector('canvas').dataset.snapshot).colour === '#fff');
    assert.equal(await page.$eval('[data-md-component=palette]', el => el.previousElementSibling.classList.contains('pdk-festive-toggle')), true);
    await page.click('.pdk-festive-toggle');
    assert.equal((await state()).hidden, true);
    await page.click('.pdk-festive-toggle');
    assert.equal((await state()).hidden, false);
    await page.evaluate(() => scrollTo(0,500));
    assert.equal(await page.$eval('canvas', c => c.getBoundingClientRect().top), 0);
    await page.screenshot({path:'/tmp/pdk-festive-mobile.png'});
    await page.emulateMediaType('print');
    assert.equal(await page.$eval('canvas', c => getComputedStyle(c).display), 'none');
    await page.emulateMediaType('screen');
    await page.emulateMediaFeatures([{name:'prefers-reduced-motion', value:'reduce'}]);
    await page.waitForFunction(() => JSON.parse(document.querySelector('canvas').dataset.snapshot).paused);
    await page.evaluate(() => {
      const step = [...document.querySelectorAll('button')].find(b => b.textContent === 'Step');
      for(let i=0;i<800;i++) step.click();
    });
    assert.equal((await state()).destination, 'Chatham');
    // Accelerate ten minutes of snowfall by deterministic single-frame steps.
    await page.evaluate(() => {
      const step = [...document.querySelectorAll('button')].find(b => b.textContent === 'Step');
      for(let i=0;i<36000;i++) step.click();
    });
    const bounded = await state();
    assert.ok(bounded.particles <= 180 && bounded.bank <= 48);
    await page.select('select[aria-label="Preview preset"]', 'Current Santa zone');
    const previewTime = await page.$eval('input[aria-label="Simulated UTC time"]', el => el.value);
    const utcNow = new Date();
    assert.equal(previewTime.slice(5, 10), '12-25');
    assert.equal(previewTime.slice(11, 16), utcNow.toISOString().slice(11, 16));
    assert.equal(await page.$eval('input[aria-label="Clock speed"]', el => el.value), '1');
    await page.goto(base);
    assert.equal(await page.$$('canvas').then(x=>x.length), 0);
    console.log('Passed Christmas boundaries, Nepal handover, mobile, palette, navigation, print, reduced motion and ten simulated minutes.');
  } finally { await browser.close(); server.close(); }
})().catch(error => {console.error(error); server.close(); process.exitCode=1;});

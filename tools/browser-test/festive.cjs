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
  const path = new URL(req.url, 'http://localhost').pathname;
  if (req.url === '/pdk-sleigh.png') {
    res.setHeader('Content-Type', 'image/png');
    return res.end(fs.readFileSync('docs/javascripts/pdk-sleigh.png'));
  }
  res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(
  '<meta charset="utf-8"><style>' + css + '</style><body data-md-color-scheme="default"><div data-md-component="palette"></div><a href="#target">Underlying link</a>' +
  (path === '/enabled' ? '<span hidden data-pdk-festive=\'{"enabled":true,"effect":"snow"}\'></span>' :
    path === '/custom' ? '<span hidden data-pdk-festive=\'{"enabled":true,"effect":"auto","fireworks_start":"12-31","fireworks_hours":2,"sound":false,"position":"bottom-left"}\'></span>' : '') +
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
      ['2026-12-24T18:15:00Z', 'Nepal'], ['2026-12-25T10:59:59Z', 'Hawaii'],
      ['2026-12-25T11:00:00Z', undefined]
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
    assert.equal((await state()).destination, 'New Zealand');
    await page.evaluate(() => {
      const step = [...document.querySelectorAll('button')].find(b => b.textContent === 'Step');
      for(let i=0;i<800;i++) step.click();
    });
    assert.equal((await state()).destination, 'Fiji');
    // Accelerate ten minutes of snowfall by deterministic single-frame steps.
    await page.evaluate(() => {
      const step = [...document.querySelectorAll('button')].find(b => b.textContent === 'Step');
      for(let i=0;i<36000;i++) step.click();
    });
    const bounded = await state();
    assert.ok(bounded.particles <= 180 && bounded.bank <= 48);
    await page.select('select[aria-label="Preview preset"]', 'Changing Location');
    assert.equal((await state()).destination, 'Kiritimati');
    assert.equal(await page.$eval('input[aria-label="Clock speed"]', el => el.value), '0');
    await page.select('select[aria-label="Preview preset"]', 'Reset');
    assert.equal((await state()).bank, 0);
    await page.select('select[aria-label="Preview preset"]', 'Current Santa zone');
    const previewTime = await page.$eval('input[aria-label="Simulated UTC time"]', el => el.value);
    const utcNow = new Date();
    assert.ok(Date.parse(previewTime + 'Z') >= Date.UTC(2026, 11, 24, 10));
    assert.ok(Date.parse(previewTime + 'Z') < Date.UTC(2026, 11, 25, 11));
    const shownMinutes = Number(previewTime.slice(11, 13)) * 60 + Number(previewTime.slice(14, 16));
    const nowMinutes = utcNow.getUTCHours() * 60 + utcNow.getUTCMinutes();
    assert.ok((nowMinutes - shownMinutes + 1440) % 1440 <= 1, 'preview follows the current UTC minute');
    assert.equal(await page.$eval('input[aria-label="Clock speed"]', el => el.value), '1');
    await page.goto(base);
    assert.equal(await page.$$('canvas').then(x=>x.length), 0);
    const fireworksURL = base + '/?pdk-festive-test=1&pdk-festive-effect=fireworks&pdk-festive-speed=0&pdk-festive-zone=Asia%2FKathmandu&pdk-festive-time=';
    for (const [instant, expected] of [
      ['2026-12-31T18:14:59Z', false], ['2026-12-31T18:15:00Z', true],
      ['2026-12-31T20:15:00Z', true], ['2027-01-01T06:15:00Z', true],
      ['2027-01-01T18:14:59Z', true], ['2027-01-01T18:15:00Z', false]
    ]) {
      await page.goto(fireworksURL + encodeURIComponent(instant));
      assert.equal((await state()).active, expected);
      assert.equal(await page.$eval('.pdk-festive-toggle', el => !el.hidden), expected);
      assert.equal(await page.$eval('.pdk-festive-speaker', el => !el.hidden), expected);
    }
    await page.goto(fireworksURL + encodeURIComponent('2026-12-31T18:15:00Z'));
    assert.equal((await state()).sound, false);
    assert.equal(await page.$eval('.pdk-festive-toggle svg', el => el.getAttribute('stroke')), 'currentColor');
    await page.click('.pdk-festive-speaker');
    await page.waitForFunction(() => JSON.parse(document.querySelector('canvas').dataset.snapshot).sound);
    await page.click('.pdk-festive-speaker');
    assert.equal((await state()).sound, false);
    assert.equal(await page.$$('select[aria-label="Fireworks style"]').then(els => els.length), 0);
    await page.click('button[aria-label="Launch a test firework"]');
    const rotation = await page.evaluate(() => {
      const step = document.querySelector('button[aria-label="Advance fireworks one frame"]');
      const shows = [], scenes = new Set(), ground = new Set();
      for (let i = 0; i < 18000; i++) {
        step.click();
        if (i % 30 === 0) {
          const state = JSON.parse(document.querySelector('canvas').dataset.snapshot);
          if (shows.at(-1) !== state.show) shows.push(state.show);
          state.groundEffects.forEach(style => ground.add(style));
          if (state.drone) {
            scenes.add(state.drone);
            if (state.rockets || state.sparks || state.groundEffects.length) throw Error('fireworks overlap drones');
            if (state.drone !== 'Happy New Year' && state.droneDepthLevels < 10) throw Error('formation must have volumetric depth');
          }
          if (state.sparks > 1400 || state.groundEffects.length > 3 || state.rockets > 5) throw Error('particle budget exceeded');
          if (new Set(state.groundEffects).size > 1) throw Error('ground styles overlap');
        }
      }
      return {shows, scenes:[...scenes], ground:[...ground]};
    });
    assert.deepEqual(rotation.shows.slice(0,3), ['fireworks','drones','fireworks']);
    assert.deepEqual(rotation.scenes, ['Happy New Year','Bird','Deer','Dolphin','Butterfly','Heart','Star','Globe','Tree','Flower']);
    assert.ok(rotation.ground.length > 0);
    for (const enabled of [true, false]) {
      await page.evaluate(enabled => {
        const marker = document.createElement('span');
        marker.dataset.pdkFestive = JSON.stringify({enabled:true, effect:'fireworks', drone:enabled});
        document.body.append(marker);
        window.refresh();
      }, enabled);
      const result = await page.evaluate(() => {
        const step = document.querySelector('button[aria-label="Advance fireworks one frame"]');
        let sawDrones = false, laterFireworks = false;
        for (let i = 0; i < 9000; i++) {
          step.click();
          if (i % 30 === 0) {
            const state = JSON.parse(document.querySelector('canvas').dataset.snapshot);
            sawDrones ||= state.show === 'drones';
            if (i > 8000 && (state.rockets || state.sparks || state.groundEffects.length)) laterFireworks = true;
          }
        }
        return {sawDrones, laterFireworks};
      });
      assert.equal(result.sawDrones, enabled);
      if (!enabled) assert.ok(result.laterFireworks, 'fireworks continue beyond the drone transition');
      await page.evaluate(() => document.querySelector('[data-pdk-festive]').remove());
    }
    await page.emulateMediaType('print');
    assert.equal(await page.$eval('.pdk-festive-speaker', el => getComputedStyle(el).display), 'none');
    await page.emulateMediaType('screen');
    await page.emulateMediaFeatures([{name:'prefers-reduced-motion', value:'no-preference'}]);
    await page.evaluate(() => localStorage.removeItem('pdk-festive'));
    await page.goto(base + '/?pdk-festive-snow=true');
    assert.equal(await page.$('canvas'), null, 'public presets require opt-in');
    await page.goto(base + '/enabled?pdk-festive-snow=true');
    assert.equal((await state()).destination, undefined);
    await page.evaluate(() => {
      history.pushState(null, '', '?pdk-festive-santa=true');
      window.PdkFestive.refresh();
    });
    assert.ok((await state()).destination, 'the sleigh preset works after instant navigation');
    assert.equal(await page.$('.pdk-festive-preview'), null);
    await page.goto(base + '/enabled?pdk-festive-drone=true');
    await page.waitForFunction(() => JSON.parse(document.querySelector('canvas').dataset.snapshot).show === 'drones');
    assert.equal(await page.$eval('.pdk-festive-speaker', el => el.hidden), true);
    await page.click('button[aria-label="Pause drone display"]');
    await page.reload();
    assert.equal((await state()).paused, true);
    await page.evaluate(() => localStorage.removeItem('pdk-festive'));
    for (const preset of ['fireworks', 'fireworks-drone']) {
      await page.goto(base + '/enabled?pdk-festive-' + preset + '=true');
      assert.equal((await state()).active, true);
      assert.equal((await state()).show, 'fireworks');
      assert.equal((await state()).sound, false);
      assert.equal(await page.$('input[aria-label="Simulated UTC time"]'), null);
    }
    const customURL = base + '/custom?pdk-festive-test=1&pdk-festive-speed=0&pdk-festive-zone=Asia%2FKathmandu&pdk-festive-time=';
    for (const [instant, active] of [['2026-12-30T18:15:00Z', true], ['2026-12-30T20:15:00Z', false]]) {
      await page.goto(customURL + encodeURIComponent(instant));
      assert.equal((await state()).active, active);
      assert.equal(await page.$eval('.pdk-festive-speaker', el => el.hidden), true);
      assert.equal(await page.$eval('.pdk-festive-controls', el => el.dataset.position), 'bottom-left');
    }
    console.log('Passed seasonal boundaries, public presets, saved controls, palette, navigation, mobile, print and fireworks/drone rotation.');
  } finally { await browser.close(); server.close(); }
})().catch(error => {console.error(error); server.close(); process.exitCode=1;});

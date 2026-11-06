// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT
// Run with node tools/browser-test/carousel.cjs /path/to/chrome [evidence-dir].
// Self-contained fixtures: no external sites, scripts or user browser profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require('puppeteer-core');
const root = path.resolve(__dirname, '../..');
const script = fs.readFileSync(path.join(root, 'docs/javascripts/pdk.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'docs/stylesheets/pdk.css'), 'utf8');
const evidence = process.argv[3];
const fixture = (count, extra = '', prefix = 'card') => `<div class="grid cards pdk-carousel" data-carousel-label="Resources" ${extra}><ul>${Array.from({length: count}, (_, i) => `<li id="${prefix}-${i + 1}"><p><strong>Resource ${i + 1}</strong></p><p>Card ${i + 1} content for reading and printing.${i === 2 ? " A longer card checks that every card keeps an equal height throughout the loop, including cards outside the current window." : ""}</p><a href="#target-${i}">Read resource ${i + 1}</a></li>`).join('')}</ul></div>`;
(async () => {
  const browser = await puppeteer.launch({executablePath: process.argv[2], headless: true, args: ['--no-sandbox']});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    async function load(html, enhance = true) {
      await page.goto('about:blank');
      await page.setViewport({width: 1050, height: 900, hasTouch: true});
      await page.setContent(`<style>:root {--md-typeset-color:#222;--md-default-bg-color:white;--md-accent-fg-color:#005a9c}html{background:white;color:#222}body{font:18px sans-serif;margin:40px;background:white;color:#222}*{box-sizing:border-box}.grid{max-width:900px}.grid.cards>ul{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;list-style:none;padding:0}.grid.cards>ul>li{padding:16px;border:1px solid #aaa;border-radius:4px}a{color:#005a9c}${css}</style><main class="md-typeset"><h1>Card carousel verification</h1>${html}</main>`);
      await page.evaluate(() => {
        window.timers = new Map(); window.serial = 0;
        window.setInterval = callback => { const id = ++window.serial; window.timers.set(id, callback); return id; };
        window.clearInterval = id => window.timers.delete(id);
        window.document$ = {subscribe(callback) { window.navigate = callback; }};
      });
      if (enhance) await page.addScriptTag({content: script});
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    }
    async function state() {
      return page.evaluate(() => {
        const container = document.querySelector('.pdk-carousel');
        return {
          visible: Array.from(container.querySelectorAll(':scope > ul > li:not([data-pdk-carousel-clone])')).filter(c => c.getAttribute('aria-hidden') !== 'true').sort((a,b) => +a.style.order - +b.style.order).map(c => c.id),
          total: container.querySelectorAll(':scope > ul > li:not([data-pdk-carousel-clone])').length,
          timers: window.timers.size,
          controls: container.querySelectorAll('.pdk-carousel-controls').length,
        };
      });
    }
    async function next(direction = 1) {
      await page.evaluate(d => document.querySelector(`.pdk-carousel-controls button:nth-child(${d === 1 ? 2 : 1})`).click(), direction);
      await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    }
    for (const count of [1, 2, 3, 5, 10, 25]) {
      await load(fixture(count, 'data-carousel-duration="0"'));
      assert.equal((await state()).total, count);
      assert.equal((await state()).visible.length, Math.min(3, count));
      await page.evaluate(() => { window.navigate(); window.navigate(); });
      assert.equal((await state()).controls, 1, 'idempotent initialization');
      for (let i = 0; i < count * 2; i++) {
        await next();
        const start = count <= 3 ? 0 : (i + 1) % count;
        assert.deepEqual((await state()).visible, Array.from({length: Math.min(3, count)}, (_, k) => `card-${(start + k) % count + 1}`));
      }
      await next(-1);
      assert.equal((await state()).visible[0], `card-${count <= 3 ? 1 : count}`);
      assert.equal(await page.evaluate(() => { const ids = Array.from(document.querySelectorAll('[id]'), el => el.id); return ids.length === new Set(ids).size; }), true, 'no duplicate IDs in edge copies');
      await page.evaluate(() => {
        const root = document.querySelector('.pdk-carousel');
        root.style.width = '260px';
        window.resized = false;
        new ResizeObserver(() => { window.resized = true; }).observe(root);
      });
      await page.waitForFunction(() => window.resized && document.querySelectorAll('.pdk-carousel > ul > li:not([aria-hidden="true"]):not([data-pdk-carousel-clone])').length === 1);
      assert.equal((await state()).visible.length, 1);
    }
    for (const count of [1, 2, 3, 5, 10, 25]) {
      for (const peek of [false, true]) {
        await load(fixture(count, `data-carousel-loop="false" data-carousel-peek="${peek}" data-carousel-badges="true" data-carousel-duration="0"`));
        const visible = (await state()).visible.length;
        const last = Math.max(0, count - visible);
        assert.equal(await page.$eval('.pdk-carousel-previous', el => el.disabled), true);
        assert.equal(await page.$$eval('[data-pdk-carousel-clone]', els => els.length), 0, 'finite mode has no wrapped copies');
        for (let i = 0; i < count + 2; i++) {
          await next();
          const start = Math.min(i + 1, last);
          assert.deepEqual((await state()).visible, Array.from({length:visible}, (_, k) => `card-${start+k+1}`));
        }
        assert.equal(await page.$eval('.pdk-carousel-next', el => el.disabled), true);
        const box = await page.$eval('.pdk-carousel > ul > li:not([aria-hidden="true"]) p', el => {const r=el.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};});
        await page.mouse.move(box.x, box.y); await page.mouse.down();
        await page.mouse.move(box.x-100, box.y, {steps:8}); await page.mouse.up();
        assert.equal((await state()).visible[0], `card-${last+1}`, 'drag cannot pass last window');
        await page.$eval('.pdk-carousel', el => el.focus());
        await page.keyboard.press('ArrowRight');
        assert.equal((await state()).visible[0], `card-${last+1}`, 'keyboard cannot pass last window');
        for (let i=0;i<count+2;i++) await next(-1);
        assert.equal((await state()).visible[0], 'card-1');
        await page.$eval('.pdk-carousel', el => el.focus());
        await page.keyboard.press('ArrowLeft');
        assert.equal((await state()).visible[0], 'card-1', 'keyboard cannot pass first window');
        assert.deepEqual(await page.$$eval('li:not([data-pdk-carousel-clone]) > .pdk-carousel-badge', els=>els.map(el=>el.textContent)), Array.from({length:count},(_,i)=>`${i+1}/${count}`));
      }
    }
    await load(fixture(5, 'data-carousel-loop="false" data-carousel-visible="2" data-carousel-peek="true" data-carousel-badges="true" data-carousel-duration="120"'));
    async function finitePreviews() {
      return page.$eval('.pdk-carousel', root=>{
        const viewport=root.getBoundingClientRect();
        return Array.from(root.querySelectorAll('li[aria-hidden="true"]'), card=>{
          const r=card.getBoundingClientRect();
          return Math.max(0,Math.min(r.right,viewport.right)-Math.max(r.left,viewport.left))/r.width;
        }).filter(ratio=>ratio>0);
      });
    }
    assert.ok((await finitePreviews()).length===1 && (await finitePreviews()).every(r=>Math.abs(r-.5)<.05),'only next half-card at first finite window');
    const firstBox=await page.$eval('#card-1 p',el=>{const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};});
    await page.mouse.move(firstBox.x,firstBox.y);await page.mouse.down();await page.mouse.move(firstBox.x+70,firstBox.y,{steps:8});
    const blockedTransform=await page.$eval('.pdk-carousel > ul',el=>new DOMMatrix(getComputedStyle(el).transform).m41);
    await page.mouse.up();
    assert.equal((await state()).visible[0],'card-1','drag cannot pass first finite window');
    assert.equal(await page.$eval('.pdk-carousel > ul',el=>new DOMMatrix(getComputedStyle(el).transform).m41),blockedTransform,'no overshoot at first boundary');
    const slide=await page.evaluate(async()=>{
      const root=document.querySelector('.pdk-carousel'),card=document.querySelector('#card-2');
      const initial=card.getBoundingClientRect().x;root.querySelector('.pdk-carousel-next').click();
      const animation=root.querySelector('ul').getAnimations()[0];animation.pause();animation.currentTime=60;
      const halfway=card.getBoundingClientRect().x;animation.currentTime=119;const end=card.getBoundingClientRect().x;
      animation.play();await animation.finished.catch(()=>{});await new Promise(r=>requestAnimationFrame(r));
      return {initial,halfway,end,committed:card.getBoundingClientRect().x};
    });
    assert.ok(slide.initial>slide.halfway && slide.halfway>slide.end && Math.abs(slide.end-slide.committed)<1,'finite animation commits without a jump');
    assert.equal((await finitePreviews()).length,2,'interior finite window shows both neighbours');
    const touch=await page.$eval('#card-2 p',el=>{const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};});
    await page.touchscreen.touchStart(touch.x,touch.y);await page.touchscreen.touchMove(touch.x-40,touch.y);
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(r)));
    await page.touchscreen.touchMove(touch.x-100,touch.y);await page.touchscreen.touchEnd();
    await page.waitForFunction(()=>!document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.equal((await state()).visible[0],'card-3','finite touch swipe advances');
    await next();
    assert.ok((await finitePreviews()).length===1 && (await finitePreviews()).every(r=>Math.abs(r-.5)<.05),'only previous half-card at final finite window');
    await load(fixture(18, 'data-carousel-visible="6" data-carousel-min-width="80" data-carousel-gap="8" data-carousel-duration="0"'));
    assert.equal((await state()).visible.length,6,'compact desktop cards can show six across');
    // Badges keep source identities through repeated wrapping and do not
    // duplicate the slide's accessible position announcement.
    for (const corner of ['top-left','top-right','bottom-left','bottom-right','invalid']) {
      await load(fixture(5, `data-carousel-badges="true" data-carousel-badge-corner="${corner}" data-carousel-duration="0" style="--pdk-carousel-badge-color:rgb(255,255,0);--pdk-carousel-badge-bg:rgba(10,20,30,0.8)"`));
      for(let i=0;i<7;i++) await next();
      const badge = await page.$eval('#card-3 > .pdk-carousel-badge', el=>{
        const r=el.getBoundingClientRect(), c=el.parentElement.getBoundingClientRect(), s=getComputedStyle(el);
        return {text:el.textContent, hidden:el.getAttribute('aria-hidden'), pointer:s.pointerEvents, color:s.color, bg:s.backgroundColor, left:r.left-c.left, right:c.right-r.right, top:r.top-c.top, bottom:c.bottom-r.bottom};
      });
      assert.equal(badge.text, '3/5'); assert.equal(badge.hidden,'true'); assert.equal(badge.pointer,'none');
      assert.equal(badge.color,'rgb(255, 255, 0)'); assert.equal(badge.bg,'rgba(10, 20, 30, 0.8)');
      assert.ok(badge[corner.endsWith('left')?'left':'right'] < 15);
      assert.ok(corner.startsWith('bottom') ? badge.bottom > 30 && badge.bottom < 50 : badge.top < 15, 'bottom badges clear the arrow row');
      const link = await page.$eval('#card-3 a', el=>{const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};});
      await page.evaluate(()=>{window.linkClicks=0;document.querySelector('#card-3 a').addEventListener('click',e=>{e.preventDefault();window.linkClicks++;});});
      await page.mouse.click(link.x,link.y);
      assert.equal(await page.evaluate(()=>window.linkClicks),1,'badge preserves links');
      await page.emulateMediaType('print');
      assert.equal(await page.$eval('.pdk-carousel-badge',el=>getComputedStyle(el).display),'none');
      const printed = await page.$$eval('li:not([data-pdk-carousel-clone])', els=>els.map(el=>el.getBoundingClientRect().top));
      assert.ok(printed.every((top,i)=>i<3||top>printed[i-3]),'badged print rows follow source order');
      assert.ok(Math.abs(printed[0]-printed[1])<1 && Math.abs(printed[1]-printed[2])<1,'badged cards print three across');
      await page.emulateMediaType('screen');
      await page.evaluate(()=>{window.removed=document.querySelector('.pdk-carousel');window.removed.remove();window.navigate();});
      assert.equal(await page.evaluate(()=>window.removed.querySelectorAll('.pdk-carousel-badge').length),0,'teardown removes generated badges');
      await page.evaluate(()=>{document.querySelector('main').append(window.removed);window.navigate();});
      assert.equal(await page.$$eval('li:not([data-pdk-carousel-clone]) > .pdk-carousel-badge', els=>els.length),5,'restore does not duplicate badges');
    }
    await load(fixture(5, 'data-carousel-loop="false" data-carousel-badges="true" data-carousel-autoplay="true" data-carousel-duration="0"'));
    await page.mouse.move(0,0);
    for(let i=0;i<4;i++) await page.evaluate(()=>Array.from(window.timers.values()).forEach(callback=>callback()));
    assert.deepEqual((await state()).visible,['card-3','card-4','card-5']);
    assert.equal((await state()).timers,0,'finite autoplay stops at end');
    assert.equal(await page.$eval('.pdk-carousel-toggle',el=>el.disabled),true);
    await next(-1);
    assert.equal((await state()).timers,1,'finite autoplay can run again after navigating back');
    await next();
    await page.$eval('.pdk-carousel',el=>el.style.width='260px');
    await page.waitForFunction(()=>document.querySelectorAll('.pdk-carousel li:not([aria-hidden="true"])').length===1);
    assert.equal((await state()).visible[0],'card-3');
    await next(); await next();
    assert.equal((await state()).visible[0],'card-5');
    await page.$eval('.pdk-carousel',el=>el.style.width='900px');
    await page.waitForFunction(()=>document.querySelectorAll('.pdk-carousel li:not([aria-hidden="true"])').length===3);
    assert.deepEqual((await state()).visible,['card-3','card-4','card-5'],'resize clamps finite window');
    assert.equal((await state()).timers,0);
    if(evidence) await page.screenshot({path:path.join(evidence,'carousel-finite-badges.png'),fullPage:true});
    const countries = ['united-kingdom', 'france', 'italy', 'japan', 'germany', 'australia'];
    const countryCards = countries.map((name, index) => {
      const image = fs.readFileSync(path.join(root, 'docs/assets/carousel', `${name}.jpg`)).toString('base64');
      return `<li id="country-${index}"><a href="#country-${index}"><img class="pdk-carousel-image" src="data:image/jpeg;base64,${image}" width="640" height="426" alt="${name}">${name}</a></li>`;
    }).join('');
    await load(`<div class="grid cards pdk-carousel" style="width:650px" data-carousel-visible="3" data-carousel-min-width="160" data-carousel-gap="8" data-carousel-image-fill="true"><ul>${countryCards}</ul></div>`);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('img')).every(image => image.complete && image.naturalWidth === 640));
    assert.equal((await state()).visible.length, 3, 'compact country cards show three across');
    const tileGeometry = await page.evaluate(() => {
      const first = document.querySelector('#country-0').getBoundingClientRect();
      const second = document.querySelector('#country-1').getBoundingClientRect();
      const image = document.querySelector('#country-0 img').getBoundingClientRect();
      return {gap: second.left-first.right, left: image.left-first.left, right:first.right-image.right};
    });
    assert.ok(Math.abs(tileGeometry.gap-8) < 0.5, 'configurable small gap');
    assert.ok(tileGeometry.left <= 1.5 && tileGeometry.right <= 1.5, 'photos fill the card edge to edge');
    const countryImage = await page.$eval('#country-0 img', el => { const r = el.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; });
    await page.evaluate(() => { window.countryClicks = 0; document.querySelector('#country-0 a').addEventListener('click', event => { event.preventDefault(); window.countryClicks++; }); });
    await page.mouse.click(countryImage.x, countryImage.y);
    assert.equal(await page.evaluate(() => window.countryClicks), 1, 'clicking a linked photo preserves activation');
    await page.mouse.move(countryImage.x, countryImage.y);
    await page.mouse.down();
    await page.mouse.move(countryImage.x - 100, countryImage.y, {steps:8});
    await page.mouse.up();
    await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.equal((await state()).visible[0], 'country-1', 'dragging a linked photo moves cards');
    assert.equal(await page.evaluate(() => window.countryClicks), 1, 'drag does not activate the photo link');
    if (evidence) await page.screenshot({path:path.join(evidence, 'carousel-countries.png'), fullPage:true});
    await load(fixture(5, 'data-carousel-peek="true" data-carousel-visible="2" data-carousel-position="false"'));
    assert.equal((await state()).visible.length, 2);
    assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector('.pdk-carousel-position')).display), 'none', 'position label can be hidden');
    const dimensions = await page.evaluate(() => {
      const root = document.querySelector('.pdk-carousel');
      const viewport = root.getBoundingClientRect();
      const originals = Array.from(root.querySelectorAll('li:not([data-pdk-carousel-clone])'));
      const previews = Array.from(root.querySelectorAll('li[aria-hidden="true"]')).map(card => {
        const rect = card.getBoundingClientRect();
        return Math.max(0, Math.min(rect.right, viewport.right) - Math.max(rect.left, viewport.left)) / rect.width;
      }).filter(ratio => ratio > 0 && ratio < 0.99);
      return {heights: originals.map(card => card.getBoundingClientRect().height), previews,
        background: getComputedStyle(root.querySelector('button')).backgroundColor,
        color: getComputedStyle(root.querySelector('button')).color};
    });
    assert.ok(dimensions.heights.every(height => Math.abs(height - dimensions.heights[0]) < 1), 'all original cards have equal height');
    assert.equal(dimensions.previews.length, 2, 'both edges show previews');
    assert.ok(dimensions.previews.every(ratio => Math.abs(ratio - 0.5) < 0.05), 'half-card previews');
    assert.equal(dimensions.background, 'rgba(238, 238, 238, 0.75)');
    assert.equal(dimensions.color, 'rgb(0, 0, 0)');
    const motionCheck = await page.evaluate(async () => {
      const root = document.querySelector('.pdk-carousel');
      const list = root.querySelector('ul');
      const second = root.querySelector('#card-2');
      const initial = second.getBoundingClientRect().x;
      root.querySelector('.pdk-carousel-next').click();
      const animation = list.getAnimations()[0];
      animation.pause();
      animation.currentTime = 300;
      const halfway = second.getBoundingClientRect().x;
      animation.currentTime = 599;
      const end = second.getBoundingClientRect().x;
      animation.play();
      await animation.finished.catch(() => {});
      await new Promise(resolve => requestAnimationFrame(resolve));
      return {initial, halfway, end, committed: second.getBoundingClientRect().x};
    });
    assert.ok(motionCheck.initial > motionCheck.halfway && motionCheck.halfway > motionCheck.end, 'continuous sliding between positions');
    assert.ok(Math.abs(motionCheck.end - motionCheck.committed) < 1, 'no jump when committing the next window');
    await next(); await next(); await next(); await next();
    assert.deepEqual((await state()).visible, ['card-1', 'card-2'], 'peek window wraps');
    if (evidence) await page.screenshot({path:path.join(evidence, 'carousel-peek.png'), fullPage:true});
    await page.emulateMediaType('print');
    assert.equal(await page.evaluate(() => Array.from(document.querySelectorAll('[data-pdk-carousel-clone]')).every(card => getComputedStyle(card).display === 'none')), true, 'print excludes decorative buffers');
    const twoWidePrint = await page.$$eval('li:not([data-pdk-carousel-clone])', els=>els.map(el=>el.getBoundingClientRect().top));
    assert.ok(Math.abs(twoWidePrint[0]-twoWidePrint[1])<1 && twoWidePrint[2]>twoWidePrint[0], 'print retains two full cards per row without counting peek cards');

    await page.emulateMediaType('screen');
    await load(fixture(2, 'data-carousel-peek="true" data-carousel-visible="1"'));
    await next();
    assert.deepEqual((await state()).visible, ['card-2'], 'two-card preview works without duplicate IDs');
    await load(fixture(5), false);
    await page.evaluate(() => { window.ResizeObserver = undefined; });
    await page.addScriptTag({content: script});
    assert.equal((await state()).controls, 0, 'unsupported browser retains grid');
    assert.equal((await state()).visible.length, 5);
    await load(fixture(5, 'data-carousel-badges="true"'), false);
    await page.evaluate(() => { window.ResizeObserver = class { observe() { throw Error('fixture failure'); } disconnect() {} }; });
    await page.addScriptTag({content: script});
    assert.equal((await state()).controls, 0, 'failed initialization rolls back enhancement');
    assert.equal((await state()).visible.length, 5);
    assert.equal(await page.$$eval('.pdk-carousel-badge', els=>els.length), 0, 'failed enhancement rolls back badges');
    assert.equal(await page.evaluate(() => document.querySelectorAll('[inert], [role="region"]').length), 0);
    await load(fixture(5).replace('<p><strong>Resource 1</strong></p>', '<p id="input-label">Resource 1</p><input id="choice" name="choice" aria-labelledby="input-label" type="checkbox" checked><svg width="20" height="20"><defs><linearGradient id="shade"><stop stop-color="blue"/></linearGradient></defs><rect width="20" height="20" fill="url(#shade)"/></svg>'));
    assert.equal(await page.evaluate(() => Array.from(document.querySelectorAll('[data-pdk-carousel-clone] input')).every(input => input.disabled && !input.name)), true, 'buffer forms cannot submit duplicate values');
    assert.equal(await page.evaluate(() => {
      const ids = Array.from(document.querySelectorAll('[id]'), el => el.id);
      return ids.length === new Set(ids).size && Array.from(document.querySelectorAll('[data-pdk-carousel-clone] rect')).every(rect => rect.closest('svg').querySelector(`[id="${rect.getAttribute('fill').slice(5, -1)}"]`));
    }), true, 'nested IDs and SVG fragment references are remapped');
    await load(fixture(0));
    assert.equal((await state()).controls, 0);
    await load(fixture(5), false);
    assert.equal((await state()).visible.length, 5, 'no-JS fallback');
    await page.addScriptTag({content: script});
    await next(); await next(); await next(); await next();
    assert.deepEqual((await state()).visible, ['card-5', 'card-1', 'card-2']);
    assert.equal(await page.evaluate(() => document.querySelector('#card-3').inert), true);
    await page.evaluate(() => document.querySelector('.pdk-carousel-controls button').focus());
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.deepEqual((await state()).visible, ['card-1', 'card-2', 'card-3']);
    await page.evaluate(() => document.querySelector('#card-1 a').focus());
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.deepEqual((await state()).visible, ['card-1', 'card-2', 'card-3'], 'preserve card-link keyboard handling');
    await page.evaluate(() => {
      document.querySelector('.pdk-carousel').style.width = '260px';
      document.querySelector('#card-3 a').focus();
    });
    await page.waitForFunction(() => document.querySelectorAll('.pdk-carousel > ul > li:not([aria-hidden="true"]):not([data-pdk-carousel-clone])').length === 1);
    assert.equal((await state()).visible[0], 'card-3', 'resize preserves focused card');
    const dragBox = await page.$eval('.pdk-carousel > ul > li:not([aria-hidden="true"]) p', el => { const r = el.getBoundingClientRect(); return {x:r.x + r.width / 2, y:r.y + r.height / 2}; });
    await page.mouse.move(dragBox.x, dragBox.y);
    await page.mouse.down();
    await page.mouse.move(dragBox.x - 100, dragBox.y, {steps: 8});
    await page.mouse.up();
    await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.equal((await state()).visible[0], 'card-4', 'mouse drag advances');
    const touchBox = await page.$eval('.pdk-carousel > ul > li:not([aria-hidden="true"]) p', el => { const r = el.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; });
    await page.evaluate(() => { window.touchEvents = []; for (const type of ['pointerdown','pointermove','pointerup','pointercancel','lostpointercapture']) document.querySelector('.pdk-carousel').addEventListener(type, event => window.touchEvents.push([type,event.clientX,event.clientY])); });
    await page.touchscreen.touchStart(touchBox.x, touchBox.y);
    await page.touchscreen.touchMove(touchBox.x - 40, touchBox.y);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    await page.touchscreen.touchMove(touchBox.x - 80, touchBox.y);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    await page.touchscreen.touchMove(touchBox.x - 100, touchBox.y);
    await page.touchscreen.touchEnd();
    await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.equal((await state()).visible[0], 'card-5', 'touch swipe advances: ' + JSON.stringify(await page.evaluate(() => window.touchEvents)));
    await page.evaluate(() => document.querySelector('.pdk-carousel').style.width = '900px');
    await page.waitForFunction(() => document.querySelectorAll('.pdk-carousel > ul > li:not([aria-hidden="true"]):not([data-pdk-carousel-clone])').length === 3);
    if (evidence) {
      fs.mkdirSync(evidence, {recursive:true});
      await page.screenshot({path:path.join(evidence, 'carousel-screen.png'), fullPage:true});
    }
    await page.emulateMediaType('print');
    const printCards = await page.evaluate(() => Array.from(document.querySelectorAll('.pdk-carousel > ul > li:not([data-pdk-carousel-clone])'), card => ({id:card.id, top:card.getBoundingClientRect().top, height:card.getBoundingClientRect().height, display:getComputedStyle(card).display})));
    assert.equal(printCards.length, 5);
    printCards.forEach((card, i) => {
      assert.ok(card.height > 0 && card.display !== 'none');
      if (i>=3) assert.ok(card.top > printCards[i-3].top, 'print rows follow original source order');
      if (i%3) assert.ok(Math.abs(card.top-printCards[i-1].top)<1, 'print retains three cards per row');
    });
    assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector('.pdk-carousel-controls')).display), 'none');
    if (evidence) {
      await page.screenshot({path:path.join(evidence, 'carousel-print.png'), fullPage:true});
      await page.pdf({path:path.join(evidence, 'carousel-browser-print.pdf'), format:'A4', printBackground:true});
    }
    await page.emulateMediaType('screen');
    await load(fixture(7, 'data-carousel-autoplay="true" data-carousel-pause="false"'));
    assert.equal(await page.evaluate(() => document.querySelector('.pdk-carousel-toggle')), null, 'pause button can be hidden');
    await page.evaluate(() => document.querySelector('.pdk-carousel-next').focus());
    await page.keyboard.press('p');
    await page.evaluate(() => document.activeElement.blur());
    assert.equal((await state()).timers, 0, 'keyboard pause persists without a visible button');
    await page.evaluate(() => document.querySelector('.pdk-carousel-next').focus());
    await page.keyboard.press('p');
    await page.evaluate(() => document.activeElement.blur());
    assert.equal((await state()).timers, 1, 'keyboard resume works without a visible button');
    await load(fixture(7, 'data-carousel-autoplay="true" data-carousel-interval="4000"') + fixture(5, '', 'second'));
    assert.equal((await state()).timers, 1);
    await page.evaluate(() => { Array.from(window.timers.values()).forEach(callback => callback()); });
    await page.waitForFunction(() => !document.querySelector('.pdk-carousel').dataset.carouselMoving);
    assert.equal((await state()).visible[0], 'card-2');
    assert.equal(await page.evaluate(() => document.querySelector('.pdk-carousel-announcement').textContent), '', 'autoplay is not announced');
    await page.evaluate(() => document.querySelector('.pdk-carousel').dispatchEvent(new MouseEvent('mouseenter')));
    assert.equal((await state()).timers, 0);
    await page.evaluate(() => document.querySelector('.pdk-carousel').dispatchEvent(new MouseEvent('mouseleave')));
    assert.equal((await state()).timers, 1);
    await page.evaluate(() => document.querySelector('.pdk-carousel button').focus());
    assert.equal((await state()).timers, 0);
    await page.evaluate(() => document.activeElement.blur());
    assert.equal((await state()).timers, 1);
    await page.evaluate(() => document.querySelector('.pdk-carousel button:nth-child(3)').click());
    assert.equal((await state()).timers, 0, 'explicit pause persists');
    await page.evaluate(() => document.querySelector('.pdk-carousel button:nth-child(3)').click());
    assert.equal((await state()).timers, 1);
    await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
    await page.waitForFunction(() => window.timers.size === 0);
    await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'no-preference'}]);
    await page.waitForFunction(() => window.timers.size === 1);
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    assert.equal((await state()).timers, 0);
    await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
    assert.equal((await state()).timers, 1);
    assert.equal(await page.evaluate(() => document.querySelectorAll('.pdk-carousel')[1].querySelector('li').hidden), false, 'instances independent');
    await page.evaluate(() => {
      window.oldCarousel = document.querySelector('.pdk-carousel');
      window.oldCarousel.remove();
      window.navigate();
    });
    assert.equal((await state()).timers, 0, 'navigation clears old timer');
    assert.equal(await page.evaluate(() => window.oldCarousel.querySelectorAll('[hidden], [inert], .pdk-carousel-controls').length), 0, 'teardown restores original markup');
    await page.evaluate(() => { document.querySelector('main').append(window.oldCarousel); window.navigate(); });
    assert.equal((await state()).timers, 1, 'back navigation initializes restored markup');
    assert.deepEqual(errors, []);
    console.log('Carousel browser checks passed: counts, badges, finite boundaries, wrap, resize, focus, swipe, print, autoplay, reduced motion and navigation.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

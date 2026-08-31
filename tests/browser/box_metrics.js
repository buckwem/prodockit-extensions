// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const puppeteer = require(path.resolve(
  __dirname,
  "../../tools/mermaid/node_modules/puppeteer",
));

const [pageUrl, ...selectors] = process.argv.slice(2);
if (!pageUrl || selectors.length === 0) {
  throw new Error("usage: box_metrics.js PAGE-URL SELECTOR [SELECTOR ...]");
}

const browserCandidates = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "/usr/bin/google-chrome-stable",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium-browser",
  "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const executablePath = browserCandidates.find(candidate => fs.existsSync(candidate));
if (!executablePath) {
  throw new Error("Chrome or Chromium is not installed");
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath,
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({width: 1200, height: 900});
    await page.goto(pageUrl, {waitUntil: "domcontentloaded"});
    await page.evaluate(() => Promise.all(
      Array.from(document.images, image => image.decode()),
    ));
    const metrics = {};
    for (const selector of selectors) {
      await page.evaluate(candidate => {
        const element = document.querySelector(candidate);
        const block = element?.closest(".tabbed-block");
        const content = block?.parentElement;
        const tabbedSet = content?.closest(".tabbed-set");
        if (!block || !content || !tabbedSet) return;
        const blocks = Array.from(content.children).filter(
          child => child.classList.contains("tabbed-block"),
        );
        const input = Array.from(tabbedSet.children).filter(
          child => child.matches('input[type="radio"]'),
        )[blocks.indexOf(block)];
        if (input) input.checked = true;
      }, selector);
      metrics[selector] = await page.$eval(selector, element => {
        const rect = element.getBoundingClientRect();
        const content = document.createRange();
        content.selectNodeContents(element);
        const contentRect = content.getBoundingClientRect();
        return {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
          contentY: contentRect.y,
          contentHeight: contentRect.height,
          verticalAlign: getComputedStyle(element).verticalAlign,
        };
      });
    }
    process.stdout.write(JSON.stringify(metrics));
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});

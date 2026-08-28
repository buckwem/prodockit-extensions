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
      metrics[selector] = await page.$eval(selector, element => {
        const rect = element.getBoundingClientRect();
        return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
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

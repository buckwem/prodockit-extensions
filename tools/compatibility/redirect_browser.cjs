// Copyright (c) 2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT
"use strict";
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const puppeteer = require(process.env.PDK_COMPAT_PUPPETEER ||
  path.resolve(__dirname, "../mermaid/node_modules/puppeteer"));
const [directory, start, expected] = process.argv.slice(2);
const root = path.resolve(directory);
const server = http.createServer((request, response) => {
  let file = path.resolve(root, "." + decodeURIComponent(new URL(request.url, "http://localhost").pathname));
  if (file !== root && !file.startsWith(root + path.sep)) {
    response.writeHead(403).end(); return;
  }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  const types = {".js": "application/javascript", ".json": "application/json", ".css": "text/css", ".html": "text/html"};
  if (!fs.existsSync(file)) { response.writeHead(404).end(); return; }
  response.setHeader("Content-Type", types[path.extname(file)] || "application/octet-stream");
  fs.createReadStream(file).pipe(response);
});
(async () => {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await puppeteer.launch({headless: true,
      executablePath: process.env.PUPPETEER_EXECUTABLE_PATH, args: ["--no-sandbox"]});
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(String(error)));
    const origin = `http://127.0.0.1:${server.address().port}`;
    await page.goto(origin + "/" + start, {waitUntil: "domcontentloaded", timeout: 30000});
    try {
      await page.waitForFunction(target => location.pathname + location.hash === target,
        {timeout: 15000}, expected);
      if (errors.length) throw new Error(errors.join("\n"));
      console.log(JSON.stringify({url: page.url(), expected: origin + expected, errors}));
    } catch (error) {
      await page.screenshot({path: "browser-failure.png"});
      fs.writeFileSync("browser-failure.html", await page.content());
      throw error;
    }
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

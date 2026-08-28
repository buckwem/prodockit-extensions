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
  throw new Error("usage: rendered_text.js PAGE-URL SELECTOR [SELECTOR ...]");
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

function staticText(node, nodesById) {
  const own = node.role && node.role.value === "StaticText"
    ? [node.name.value]
    : [];
  const children = (node.childIds || []).flatMap(id =>
    staticText(nodesById.get(id), nodesById),
  );
  return own.concat(children);
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath,
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({width: 1440, height: 900});
    await page.goto(pageUrl, {waitUntil: "domcontentloaded"});

    const client = await page.createCDPSession();
    await client.send("Accessibility.enable");
    const document = await client.send("DOM.getDocument");
    const tree = await client.send("Accessibility.getFullAXTree");
    const nodesById = new Map(tree.nodes.map(node => [node.nodeId, node]));
    const rendered = {};

    for (const selector of selectors) {
      const target = await client.send("DOM.querySelector", {
        nodeId: document.root.nodeId,
        selector,
      });
      if (!target.nodeId) {
        throw new Error(`selector did not match: ${selector}`);
      }
      const described = await client.send("DOM.describeNode", {nodeId: target.nodeId});
      const accessibilityNode = tree.nodes.find(node =>
        node.backendDOMNodeId === described.node.backendNodeId,
      );
      if (!accessibilityNode) {
        throw new Error(`no accessibility node for: ${selector}`);
      }
      rendered[selector] = staticText(accessibilityNode, nodesById)
        .join("")
        .replace(/\s+/g, " ")
        .trim();
    }

    process.stdout.write(JSON.stringify(rendered));
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});

// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
// Drive the real patcher page in headless Chromium from a file:// URL, like a user would.
//   node patcher/test/ui_test.js STOCK_F3SYSTEM.BIN [page.html]
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args: ["--autoplay-policy=no-user-gesture-required"] }).catch(async () =>
    await chromium.launch());
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = []; page.on("pageerror", e => errors.push(e.message)); page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  const pagePath = require("path").resolve(process.argv[3] || require("path").join(__dirname, "../../dist/talking-f3-patcher.html"));
  await page.goto("file://" + pagePath);
  console.log("title:", await page.title());
  // wrong file first
  await page.setInputFiles("#stock", { name: "x.bin", mimeType: "application/octet-stream", buffer: Buffer.alloc(1000) });
  await page.waitForTimeout(500); console.log("wrong file ->", await page.textContent("#fileMsg"));
  await page.setInputFiles("#stock", process.argv[2]);
  await page.waitForFunction(() => !document.getElementById("build").disabled, null, { timeout: 30000 });
  console.log("right file ->", await page.textContent("#fileMsg"));
  await page.selectOption("#previewLang", "FR"); await page.click("#preview");
  await page.waitForFunction(() => document.getElementById("previewMsg").textContent.length > 0, null, { timeout: 60000 });
  console.log("preview ->", await page.textContent("#previewMsg"));
  const t0 = Date.now();
  await page.click("#build");
  await page.waitForSelector("a.save", { timeout: 600000 });
  console.log("build ->", (await page.textContent("#result")).trim().slice(0, 160), `(${((Date.now() - t0) / 1000).toFixed(0)} s)`);
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("a.save")]);
  await dl.saveAs("ui_out.BIN"); console.log("downloaded as", dl.suggestedFilename());
  console.log("errors:", errors);
  await browser.close();
})();

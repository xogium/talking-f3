// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
// Node end-to-end test of the patcher core: same code path as the web page.
const fs = require("fs"), path = require("path"), crypto = require("crypto");
globalThis.crypto = crypto.webcrypto; globalThis.atob = (s) => Buffer.from(s, "base64").toString("binary");
const P = require("../src/core.js");
const ROOT = path.join(__dirname, "..");
function readTree(dir, base = "") {
  const m = new Map();
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name), rel = base ? base + "/" + e.name : e.name;
    if (e.isDirectory()) for (const [k, v] of readTree(p, rel)) m.set(k, v); else m.set(rel, new Uint8Array(fs.readFileSync(p)));
  }
  return m;
}
(async () => {
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, "build/data.json")));
  const files = readTree(path.join(ROOT, "wasm/out/espeak-data"));
  const espeak = await P.loadEspeak(fs.readFileSync(path.join(ROOT, "wasm/out/f3speak.wasm")), files, (l) => {});
  const opus = await P.loadOpus(fs.readFileSync(path.join(ROOT, "wasm/out/f3opus.wasm")));
  const stock = new Uint8Array(fs.readFileSync(process.argv[2]));
  console.log("stock check:", await P.checkStock(data, stock) || "OK");
  const settings = Object.assign({}, data.defaults, { langs: (process.argv[4] || "EN,FR,DE,IT,ES,L5,L6").split(","), rates: {},
                                                    kbps: +(process.argv[5] || data.defaults.kbps) });
  console.log("quality", P.quality(settings.kbps).name, "| estimate", (P.estimateSize(data, settings) / 1048576).toFixed(2), "MB");
  const t0 = Date.now();
  const banks = await P.buildBanks(data, settings, espeak, opus, (d, t, n) => { if (d % 500 === 0 || d === t) console.log(`  ${d}/${t} ${n}`); });
  console.log("banks", (banks.length / 1048576).toFixed(2), "MB in", ((Date.now() - t0) / 1000).toFixed(1), "s");
  const img = P.buildImage(data, stock, banks, settings);
  fs.writeFileSync(process.argv[3], img);
  console.log("wrote", process.argv[3], "verified");
})().catch(e => { console.error("FAIL", e); process.exit(1); });

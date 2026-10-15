// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
// Measure seconds of speech per language with the patcher's own eSpeak at the default
// settings (300 words/min): written to build/dur300.json, read by export_data.py for the
// page's size estimate.   node patcher/test/measure_dur.js
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
  const espeak = await P.loadEspeak(fs.readFileSync(path.join(ROOT, "wasm/out/f3speak.wasm")), readTree(path.join(ROOT, "wasm/out/espeak-data")), () => {});
  const d = data.defaults, out = {};
  for (const lang of data.langs) {
    let n = 0;
    for (const c of lang.clips) if (!c.chime) for (const [v, t] of c.segs) n += espeak.synth(t, v, d.variant, d.rate, d.pitch).length;
    out[lang.key] = +(n / espeak.sampleRate).toFixed(1); console.log(lang.key, out[lang.key], "s");
  }
  fs.writeFileSync(path.join(ROOT, "build/dur300.json"), JSON.stringify(out));
})();

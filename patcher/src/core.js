// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
/* F3 talking-firmware patcher -- core (runs in the browser; also in Node for testing).
 * Builds a talking F3SYSTEM.BIN from the user's stock v2.20 file:
 *   1. synthesize every clip with espeak-ng (WebAssembly) using the chosen voice settings
 *   2. resample 22050 -> the bank rate (16 kHz; 24 kHz for 24 kbps and up; 8 kHz for 6 kbps), Opus-encode
 *      (libopus WebAssembly, 16 kbps by default, 10 ms frames)
 *   3. assemble one bank per language (same layout as tools/gen_flash_bank.py)
 *   4. place module + banks into the stock image, set the settings block, fix length,
 *      version and checksum, and verify the safety rules before handing the file out.
 * No network access: everything (code, data, voices) is inside the page. */
"use strict";

/* ------------------------------------------------------------------ WASI shim
 * Just enough of wasi_snapshot_preview1 for espeak-ng: a read-only in-memory file system
 * (files: Map "espeak-ng-data/phontab" -> Uint8Array), directory listing, clock, stdout. */
function makeWasi(files, log) {
  const E = { OK: 0, ACCES: 2, BADF: 8, INVAL: 28, NOENT: 44, NOTDIR: 54, NOSYS: 52 };
  const dirs = new Set([""]);
  for (const p of files.keys()) { const parts = p.split("/"); for (let i = 1; i < parts.length; i++) dirs.add(parts.slice(0, i).join("/")); }
  const fds = new Map([[0, { kind: "chr" }], [1, { kind: "chr" }], [2, { kind: "chr" }], [3, { kind: "dir", path: "", pre: true }]]);
  let nextFd = 4, mem = null, out = "";
  const view = () => new DataView(mem.buffer), u8 = () => new Uint8Array(mem.buffer);
  const str = (p, n) => new TextDecoder().decode(u8().subarray(p, p + n));
  const norm = (base, rel) => {
    const st = [];
    for (const s of (base ? base + "/" + rel : rel).split("/")) {
      if (!s || s === ".") continue; if (s === "..") st.pop(); else st.push(s);
    }
    return st.join("/");
  };
  const children = (d) => {
    const pre = d ? d + "/" : "", seen = new Map();
    for (const p of [...files.keys(), ...dirs]) {
      if (p === d || !p.startsWith(pre)) continue;
      const name = p.slice(pre.length).split("/")[0];
      if (name && !seen.has(name)) seen.set(name, dirs.has(pre + name) ? 3 : 4);
    }
    return [...seen.entries()];
  };
  const imp = {
    fd_prestat_get(fd, buf) { const f = fds.get(fd); if (!f || !f.pre) return E.BADF;
      view().setUint8(buf, 0); view().setUint32(buf + 4, 1, true); return E.OK; },
    fd_prestat_dir_name(fd, p, n) { u8()[p] = 47; return E.OK; },          // "/"
    fd_fdstat_get(fd, buf) { const f = fds.get(fd); if (!f) return E.BADF; const v = view();
      v.setUint8(buf, f.kind === "dir" ? 3 : f.kind === "file" ? 4 : 2); v.setUint16(buf + 2, 0, true);
      v.setBigUint64(buf + 8, 0xFFFFFFFFFFFFFFFFn, true); v.setBigUint64(buf + 16, 0xFFFFFFFFFFFFFFFFn, true); return E.OK; },
    fd_fdstat_set_flags() { return E.OK; },
    path_open(dirfd, dirflags, pp, pl, oflags, rb, ri, fdflags, outp) {
      const d = fds.get(dirfd); if (!d || d.kind !== "dir") return E.BADF;
      if (oflags & (1 | 4 | 8)) return E.ACCES;                              // creat/excl/trunc: read-only FS
      const path = norm(d.path, str(pp, pl));
      let f;
      if (files.has(path)) f = { kind: "file", data: files.get(path), pos: 0 };
      else if (dirs.has(path)) f = { kind: "dir", path };
      else return E.NOENT;
      if ((oflags & 2) && f.kind !== "dir") return E.NOTDIR;
      const fd = nextFd++; fds.set(fd, f); view().setUint32(outp, fd, true); return E.OK;
    },
    path_filestat_get(dirfd, flags, pp, pl, buf) {
      const d = fds.get(dirfd); if (!d) return E.BADF;
      const path = norm(d.path, str(pp, pl)), v = view();
      const isF = files.has(path), isD = dirs.has(path); if (!isF && !isD) return E.NOENT;
      for (let i = 0; i < 64; i += 8) v.setBigUint64(buf + i, 0n, true);
      v.setUint8(buf + 16, isD ? 3 : 4); v.setBigUint64(buf + 24, 1n, true);
      v.setBigUint64(buf + 32, BigInt(isF ? files.get(path).length : 0), true); return E.OK;
    },
    fd_read(fd, iovs, n, nread) {
      const f = fds.get(fd); if (!f) return E.BADF; const v = view(); let tot = 0;
      if (f.kind === "file") for (let i = 0; i < n; i++) {
        const p = v.getUint32(iovs + 8 * i, true), l = v.getUint32(iovs + 8 * i + 4, true);
        const chunk = f.data.subarray(f.pos, f.pos + l); u8().set(chunk, p); f.pos += chunk.length; tot += chunk.length;
        if (chunk.length < l) break;
      }
      v.setUint32(nread, tot, true); return E.OK;
    },
    fd_seek(fd, off, whence, outp) {
      const f = fds.get(fd); if (!f || f.kind !== "file") return E.BADF;
      const o = Number(off), base = whence === 0 ? 0 : whence === 1 ? f.pos : f.data.length;
      if (base + o < 0) return E.INVAL; f.pos = base + o; view().setBigUint64(outp, BigInt(f.pos), true); return E.OK;
    },
    fd_close(fd) { if (fd > 3) fds.delete(fd); return E.OK; },
    fd_readdir(fd, buf, len, cookie, usedp) {
      const f = fds.get(fd); if (!f || f.kind !== "dir") return E.BADF;
      const ents = [[".", 3], ["..", 3], ...children(f.path)], enc = new TextEncoder(); const v = view();
      let used = 0;
      for (let i = Number(cookie); i < ents.length; i++) {
        const name = enc.encode(ents[i][0]), hdr = new DataView(new ArrayBuffer(24));
        hdr.setBigUint64(0, BigInt(i + 1), true); hdr.setBigUint64(8, BigInt(i + 1), true);
        hdr.setUint32(16, name.length, true); hdr.setUint8(20, ents[i][1]);
        const rec = new Uint8Array(24 + name.length); rec.set(new Uint8Array(hdr.buffer)); rec.set(name, 24);
        const take = Math.min(rec.length, len - used); u8().set(rec.subarray(0, take), buf + used); used += take;
        if (used >= len) break;
      }
      v.setUint32(usedp, used, true); return E.OK;
    },
    fd_write(fd, iovs, n, nw) {
      const v = view(); let tot = 0;
      for (let i = 0; i < n; i++) { const p = v.getUint32(iovs + 8 * i, true), l = v.getUint32(iovs + 8 * i + 4, true); out += str(p, l); tot += l; }
      if (out.includes("\n")) { const lines = out.split("\n"); out = lines.pop(); lines.forEach(l => log && log(l)); }
      v.setUint32(nw, tot, true); return E.OK;
    },
    environ_sizes_get(c, s) { view().setUint32(c, 0, true); view().setUint32(s, 0, true); return E.OK; },
    environ_get() { return E.OK; },
    clock_time_get(id, prec, outp) { view().setBigUint64(outp, BigInt(Math.round(Date.now() * 1e6)), true); return E.OK; },
    path_remove_directory() { return E.ACCES; },
    path_unlink_file() { return E.ACCES; },
    proc_exit(code) { throw new Error("wasm exit " + code); },
  };
  return { imports: { wasi_snapshot_preview1: imp }, setMemory(m) { mem = m; } };
}

async function instantiate(bytes, files, log) {
  const w = makeWasi(files || new Map(), log);
  const { instance } = await WebAssembly.instantiate(bytes, w.imports);
  w.setMemory(instance.exports.memory);
  if (instance.exports._initialize) instance.exports._initialize();
  return instance.exports;
}

/* ------------------------------------------------------------------ espeak-ng */
async function loadEspeak(wasmBytes, files, log) {
  const e = await instantiate(wasmBytes, files, log);
  const cstr = (s) => { const b = new TextEncoder().encode(s + "\0"); const p = e.f3_alloc(b.length); new Uint8Array(e.memory.buffer).set(b, p); return p; };
  const call = (fn, s, ...a) => { const p = cstr(s); try { return fn(p, ...a); } finally { e.f3_free(p); } };
  const rate = call(e.f3_init, "/espeak-ng-data");
  if (rate <= 0) throw new Error("espeak-ng failed to start (" + rate + ")");
  let cur = "";
  return {
    sampleRate: rate,
    /* voice = "fr", variant = "michel" or "", speed in words/min, pitch 0..99 */
    synth(text, voice, variant, speed, pitch) {
      const v = variant ? voice + "+" + variant : voice;
      if (v !== cur) { if (call(e.f3_voice, v) !== 0) throw new Error("unknown voice " + v); cur = v; }
      e.f3_param(1, speed); e.f3_param(3, pitch);
      const n = call(e.f3_synth, text);
      if (n < 0) throw new Error("espeak-ng error " + n);
      return new Int16Array(e.memory.buffer, e.f3_buf(), n).slice();
    },
  };
}

/* ------------------------------------------------------------------ Opus encoder */
async function loadOpus(wasmBytes) {
  const e = await instantiate(wasmBytes);
  return {
    /* mono PCM at `rate` (8000/16000/24000) -> [u8 len][packet]... ; 10 ms frames, last frame zero-padded */
    encode(pcm, rate, bitrate, music) {
      const enc = e.op_enc_new(rate, bitrate, music ? 1 : 0); if (!enc) throw new Error("opus encoder");
      const FR = rate / 100, inP = e.op_alloc(FR * 2), outP = e.op_alloc(1500), parts = []; let total = 0;
      try {
        for (let i = 0; i < pcm.length; i += FR) {
          const fr = new Int16Array(FR); fr.set(pcm.subarray(i, Math.min(i + FR, pcm.length)));
          new Int16Array(e.memory.buffer, inP, FR).set(fr);
          const n = e.op_encode(enc, inP, FR, outP, 1500);
          if (n <= 0 || n > 255) throw new Error("opus packet length " + n);
          const pk = new Uint8Array(n + 1); pk[0] = n; pk.set(new Uint8Array(e.memory.buffer, outP, n), 1);
          parts.push(pk); total += n + 1;
        }
      } finally { e.op_free(inP); e.op_free(outP); e.op_enc_free(enc); }
      const out = new Uint8Array(total); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; }
      return out;
    },
    /* [u8 len][packet]... -> PCM at `rate` (what the F3 will play) */
    decode(data, rate) {
      const dec = e.op_dec_new(rate); if (!dec) throw new Error("opus decoder");
      const inP = e.op_alloc(256), outP = e.op_alloc(960 * 2), parts = []; let total = 0;
      try {
        for (let i = 0; i < data.length; ) {
          const L = data[i]; new Uint8Array(e.memory.buffer, inP, L).set(data.subarray(i + 1, i + 1 + L)); i += 1 + L;
          const n = e.op_decode(dec, inP, L, outP, 960);
          if (n > 0) { parts.push(new Int16Array(e.memory.buffer, outP, n).slice()); total += n; }
        }
      } finally { e.op_free(inP); e.op_free(outP); e.op_dec_free(dec); }
      const out = new Int16Array(total); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; }
      return out;
    },
  };
}

/* ------------------------------------------------------------------ resampler
 * 22050 -> 16000 Hz (= 441 -> 320), polyphase windowed-sinc (Blackman, 64 taps), cut-off
 * 7.2 kHz. Deterministic, no Web Audio needed. Generic rates fall back to the same kernel. */
const _rsCache = new Map();
function resample(input, inRate, outRate) {
  const g = (a, b) => b ? g(b, a % b) : a, d = g(inRate, outRate), up = outRate / d, down = inRate / d;
  const half = 32, taps = 2 * half, fc = 0.45 * outRate / inRate * 2, key = up + "/" + down;
  let tab = _rsCache.get(key);
  if (!tab) {                                     // tab[phase*taps + j], phase = output index mod up
    tab = new Float32Array(up * taps);
    for (let ph = 0; ph < up; ph++) {
      const frac = (ph * down) / up - Math.floor((ph * down) / up); let sum = 0;
      for (let j = 0; j < taps; j++) {
        const x = (j - half + 1) - frac;
        const s = x === 0 ? fc : Math.sin(Math.PI * fc * x) / (Math.PI * x);
        const w = 0.42 + 0.5 * Math.cos(Math.PI * x / half) + 0.08 * Math.cos(2 * Math.PI * x / half);
        tab[ph * taps + j] = s * w; sum += s * w;
      }
      for (let j = 0; j < taps; j++) tab[ph * taps + j] /= sum;   // unity DC gain
    }
    _rsCache.set(key, tab);
  }
  const n = Math.floor(input.length * up / down), out = new Int16Array(n), L = input.length;
  for (let i = 0; i < n; i++) {
    const c = Math.floor(i * down / up), ph = i % up, base = ph * taps, k0 = c - half + 1;
    let acc = 0;
    if (k0 >= 0 && k0 + taps <= L) for (let j = 0; j < taps; j++) acc += input[k0 + j] * tab[base + j];
    else for (let j = 0; j < taps; j++) { const k = k0 + j; if (k >= 0 && k < L) acc += input[k] * tab[base + j]; }
    const v = Math.round(acc); out[i] = v > 32767 ? 32767 : v < -32768 ? -32768 : v;
  }
  return out;
}

/* ------------------------------------------------------------------ bank assembly
 * Same layout as tools/gen_flash_bank.py assemble():
 * header 32 B | index nslots x {offset, nsamples} | clip data (4-aligned) | r0 | r1 */
const b64 = (s) => { const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; };
function assembleBank(lang, clipData, rate) {
  const ns = lang.nslots, offs = []; let size = 0;
  for (const [enc, n] of clipData) { offs.push([size, n]); size += enc.length; }
  const pad = (-size) & 3, r0 = b64(lang.r0), r1 = b64(lang.r1);
  const hashOff = 32 + ns * 8 + size + pad, lookOff = hashOff + ns * 2;
  const blob = new Uint8Array(lookOff + ns * 4), v = new DataView(blob.buffer);
  [0x58563346, 0x4B4E4142, rate || 16000, ns, 2, hashOff, lookOff, lang.L | (lang.year_style << 8)]
    .forEach((x, i) => v.setUint32(i * 4, x >>> 0, true));
  for (const [sid, ci] of lang.slots) { v.setUint32(32 + sid * 8, offs[ci][0], true); v.setUint32(36 + sid * 8, offs[ci][1], true); }
  let o = 32 + ns * 8; for (const [enc] of clipData) { blob.set(enc, o); o += enc.length; }
  blob.set(r0, hashOff); blob.set(r1, lookOff);
  return blob;
}

/* Sound quality: Opus bitrate and the bank's sample rate. 16 kHz keeps eSpeak's speech up to
 * 8 kHz; from 24 kbps the bank is 24 kHz (all of eSpeak's 11 kHz); 6 kbps is 8 kHz narrowband.
 * bps = bank bytes per second of speech (incl. packet lengths), the largest of EN/DE/JA measured
 * with this page's own eSpeak and encoder; speech seconds per language: data.json dur300. */
const QUALITIES = [
  { kbps: 6,  rate: 8000,  bps: 1086, name: "Smallest: 6 kbps, telephone quality" },
  { kbps: 8,  rate: 16000, bps: 1367, name: "Very small: 8 kbps" },
  { kbps: 12, rate: 16000, bps: 1775, name: "Small: 12 kbps" },
  { kbps: 16, rate: 16000, bps: 2235, name: "Standard: 16 kbps (recommended)" },
  { kbps: 24, rate: 24000, bps: 3496, name: "High: 24 kbps, wider sound" },
  { kbps: 32, rate: 24000, bps: 4429, name: "Higher: 32 kbps, wider sound" },
  { kbps: 48, rate: 24000, bps: 6291, name: "Highest: 48 kbps, wider sound" },
];
function quality(kbps) { return QUALITIES.find(q => q.kbps === kbps) || QUALITIES[3]; }
/* Estimated size of the voices (bytes) for the chosen languages, speeds and quality: speech
 * time scales with 300 / words per minute. Measured 0-5 % above the real build. */
function estimateSize(data, settings) {
  const q = quality(settings.kbps); let size = 0;
  for (const lang of data.langs) {
    if (!settings.langs.includes(lang.key)) continue;
    const wpm = (settings.rates && settings.rates[lang.key]) || settings.rate;
    const t = Math.max(300 / wpm, 0.07 + 0.93 * 300 / wpm);   /* fast rates shrink less (pauses, libsonic): measured at 900 */
    size += lang.dur300 * t * q.bps + lang.nslots * 14 + 16;
  }
  return size;
}
function voiceRoom() { return IMG.TRAILER - IMG.BANK_FILE; }   /* bytes available for the voices */
/* settings: { variant, pitch, rate (global), rates: {EN: 300,...} overrides, langs: ["EN",...],
 *             level, chime, kbps }  -> { banks: Uint8Array (all chosen languages, 16-byte aligned) } */
async function buildBanks(data, settings, espeak, opus, progress) {
  const chosen = data.langs.filter(l => settings.langs.includes(l.key));
  const total = chosen.reduce((a, l) => a + l.clips.length, 0); let done = 0;
  const q = quality(settings.kbps), ch = data.chime[q.rate];
  const chime = [b64(ch.enc), ch.nsamples];
  const parts = [];
  for (const lang of chosen) {
    const rate = (settings.rates && settings.rates[lang.key]) || settings.rate;
    const clipData = [];
    for (const c of lang.clips) {
      if (c.chime) clipData.push(chime);
      else {
        const pieces = c.segs.map(([voice, text]) => espeak.synth(text, voice, settings.variant, rate, settings.pitch));
        const len = pieces.reduce((a, p) => a + p.length, 0), pcm = new Int16Array(len); let o = 0;
        for (const p of pieces) { pcm.set(p, o); o += p.length; }
        const pcmQ = resample(pcm, espeak.sampleRate, q.rate);
        clipData.push([opus.encode(pcmQ, q.rate, q.kbps * 1000, false), pcmQ.length]);
      }
      if (++done % 25 === 0 || done === total) { progress && progress(done, total, lang.name); await new Promise(r => setTimeout(r, 0)); }
    }
    parts.push(assembleBank(lang, clipData, q.rate));
  }
  let size = 0; for (const p of parts) size += p.length + ((-p.length) & 15);
  const banks = new Uint8Array(size); let o = 0;
  for (const p of parts) { banks.set(p, o); o += p.length + ((-p.length) & 15); }
  return banks;
}

/* ------------------------------------------------------------------ image */
const IMG = { SIZE: 0x7FA300, CODE_START: 0x200300, CKSUM: 0x2002FC, LEN: 0x7FA2F8, VER: 0x7FA2FC,
  BOOT_END: 0x200200, HOOK_RT: 0x80010F3E, HOOK_FILE: 0x21123E, HOOK_ORIG: [0xa4, 0xf1, 0x40, 0x01],
  MODULE_FILE: 0x3C0000, GAP_END_RT: 0x801F4400, BANK_FILE: 0x400000, TRAILER: 0x7F9000 /* below the calibration sector at 0x7FA000 */, CFG_MAGIC: 0x47464356 };
const rt2file = (a) => a - 0x80000000 + IMG.CODE_START;

/* Thumb-2 B.W (encoding T4), same as arm/thumb_branch.py */
function thumbBW(src, dst) {
  const off = dst - (src + 4);
  if (off % 2 || off < -(1 << 24) || off >= (1 << 24)) throw new Error("branch out of range");
  const imm = off >>> 1 & 0xFFFFFF, S = imm >> 23 & 1, I1 = imm >> 22 & 1, I2 = imm >> 21 & 1;
  const J1 = (~I1 ^ S) & 1, J2 = (~I2 ^ S) & 1, imm10 = imm >> 11 & 0x3FF, imm11 = imm & 0x7FF;
  const h1 = 0xF000 | S << 10 | imm10, h2 = 0x9000 | J1 << 13 | J2 << 11 | imm11;
  return [h1 & 255, h1 >> 8, h2 & 255, h2 >> 8];
}

async function sha256hex(bytes) {
  if (globalThis.crypto && crypto.subtle) {
    try { const d = await crypto.subtle.digest("SHA-256", bytes);
          return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, "0")).join(""); } catch (e) { /* fall through */ }
  }
  return sha256js(bytes);                       // pages opened from disk may lack crypto.subtle
}
function sha256js(m) {
  const K = new Uint32Array([0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,
    0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,
    0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,
    0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,
    0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
  const H = new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
  const len = m.length, nb = ((len + 9 + 63) >> 6) << 6, buf = new Uint8Array(nb); buf.set(m); buf[len] = 0x80;
  const dv = new DataView(buf.buffer); dv.setUint32(nb - 4, (len * 8) >>> 0); dv.setUint32(nb - 8, Math.floor(len / 0x20000000));
  const W = new Uint32Array(64), r = (x, n) => (x >>> n) | (x << (32 - n));
  for (let o = 0; o < nb; o += 64) {
    for (let i = 0; i < 16; i++) W[i] = dv.getUint32(o + 4 * i);
    for (let i = 16; i < 64; i++) { const a = W[i-15], b = W[i-2];
      W[i] = (W[i-16] + (r(a,7) ^ r(a,18) ^ (a >>> 3)) + W[i-7] + (r(b,17) ^ r(b,19) ^ (b >>> 10))) >>> 0; }
    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (r(e,6) ^ r(e,11) ^ r(e,25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) >>> 0;
      const t2 = ((r(a,2) ^ r(a,13) ^ r(a,22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
  }
  return [...H].map(x => x.toString(16).padStart(8, "0")).join("");
}

/* Check the user's file is the stock v2.20 image this patch was made for. */
async function checkStock(data, stock) {
  if (stock.length !== data.stock.size) return "This file has the wrong size for an F3 firmware file (F3SYSTEM.BIN).";
  const ver = String.fromCharCode(...stock.subarray(IMG.VER, IMG.VER + 4));
  if (ver === "0221") return "This file is already a talking firmware. Please choose the original F3SYSTEM.BIN from Zoom (version 2.20).";
  if ((await sha256hex(stock)) !== data.stock.sha256)
    return "This is not the official Zoom F3 firmware version 2.20 that the patch was made for. Please download version 2.20 from zoomcorp.com and choose its F3SYSTEM.BIN.";
  return null;
}

function buildImage(data, stock, banks, settings) {
  const img = new Uint8Array(stock), v = new DataView(img.buffer), m = data.module, mod = b64(m.bin);
  if (!IMG.HOOK_ORIG.every((b, i) => img[IMG.HOOK_FILE + i] === b)) throw new Error("hook site not as expected");
  img.set(thumbBW(IMG.HOOK_RT, m.tramp), IMG.HOOK_FILE);
  if (m.end_rt > IMG.GAP_END_RT) throw new Error("module too large");
  const modEnd = Math.min((rt2file(m.end_rt) + 0xFFF) & ~0xFFF, rt2file(IMG.GAP_END_RT));
  img.fill(0, IMG.MODULE_FILE, modEnd); img.set(mod, IMG.MODULE_FILE);
  const c = rt2file(m.cfg_rt);
  if (v.getUint32(c, true) !== IMG.CFG_MAGIC) throw new Error("settings block not found");
  img[c + 4] = settings.level; img[c + 5] = settings.chime ? 1 : 0;
  v.setUint32(IMG.LEN, modEnd - IMG.CODE_START, true);
  if (IMG.BANK_FILE + banks.length > IMG.TRAILER) throw new Error("the voices are too large for the F3's memory -- choose fewer languages or a faster speech rate");
  img.set(banks, IMG.BANK_FILE);
  img.set([48, 50, 50, 49], IMG.VER);                                     // "0221"
  let sum = 0; for (let i = IMG.CODE_START; i < img.length; i++) sum = (sum + img[i]) >>> 0;
  v.setUint32(IMG.CKSUM, sum, false);
  verifyImage(stock, img);
  return img;
}

function verifyImage(stock, img) {
  if (img.length !== stock.length) throw new Error("size changed");
  for (let i = 0; i < IMG.BOOT_END; i++) if (img[i] !== stock[i]) throw new Error("BOOT region changed");
  let sum = 0; for (let i = IMG.CODE_START; i < img.length; i++) sum = (sum + img[i]) >>> 0;
  if (new DataView(img.buffer).getUint32(IMG.CKSUM, false) !== sum) throw new Error("checksum mismatch");
  const allowed = [[IMG.CKSUM, IMG.CKSUM + 4], [IMG.HOOK_FILE, IMG.HOOK_FILE + 4], [IMG.MODULE_FILE, rt2file(IMG.GAP_END_RT)],
                   [IMG.BANK_FILE, IMG.TRAILER], [IMG.LEN, IMG.LEN + 8]];
  for (let i = 0; i < img.length; i++)
    if (img[i] !== stock[i] && !allowed.some(([a, b]) => i >= a && i < b)) throw new Error("unexpected change at 0x" + i.toString(16));
  for (let i = 0x211242; i < 0x211282; i++) if (img[i] !== stock[i]) throw new Error("audio loop changed");
}

const F3Patcher = { QUALITIES, quality, estimateSize, voiceRoom, sha256js, makeWasi, loadEspeak, loadOpus, resample, assembleBank, buildBanks, checkStock, buildImage, verifyImage, thumbBW, b64 };
if (typeof module !== "undefined") module.exports = F3Patcher; else globalThis.F3Patcher = F3Patcher;

#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Export everything the web patcher needs that does not depend on the user's choices:
per-language bank plans (unique clips as espeak-ng segments, slot map, hash tables), the
pre-encoded startup chime, the voice module and its addresses, the stock-image check.
  python3 patcher/export_data.py STOCK_F3SYSTEM.BIN  -> patcher/build/data.json"""
import sys, os, json, base64, hashlib, subprocess, struct
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_flash_bank as g

def sym(elf, name):
    for line in subprocess.check_output(["arm-none-eabi-nm", elf], text=True).splitlines():
        p = line.split()
        if len(p) >= 3 and p[2] == name: return int(p[0], 16)
    raise SystemExit(f"{name} not in {elf}")

def dur300(key):
    """Seconds of speech in a language at 300 words/min, for the patcher's size estimate:
    measured with the patcher's own eSpeak (patcher/test/measure_dur.js -> build/dur300.json)
    when available, else from the reference bank in build/banks/<key> (tools/gen_all_banks.sh;
    the PC eSpeak speaks ~5% longer, so that estimate errs on the large side)."""
    m = os.path.join(HERE, "build", "dur300.json")
    if os.path.exists(m):
        d = json.load(open(m))
        if key in d: return d[key]
    b = open(os.path.join(ROOT, "build", "banks", key, "flash_bank.bin"), "rb").read()
    rate, ns = struct.unpack_from("<I", b, 8)[0], struct.unpack_from("<I", b, 12)[0]
    clips = {}
    for i in range(ns):
        o, n = struct.unpack_from("<II", b, 32 + i * 8)
        if n: clips[o] = n
    return round(sum(clips.values()) / rate, 1)

def main():
    stock = open(sys.argv[1], "rb").read()
    b64 = lambda b: base64.b64encode(b).decode()
    names = {"EN": "English", "FR": "Français", "DE": "Deutsch", "IT": "Italiano",
             "ES": "Español", "L5": "简体中文 (Chinese)", "L6": "日本語 (Japanese)"}
    langs = []
    for key in ["EN", "FR", "DE", "IT", "ES", "L5", "L6"]:
        p = g.bank_plan(key)
        langs.append({"key": key, "name": names[key], "L": p["L"], "year_style": p["year_style"],
                      "nslots": p["nslots"], "clips": p["clips"],
                      "slots": sorted((sid, e["clip"]) for sid, e in p["slots"].items()),
                      "r0": b64(p["r0"]), "r1": b64(p["r1"]), "dur300": dur300(key)})
    chime = {}                                       # one per bank rate (see QUALITIES in core.js)
    for rate in (8000, 16000, 24000):
        pcm = g.chime_pcm(rate)
        chime[rate] = {"enc": b64(g.opus_encode(pcm, 32, 10, music=True, rate=rate)), "nsamples": len(pcm)}
    elf = os.path.join(ROOT, "arm", "voice.elf")
    module = {"bin": b64(open(os.path.join(ROOT, "arm", "voice.bin"), "rb").read()),
              "end_rt": sym(elf, "_end"), "tramp": sym(elf, "tramp_audio_out"), "cfg_rt": sym(elf, "g_cfg")}
    data = {"format": 1, "stock": {"size": len(stock), "sha256": hashlib.sha256(stock).hexdigest(),
                                   "version": "2.20"},
            "module": module, "chime": chime, "langs": langs,
            "defaults": {"variant": "michel", "pitch": 50, "rate": 300, "level": 13, "chime": True, "switchStartOnly": False, "kbps": 16}}
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    out = os.path.join(HERE, "build", "data.json")
    json.dump(data, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
    print(out, os.path.getsize(out), "bytes;", sum(len(l["clips"]) for l in langs), "clips")

if __name__ == "__main__": main()

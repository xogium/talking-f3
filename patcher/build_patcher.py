#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Assemble the single-file web patcher: dist/talking-f3-patcher.html
Inlines src/core.js, build/data.json (from export_data.py), the two WebAssembly modules and the
espeak-ng data subset (from wasm/build_wasm.sh). The result works offline from a local file.
  python3 patcher/export_data.py STOCK_F3SYSTEM.BIN
  sh patcher/wasm/build_wasm.sh
  python3 patcher/build_patcher.py"""
import os, json, base64
HERE = os.path.dirname(os.path.abspath(__file__))
b64 = lambda p: base64.b64encode(open(p, "rb").read()).decode()

def main():
    page = open(os.path.join(HERE, "src", "page.html"), encoding="utf-8").read()
    core = open(os.path.join(HERE, "src", "core.js"), encoding="utf-8").read()
    data = open(os.path.join(HERE, "build", "data.json"), encoding="utf-8").read()
    out = os.path.join(HERE, "wasm", "out"); root = os.path.join(out, "espeak-data")
    files = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f); files[os.path.relpath(p, root).replace(os.sep, "/")] = b64(p)
    variants = sorted(os.listdir(os.path.join(root, "espeak-ng-data", "voices", "!v")), key=str.lower)
    for k, v in {"/*CORE_JS*/": core, "/*DATA_JSON*/null": data, "/*SPEAK_WASM*/": b64(os.path.join(out, "f3speak.wasm")),
                 "/*OPUS_WASM*/": b64(os.path.join(out, "f3opus.wasm")), "/*ESPEAK_FILES*/null": json.dumps(files),
                 "/*VARIANTS*/[]": json.dumps(variants)}.items():
        assert k in page, k
        page = page.replace(k, v.replace("</script", "<\\/script"))
    # The built page contains eSpeak NG (GPL-3.0-or-later) and libopus (BSD-3-Clause) compiled
    # to WebAssembly: as a whole it is distributed under GPL-3.0-or-later (the project's own
    # code in it stays MIT, which is compatible).
    note = ("<!-- This built page also contains eSpeak NG 1.52.0 (GPL-3.0-or-later,\n"
            "     https://github.com/espeak-ng/espeak-ng) and libopus 1.5.2 (BSD-3-Clause), compiled to\n"
            "     WebAssembly. The page as a whole is distributed under GPL-3.0-or-later; source:\n"
            "     https://github.com/xogium/talking-f3 -->")
    a = page.index("-->", page.index("SPDX-License-Identifier")) + 3
    page = page[:a] + "\n" + note + page[a:]
    dist = os.path.join(HERE, "..", "dist"); os.makedirs(dist, exist_ok=True)
    path = os.path.join(dist, "talking-f3-patcher.html")
    open(path, "w", encoding="utf-8").write(page)
    print(path, f"{os.path.getsize(path)/1048576:.1f} MB")

if __name__ == "__main__": main()

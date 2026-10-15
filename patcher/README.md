<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Web patcher

`dist/talking-f3-patcher.html` is a single offline page that turns Zoom's stock F3SYSTEM.BIN
v2.20 into the talking firmware, with the user's choice of languages, voice, pitch, speed,
loudness and chime.

- `src/core.js` — synthesis (eSpeak NG via a small in-page WASI shim), 22050->16000 Hz
  resampling, Opus encoding, bank assembly (same layout as tools/gen_flash_bank.py), image
  build and the same safety checks as tools/build_flash_image.py. Runs in browsers and Node.
- `src/page.html` — the accessible form; `build_patcher.py` inlines everything into one file.
- `wasm/` — `f3speak.c` (espeak-ng as a WASI reactor library) and `f3opus.c` (libopus encoder),
  built with zig by `build_wasm.sh`, which also extracts the 7-language espeak-ng data.
- `export_data.py` — exports the language-independent parts (bank plans from
  tools/gen_flash_bank.py, the encoded chime, the voice module, the stock file's SHA-256).
- `test/node_build.js` builds an image in Node; `test/ui_test.js` drives the real page in
  headless Chromium (Playwright) from a file:// URL, including the download.

<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Talking F3

A spoken voice guide for the **Zoom F3** field recorder, made by patching its firmware, for
blind and low-vision users. Through the headphones, the F3 says what is on its screen:
- menus as you scroll, and the selected option;
- popups and confirmation dialogs;
- the Date/Time screen and the waveform magnification;
- file names in the Finder and Playback, and file info;
- firmware versions;
- the user defined name editor;
- on request (Stop on the home screen), the remaining recording time and battery.

It speaks in the language the F3 is set to: English, French, German, Italian, Spanish,
Chinese or Japanese.

## Get it

**Use the patcher: <https://xogium.github.io/talking-f3/>**

It is a single web page that runs entirely in your browser. Nothing is uploaded, and your
firmware file never leaves your computer. To use it offline, save the page (it is
`index.html` in this repository) and open it from your disk.

1. Download Zoom's official F3 firmware **version 2.20** from zoomcorp.com and unzip it.
2. In the patcher, choose its `F3SYSTEM.BIN`, then pick:
   - languages;
   - voice, pitch and speed;
   - sound quality and loudness;
   - the start-up chime.
3. Build, save the new `F3SYSTEM.BIN`, and install it with the F3's normal SD-card update:
   hold PLAY/PAUSE while switching on, then choose Execute.

To go back, install Zoom's original file the same way. The patch never touches the F3's boot
area, so this always works.

## The F3 guide for blind users

[Zoom_menu.md](Zoom_menu.md) describes the F3's buttons, connectors and every menu, written
in 2022 by and for blind users. Its first section covers the talking F3: what it says, what
does not talk (the first screens after a factory reset), and how to type a file name.
It is also readable as a web page: <https://xogium.github.io/talking-f3/Zoom_menu.html>.

## How it works

- [TECHNICAL.md](TECHNICAL.md): the design in depth (audio hook, voice engine, Opus clip banks,
  screens, safety checks) and how to build everything from source.
- [RE_REFERENCE.md](RE_REFERENCE.md): every firmware address and structure used.
- [HOW_TO_DECOMPILE.md](HOW_TO_DECOMPILE.md): how the F3 firmware was read.
- [METHOD.md](METHOD.md): how the whole work was done, step by step, for anyone who wants to
  make another device talk.
- [EMULATION.md](EMULATION.md): testing the voice module in the Unicorn emulator before
  flashing: set-up, the harness, worked examples.

```
index.html              the patcher (built from patcher/ by patcher/build_patcher.py)
Zoom_menu.md            the F3 guide
arm/                    the voice engine that runs on the F3 (C, Thumb-2 assembly)
tools/                  clip bank generator, image builder, firmware unpacker, Ghidra scripts,
                        emulator tests
patcher/                the patcher's source: page, core, WebAssembly wrappers and build scripts
third_party/opus/       libopus 1.5.2
F3_strings_all_langs.json   the F3's interface texts in its 7 languages, by string id
```

Zoom's firmware is not in this repository and no build ever publishes it: the patcher works
on the copy each user downloads from Zoom.

## Licences and credits

- The project's own code and documents are under the **MIT licence** ([LICENSE](LICENSE)),
  © 2026 Casey Reeves <contact@xogium.me>. Each file says so in its SPDX header.
- The built patcher page (`index.html`) also contains eSpeak NG and libopus compiled to
  WebAssembly. As a whole it is distributed under **GPL-3.0-or-later**, as eSpeak NG requires.
  The project's code inside it stays MIT, which is compatible.
- `F3_strings_all_langs.json` holds the F3's interface texts, extracted from Zoom's firmware.
  They are Zoom's text, not covered by the project's licence, and included only so that the
  voices can be built.
- **eSpeak NG** (GPL-3.0) makes the voices. It is compiled into the patcher page from the
  unmodified 1.52.0 release (<https://github.com/espeak-ng/espeak-ng/tree/1.52.0>) by
  `patcher/wasm/build_wasm.sh`, with the wrapper `patcher/wasm/f3speak.c` and its
  configuration `patcher/wasm/espeak_config.h`.
- **libopus** 1.5.2 (BSD-3-Clause, `third_party/opus/COPYING`) encodes and decodes the voice.

This is an independent accessibility project, not made, endorsed or supported by Zoom.

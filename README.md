<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Talking F3

A spoken voice guide for the **Zoom F3** field recorder, made by patching its firmware, for
blind and low-vision users. Through the headphones, the F3 says what is on its screen:
- The menus as you move through them, and which option is currently selected in check box menus.
- Language names in the Language menu, each in its own language.
- Popups such as VOLUME, Hold, No SD Card and so on, including values that change while the popup is shown.
- Execute/cancel and OK/cancel dialogs, with the option you are on.
- The waveform magnification popup.
- The Set Date/Time screen: which field you are on, its value, and when you start or finish editing it. Setting the date and time no longer needs sighted help or the bluetooth app.
- The Finder: file names, and where you are in the list.
- Playback: the name of the file being played, and the file info pages (date and time, format, length).
- The Versions screen.
- Settings that take a value: hp alert vol, line out level (and its test tone), line out delay, contrast, and each input's hpf and delay. You hear the setting and its value when it opens, then each new value as you press up or down.
- The user defined name editor: every key as you move, each character you type or delete, and the whole name when you reach OK.
- On the home screen, while not recording or playing, pressing stop tells you the remaining recording time, the battery level, and the name the next recording will get (so you can check it before pressing record).
- Holding stop for about a second switches the speech off, anywhere ("Okay, I'm shutting up."); hold it again to bring it back ("I can talk now, wow!"). Stop still does its usual job when you press it: it stops playback, or a recording in progress. The speech is always on when the F3 is switched on.
- During playback, after you fast forward or rewind (holding the enter or back button), it tells you how much time is left in the file.

It speaks in the language the F3 is set to: English, French, German, Italian, Spanish,
Chinese or Japanese.

## Get it

**Use the patcher: <https://xogium.github.io/talking-f3/>**

It is a single web page that runs entirely in your browser. Nothing is uploaded, and your
firmware file never leaves your computer. To use it offline, save the page (it is
`index.html` in this repository) and open it from your disk.

1. Download Zoom's official F3 firmware **version 2.20**:
   [F3_v2.20_E.zip](https://zoomcorp.com/documents/2366/F3_v2.20_E.zip) from zoomcorp.com.
2. In the patcher, choose that zip file as it is (no need to unzip it), then pick:
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
third_party/sonic/      libsonic 0.2.0, for speech above 450 words per minute
F3_strings_all_langs.json   the F3's interface texts in its 7 languages, by string id
```

Zoom's firmware is not in this repository and no build ever publishes it: the patcher works
on the copy each user downloads from Zoom.

## Licences and credits

- The project's own code and documents are under the **MIT licence** ([LICENSE](LICENSE)),
  © 2026 Casey Reeves <contact@xogium.me>. Each file says so in its SPDX header.
- The built patcher page (`index.html`) also contains eSpeak NG and libopus compiled to
  WebAssembly, with libsonic. As a whole it is distributed under **GPL-3.0-or-later**, as eSpeak NG requires.
  The project's code inside it stays MIT, which is compatible.
- `F3_strings_all_langs.json` holds the F3's interface texts, extracted from Zoom's firmware.
  They are Zoom's text, not covered by the project's licence, and included only so that the
  voices can be built.
- **eSpeak NG** (GPL-3.0) makes the voices. It is compiled into the patcher page from the
  unmodified 1.52.0 release (<https://github.com/espeak-ng/espeak-ng/tree/1.52.0>) by
  `patcher/wasm/build_wasm.sh`, with the wrapper `patcher/wasm/f3speak.c` and its
  configuration `patcher/wasm/espeak_config.h`.
- **libsonic** 0.2.0 (Apache-2.0, `third_party/sonic/COPYING`) lets eSpeak NG speak faster than
  450 words per minute in the patcher.
- **libopus** 1.5.2 (BSD-3-Clause, `third_party/opus/COPYING`) encodes and decodes the voice.

This is an independent accessibility project, not made, endorsed or supported by Zoom.

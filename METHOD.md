<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# How this was done: making a closed device talk

This is the method behind the talking F3, written for anyone who wants to do the same for
another recorder or gadget with a screen and a headphone output. `HOW_TO_DECOMPILE.md` covers
the first step (getting readable code out of the firmware file). `TECHNICAL.md` describes the
result. This file is the path in between: the order things were done in, the techniques that
worked, and the traps.

It assumes some reverse-engineering background (reading Arm disassembly or Ghidra
output). It was done by a blind developer, with an AI assistant doing most of the code
reading. Every finding was confirmed on the real device by ear.

---

## 0. Before anything: a guaranteed way back

Do not change a single byte until you know how to undo any change. For the F3:

- The firmware is installed by Zoom's own SD-card updater, which lives in the **boot region**
  of the flash. As long as the boot region is never written, the updater survives anything the
  main firmware does. So reinstalling Zoom's original file is always possible, even after a
  build that crashes at start-up. (One of ours did. It was recovered this way.)
- So the rule: **never modify the boot region**, and check that rule on every build. The
  image builder refuses to save a file whose boot region differs from Zoom's.
- Learn the file's integrity checks before the first patch. For the F3 that is a byte-sum
  checksum, the code length and the version field, all in the trailer.
  `tools/build_flash_image.py` recomputes and verifies them.
- Keep every changed byte inside a short list of expected regions, and verify that list
  automatically. A patch that touches anything else is a bug.

If a device has no safe recovery path like this, stop and find one (a debug port, a
bootloader mode) before going further.

## 1. Read the firmware

Unpack and decompile (`HOW_TO_DECOMPILE.md`). The two things that made the F3 readable were
undoing armlink's compressed data (otherwise every table looks like random bytes) and
loading each program at its real run-time address. Expect to spend real time here; nothing
else works until the disassembly makes sense.

Then get your bearings:
- **The CPU and its memory map.** Here an NXP i.MX RT1061: SDRAM at 0x80000000, flash
  readable directly at 0x60000000.
- **The operating system.** FreeRTOS here. Find `xTaskCreate` and `vTaskDelay` from their
  string names, and list every task with its priority.
- **Where text comes from.** Search for a menu word you know is on screen. That finds the
  string tables, then the code that draws them, then the variables that say what is shown.

## 2. Find room

The patch needs space for code, RAM and voice data that the firmware never uses:
- **RAM and code:** a gap in SDRAM between the firmware's data and whatever follows. Prove
  it is unused from the linker layout (scatter table) and the zero-init ranges, not by
  guessing. Here: 0x801BFD00 to 0x801F4400.
- **Voice data:** the flash beyond the code length is copied nowhere and read by no one, so
  it can hold the clips, read in place through the flash window. Watch for the device's own
  data near the end of the flash: the F3 keeps its settings and a per-unit converter
  calibration there. Find those writers in the code and stay well clear (here, below
  0x7F9000).
- **Getting the code loaded:** extend the code length so the bootloader copies the module
  into the gap along with the firmware.

## 3. One hook in the audio path

Speech has to be mixed into what the headphones receive. Find the audio output task: the
DMA buffers feeding the audio interface (SAI on this chip), and the loop that fills them.
Then choose **one** instruction to replace with a branch to your code:
- 4 bytes, not position-dependent, and with no branch into its middle;
- at a moment when the buffer about to be sent is complete, but before it is copied out.

The trampoline runs the instruction it replaced, saves registers, calls the module, then
returns. Everything else in the firmware stays exactly as Zoom built it.

Check the facts you are tempted to assume, by measuring them:
- the sample format (here 32-bit, full scale 2^31);
- the frame count (all 128 frames; filling 120 gave a buzz);
- the real output rate (here twice the recording rate, at every setting).

## 4. First sound, then a talking debugger

The first build should do nothing but play a test tone. It proves the hook, the rate and the
level, and that the device still records normally.

From then on, **the device's own voice is the debugger.** There was no debug port, and the
developer is blind, so a screen was no use either. Instead, diagnostic builds say numbers:
- the index of the current screen when it changes;
- the value of a variable when a button is pressed;
- a measured audio level in dB.

(`SCR_PROBE`, `MON_PROBE`, `LANG_PROBE`, `OPUS_PROBE` in `arm/voice.c`.) One flash of a probe
build answers a question that would otherwise take hours of reading. For example, the
Versions screen turned out to be screen 16, not the one the code reading suggested.

## 5. Test in an emulator before every flash

Each build runs first in an emulator (Unicorn): the real module, the real voice data and the
firmware's real data, with the emulated screen and button state set by the test script
(`tools/emu/`; set-up and walk-through in `EMULATION.md`). It catches crashes, wrong output
and timing before the device ever sees the file:
- every clip is decoded and compared with a reference decoder;
- the worst-case cost per audio tick is measured;
- the stack depth of each task is measured;
- whole interactions are replayed, such as scrolling, Playback, or typing a name.

The emulator does not replace the device. It cannot show priority problems between tasks,
or what happens during start-up. But it means a device test only checks behaviour, never
"does it boot".

## 6. Know what is on screen, one screen at a time

The firmware already knows what it displays. The work is finding where it keeps that:
- **Menus:** usually a static tree of records (title, children, checked item) plus a few
  bytes of navigation state. Read the highlighted item from those.
- **Screens:** a "current screen" pointer, and per-screen state found by reading that
  screen's key handler. For example, the name editor's handler showed the focused key, the
  text buffer, the cursor and the character table.
- **Popups and dialogs:** a queue or a type variable, plus tables of string ids.
- **Text changed at run time** (file names, values): compare the string with its original to
  know whether to read the text itself or play the prepared clip.

Rules that saved a lot of trouble:
- **Only read a screen's state while that screen is current and fully drawn.** The F3 has a
  per-screen "initialised" flag.
- **Wait until a value has stayed the same for one poll** before speaking it.
- **Prefer reading state to hooking events.** Every attempt to hook a key handler or the
  display code ran in the wrong task or missed events. Polling the state every few
  milliseconds from the audio hook is simpler and more robust.

## 7. Speech that fits

A full speech synthesiser does not fit or run on such a device. Pre-recorded phrases do:
- **Clips:** one clip per interface string, in each language, made with eSpeak NG. Add numbers,
  letters, months and a few words, so values and file names can be spoken from pieces.
- **Storage:** clips are compressed with Opus (16 kbps), 3.8 MB for seven languages.
- **Decoding:** a background task decodes into a ring buffer, and the audio hook only copies
  samples out, so it stays cheap.
- **Text preparation:** the text needs preparing per language before synthesis:
  - units spoken as words;
  - Chinese converted to pinyin;
  - Japanese kanji converted to kana, with Latin words read by an English voice;
  - corrections from native speakers.

## 8. Timing and priorities on a real-time device

Most of the bugs that remained came from sharing the CPU:
- **Heavy work in the audio task causes crackle** at high sample rates. Move it out.
- **A low-priority background task starves** when the interface is busy (during playback).
  Choose a priority between the recording path and the interface.
- **Do nothing during the device's start-up.** Touching the flash while the firmware does
  froze the F3. The module now waits for the home screen.
- **Values read at start-up may not be loaded yet.** The volume was 0, so the start-up chime
  was silent.

## 9. Make it usable by others

A web page that builds the firmware in the browser means nobody needs a toolchain:
- the speech synthesiser and the encoder are compiled to WebAssembly;
- the user's own copy of the stock firmware is checked against its known hash;
- the result is built and verified with the same safety checks as the developer's tools.

Only the patch is distributed; the manufacturer's firmware never is.

---

## A note on the law

This work reads the manufacturer's firmware in order to make an independent program (the
voice module) work with it, for accessibility. In the EU, Directive 2009/24/EC (article 6)
allows decompiling for that kind of interoperability, under conditions. This repository
publishes the following, all written for this project:
- the method;
- the addresses and structures needed to build and maintain the module;
- the tools.

It does not publish the manufacturer's firmware or decompiled code. This is not legal
advice; check what applies where you live.

<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Talking F3: how it works

A technical description of the talking firmware for the Zoom F3 field recorder: what the
patch changes, how the voice engine finds out what is on screen, how it plays speech
without disturbing recording or monitoring, and how the voice data is made. It is written
for people who want to understand, check or extend the work. Addresses are for the stock
**F3 firmware v2.20**; `RE_REFERENCE.md` lists them all in one place.

---

## 1. At a glance

- The F3 runs an NXP **i.MX RT1061** (Arm Cortex-M7, 528 MHz) with FreeRTOS. Its firmware is
  one file, `F3SYSTEM.BIN`, installed with Zoom's own SD-card updater.
- The patch adds a small **voice module** (87 KB of code, about 125 KB with its RAM) to a region of
  memory the firmware never uses, adds **voice data** for seven languages (about 3.8 MB) to unused
  flash, and changes **one instruction** in the firmware: a branch in the audio output task.
- The module never writes to flash, never touches the boot code, and when it has nothing to
  say it leaves the audio exactly as the stock firmware made it.
- Every ~1 ms, from inside the audio task, the module reads the firmware's own state
  (current screen, menu position, popups, file list...) and decides what to say. Speech is
  pre-recorded phrase by phrase ("clips") with eSpeak NG, compressed with Opus, and decoded
  on the recorder by a background task.

```
             F3SYSTEM.BIN (8 MB)
 0x000000  ┌──────────────────────────────┐
           │ BOOT: bootloader, headers     │  never modified
 0x200300  ├──────────────────────────────┤
           │ MAIN: the firmware           │  one instruction changed (the hook)
           │  ...                         │
 0x3C0000  │ voice module (+ its RAM)     │  copied to SDRAM with MAIN at boot
 0x3DF000  ├ - - - - code_length - - - - -┤
 0x400000  │ clip banks, 7 languages      │  stays in flash, read in place (XIP)
 ~0x7C0000 │ (unused)                     │
 0x7F9000  │ limit for the voice data     │
 0x7FA000  │ (calibration, in flash only) │  the F3's own per-unit data: never written
 0x7FA2F8  │ code_length, version         │  updated; checksum at 0x2002FC
 0x7FB000  │ (settings, in flash only)    │  past the end of the file
           └──────────────────────────────┘
```

---

## 2. The firmware image

`F3SYSTEM.BIN` (0x7FA300 bytes) holds a boot region `[0, 0x200200)` and the **MAIN** region
from file offset `0x200300`, which the bootloader copies to SDRAM at `0x80000000`:

    runtime address = file offset - 0x200300 + 0x80000000

Three trailer fields matter:

| File offset | Field | Notes |
|---|---|---|
| `0x2002FC` | checksum | big-endian 32-bit sum of every byte from 0x200300 to the end |
| `0x7FA2F8` | code_length | how many bytes of MAIN the bootloader copies to SDRAM |
| `0x7FA2FC` | version | ASCII "0220"; the patch writes "0221" |

MAIN is linked with Arm's armlink. Its startup code (`__scatterload`) decompresses the
initialised data (0x801F4400..0x802AD280, compressed in the file), copies ITCM/DTCM/OCRAM
code and data, and zero-fills the rest. Reading the firmware therefore needs that step
reproduced first; `HOW_TO_DECOMPILE.md` explains it and `tools/f3_unpack.py` does it.

**Where the patch lives.** Between the end of the stock code (0x801BE454) and the start of
the initialised data (0x801F4400) there are ~214 KB of SDRAM that nothing references (no
pointer into it in code or data). The module is linked at **0x801BFD00** (file 0x3C0000),
and `code_length` is extended just enough to cover it, so the bootloader copies it along
with the firmware. Data placed in the file *past* `code_length` is not copied: it stays in
flash, where the CPU can read it directly through the FlexSPI window at **0x60000000**. That
is where the clip banks go (file 0x400000 = 0x60400000).

---

## 3. The audio path and the one hook

The F3's audio output runs in the FreeRTOS task **AudioProcess** (priority 30, second only
to the system timer task). Each cycle it produces one half of a double-buffered DMA output:
**128 stereo frames of 32-bit samples**, played at **twice the record rate** (96 kHz output
for 48 kHz recording), so a cycle lasts 0.33 to 1.45 ms depending on the sample rate.

```
 loop1:   sources            -> B1
 mixer:   monitor mix        -> B2          (the native mixer callback)
 ┌──── hook at 0x80010F3E ────────────────┐
 │ voice_tick(): what should be said?     │
 │ voice_fill_half(B2): speaking? write   │
 │   all 128 frames of B2 : leave B2 alone│
 └────────────────────────────────────────┘
 loop2:   B2                 -> DMA half    (stock, unchanged)
```

The hook replaces the instruction `sub.w r1, r4, #0x40` at 0x80010F3E, just before loop2,
with a branch to `tramp_audio_out` (in `arm/trampolines.S`). The trampoline saves registers,
calls the engine, runs the displaced instruction and jumps back. At that point B2 already
holds the monitor mix, so:

- **while speaking**, the engine overwrites all 128 frames of B2 with the voice, and the
  firmware's own loop2 copies it to the DMA buffer;
- **while silent**, it does not touch B2, so monitoring is byte-identical to stock.

Two rules came out of real bugs. Fill *all* 128 frames: filling 120 left 8 stale frames per
buffer, heard as a metallic 1.5 kHz buzz. Never patch loop2: it already copies all 128
frames, and widening its loop count made it overrun into the other DMA half.

The SAI (I2S) transmitter is set to 32-bit words, most significant bit first, so digital
full scale is 2^31. Room sound on the monitor peaks around -40 dBFS; the voice is written as
`sample16 << 13` (peaks around -21 dBFS), adjustable through the settings block.

---

## 4. The voice engine

Source: `arm/voice.c` (engine), `arm/exports.c`, `arm/trampolines.S`, `arm/voice.ld`, and the
vendored decode-only **libopus 1.5.2** (fixed point) in `third_party/opus`.

### Two execution contexts

| Context | Runs | Does |
|---|---|---|
| AudioProcess task (prio 30), via the hook | every DMA half | `voice_tick` (init, language, chime, screen poll) and `voice_fill_half` (copy PCM to B2) |
| VoiceDecode task (prio 25), created by the module | every 1 ms | Opus decoding into a 256 ms ring buffer |

The first version decoded Opus inside AudioProcess. At 88.2 kHz and above, where a cycle is
0.73 ms or less, the extra ~0.3 ms per decoded frame made the output crackle. Decoding now
happens in the module's own FreeRTOS task, created at start-up with the firmware's
`xTaskCreate` (0x80096748) and paced with its `vTaskDelay` (0x80095D90). It runs at priority
25: below the recording path (AudioProcess 30, AudioSubProcess 27, StreamDrive 26) and above
the interface (buttons 23, waveform 22, display 18/19). A first version at priority 2 starved
during playback, when the display and file reading keep the CPU busy, and clips timed out.
Its work is small: at most two 10 ms frames (about 0.5 ms) per 1 ms wake, and it sleeps as
soon as the ring buffer is full. The audio-task part
now costs about 6,000 instructions per cycle.

The two contexts share a single-producer, single-consumer ring: the decode task alone writes
the write index, the audio task alone writes the read index. A new clip is requested by
bumping a generation counter; the decode task resets its decoder, discards what is in the
ring, and acknowledges. Until the first 30 ms are decoded the audio task outputs silence,
and it gives up on a clip that has not started after 1.5 s.

### Playing speech

- **Resampling.** Clips are 16 kHz; the output runs at 88.2 to 384 kHz. A 32-bit phase
  accumulator with linear interpolation converts on the fly. The output rate is re-read on
  every audio cycle, so a clip playing while the SAMPLE RATE setting changes keeps its pitch.
- **Sequences.** Phrases are queued ("Remaining time", "3", "hours", ...). The next clip
  starts from inside the fill loop, so a sequence plays back to back and none of the
  monitor sound leaks in between.
- **Volume.** The F3 applies the headphone VOLUME setting in its audio converter, after the
  point where the voice is added. Measured on the device: the monitor in B2 peaks at the
  same level at VOLUME 100 and 50. So the engine reads the level (u16 at 0x804BEBB8, 0..50,
  shown as 0..100) and scales the voice itself: 1 dB per step, 50 = unity.
- **Settings block.** `g_cfg` at 0x801BFD20 (right after the export table) holds the output
  level, the chime switch and the volume-follow switch. The image builder and the web
  patcher write it; nothing is recompiled.
- **Start-up.** The module does nothing at all (no flash reads, no decode task, no speech)
  until the home screen appears, or for 12 s if it never does. During its audio set-up the
  firmware reads calibration data from flash with FlexSPI commands; a diagnostic build that
  started decoding then froze the F3 at "SD card access". The first-boot language and date
  screens stay silent: the headphone amplifier is still off at that point (no power-up
  click), so there is nothing to speak through.
- **Start-up chime.** Played once the decode task has run, the home screen has been shown
  for 0.4 s and the VOLUME level has been loaded (earlier it reads 0). Nothing waits for it.

### Memory

| Item | Size |
|---|---|
| module code + tables (incl. libopus) | 85 KB |
| Opus decoder state | 17.8 KB (18 KB reserved) |
| libopus scratch ("pseudo-stack") | 8 KB reserved, 4.2 KB peak |
| PCM ring | 8 KB (4096 samples) |
| decode task stack (from the FreeRTOS heap) | 4 KB, 1.9 KB peak |
| AudioProcess stack used by the module | 72 bytes |

Peaks were measured by decoding every clip of every bank in an emulator, since the data is
fixed.

---

## 5. Knowing what is on screen

The engine never draws or hooks the UI. It reads the firmware's own state, validates every
pointer against known memory ranges, and treats anything unexpected as "say nothing".

### Strings

All UI text lives in a writable table per language: string *n* in language *L* is a UTF-16
buffer at `*(*(0x802A3D60 + L*4) + n*4)`, and the current language is
`L = *(u16*)*(u32*)0x80498360` (0 English, 1 French, 2 German, 3 Italian, 4 Spanish,
5 Chinese, 6 Japanese). Clip numbers *are* string numbers: clip 46 says string 46
("System") in the bank of the current language.

Some strings are placeholders the firmware fills at runtime ("****", "99.99"): file names,
versions, levels. Each bank carries a 16-bit hash of every built-in string; if the live
buffer no longer matches, the engine **reads the text itself**:

- numbers as numbers ("2026" as a year in each language's style, "08" as "zero eight",
  long digit runs in pairs), "." between digits as "point", "%" as "percent";
- a trailing file extension dropped;
- any run of words that has its own clip spoken as that clip (a second hash table maps clip
  text to clip number, so "32-bit float" is not spelled out);
- everything else letter by letter.

### Screens

Screens are 32-byte objects from 0x8020740C; the current one is `*(u32*)0x8020A55C`. Bit 2
of an object's first word is set once its initialisation and first draw are done, and the
engine reads a screen's data only while it is current and that bit is set. Runtime values
must also be stable for one poll before they are spoken.

| What | How it is read |
|---|---|
| **Menus** | The menu is a static tree of 36-byte records in RW data (string id at +8, children at +0x0C, count at +0x10, checked value at +0x12, top row at +0x14). Navigation state: level `0x804BF76C`, depth per level `0x804BF76D`, node table `0x804BF774`, cursor row `0x804BF838`. The highlighted item is `children[top + row]`. Entering a menu says its title and the item; scrolling says the item; "selected" is added where the screen shows the check mark. |
| **Popups** | Queue of popup numbers at 0x802AD61C (head 0x802AD63A, active flag 0x802AD638); each popup has three lines of string ids in a table at 0x80208A54. Lines are re-spoken when their text changes (the VOLUME popup level). |
| **Dialogs** | Type at 0x804C058A (Format, Delete, Factory Reset, ...), focused button at 0x804C04F0. The Factory Reset dialog adds a sentence (clip 757) saying the F3 switches itself off afterwards. |
| **Set Date/Time** | Focused field 0x804C04FC, edit mode 0x804C04FD, values from 0x804C04FE. |
| **Magnification** | Open channel 0x80302508, zoom index per input at 0x804BEBB4. |
| **Playback / file INFO / Finder** | A newly opened Playback screen is handled on the next audio cycle: "Play" takes over the output at once, so the recording is not heard before its name. If a popup on the Playback screen shows the current file's name (skipping files), the file counts as announced, so the name isn't repeated when the popup closes. Current file index 0x804C0586 into the file database at 0x8049E6E8 (0x84-byte entries); INFO page 0x804BFA58; Finder row/position/count 0x804C028E / 0x804C0290 / 0x804BEA8E. |
| **Versions** | Screen object 16 (0x8020760C); labels and values are widgets 57-62. Digits after a decimal point are read one by one ("2.21" = two point two one). |
| **Name editor** (User Defined Name) | Screen object 5 (0x802074AC). Character set (row) u8 0x804C02A4: uppercase, lowercase, digits and symbols. Focused key u16 0x804C02A6: 0-28 a character of the 3 x 29 table at 0x80166FEC (A-Z _ - space / a-z _ - space / 1234567890+=!#',;()[]{}$@^`~ space), 29 switch set, 30 delete, 31 cursor left, 32 cursor right, 33 OK; Up/Down move it and wrap, it opens on OK. Text UTF-16 at 0x804C02CC (40 characters); cursor = 0x804C02A8 (position in the 13-character window) + 0x804C02AE (scroll). Spoken: on opening the title, the set and "OK" with the name spelled; each key as you move; the character typed; "deleted" and the character removed; the character after the cursor (or "end") when it moves; "capital" for uppercase letters in the name. Our phrases are slots 800-830. |
| **Home screen status** | Stop does nothing on the idle home screen in the stock firmware. The engine reads the raw button state (0x80490BAC, active low, Stop = bit 3) and, when Stop is pressed while not recording or playing, says the remaining recording time, battery level and battery type. |
| **Anything else** | Widget 4's label (descriptor pointer 0x802087B4) changes when an item is entered or confirmed; it is spoken as a fallback. |

---

## 6. The voice data

### Bank format

One bank per language, back to back from file 0x400000, each starting on a 16-byte
boundary. The engine finds the first one (0x60400000, or by scanning for the magic) and
follows the chain.

```
header (32 B)   'F3VX' 'BANK', sample rate (16000), slots (800), format (2 = Opus),
                r0 = offset of table A, r1 = offset of table B,
                r2 = language index | year style << 8
index           800 x { offset, sample count }       slot = string id
clip data       per clip: [u8 length][Opus packet] ...  (mono, 16 kHz, 10 ms frames)
table A         800 x u16: hash of each built-in string (runtime-text detection)
table B         800 x u32: hash of each clip's lower-cased text (lookup by text)
```

Slots 1-589 are the F3's strings. 590-799 are added phrases: "selected" (590), numbers 0-99
(600-699), months (700-711), date-field names (712-716), "2000" (717), letters A-Z (720-745),
"point", "percent", "of", "hours", "minutes", "Battery", "external power" (748-754), the chime
(756), the Factory Reset notice (757), hundreds 100-900 (781-789), thousands 1000-9000 (790-798) and, for Chinese, the
linking "零" (799). Numbers are composed from these ("345" = "300" + "45"), which keeps each
language's own number words ("trois cents", "trescientos", "三百"). Years follow the
language: English pairs ("twenty twenty-six"), whole numbers ("deux mille vingt-six"), or
digit by digit in Chinese ("二零二六").

### Making the clips

`tools/gen_flash_bank.py` (and the same logic in the web patcher) prepares each string
before eSpeak NG reads it:

- **Spoken overrides.** About 60 strings stay in English on every language's screen
  (Input1, "× 8", Please Power Off, Linear/Float...). `tools/spoken_overrides.py` gives each
  language its own spoken form; the screen text is unchanged.
- **Units.** kHz, Hz, bit, float, dB and ms are replaced by spoken words, which eSpeak would
  otherwise spell out.
- **Chinese.** eSpeak's Chinese dictionary does not cover every character, so Han
  characters become tone-numbered pinyin (pypinyin), read by the `cmn-latn-pinyin` voice.
- **Japanese.** Kanji become hiragana (pykakasi). eSpeak's Japanese voice spells every
  Latin-letter word, so those runs ("SD", "Off", "Firmware") are read by the English voice.
- **Language names** in the Language menu are read in their own language in every bank:
  "Français" always in the French voice.

Each clip is synthesized, resampled to 16 kHz, and encoded with libopus (VOIP mode, 16 kbps,
10 ms frames; the chime in music mode at 32 kbps). Seven languages take about 3.8 MB of the
3.97 MB available (0x400000 to 0x7F9000), against 26 MB for the same audio as 8-bit µ-law.
Japanese corrections from a native speaker (tkna, 2026-10-14) are in `spoken_overrides.py`
and the extra words; a spoken override of `None` silences a popup line.

**Speeds above 450 words per minute (patcher).** eSpeak NG stops getting faster at 450. The
patcher's eSpeak is built with libsonic (`third_party/sonic`, `USE_LIBSONIC` in
`patcher/wasm/espeak_config.h`): from 450 up to the page's limit of 1000, eSpeak speaks at its
normal rate and libsonic speeds the audio up by the remaining factor. Below 450 the output is
byte-for-byte the same as without libsonic. The PC generator (`tools/gen_flash_bank.py`) uses the
system's `espeak-ng`, which may be built without libsonic and then caps at 450.

**Sound quality (patcher option).** The bank header's rate field sets the clip rate, and the
engine decodes at it: 8 kHz narrowband for 6 kbps, 16 kHz wideband for 8 to 16 kbps (the
default), 24 kHz super-wideband for 24, 32 and 48 kbps (eSpeak's output is 22.05 kHz, so 24 kHz
keeps all of it; at 16 kHz the voice stops at 8 kHz and more bitrate barely helps). At 24 kHz
the decode task's stack peaks at 3.5 KB (1.9 KB at 16 kHz), so it has 5 KB; one decode wake
(two 10 ms frames) costs ~0.34 M instructions against 0.14 M at 16 kHz. CELT frames decode up
to 1 LSB different from the PC build of libopus (rounding in the ARM path), which is inaudible.
The page estimates the size from each language's seconds of speech at 300 words/min
(measured with its own eSpeak, `patcher/test/measure_dur.js`) times the measured bytes per
second for each quality, and warns before building.

---

## 7. Safety

- Only Zoom's SD-card updater is used to install. The boot region is never modified, so
  the updater, and with it the way back to stock, always remains.
- The image builders (`tools/build_flash_image.py` and the web patcher) refuse anything but
  the stock v2.20 file, and before saving they check that: the boot region is identical,
  the checksum is right, the audio loop (loop2) is unchanged, and every changed byte is
  inside the hook, the module region, the bank region or the trailer fields.
- The module only reads firmware state and validates every pointer; unknown state means
  silence. If its banks or its task are missing, it stays off and the F3 behaves as stock.
- Every build was run in an emulator (Unicorn) on the real firmware image and data before
  it went near the recorder: the full menu and screen behaviour, all clips decoded and
  compared bit for bit with the reference decoder, stack and memory peaks, and checks that
  no monitor audio leaks between clips.

---

## 8. Things that did not work

- **Filling 120 of 128 frames**: a 1.5 kHz buzz (the buffer rate). Fill all 128.
- **Patching loop2's count**: overran the next DMA half. Leave loop2 alone.
- **Decoding Opus in the audio task**: crackle at 88.2 kHz and above. Decode in a
  low-priority task.
- **Hooking the menu composer, a key dispatcher, or the home screen's message handler**
  to detect scrolling or buttons: these run in other tasks or never see the events. Reading
  the menu tree and the raw button state is simpler and robust.
- **Reading the F3's volume parameters or assuming the converter scales the voice**: the
  volume is applied after B2, so the engine follows the level itself.
- **Decoding at the lowest priority**: starved during playback (words cut, recording heard
  in between). Priority 25 sits between the recording path and the interface.
- **Speaking during start-up**: froze the F3 (flash access clash during its audio set-up).
  The module now waits for the home screen.
- **Playing the chime as soon as possible**: the volume level reads 0 that early, so the
  chime was silent. Wait for the home screen.
- **Spelling Latin words in Japanese, and Chinese characters missing from the dictionary**:
  fixed by preparing the text (section 6).

---

## 9. Building from source

Needs `arm-none-eabi-gcc`, Python 3 with `pypinyin` and `pykakasi`, `espeak-ng`, `ffmpeg`,
and the stock `F3SYSTEM.BIN` v2.20 (not included; it is Zoom's).

```sh
sh tools/build_opus_tool.sh                  # host Opus encoder/decoder used by the generator
sh tools/gen_all_banks.sh                    # 7 banks -> build/flash_bank_all/flash_bank.bin
sh arm/build.sh                              # module -> arm/voice.bin, arm/voice.elf
python3 tools/build_flash_image.py STOCK.BIN arm/voice.bin \
        build/flash_bank_all/flash_bank.bin dist/F3SYSTEM.BIN [--level 13] [--no-chime]
```

The web patcher (`patcher/`) does the bank and image steps in the browser with the same
logic, using eSpeak NG and libopus compiled to WebAssembly:

```sh
sh patcher/wasm/build_wasm.sh                # needs: pip install ziglang
python3 patcher/export_data.py STOCK.BIN     # plans, chime, module -> patcher/build/data.json
node patcher/test/measure_dur.js             # speech time per language, for the size estimate
python3 patcher/export_data.py STOCK.BIN     # again, to include those measurements
python3 patcher/build_patcher.py             # -> dist/talking-f3-patcher.html
```

Before flashing a new build, run it in the emulator (`EMULATION.md`):

```sh
python3 tools/f3_unpack.py --preset f3 STOCK.BIN build/unpack     # once
python3 tools/emu/emu_task.py arm/voice.elf build/flash_bank_all/flash_bank.bin
python3 tools/emu/example_status.py dist/F3SYSTEM.BIN arm/voice.elf
```

Diagnostic module builds: `sh arm/build.sh _probe -DOPUS_PROBE=1` (also `MON_PROBE`,
`LANG_PROBE`, `SCR_PROBE`; see the top of `arm/voice.c`).

## 10. Credits and licences

Engine, tools and documentation: this project, MIT licence (`LICENSE`), © 2026 Casey Reeves.
The built patcher page is GPL-3.0-or-later as a whole, because it contains eSpeak NG. Speech: eSpeak NG (GPL-3.0). Audio coding:
Opus / libopus (BSD-3-Clause). Fast speech: libsonic (Apache-2.0). Text preparation: pypinyin (MIT), pykakasi (GPL-3.0). The
F3 firmware is Zoom's and is not distributed here.

<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Testing the voice module in an emulator

Every talking F3 build was run in an emulator before it went near a real recorder. This
guide explains how to set that up and use it: what is emulated, how to drive a screen, how
to read what the module said (as words or as audio), and how to test something new.

The emulator is [Unicorn](https://www.unicorn-engine.org/), a CPU emulator library: it runs
Arm code instruction by instruction, but it emulates only the CPU and memory, not the F3's
chips. So the F3 itself does not run. **The voice module runs**, against the F3 firmware's
real code and data, while the test plays the part of the rest of the firmware by writing
its state into memory (which screen is shown, which button is down, the volume...).

That is enough to catch most problems before flashing:
- crashes and reads outside memory;
- a screen read wrongly, or something said twice;
- clips that fail to decode;
- too much work per audio tick, and the depth of each stack.

It cannot catch the F3's real timing, its tasks competing for the CPU, or anything that
happens during its own start-up. Those still need the device.

---

## 1. Set-up

You need:
- Python 3 with `unicorn` and `capstone`: `pip install unicorn capstone`. The bank plans
  also need `pypinyin` and `pykakasi`, to turn clip numbers back into text.
- `arm-none-eabi-gcc` and `arm-none-eabi-nm`, to build the module and read its symbols.
- Zoom's stock `F3SYSTEM.BIN` v2.20.
- A built talking image and the module's ELF. Build them as in TECHNICAL.md, section 9:
  `arm/voice.elf`, then `tools/build_flash_image.py`. An image saved from the web patcher
  also works, as long as you use the matching `arm/voice.elf`.

Then unpack the stock firmware once. The F3 keeps its initialised data compressed in the
file, and the emulator needs it unpacked (HOW_TO_DECOMPILE.md explains why):

```sh
python3 tools/f3_unpack.py --preset f3 F3SYSTEM.BIN build/unpack
```

The tests look for `build/unpack/`. Set `F3_UNPACK=/some/dir` to use another place.

Check that everything works:

```sh
cd tools/emu
python3 example_status.py ../../my_build.BIN ../../arm/voice.elf
```

It should print the status in English and French, for example:

```
EN ['Remaining Time', '2', 'hours', '17', 'minutes', 'Battery', '3', 'of', '4', 'Alkaline']
FR ['Tps restant', '2', 'heures', '17', 'minutes', 'Batterie', '3', 'sur', '4', 'Alcalines']
faults: none
```

It also writes `status_EN.wav` and `status_FR.wav`, which you can listen to.

---

## 2. How it works

`tools/emu/f3emu.py` sets up memory the way the F3 has it after start-up:

| Address | Region | Filled with |
|---|---|---|
| 0x60000000 | flash, read in place | the whole built image, so the clip banks are where the module looks |
| 0x80000000 | SDRAM | the firmware code and the voice module, as the bootloader copies them |
| 0x801F4400 | SDRAM | the firmware's initialised data, from `build/unpack/0x801F4400_rw.bin` |
| 0x20000000 | on-chip RAM | zeros; stacks and the audio buffer live here |

On the F3, three things call into the module. The test calls them in the same order, once
per audio buffer (128 frames, so 750 times a second at 48 kHz recording):

1. `voice_dec_step()`: the work of the background decode task (Opus to PCM), on its own stack.
2. `voice_tick()`: what the hook in the audio task calls. It looks at the screen and decides
   what to say.
3. `voice_fill_half(b2)`: writes the voice into the 128-frame stereo buffer when speaking.

Two FreeRTOS details are faked:
- `xTaskCreate` is intercepted and reports success. The test runs the task's body itself
  (step 1).
- There is no clock: time is counted in audio buffers. `run(1.0)` means one second of
  buffers.

The F3's state is plain memory. When the test writes the current screen pointer, the
module sees that screen, exactly as if the firmware had switched to it.

**What was said** is collected by stopping briefly at every call to `voice_start(clip)`,
the function that starts a clip. `words()` turns the clip numbers into text with the bank
plan from `tools/gen_flash_bank.py`. **What was heard** is collected from the buffer after
each `voice_fill_half`; `save_wav()` writes it at the output rate (twice the record rate).

---

## 3. The F3Emu class

```python
import sys; sys.path.insert(0, "tools/emu")
from f3emu import F3Emu

e = F3Emu("my_build.BIN", "arm/voice.elf", rec_rate=48000)
e.boot()                        # home screen, engine started, start-up chime done
e.screen("menu")                # make a screen current (and 'drawn'); names in SCREENS
e.language("FR")                # the F3's language: EN FR DE IT ES L5 (Chinese) L6 (Japanese)
e.press_stop()                  # hold Stop for 0.3 s
e.run(2.0)                      # two seconds of audio buffers
print(e.words())                # what was said, as text
e.save_wav("out.wav", normalize=True)
e.clear()                       # forget what was said and heard so far
print(e.faults)                 # emulator errors (bad reads/writes): should be empty
```

Lower level:
- `e.w8/w16/w32(address, value)` and `e.wtext(address, "text")` write F3 state. Text is
  UTF-16, as the F3 stores it.
- `e.r32(address)` reads memory. `e.var("g_active")` reads a module variable by name.
- `e.call("function", r0, r1)` runs any module function.
- `e.spoken` is the raw list of clip numbers. `e.audio` holds the raw samples.

Addresses for the F3's state are in `RE_REFERENCE.md`. The common ones are constants in
`f3emu.py` (`BUTTONS`, `VOLUME`, `BATTERY`, `REC_TOTAL`...).

---

## 4. Testing a screen: a worked example

`example_name_editor.py` tests the user defined name editor. The pattern is the same for
any screen:

1. **Find the screen's state** in RE_REFERENCE.md. Here:
   - the character set is at 0x804C02A4;
   - the focused key is at 0x804C02A6;
   - the cursor is at 0x804C02A8 and 0x804C02AE;
   - the text is at 0x804C02CC.
2. **Write the state as the F3 would have it** when the screen opens, then make the screen
   current: `e.screen("name")`.
3. **Change the state as one key press would**, run a little, and print the words:

```python
state(0, 33, 4, "Ab-1"); e.screen("name"); step("open the editor", 6)
state(0, 0, 4);  step("down: key 0")
state(1, 2, 5, "Ab-1c"); step("Enter: types 'c'")
```

Output:

```
open the editor (name 'Ab-1', on OK)   -> ['User Defined Name', 'uppercase letters', 'OK', 'capital', 'A', 'B', 'dash', '1']
down: key 0                            -> ['A']
Enter: types 'c'                       -> ['C']
```

Things to know when writing a test:
- **The engine only reads a screen once it is drawn** (bit 2 of the screen object's first
  word). `e.screen(name)` sets it; `e.screen(name, ready=False)` tests a screen that is
  still being drawn.
- **Most values must stay the same for one poll** before they are spoken (about 20 ms).
  Run at least 0.1 s after each change, more if you want to hear the whole phrase.
- **A clip that starts is listed even if it is interrupted later.** That is the right
  behaviour, but remember it when reading the output.
- **The engine stays idle until the home screen appears** (or 12 s pass), as on the
  device. Use `boot()` first.
- **The voice follows the simulated VOLUME** (30 of 50 by default). Write 0 and it falls
  silent; `save_wav(normalize=True)` makes quiet output audible.

---

## 5. The test scripts

All are in `tools/emu/` and run from the project root.

| Script | What it checks | Run |
|---|---|---|
| `example_status.py` | Stop on the home screen: words and audio, two languages | `python3 tools/emu/example_status.py IMAGE arm/voice.elf` |
| `example_name_editor.py` | the name editor, key by key | same arguments |
| `example_record_status.py` | Play/Pause during a recording: elapsed and remaining time, battery | same arguments, then a language |
| `example_speech_toggle.py` | holding Stop: speech off, silence, speech on; short Stop still gives the status | same arguments |
| `example_value_screen.py` | the value screen (HP Alert Vol, Line Out Level / Delay, Contrast, Input HPF / Delay), value by value | same arguments, then a language (`FR`, `L6`...) |
| `emu_task.py` | every clip of a bank through the engine, compared with the PC decoder; worst cost per tick, stack peaks, decode errors; any record rate | `python3 tools/emu/emu_task.py arm/voice.elf build/flash_bank_all/flash_bank.bin [clips] [rate]` |
| `emu_seam_ml.py` | Playback: "Play" then the file name, with no recording heard between the clips | `python3 tools/emu/emu_seam_ml.py 0` (language 0..6) |
| `emu_lang1.py` | the language banks are found, and the voice follows the F3's language | `python3 tools/emu/emu_lang1.py 1` (0..6) |
| `emu_chime2.py` | the start-up chime waits for the task, the home screen and the volume | `python3 tools/emu/emu_chime2.py` |

The three without an image argument load `arm/voice.elf` and
`build/flash_bank_all/flash_bank.bin` directly (built by `tools/gen_all_banks.sh`), with the
firmware's data from `build/unpack/`.

How to read `emu_task.py`'s summary:
- **"within 1 LSB"**: banks at 24 kHz (the patcher's higher qualities) may differ from the PC
  decoder by one unit in 32768. That is rounding in the Arm build, and inaudible.
- **"worst audio tick"**: must stay far below the time one buffer lasts. At 192 kHz output
  that is 0.67 ms, so about 350,000 instructions.
- **"decode-task stack peak"**: must stay below the 5 KB the task gets.
- **"late frames"**: must be 0. Otherwise the decoder fell behind the audio.

---

## 6. Diagnostic builds and the emulator

The module has diagnostic modes that speak numbers on the device (TECHNICAL.md, section 9;
the top of `arm/voice.c`). They work in the emulator too, which is a quick way to check a
probe before flashing it:

```sh
sh arm/build.sh _scr -DSCR_PROBE=1        # says the screen index whenever it changes
```

Build an image with that module (`tools/build_flash_image.py ... arm/voice_scr.bin ...`),
load it with `arm/voice_scr.elf`, and each `e.screen(...)` starts with the screen's index:
`e.screen("versions")` gives `['16', 'SYSTEM', 'BOOT', 'CHECKSUM']`. The flag byte that
follows the index is often cut off by the screen's own reading, as it is on the device.

---

## 7. When something goes wrong

- **`faults` is not empty.** The module read or wrote memory that is not mapped: usually a
  wrong address, or a state the test left unset (a pointer still 0). The fault shows the
  address.
- **Nothing is said.**
  - Did you call `boot()` (or make the home screen current)?
  - Is the screen marked as drawn?
  - Is the VOLUME above 0?
  - Is the module ELF the one inside the image? A mismatch gives nonsense.
- **"unpacked RW data not found".** Run the `f3_unpack.py` step, or set `F3_UNPACK`.
- **It is slow.** Emulating a second of audio takes several seconds (much more at high
  record rates, which have more buffers per second). Use `run(..., keep_audio=False)` when you only need
  the words, and lower record rates for long tests.

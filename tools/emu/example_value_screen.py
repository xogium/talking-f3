# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: the value screen (HP Alert Vol, Line Out Level / Delay, Contrast, Input HPF /
Delay), driven the way the F3's draw code does it: mode byte, widget 0x25 pointing at the
placeholder string, live text written into that string (RE_REFERENCE.md, "Value screen").
  python3 tools/emu/example_value_screen.py F3SYSTEM.BIN arm/voice.elf [EN|FR|...]"""
import sys
from f3emu import F3Emu, LANGS

SCR_VAL, MODE, WIDGETS, STR_TABLES = 0x8020754C, 0x804C0589, 0x802087A4, 0x802A3D60
PLACEHOLDER = {1: 257, 2: 256, 3: 255, 4: 64, 5: 260, 6: 329}
e = F3Emu(sys.argv[1], sys.argv[2])
lang = sys.argv[3] if len(sys.argv) > 3 else "EN"
e.language(lang); e.boot()

def widget_text(w, sid, text):
    e.w16(e.r32(WIDGETS + w * 4) + 4, sid)
    arr = e.r32(STR_TABLES + LANGS.index(lang) * 4)
    e.wtext(e.r32(arr + sid * 4), text)
def step(label, seconds=2.5):
    e.run(seconds, keep_audio=False); print(f"{label:34s} -> {e.words()}"); e.clear()
def open_mode(mode, text, label):
    e.screen("home"); e.run(0.3, keep_audio=False); e.clear()
    e.w8(MODE, mode); widget_text(0x25, PLACEHOLDER[mode], text); e.screen(SCR_VAL)
    step(label, 3)

open_mode(1, "-20dBFS", "open HP Alert Vol (-20dBFS)")
widget_text(0x25, 257, "-19dBFS"); step("up: -19dBFS")
widget_text(0x25, 257, "Off");     step("down to Off (English on every F3)")
open_mode(2, "-1dB", "open Line Out Level (-1dB)")
widget_text(0x25, 256, "\u00b10dB"); step("up: \u00b10dB")
widget_text(0x25, 256, "+24dB");   step("up to +24dB")
widget_text(0x25, 256, "-48dB");   step("down to -48dB")
widget_text(0x25, 256, "Mute");    step("down to Mute (English on every F3)")
widget_text(0x26, 241, ": Tone On"); step("test tone on")
open_mode(3, "12ms", "open Line Out Delay (12ms)")
open_mode(4, "10", "open Contrast (10)")
open_mode(5, "240Hz", "open Input HPF (240Hz)")
open_mode(5, "Off", "open Input HPF (Off)")
open_mode(6, "30.5ms", "open Input Delay (30.5ms)")
widget_text(0x25, 329, "30.0ms"); step("down: 30.0ms")
print("faults:", e.faults or "none")

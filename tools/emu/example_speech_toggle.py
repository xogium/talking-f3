# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: switching the speech off and on by holding Stop about a second; a short press
on the idle home screen still says the status (on release).
  python3 tools/emu/example_speech_toggle.py F3SYSTEM.BIN arm/voice.elf"""
import sys
from f3emu import F3Emu

SCR_VAL, MODE, WIDGETS, STR_TABLES = 0x8020754C, 0x804C0589, 0x802087A4, 0x802A3D60
e = F3Emu(sys.argv[1], sys.argv[2])
e.boot()

def step(label, seconds=2.5):
    e.run(seconds, keep_audio=False); print(f"{label:44s} -> {e.words()}"); e.clear()
def value_screen(text):
    e.screen("home"); e.run(0.3, keep_audio=False)
    e.w8(MODE, 3); e.w16(e.r32(WIDGETS + 0x25 * 4) + 4, 255)
    e.wtext(e.r32(e.r32(STR_TABLES) + 255 * 4), text); e.screen(SCR_VAL)

e.press_stop(0.3);  step("short Stop on the home screen", 4)
e.press_stop(1.5);  step("hold Stop 1.5 s")
e.press_stop(0.3);  step("short Stop while off")
value_screen("12ms"); step("open Line Out Delay while off")
e.screen("home");   e.run(0.3, keep_audio=False); e.clear()
e.press_stop(1.5);  step("hold Stop 1.5 s again")
value_screen("15ms"); step("open Line Out Delay after")
e.screen("home");   e.run(0.3, keep_audio=False); e.clear()
e.press_stop(0.7);  step("Stop for 0.7 s (short: status)", 4)
print("faults:", e.faults or "none")

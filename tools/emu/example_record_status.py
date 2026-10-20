# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: Play/Pause during a recording says the elapsed time, the remaining time and the
battery; while idle it does nothing (Zoom opens Playback then).
  python3 tools/emu/example_record_status.py F3SYSTEM.BIN arm/voice.elf [EN|FR|...]"""
import sys
from f3emu import F3Emu, BUTTONS, REC_STATE, REC_ELAPSED, REC_TOTAL

PLAY = 5                     # raw button bit of Play/Pause (Stop = 3)
e = F3Emu(sys.argv[1], sys.argv[2])
e.language(sys.argv[3] if len(sys.argv) > 3 else "EN"); e.boot()

def press_play(hold=0.3):
    e.w32(BUTTONS, 0xFFFFFFFF & ~(1 << PLAY)); e.run(hold); e.w32(BUTTONS, 0xFFFFFFFF)
def step(label, seconds=5):
    e.run(seconds, keep_audio=False); print(f"{label:40s} -> {e.words()}"); e.clear()

press_play(); step("Play/Pause while idle (nothing)", 2)
e.w32(REC_TOTAL, 2 * 3600 + 17 * 60); e.w16(REC_STATE, 1); e.w32(REC_ELAPSED, 125)
press_play(); step("Play/Pause while recording, 2 min 5 s in")
e.w32(REC_ELAPSED, 3600 + 42)
press_play(); step("1 h 0 min 42 s in")
e.w16(REC_STATE, 0); e.w32(REC_ELAPSED, 0xFFFFFFFF)
e.press_stop(); step("Stop after the recording (idle status)")
print("faults:", e.faults or "none")

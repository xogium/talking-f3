# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: the on-demand status (Stop on the home screen), in English and French.
  python3 tools/emu/example_status.py F3SYSTEM.BIN arm/voice.elf
Prints the words spoken and writes status_EN.wav / status_FR.wav to listen to."""
import sys
from f3emu import F3Emu, BATTERY, REC_TOTAL

e = F3Emu(sys.argv[1], sys.argv[2])
e.boot()                                   # home screen, voice ready
e.w32(REC_TOTAL, 2 * 3600 + 17 * 60)       # pretend: 2 h 17 min of recording left
e.w8(BATTERY, 3)                           # and 3 battery bars out of 4
for lang in ("EN", "FR"):
    e.language(lang); e.run(0.3, keep_audio=False); e.clear()   # let it switch banks
    e.press_stop(); e.run(6.0)
    print(lang, e.words())
    e.save_wav(f"status_{lang}.wav", normalize=True)
print("faults:", e.faults or "none")

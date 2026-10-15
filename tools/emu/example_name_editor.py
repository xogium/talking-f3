# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: the user defined name editor, driven by writing its state the way the F3's
key handler would (addresses from RE_REFERENCE.md, "Name editor").
  python3 tools/emu/example_name_editor.py F3SYSTEM.BIN arm/voice.elf"""
import sys
from f3emu import F3Emu

ROW, KEY, WIN, SCROLL, TEXT = 0x804C02A4, 0x804C02A6, 0x804C02A8, 0x804C02AE, 0x804C02CC
e = F3Emu(sys.argv[1], sys.argv[2])
e.boot()

def state(row, key, cursor, text=None):
    if text is not None: e.wtext(TEXT, text)
    e.w8(ROW, row); e.w16(KEY, key); e.w16(WIN, cursor); e.w16(SCROLL, 0)
def step(label, seconds=2.0):
    e.run(seconds, keep_audio=False); print(f"{label:38s} -> {e.words()}"); e.clear()

state(0, 33, 4, "Ab-1"); e.screen("name"); step("open the editor (name 'Ab-1', on OK)", 6)
state(0, 0, 4);  step("down: key 0")
state(0, 29, 4); step("move to the character-set key")
state(1, 29, 4); step("Enter: lowercase set")
state(1, 2, 4);  step("move to 'c'")
state(1, 2, 5, "Ab-1c"); step("Enter: types 'c'")
state(1, 31, 5); step("move to cursor left")
state(1, 31, 4); step("Enter: cursor left")
state(1, 30, 4); step("move to delete")
state(1, 30, 4, "Ab-1"); step("Enter: delete")
state(1, 33, 4); step("move to OK (reads the name)", 6)
print("faults:", e.faults or "none")

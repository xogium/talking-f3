# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: menu speech across screen switches, with Zoom's real menu records (main menu,
Output, Input1). Includes the in-between moments of a screen switch: the new screen not yet
drawn while the navigation state still holds the old menu, and the home screen, where the
state stays readable but stale. Nothing stale may be spoken; reopening a menu is announced.
  python3 tools/emu/example_menu_switch.py F3SYSTEM.BIN arm/voice.elf"""
import sys
from f3emu import F3Emu, SCREENS, SCR_CUR

LEVEL, NODES, ROW = 0x804BF76C, 0x804BF774, 0x804BF838
MAIN, OUTPUT, INPUT1, USB_MENU = 0x8020A3D8, 0x80209A28, 0x8020A3B4, 0x8020A300
USB_HOME = 0x802073CC              # the home screen in USB audio interface mode
OTHER_SCREEN = 0x8020744C          # stands in for a screen other than the menu (e.g. Input 1)
e = F3Emu(sys.argv[1], sys.argv[2]); e.boot()

def state(level, depth, node, row=0, top=0):
    e.w8(LEVEL, level); e.w8(LEVEL + 1 + level, depth)
    e.w32(NODES + (level * 7 + depth) * 4, node); e.w16(ROW, row); e.w16(node + 0x14, top)
def screen(addr, ready=True):
    e.w32(addr, 6 if ready else 2); e.w32(SCR_CUR, addr)
def step(label, seconds=2.5):
    e.run(seconds, keep_audio=False); print(f"{label:52s} -> {e.words()}"); e.clear()

state(0, 0, MAIN, row=2); screen(SCREENS["menu"]);          step("Menu pressed: main menu, on Output")
state(0, 1, OUTPUT, row=1);                                  step("Enter: Output, on Line Out Level")
screen(SCREENS["home"]);                                     step("Menu pressed: back home (state unchanged)")
state(0, 0, MAIN, row=2);                                    step("  ...state moves on while home")
state(0, 1, OUTPUT, row=1); screen(SCREENS["menu"]);         step("Menu again: reopens Output where it was")
screen(SCREENS["home"]);                                     step("Menu: home")
state(2, 0, INPUT1, row=0); screen(OTHER_SCREEN);            step("Up: Input 1 settings, on On/Off")
screen(SCREENS["menu"], ready=False);                        step("Menu: menu screen opening, state still Input1", 0.05)
state(0, 0, MAIN, row=0); e.w32(SCREENS["menu"], 6);         step("  ...menu drawn, main menu")
state(0, 0, MAIN, row=1);                                    step("Down: scrolling still immediate")
screen(USB_HOME);                                            step("USB audio interface mode: its home screen")
state(0, 0, USB_MENU, row=0); screen(SCREENS["menu"]);       step("Menu: USB menu, on Exit USB Audio I/F")
screen(USB_HOME);                                            step("Menu: back to the USB home (silent)")
print("faults:", e.faults or "none")

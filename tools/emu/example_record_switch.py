# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Example: runs Zoom's own record-switch handlers (not the voice module) to check the
"switch only starts" option: home screen FUN_8003eb78 case 3 and the shared FUN_8002e208,
idle and while recording; reports whether the stop routine (FUN_80005f80 / FUN_8002eb70) or
the start path (FUN_80005a28) is reached. Calls past those points are not followed.
  python3 tools/emu/example_record_switch.py F3SYSTEM.BIN arm/voice.elf"""
import sys
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC
from f3emu import F3Emu, REC_STATE

STOP = {0x80005F80: "stop recording", 0x8002EB70: "stop recording"}
START = {0x80005A28: "start a recording"}
e = F3Emu(sys.argv[1], sys.argv[2]); e.boot()
mu = e.mu

def run(addr, r0, label):
    seen = []
    def hook(uc, a, size, _):
        if a in STOP or a in START:
            seen.append(STOP.get(a) or START.get(a)); uc.emu_stop()
    h = mu.hook_add(UC_HOOK_CODE, hook)
    mu.reg_write(UC_ARM_REG_SP, 0x20040000); mu.reg_write(UC_ARM_REG_LR, 0x20000001)
    mu.reg_write(UC_ARM_REG_R0, r0); mu.reg_write(UC_ARM_REG_R1, 0); mu.reg_write(UC_ARM_REG_R2, 0)
    try: mu.emu_start(addr | 1, 0x20000000, count=200000)
    except Exception as ex: seen.append(f"fault {ex}")
    mu.hook_del(h)
    print(f"{label:46s} -> {seen[0] if seen else 'returns, nothing done'}")

for rec, name in ((0, "idle"), (1, "recording")):
    e.w16(REC_STATE, rec)
    run(0x8003EB78, 3, f"home screen, switch pushed, {name}")
    run(0x8002E208, 0, f"other screen, switch pushed, {name}")
e.w16(REC_STATE, 1)
run(0x8003EB78, 4, "home screen, Stop pressed, recording")

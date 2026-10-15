# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Run the REAL Opus engine module against the REAL Opus bank in Unicorn.
  python3 tools/emu/emu_task.py arm/voice.elf build/flash_bank_all/flash_bank.bin [max_clips] [rec_rate]
For every clip: voice_start(id), fill audio ticks until idle, recover the 16 kHz samples
from the 96 kHz output (phase-0 points of the linear interpolator) and compare with the
host libopus decode of the same packets. Also: per-tick instruction counts (worst tick),
audio-task stack depth vs private stack depth, faults, leak test for seamless chains."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from f3emu import ROOT, UNPACK
import struct, subprocess, sys, json
from unicorn import *; from unicorn.arm_const import *
import capstone

ELF, BANK = sys.argv[1], sys.argv[2]
REC = int(sys.argv[4]) if len(sys.argv) > 4 else 48000
STEP_EVERY = int(sys.argv[5]) if len(sys.argv) > 5 else 1
SHIFT = 13                     # output level (sample << 13, the default --level)
BIN = ELF[:-4] + ".bin"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9
BASE = 0x801BFD00
def sym(n):
    for l in subprocess.check_output(["arm-none-eabi-nm", ELF], text=True).splitlines():
        p = l.split()
        if len(p) >= 3 and p[2] == n: return int(p[0], 16)
TICK, START, FILL = sym("voice_tick"), sym("voice_start"), sym("voice_fill_half")
OST = 0; DSTEP = sym("voice_dec_step"); OWAIT = sym("g_owait"); OLATE = sym("g_olate"); OERR = sym("g_oerr")

mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
mu.mem_map(0x20000000, 0x80000); mu.mem_map(0x80000000, 0x1000000); mu.mem_map(0x60000000, 0x800000)
mu.mem_map(0xE0000000, 0x100000)
mu.mem_write(0x80000000, open(UNPACK+"/main_0x80000000.bin", "rb").read())
mu.mem_write(BASE, open(BIN, "rb").read())
end = sym("_end"); mu.mem_write(BASE + len(open(BIN, "rb").read()), b"\0" * (end - BASE - len(open(BIN, "rb").read())))
mu.mem_write(0x801F4400, open(UNPACK+"/0x801F4400_rw.bin", "rb").read())
mu.mem_write(0x2000a248, struct.pack("<I", REC))          # record 48k -> output 96k
mu.mem_write(0x804BEBB8, struct.pack("<H", 50))              # volume max = unity gain
bank = open(BANK, "rb").read(); mu.mem_write(0x60000000, bank)

faults = []
mu.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED,
            lambda u, a, ad, s, v, d: (faults.append(hex(ad)), False)[1])
created = []
def htc(uc, a, sz, _):
    created.append(uc.reg_read(UC_ARM_REG_R0)); uc.reg_write(UC_ARM_REG_R0, 1); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
mu.hook_add(UC_HOOK_CODE, htc, begin=0x80096748, end=0x80096749)
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
cache = {}; cnt = [0]; sp_task = [1 << 32]; sp_priv = [1 << 32]
TASK_TOP = 0x20040000
def hb(uc, a, sz, _):
    n = cache.get((a, sz))
    if n is None:
        n = sum(1 for _ in cs.disasm_lite(bytes(uc.mem_read(a, sz)), a)); cache[(a, sz)] = n
    cnt[0] += n
    sp = uc.reg_read(UC_ARM_REG_SP)
    if 0x20000000 <= sp <= TASK_TOP: sp_task[0] = min(sp_task[0], sp)
    elif 0x20050000 <= sp <= 0x20060000: sp_priv[0] = min(sp_priv[0], sp)
mu.hook_add(UC_HOOK_BLOCK, hb)

def call(fn, r0=0, r1=0, top=None):
    mu.reg_write(UC_ARM_REG_SP, top or TASK_TOP); mu.reg_write(UC_ARM_REG_LR, 0x20000001)
    mu.reg_write(UC_ARM_REG_R0, r0); mu.reg_write(UC_ARM_REG_R1, r1)
    try: mu.emu_start(fn | 1, 0x20000000, count=5_000_000)
    except UcError as e: faults.append(str(e))
    return mu.reg_read(UC_ARM_REG_R0)

mu.mem_write(0x8020A55C, struct.pack("<I", 0x8020764C)); mu.mem_write(0x8020764C, struct.pack("<I", 4))  # home screen: the engine starts
mu.mem_write(0x80498360, struct.pack("<I", 0x20030000)); mu.mem_write(0x20030000, struct.pack("<H", 0))   # language: English
for _ in range(300): call(TICK); call(FILL, 0x20010000, 0)
print("task created:", [hex(x) for x in created])
tk = [0]; dstep_max = [0]
def step():
    tk[0] += 1
    if tk[0] % STEP_EVERY == 0:
        c = cnt[0]; cnt[0] = 0; call(DSTEP, top=0x20060000); dstep_max[0] = max(dstep_max[0], cnt[0]); cnt[0] = c       # boot/prime (nav state zero)

hdr = struct.unpack_from("<8I", bank, 0); nslots = hdr[3]; fmt = hdr[4]; CR = hdr[2]   # clip rate
assert fmt == 2, fmt
idx = [struct.unpack_from("<II", bank, 32 + i * 8) for i in range(nslots)]
data0 = 32 + nslots * 8
WS = [0]; WF = [0]
seen = set(); worst_tick = 0; checked = mism = exact = 0; total_ticks = 0
for sid in range(1, nslots):
    off, ns = idx[sid]
    if not ns or off in seen: continue
    seen.add(off)
    if checked >= LIMIT: break
    # host reference: same packets through the host decoder
    p = bank[data0 + off:]; pk = bytearray(); got = 0; i = 0
    while got < ns:
        L = p[i]; pk += bytes([L, 0]) + p[i + 1:i + 1 + L]; i += 1 + L; got += CR // 100
    ref = subprocess.run([ROOT+"/tools/opus_tool", "dec", "rate=%d" % CR], input=bytes(pk), capture_output=True).stdout
    ref = struct.unpack("<%dh" % (len(ref) // 2), ref)[:ns]
    cnt[0] = 0; call(START, sid); t0 = cnt[0]
    outs = []; started = False
    for t in range(ns * 2 * REC // CR // 128 + 400):
        step()
        cnt[0] = 0
        act = call(FILL, 0x20010000, 0)
        w = struct.unpack("<I", bytes(mu.mem_read(OWAIT, 4)))[0]
        if not started and w == 0 and act: started = True
        if not started:
            if not act: break
            continue
        worst_tick = max(worst_tick, cnt[0] + (t0 if t == 0 else 0)); WS[0] = max(WS[0], t0); WF[0] = max(WF[0], cnt[0])
        total_ticks += 1
        if not act: break
        outs += struct.unpack("<256i", bytes(mu.mem_read(0x20010000, 1024)))[0::2]
    # phase-0 samples: out[6k] = prev sample << 7 ; the first output uses prev=cur=s0
    R = 2 * REC // CR
    rec = [outs[R * k] >> SHIFT for k in range(len(outs) // R)]
    want = [ref[0]] + list(ref[:-1])
    n = min(len(rec), len(want)) - 2
    diff = max((abs(a - b) for a, b in zip(rec[:n], want[:n])), default=0)
    ok = diff <= 1 and n > len(ref) - 30      # 24 kHz (CELT) frames may round 1 LSB differently on Arm
    exact += (diff == 0)
    checked += 1; mism += (not ok)
    if not ok and mism < 4:
        bad = next((k for k in range(n) if rec[k] != want[k]), None)
        print(f"  MISMATCH sid {sid} ns {ns} n {n} first bad {bad}: {rec[bad:bad+4] if bad is not None else ''} vs {want[bad:bad+4] if bad is not None else ''}")
late = struct.unpack("<I", bytes(mu.mem_read(OLATE, 4)))[0]; err = struct.unpack("<I", bytes(mu.mem_read(OERR, 4)))[0]
print(f"clips checked {checked}, bit-exact vs host libopus: {exact}, within 1 LSB: {checked - mism}, mismatches {mism}")
print(f"worst audio tick {worst_tick:,} instructions (~{worst_tick*1.5/600:.0f} us at 1.5 CPI, 600 MHz); ticks {total_ticks}")
print(f"late frames {late}, decode errors {err}")
print(f"AudioProcess stack used by us: {TASK_TOP - sp_task[0]} B | decode-task stack peak: {0x20060000 - sp_priv[0]} B of 5120")
SC=sym("g_oscratch"); sc=bytes(mu.mem_read(SC,8192)); print("pseudo-stack peak", max([i for i in range(8192) if sc[i]] or [0])+1, "of 8192")
print("worst start", WS[0], "worst fill tick", WF[0], "| worst decode-task step", dstep_max[0])
print("max start wait ticks", struct.unpack("<I", bytes(mu.mem_read(sym("g_omaxwait"),4)))[0])
print("faults:", faults[:5], len(faults))

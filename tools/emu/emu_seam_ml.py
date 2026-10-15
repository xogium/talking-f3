# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from f3emu import ROOT, UNPACK
import struct, subprocess, sys
from unicorn import *
from unicorn.arm_const import *

ELF = ROOT+"/arm/voice.elf"
BIN = ROOT+"/arm/voice.bin"
RW  = UNPACK+"/0x801F4400_rw.bin"
BASE = 0x801BFD00

def sym(n):
    for l in subprocess.check_output(["arm-none-eabi-nm", ELF], text=True).splitlines():
        p = l.split()
        if len(p) >= 3 and p[2] == n: return int(p[0], 16)
TICK, START, FILL = sym("voice_tick"), sym("voice_start"), sym("voice_fill_half")

mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
mu.mem_map(0x20000000, 0x80000)
mu.mem_map(0x80000000, 0x1000000)
mu.mem_map(0x60000000, 0x800000)
mu.mem_write(0x80000000, open(UNPACK+"/main_0x80000000.bin","rb").read())  # real MAIN (rodata tables)
mu.mem_write(BASE, open(BIN, "rb").read()); mu.mem_write(0x804BEBB8, struct.pack("<H", 50)); mu.mem_map(0x20080000, 0x80000) if False else None
mu.mem_write(0x801F4400, open(RW, "rb").read())          # REAL decompressed menu data
mu.mem_write(0x2000a248, struct.pack("<I", 48000))       # record rate
bank = open(ROOT+"/build/flash_bank_all/flash_bank.bin","rb").read()   # REAL clip bank
mu.mem_write(0x60000000, bank)   # at XIP start so the magic scan is short

faults, spoken = [], []
mu.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED,
            lambda u, a, ad, s, v, d: (faults.append(hex(ad)), False)[1])
def hc(uc, addr, size, data):
    if addr == START & ~1:
        spoken.append(uc.reg_read(UC_ARM_REG_R0))
mu.hook_add(UC_HOOK_CODE, hc)

def call(fn, r0=0, r1=0):
    mu.reg_write(UC_ARM_REG_SP, 0x20040000); mu.reg_write(UC_ARM_REG_LR, 0x20000001)
    mu.reg_write(UC_ARM_REG_R0, r0); mu.reg_write(UC_ARM_REG_R1, r1)
    try: mu.emu_start(fn | 1, 0x20000000, count=400000)
    except UcError as e: faults.append(str(e))


DSTEP = sym("voice_dec_step")
def _htc(uc, a, sz, _):
    uc.reg_write(UC_ARM_REG_R0, 1); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
mu.hook_add(UC_HOOK_CODE, _htc, begin=0x80096748, end=0x80096749)
_call0 = call
def call(fn, r0=0, r1=0):
    if fn == FILL:
        mu.reg_write(UC_ARM_REG_SP, 0x20060000); mu.reg_write(UC_ARM_REG_LR, 0x20000001)
        try: mu.emu_start(DSTEP | 1, 0x20000000, count=4000000)
        except UcError as e: faults.append(str(e))
    return _call0(fn, r0, r1)
def ticks(n):
    for _ in range(n):
        call(TICK); call(FILL, 0x20010000, 0)

W8  = lambda a, v: mu.mem_write(a, struct.pack("<B", v))
W16 = lambda a, v: mu.mem_write(a, struct.pack("<h", v))
W32 = lambda a, v: mu.mem_write(a, struct.pack("<I", v))
SR_NODE = 0x80209DA4                                     # "Sample Rate" record (real data)
S = json = None
import json as _j
EN = _j.load(open(ROOT+"/F3_strings_all_langs.json"))["EN"]
EN.update({"590":"selected","712":"Year","713":"Month","714":"Day","715":"Hour","716":"Minute","717":"two thousand"})
EN.update({str(600+n):"#%d"%n for n in range(100)})
EN.update({str(720+i):chr(65+i) for i in range(26)}); EN.update({"746":"hundred","747":"thousand","748":"point","749":"percent","750":"of"})
EN.update({str(700+i):m for i,m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"])})
def said(tag):
    global spoken
    print(f"{tag:46s} -> {[f'{i}:{EN.get(str(i),'?')}' for i in spoken]}")
    spoken = []

import struct as _s
RWB=0x801F4400; RWD=open(UNPACK+"/0x801F4400_rw.bin","rb").read()
def sbuf(sid): arr=_s.unpack_from("<I",RWD,0x802A4610-RWB+sid*4)[0]; return arr
def settext(sid, t): mu.mem_write(sbuf(sid), (t+"\0").encode("utf-16-le"))
W32(0x80498360, 0x20030000); W16(0x20030000, int(sys.argv[1]))
def setw(w, sid):
    d=_s.unpack_from("<I",RWD,0x802087A4+w*4-RWB)[0]; W16(d+4, sid)
import math
def buf(amp, rail):
    out=b""
    for f in range(128):
        v=int(amp*math.sin(2*math.pi*f/32.0)); v=max(-rail-1,min(rail,v))
        out+=_s.pack("<ii",v,v)
    return out
def fill_ticks(n, data):
    for _ in range(n):
        call(TICK); mu.mem_write(0x20010000, data); call(FILL,0x20010000,0)
MARK=b"".join(_s.pack("<ii",0x100000+k*7919,0x100000+k*7919+3) for k in range(128))   # varying "program audio"
def run_leak(n):
    states=[]
    for _ in range(n):
        call(TICK)
        mu.mem_write(0x20010000, MARK)
        call(FILL,0x20010000,0)
        out=bytes(mu.mem_read(0x20010000,1024))
        if out==MARK: states.append('P')                     # untouched: F3 audio passes
        elif any(out[k:k+8]==MARK[k:k+8] for k in range(0,1024,8)): states.append('M')   # mixed
        else: states.append('V')                             # all voice/silence
    st=''.join(states); a=st.find('V'); b=st.rfind('V')
    inner=st[a:b+1] if a>=0 else ''
    return inner.count('P'), inner.count('M'), st.count('V')
ticks(10000); said("boot")
PLAY=0x8020762C; idx=5
mu.mem_write(0x8049E6EC+idx*0x84, "260815_001.WAV\0".encode("utf-16-le")); W16(0x804C0586, idx)
W32(0x8020A55C, PLAY); W32(PLAY, 4)
gaps,mixed,v=run_leak(6000); said("Playback name sequence")
print("voice buffers:", v, " F3-audio buffers leaking between clips:", gaps, " partially-leaking buffers:", mixed)
print("faults:", faults[:5], "count", len(faults))

# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from f3emu import ROOT, UNPACK
"""Bank chain and language following: start in language L (0..6), then open Playback on
a file and print what is said.   python3 tools/emu/emu_lang1.py 1"""
import struct, subprocess
from unicorn import *; from unicorn.arm_const import *
ELF=ROOT+"/arm/voice.elf"; BIN=ELF[:-4]+".bin"; BASE=0x801BFD00
def sym(n):
    for l in subprocess.check_output(["arm-none-eabi-nm",ELF],text=True).splitlines():
        p=l.split()
        if len(p)>=3 and p[2]==n: return int(p[0],16)
TICK,START,FILL,DSTEP=sym("voice_tick"),sym("voice_start"),sym("voice_fill_half"),sym("voice_dec_step")
mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
mu.mem_map(0x20000000,0x80000); mu.mem_map(0x80000000,0x1000000); mu.mem_map(0x60000000,0x800000)
mu.mem_write(0x80000000,open(UNPACK+"/main_0x80000000.bin","rb").read())
mu.mem_write(BASE,open(BIN,"rb").read())
mu.mem_write(0x801F4400,open(UNPACK+"/0x801F4400_rw.bin","rb").read())
mu.mem_write(0x2000a248,struct.pack("<I",48000))
mu.mem_write(0x60000000,open(ROOT+"/build/flash_bank_all/flash_bank.bin","rb").read())
def htc(uc,a,sz,_): uc.reg_write(UC_ARM_REG_R0,1); uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
mu.hook_add(UC_HOOK_CODE,htc,begin=0x80096748,end=0x80096749)
spoken=[]; faults=[]
mu.hook_add(UC_HOOK_CODE,lambda uc,a,s,d: spoken.append(uc.reg_read(UC_ARM_REG_R0)),begin=START&~1,end=START&~1)
def call(fn,r0=0,r1=0,top=0x20040000):
    mu.reg_write(UC_ARM_REG_SP,top); mu.reg_write(UC_ARM_REG_LR,0x20000001)
    mu.reg_write(UC_ARM_REG_R0,r0); mu.reg_write(UC_ARM_REG_R1,r1)
    try: mu.emu_start(fn|1,0x20000000,count=5000000)
    except UcError as e: faults.append(str(e))
    return mu.reg_read(UC_ARM_REG_R0)
MARK=struct.pack("<256i",*([12345]*256))
def tick(step):
    if step: call(DSTEP,top=0x20060000)
    call(TICK); mu.mem_write(0x20010000,MARK); a=call(FILL,0x20010000,0)
    return a, bytes(mu.mem_read(0x20010000,1024))==MARK
W32=lambda a,v: mu.mem_write(a,struct.pack("<I",v)); W16=lambda a,v: mu.mem_write(a,struct.pack("<H",v))
W8=lambda a,v: mu.mem_write(a,struct.pack("<B",v))
R32=lambda a: struct.unpack("<I",bytes(mu.mem_read(a,4)))[0]
import json
LJ=json.load(open(ROOT+"/F3_strings_all_langs.json"))
names=["EN","FR","DE","IT","ES","L5","L6"]
man={}
for L in names:
    m={}
    for l in open(ROOT+f"/build/banks/{L}/manifest.txt",encoding="utf-8").read().splitlines()[2:]:
        p=l.split(None,1)
        if len(p)==2: m[int(p[0])]=p[1]
    man[L]=m
bank=open(ROOT+"/build/flash_bank_all/flash_bank.bin","rb").read()
starts=[]; i=0
while True:
    i=bank.find(struct.pack("<II",0x58563346,0x4B4E4142),i)
    if i<0: break
    starts.append(0x60000000+i); i+=8
W32(0x80498360,0x20030000)
W32(0x8020A55C,0x8020764C); W16(0x804BEBB8,30); W32(0x80490BAC,0xFFFFFFFF)
TPS=96000//128
def run(n):
    for _ in range(n): tick(True)
def q(fn,arg):
    n=call(sym(fn),arg); p=call(sym("voice_t_q"))
    return list(struct.unpack("<%dH"%n,bytes(mu.mem_read(p,2*n))))
import sys
SR=0x80209DA4
L=int(sys.argv[1]); nm=names[L]
W32(0x8020764C,4); W32(0x8020A55C,0x8020764C); W16(0x20030000,L)   # home screen: the engine starts at once
run(3*TPS); boot=list(spoken); spoken.clear()
PLAY=0x8020762C; idx=5
mu.mem_write(0x8049E6EC+idx*0x84, "260815_001.WAV\0".encode("utf-16-le")); W16(0x804C0586, idx)
W32(0x8020A55C, PLAY); W32(PLAY, 4); run(6*TPS)
a=list(spoken)
print(f"{nm}: bank ok {R32(sym('g_fh'))==starts[L]} | playback 260815_001.WAV -> {[man[nm].get(i,'?') for i in a]} | faults {faults[:2]}")

# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from f3emu import ROOT, UNPACK
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
mu.mem_write(0x2000a248,struct.pack("<I",192000))
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
TPS=384000//128
def run(n,step=True):
    v=0
    for _ in range(n):
        a,u=tick(step); v+= (not u)
    return v
W32(0x8020A55C,0x8020742C); W16(0x804BEBB8,0); W32(0x80490BAC,0xFFFFFFFF)
print("booting, task idle 1 s:", spoken, run(TPS,False))
print("booting, task alive, menu screen, vol 0, 2 s:", spoken, run(2*TPS))
W32(0x8020A55C,0x8020764C)
print("home screen, vol still 0, 1 s:", spoken, run(TPS))
W16(0x804BEBB8,30)
print("vol loaded, 0.3 s (< settle 0.4):", spoken, run(int(0.3*TPS)))
v=run(int(0.2*TPS)); print("+0.2 s:", spoken, "voice buffers", v)
v=run(TPS*2); print("+2 s:", spoken, "voice buffers", v)

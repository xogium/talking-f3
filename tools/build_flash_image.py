#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""build_flash_image.py -- assemble a talking F3SYSTEM.BIN.

  python3 tools/build_flash_image.py STOCK_F3SYSTEM.BIN arm/voice.bin \\
          build/flash_bank_all/flash_bank.bin OUT.BIN [--level 13] [--no-chime]

  * The voice module goes into a free SDRAM gap: file 0x3C0000 = runtime 0x801BFD00. It is
    covered by code_length, so the bootloader copies it to SDRAM with the rest of MAIN.
    Its .bss is zero-filled in the image. It must end below 0x801F4400 (RW data starts).
  * The clip banks go PAST code_length (file 0x400000..), so they stay in flash and are
    read in place through the XIP window.
  * One detour: 0x80010F3E (sub.w r1,r4,#0x40) -> b.w tramp_audio_out.
  * The settings block (.cfg at 0x801BFD20) gets --level / --no-chime.
  * code_length, version (0220 -> 0221) and the MAIN checksum are rewritten.
  * The BOOT region [0, 0x200200) is never written; the result is verified before saving.
"""
import sys, os, struct, subprocess, argparse, hashlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "arm"))
import thumb_branch

HOOK_RUNTIME = 0x80010F3E
HOOK_FILE    = 0x21123E
HOOK_ORIG    = bytes.fromhex("a4f14001")      # sub.w r1, r4, #0x40
CODE_START   = 0x200300
CKSUM_OFF    = 0x2002FC                       # big-endian byte sum over [CODE_START, EOF)
LEN_OFF      = 0x7FA2F8                       # little-endian MAIN code length
VER_OFF      = 0x7FA2FC
BOOT_END     = 0x200200
MODULE_BASE  = 0x801BFD00
MODULE_FILE  = 0x3C0000
GAP_END_RT   = 0x801F4400
BANK_FILE    = 0x400000
FILE_TRAILER = 0x7F9000                       # banks end below here: the flash sector at 0x7FA000
                                              # holds the trailer and the "Dual AD Calibration"
                                              # record the firmware rewrites (FUN_8001b468)
# Optional (off by default, --switch-start-only): the record switch only starts recordings (Stop ends them). Zoom's switch handlers
# stop a running recording when the switch is pushed again, which is easy to do by accident
# when sliding it out of Hold. Two branches make that path return instead:
#   home / recording screen, FUN_8003eb78 case 3: "bl FUN_80005f80" (stop) -> "b" to its return 0
#   every other screen, FUN_8002e208 (shared): recording -> "b" to its return
# Starting a recording (idle) and the Stop button (FUN_8002eb70) are unchanged.
SWITCH_PATCHES = [  # (runtime address, stock bytes, new bytes)
    (0x8003EC90, bytes.fromhex("c7f776f9"), bytes.fromhex("8de000bf")),   # b 0x8003edae ; nop
    (0x8002E21E, bytes.fromhex("6ff00100"), bytes.fromhex("06e000bf")),   # b 0x8002e22e ; nop
]
CFG_RT       = 0x801BFD20
CFG_MAGIC    = 0x47464356                     # 'VCFG'

def rt2file(a): return a - 0x80000000 + CODE_START

def sym(elf, name):
    for exe in ("arm-none-eabi-nm", "nm"):
        try:
            for line in subprocess.check_output([exe, elf], text=True).splitlines():
                p = line.split()
                if len(p) >= 3 and p[2] == name: return int(p[0], 16)
        except Exception: pass
    return None

def build(stock, voice, bank, end_rt, tramp, level=13, chime=True, switch_start_only=False):
    img = bytearray(stock)
    if len(img) != 0x7FA300: sys.exit(f"ABORT: stock image size 0x{len(img):X}, expected 0x7FA300")
    if bytes(img[VER_OFF:VER_OFF+4]) != b"0220": sys.exit("ABORT: not a v2.20 image")
    if bytes(img[HOOK_FILE:HOOK_FILE+4]) != HOOK_ORIG:
        sys.exit(f"ABORT: hook bytes are {bytes(img[HOOK_FILE:HOOK_FILE+4]).hex()}, expected {HOOK_ORIG.hex()}")
    # 1) hook
    img[HOOK_FILE:HOOK_FILE+4] = thumb_branch.bw(HOOK_RUNTIME, tramp)
    # 1b) optional: record switch only starts recordings
    if switch_start_only:
        for rt, old, new in SWITCH_PATCHES:
            f = rt2file(rt)
            if bytes(img[f:f+4]) != old: sys.exit(f"ABORT: switch site 0x{rt:08X} is {bytes(img[f:f+4]).hex()}, expected {old.hex()}")
            img[f:f+4] = new
    # 2) module (+ zeroed .bss), settings
    if end_rt > GAP_END_RT: sys.exit(f"ABORT: module end 0x{end_rt:08X} past 0x{GAP_END_RT:08X}")
    mod_end = min((rt2file(end_rt) + 0xFFF) & ~0xFFF, rt2file(GAP_END_RT))
    img[MODULE_FILE:mod_end] = b"\0" * (mod_end - MODULE_FILE)
    img[MODULE_FILE:MODULE_FILE+len(voice)] = voice
    c = rt2file(CFG_RT)
    if struct.unpack_from("<I", img, c)[0] != CFG_MAGIC: sys.exit("ABORT: settings block not found")
    if not 0 <= level <= 15: sys.exit("ABORT: level must be 0..15")
    img[c+4] = level; img[c+5] = 1 if chime else 0
    # 3) code_length covers the module only
    struct.pack_into("<I", img, LEN_OFF, mod_end - CODE_START)
    # 4) banks past code_length
    if BANK_FILE + len(bank) > FILE_TRAILER:
        sys.exit(f"ABORT: banks too large ({len(bank)} B, room {FILE_TRAILER-BANK_FILE} B)")
    img[BANK_FILE:BANK_FILE+len(bank)] = bank
    # 5) version + checksum
    img[VER_OFF:VER_OFF+4] = b"0221"
    struct.pack_into(">I", img, CKSUM_OFF, sum(img[CODE_START:]) & 0xFFFFFFFF)
    verify(stock, img, switch_start_only)
    return img, mod_end

def verify(stock, img, switch_start_only=False):
    """Refuse to produce an image that breaks the safety rules."""
    assert len(img) == len(stock)
    assert img[:BOOT_END] == stock[:BOOT_END], "BOOT region changed"
    assert struct.unpack_from(">I", img, CKSUM_OFF)[0] == sum(img[CODE_START:]) & 0xFFFFFFFF
    allowed = [(CKSUM_OFF, CKSUM_OFF+4), (HOOK_FILE, HOOK_FILE+4), (MODULE_FILE, rt2file(GAP_END_RT)),
               (BANK_FILE, FILE_TRAILER), (LEN_OFF, LEN_OFF+8)]
    for rt, old, new in SWITCH_PATCHES:          # exactly the known bytes, or untouched
        f = rt2file(rt)
        assert bytes(img[f:f+4]) == (new if switch_start_only else old), f"switch site 0x{rt:08X} unexpected"
        allowed.append((f, f+4))
    for i in range(len(img)):
        if img[i] != stock[i] and not any(a <= i < b for a, b in allowed):
            raise AssertionError(f"unexpected change at file 0x{i:X}")
    assert img[0x211242:0x211282] == stock[0x211242:0x211282], "loop2 changed"

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stock"); ap.add_argument("voice_bin"); ap.add_argument("bank"); ap.add_argument("out")
    ap.add_argument("--level", type=int, default=13, help="output level (sample << level), default 13")
    ap.add_argument("--no-chime", action="store_true")
    ap.add_argument("--switch-start-only", action="store_true",
                    help="the record switch only starts recordings; only Stop ends one (patches two branches in Zoom's switch handlers)")
    a = ap.parse_args()
    elf = os.path.splitext(a.voice_bin)[0] + ".elf"
    end_rt, tramp = sym(elf, "_end"), sym(elf, "tramp_audio_out")
    if end_rt is None or tramp is None: sys.exit(f"ABORT: need {elf} for _end / tramp_audio_out")
    stock = open(a.stock, "rb").read()
    img, mod_end = build(stock, open(a.voice_bin, "rb").read(), open(a.bank, "rb").read(),
                         end_rt, tramp, a.level, not a.no_chime, a.switch_start_only)
    open(a.out, "wb").write(img)
    print(f"wrote {a.out}: module 0x{MODULE_FILE:X}..0x{mod_end:X}, banks {len(open(a.bank,'rb').read())/1048576:.2f} MB, "
          f"level {a.level}, chime {'off' if a.no_chime else 'on'}, "
          f"switch {'starts only' if a.switch_start_only else 'as stock'}; verified (BOOT identical, checksum, loop2, changes confined)")

if __name__ == "__main__":
    main()

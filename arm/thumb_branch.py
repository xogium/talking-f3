#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Thumb-2 wide-branch encoders for the F3 detour patcher.
B.W  (unconditional) and BL both have ±16 MB range on Cortex-M7."""
import struct
def _enc(src, dst, link):
    off = dst - (src + 4)                      # Thumb PC = insn addr + 4
    if off & 1: raise ValueError("odd offset")
    if not (-(1<<24) <= off < (1<<24)): raise ValueError("out of ±16MB range")
    off >>= 1
    S  = (off >> 23) & 1
    i1 = (off >> 22) & 1
    i2 = (off >> 21) & 1
    imm10 = (off >> 11) & 0x3ff
    imm11 = off & 0x7ff
    j1 = (~i1 & 1) ^ S
    j2 = (~i2 & 1) ^ S
    hw1 = 0xF000 | (S << 10) | imm10
    hw2 = (0xD000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)
def bw(src, dst):  return _enc(src, dst, False)   # B.W
def bl(src, dst):  return _enc(src, dst, True)     # BL
if __name__ == "__main__":
    import sys
    src,dst = int(sys.argv[2],0), int(sys.argv[3],0)
    print((bl if sys.argv[1]=="bl" else bw)(src,dst).hex())

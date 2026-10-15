#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""F3SYSTEM.BIN integrity tooling for the talking-F3 project.

Verified facts (F3 v2.20):
  * MAIN partition  = file [0x200200, EOF);  sub-header 0x200200..0x200300.
  * Integrity field = 32-bit big-endian sum of bytes over [0x200300, EOF),
                      stored at file 0x2002FC.  Stock value: 0x4E1D9329.
  * Code-length field (separate) = (code_end 0x3BE754 - 0x200300) = 0x1BE454,
                      stored little-endian right before the "0220" version at
                      file ~0x7FA2F8.  (Informational; not the checksum.)
"""
import sys, struct

CODE_START = 0x200300          # runtime 0x80000000
CKSUM_OFF  = 0x2002FC          # where the BE checksum is stored
STOCK_CKSUM = 0x4E1D9329

def checksum(img: bytes) -> int:
    return sum(img[CODE_START:]) & 0xFFFFFFFF   # [0x200300 .. EOF)

def read_stored(img: bytes) -> int:
    return struct.unpack_from(">I", img, CKSUM_OFF)[0]   # big-endian

def verify(path):
    img = open(path, "rb").read()
    calc, stored = checksum(img), read_stored(img)
    ok = calc == stored
    print(f"{path}: size=0x{len(img):x}")
    print(f"  stored @0x2002FC (BE) = 0x{stored:08X}")
    print(f"  computed sum[0x200300:EOF] = 0x{calc:08X}  -> {'MATCH' if ok else 'MISMATCH'}")
    return ok

def fix(in_path, out_path):
    img = bytearray(open(in_path, "rb").read())
    calc = checksum(img)
    struct.pack_into(">I", img, CKSUM_OFF, calc)
    open(out_path, "wb").write(img)
    print(f"wrote {out_path}: integrity field set to 0x{calc:08X}")

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fix":
        fix(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "verify":
        sys.exit(0 if verify(sys.argv[2]) else 1)
    else:
        print("usage: f3_image_tool.py verify <img> | fix <in> <out>")

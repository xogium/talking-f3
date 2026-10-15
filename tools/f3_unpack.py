#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""f3_unpack.py -- split a Zoom firmware image into the memory regions it occupies at
runtime, so a disassembler/decompiler sees real code and real initial data.

    python3 f3_unpack.py --preset f3  F3SYSTEM.BIN     outdir/
    python3 f3_unpack.py --preset h4e H4essential.BIN  outdir/
    python3 f3_unpack.py --main-off 0x... --base 0x... [--len 0x...] IMAGE outdir/

Why this is needed
------------------
Both images contain an ordinary armlink (Keil / ARM Compiler) application. The Zoom
bootloader copies that application to SDRAM and jumps to its reset vector. The
application's own startup code (__main -> __scatterload) then walks a *region table*
and builds the rest of RAM before main() runs:

    entry = { u32 load_addr, u32 exec_addr, u32 size, u32 handler }

handler is one of:
    __decompress   armlink "compressed RW data" -- an LZ77-style codec. Two variants
                   exist; the F3 v2.20 uses "variant 1" (literal count 3 bits, 8-bit
                   distance, zero-runs), the H4essential v2.30 uses "variant 2" (literal
                   count 2 bits, 10/16-bit distance, no zero-runs). Both are below.
    __scatterload_copy      plain word copy
    __scatterload_zeroinit  zero fill (.bss)

So in the raw file the initialised globals -- including every static table of
function pointers, menu definitions, strings referenced from RAM -- are COMPRESSED.
A disassembler pointed at the raw file sees noise where that data lives, and anything
that references RAM addresses resolves to nothing. This script reproduces what
__scatterload does, offline.

Presets
-------
  f3-boot1 / f3-boot2 : the two F3 boot stages (see HOW_TO_DECOMPILE.md)
  f3  : application at file 0x200300, runs at 0x80000000, length = code_length
        (LE u32 at file 0x7FA2F8). BOOT region [0..0x200200) is the bootloader.
  h4e : application ("H4essential Main2 Data" header) at file 0x19C200; the 0x100-byte
        header sits at 0x7FFFFF00 so the vector table lands at 0x80000000.

Output (in outdir/)
-------------------
  regions.txt          the region table, decoded
  main_<base>.bin      the application as loaded (load view)
  0x<exec>_<kind>.bin  each copied / decompressed region at its run address
  ghidra_blocks.txt    "name start size file|-" per region, for F3Setup.java
Zero-init regions are listed but not written (create them uninitialised).
"""
import sys, os, struct, argparse

PRESETS = {
    "f3":  dict(main_off=0x200300, base=0x80000000, len_from=0x7FA2F8, len_add=0),
    # F3 boot stage 1: the i.MX RT boot ROM copies flash[0..0x9F20) to OCRAM 0x2020BC00
    # (IVT at flash 0x1000, entry 0x2020E014). Length = u32 at file 0x1000F8 (flash 0xFFFF8).
    "f3-boot1": dict(main_off=0x100, base=0x2020BC00, len_from=0x1000F8, len_add=0),
    # F3 boot stage 2 ("updater"): flash 0x100000.., linked for SDRAM 0x806DE800.
    # Length = u32 at file 0x2000F8 (followed by version "0100").
    "f3-boot2": dict(main_off=0x100100, base=0x806DE800, len_from=0x2000F8, len_add=0),
    # H4e: length field (load size from 0x80000000) at file 0x3382F8; +0x100 for the header
    "h4e": dict(main_off=0x19C200, base=0x7FFFFF00, len_from=0x3382F8, len_add=0x100),
}

def u32(b, o): return struct.unpack_from("<I", b, o)[0]

def decompress_v1(src, p, out_len):
    """armlink __decompress, variant 1 (F3 v2.20, code at 0x800008A8).
    token t: lit = t&7 (0 -> next byte); n = t>>4 (0 -> next byte);
    copy lit-1 literal bytes; then if t&8: dist = next byte, copy n+2 bytes from
    out[-dist]; else emit n zero bytes."""
    out = bytearray(); s = p
    while len(out) < out_len:
        t = src[p]; p += 1
        lit = t & 7
        if lit == 0: lit = src[p]; p += 1
        n = t >> 4
        if n == 0: n = src[p]; p += 1
        out += src[p:p + lit - 1]; p += lit - 1
        if t & 8:
            d = src[p]; p += 1
            for _ in range(n + 2): out.append(out[-d])
        else:
            out += bytes(n)
    return bytes(out[:out_len]), p - s

def decompress_v2(src, p, out_len):
    """armlink __decompress, variant 2 (H4essential v2.30, code at 0x8000142E).
    token t: lit = t&3 (0 -> next byte); n = t>>4 (0 -> next byte);
    copy lit-1 literal bytes; if n != 0: d = next byte;
      if (t&0xC)==0xC: dist = d + (next byte << 8)  else dist = d + ((t&0xC) << 6);
      copy n+2 bytes from out[-dist]."""
    out = bytearray(); s = p
    while len(out) < out_len:
        t = src[p]; p += 1
        lit = t & 3
        if lit == 0: lit = src[p]; p += 1
        n = t >> 4
        if n == 0: n = src[p]; p += 1
        out += src[p:p + lit - 1]; p += lit - 1
        if n:
            d = src[p]; p += 1
            if (t & 0xC) == 0xC: d += src[p] << 8; p += 1
            else: d += (t & 0xC) << 6
            for _ in range(n + 2): out.append(out[-d])
    return bytes(out[:out_len]), p - s

def find_scatter(app, base):
    """__scatterload = 'ldr r4,[pc,#x]; ldr r5,[pc,#y]; b ...; ldr r0,[r4,#0xc]'.
    Returns (table_start, table_end, address) for the first match whose table
    lies inside the image and has a sane size."""
    for o in range(0, len(app) - 12, 2):
        h0, h1 = struct.unpack_from("<HH", app, o)
        if h0 >> 8 != 0x4C or h1 >> 8 != 0x4D: continue
        if struct.unpack_from("<H", app, o + 6)[0] != 0x68E0: continue
        rt = base + o
        l4 = ((rt + 4) & ~3) + (h0 & 0xFF) * 4
        l5 = ((rt + 6) & ~3) + (h1 & 0xFF) * 4
        if not (base <= l4 < base + len(app) and base <= l5 < base + len(app)): continue
        ts, te = u32(app, l4 - base), u32(app, l5 - base)
        if base <= ts < te <= base + len(app) and (te - ts) % 16 == 0 and te - ts <= 0x400:
            return ts, te, rt
    sys.exit("could not find __scatterload")

def handler_kind(app, base, h):
    b = app[(h & ~1) - base:(h & ~1) - base + 12]
    if b[:2] == bytes.fromhex("70b5"):          # push {r4,r5,r6,lr} -> a decompressor
        # variant 1 masks the literal count with #7, variant 2 with #3
        return "decompress_v1" if bytes.fromhex("0703") in b else "decompress_v2"
    if b[:2] == bytes.fromhex("0020"):          # movs r0,#0 -> zero-init loop
        return "zero"
    return "copy"

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image"); ap.add_argument("outdir")
    ap.add_argument("--preset", choices=PRESETS)
    ap.add_argument("--main-off", type=lambda x: int(x, 0))
    ap.add_argument("--base", type=lambda x: int(x, 0))
    ap.add_argument("--len", type=lambda x: int(x, 0))
    a = ap.parse_args()
    cfg = dict(PRESETS[a.preset]) if a.preset else dict(main_off=None, base=None, len_from=None, len_add=0)
    if a.main_off is not None: cfg["main_off"] = a.main_off
    if a.base is not None: cfg["base"] = a.base
    if cfg["main_off"] is None or cfg["base"] is None: ap.error("need --preset or --main-off and --base")

    img = open(a.image, "rb").read()
    mo, base = cfg["main_off"], cfg["base"]
    if a.len: n = a.len
    elif cfg["len_from"] is not None: n = u32(img, cfg["len_from"]) + cfg["len_add"]
    else: n = len(img) - mo
    app = img[mo:mo + n]
    os.makedirs(a.outdir, exist_ok=True)

    ts, te, sl = find_scatter(app, base)
    lines = [f"application: file 0x{mo:X}, {n:#x} bytes, runs at 0x{base:08X}..0x{base+n:08X}",
             f"__scatterload at 0x{sl:08X}, region table 0x{ts:08X}..0x{te:08X} ({(te-ts)//16} entries)", ""]
    mainfn = f"main_0x{base:08X}.bin"
    open(os.path.join(a.outdir, mainfn), "wb").write(app)
    blocks = [("MAIN", base, mainfn, n)]
    codec = {"decompress_v1": decompress_v1, "decompress_v2": decompress_v2}

    for i, ent in enumerate(range(ts, te, 16)):
        load, ex, size, h = (u32(app, ent - base + k) for k in (0, 4, 8, 12))
        k = handler_kind(app, base, h)
        if k == "zero":
            lines.append(f"[{i:2}] ZERO        exec 0x{ex:08X} size 0x{size:08X}")
            blocks.append((f"ZI_{ex:08X}", ex, None, size)); continue
        if k == "copy":
            data, used = app[load - base:load - base + size], size
        else:
            data, used = codec[k](app, load - base, size)
        fn = f"0x{ex:08X}_{'copy' if k == 'copy' else 'rw'}.bin"
        open(os.path.join(a.outdir, fn), "wb").write(data)
        lines.append(f"[{i:2}] {k.upper():13s} load 0x{load:08X} ({used:#8x} B) -> exec 0x{ex:08X} size 0x{size:08X}  {fn}")
        blocks.append((f"R{i}_{ex:08X}", ex, fn, size))

    # Everything from the first copy/decompress source to the end of the image is the
    # *load view* of other regions (compressed RW, code destined for TCM, ...). It is
    # never executed from here, so mark it as data -- otherwise a disassembler will
    # happily "find" functions inside compressed bytes.
    loads = [u32(app, e - base) for e in range(ts, te, 16)
             if handler_kind(app, base, u32(app, e - base + 12)) != "zero"]
    lo = min(loads)
    lines.append(f"\nload-only data (never executed in place): 0x{lo:08X}..0x{base+n:08X}")
    blocks.append(("LOADONLY", lo, None, base + n - lo))
    open(os.path.join(a.outdir, "regions.txt"), "w").write("\n".join(lines) + "\n")
    with open(os.path.join(a.outdir, "ghidra_blocks.txt"), "w") as f:
        for name, start, fn, size in blocks:
            f.write(f"{name} 0x{start:08X} 0x{size:X} {fn or '-'}\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()

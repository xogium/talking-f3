<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# How to decompile the Zoom F3 (and H4essential) firmware

This guide is for anyone who opens `F3SYSTEM.BIN` in radare2 or Ghidra and gets noise,
because nothing lines up and code can't be told apart from data. That isn't a skill
problem. The file isn't laid out the way the CPU sees memory. Three things have to be
undone first:

1. **The file has Zoom headers and several separate programs in it.** Each program is
   linked to run at a different address.
2. **Everything is Thumb-2 code** (Cortex-M7). A tool left in ARM mode decodes it all as
   nonsense.
3. **The initialised data is compressed.** armlink (Keil / ARM Compiler) compresses
   the RW data, and the program's startup code (`__scatterload`) decompresses it into RAM
   before `main()`. In the raw file, every initialised global, function-pointer table and
   menu/popup definition is compressed bytes. That's what looks like random code.

`tools/f3_unpack.py` undoes all three, and `tools/decompile.sh` runs the whole pipeline
headless. The rest of this guide explains what they do, so you can repeat it by hand or
in another tool.

---

## 1. Quick start

```sh
# Needs python3 and Ghidra 11.x (GHIDRA=/path/to/ghidra_11.x_PUBLIC). About 5-10 min per image.
tools/decompile.sh f3  F3SYSTEM.BIN    work/f3
tools/decompile.sh h4e H4essential.BIN work/h4e
```

You get `work/f3/decompiled.c` (every function, decompiled), `work/f3/unpack/` (the
memory regions) and `work/f3/ghidra/`, a Ghidra project you can open in the GUI to keep
exploring with everything already set up.

Only the unpacking, without Ghidra:

```sh
python3 tools/f3_unpack.py --preset f3       F3SYSTEM.BIN out/main     # application
python3 tools/f3_unpack.py --preset f3-boot1 F3SYSTEM.BIN out/boot1    # boot stage 1
python3 tools/f3_unpack.py --preset f3-boot2 F3SYSTEM.BIN out/boot2    # boot stage 2
python3 tools/f3_unpack.py --preset h4e      H4essential.BIN out/h4e
```

---

## 2. What is in `F3SYSTEM.BIN` (v2.20, 0x7FA300 bytes)

| File offset | Contents | Runs at |
|---|---|---|
| `0x000000` | Zoom header "F3 System Data" (0x100 bytes) | — |
| `0x000100` | **Raw serial-NOR flash image starts here** (file = flash + 0x100) | — |
| `0x000100` | FlexSPI config block (`FCFB` magic), for the boot ROM | — |
| `0x001100` | i.MX RT **IVT** (image vector table, tag `D1 00 20 40`) | — |
| `0x000100`..`0x00A020` | **Boot stage 1**, 0x9F20 bytes. The boot ROM copies it to OCRAM | `0x2020BC00` |
| `0x002100` | stage 1 vector table, flash 0x2000 (SP `0x20230000`, reset `0x2020E015`) | `0x2020DC00` |
| `0x1000F8` | stage 1 length (`0x9F20`) | — |
| `0x100100`..`0x13C2C0` | **Boot stage 2**, a separate ~246 KB program (own font data, a "PowerControl" module); role not confirmed | `0x806DE800` |
| `0x2000F8` | stage 2 length (`0x3C1C0`) + version `"0100"` | — |
| `0x200100` | header "F3 Boot Data" | — |
| `0x200200` | header "F3 Main Data"; **checksum** (BE byte-sum over `[0x200300..EOF)`) at `0x2002FC` | — |
| `0x200300`..`+0x1BE454` | **Application (MAIN)**, copied to SDRAM by the boot code | `0x80000000` |
| `0x7FA2F8` | MAIN `code_length` (`0x1BE454`), then version `"0220"` | — |

How the boot chain works:

- The **i.MX RT1061 boot ROM** reads the FlexSPI config block and the IVT. The IVT's
  `boot_data` says to copy flash `[0 .. 0x9F20)` to `0x2020BC00`, and its entry point is
  `0x2020E014`. That's **stage 1**, a small loader running from on-chip RAM.
- Stage 1 must bring up SDRAM itself (the IVT has no DCD). Then it copies **MAIN**
  (`code_length` bytes from file `0x200300`) to `0x80000000` and jumps to its reset vector.
- **Stage 2's role is not confirmed.** It's linked for SDRAM at `0x806DE800`, inside a
  region MAIN later zeroes, so the two can't both be resident. That means stage 2 runs
  *instead of* MAIN, which fits a recovery program (the F3's Play/Pause-at-power-on
  recovery has to work even if MAIN is broken). But MAIN itself contains the update
  messages ("Invalid Update File!", "No Update Files!", "Complete! Please Power Off"),
  so normal updates may run inside MAIN. Reading stage 1's decision logic (119 functions)
  would settle it.
- All three programs (stage 1, stage 2, MAIN) are separate armlink images. Each has its
  own vector table and its own `__scatterload` table (section 3).

I haven't analysed the boot stages in depth. The presets get them loaded correctly so
you can start.

The **H4essential** (v2.30) is the same family. Its application ("H4essential Main2
Data") is at file `0x19C200`. Its 0x100-byte header sits at `0x7FFFFF00`, so the vector
table lands at `0x80000000`. Its length field (`0x204968`) is at file `0x3382F8`.

---

## 3. armlink scatter-loading: the "compression"

When armlink links an image, it produces a **load view** (what's stored in flash) and an
**execution view** (what's in RAM while it runs). The program's startup code converts one
into the other:

```
Reset_Handler -> __main -> __scatterload:
    for (e = table_start; e < table_end; e += 16)
        e->handler(e->load_addr, e->exec_addr, e->size);
    -> main()
```

Each table entry is four little-endian u32: `load_addr, exec_addr, size, handler`.
`size` is the **output** size. The handler is one of:

- `__scatterload_copy`: plain copy (used for code that runs from TCM/OCRAM).
- `__scatterload_zeroinit`: zero fill (`.bss`).
- `__decompress`: armlink's compressed RW data, an LZ77-style codec.

### Finding the table

`__scatterload` is always the same few instructions:

```
4c xx      ldr  r4, [pc, #..]   ; table_start
4d xx      ldr  r5, [pc, #..]   ; table_end
e0 xx      b    test
e0 68      ldr  r0, [r4, #0xc]  ; handler
...
```

`f3_unpack.py` searches for that pattern, so it should work on other versions too. In F3
v2.20 it's at `0x80000884`, and the table is at `0x801703F4..0x80170464`:

```
[0] DECOMPRESS load 0x80170480 -> exec 0x801F4400 size 0xB8E80   initialised globals (SDRAM)
[1] COPY       load 0x801A8860 -> exec 0x00000000 size 0x00CF0   fast code in ITCM
[2] DECOMPRESS load 0x801A9560 -> exec 0x20000000 size 0x03A20   DTCM data
[3] COPY       load 0x801A96A0 -> exec 0x20240000 size 0x14DB4   code run from OCRAM
[4] ZERO       exec 0x802AD280 size 0x31A0E8                     .bss (SDRAM)
[5] ZERO       exec 0x806DE800 size 0x921318                     .bss incl. record buffers
[6] ZERO       exec 0x20003A20 size 0x16C60                      DTCM .bss
```

So **`0x80170480`..`0x801BE454` in the file is never executed or read in place**. It's
only the source bytes for regions 0 to 3. Disassemblers that try to decode it are where
most of the confusion comes from. And the real initialised data at `0x801F4400..0x802AD280`
doesn't exist in the file at all until you decompress it.

### The two codec variants

Both decoders work on bytes. They read a token byte `t` and repeat until `size` output bytes are written.

**Variant 1** (F3 MAIN and stage 2; code at `0x800008A8`):

```
lit = t & 7;   if (lit == 0) lit = *src++;
n   = t >> 4;  if (n   == 0) n   = *src++;
copy (lit - 1) literal bytes from src to dst
if (t & 8) { d = *src++;  copy n + 2 bytes from dst - d }   // back-reference
else       { write n zero bytes }                           // zero run
```

**Variant 2** (H4essential; code at `0x8000142E`):

```
lit = t & 3;   if (lit == 0) lit = *src++;
n   = t >> 4;  if (n   == 0) n   = *src++;
copy (lit - 1) literal bytes
if (n) {
    d = *src++;
    if ((t & 0xC) == 0xC) d += *src++ << 8;    // 16-bit distance
    else                  d += (t & 0xC) << 6; // 10-bit distance
    copy n + 2 bytes from dst - d
}
```

You can tell them apart by the first instructions. Both begin `push {r4,r5,r6,lr}`.
Variant 1 masks the literal count with `#7`, variant 2 with `#3`.

**Self-check:** each compressed stream should end just before the next region's
`load_addr`. For F3 region 0, the stream is 0x383C6 bytes, so it ends at `0x801A8846`,
just under `0x801A8860`. If your decoder reads past that, it's wrong.

---

## 4. Loading it into Ghidra by hand

`tools/ghidra/ZoomSetup.java` does all of this. By hand:

1. **Import** `main_0x80000000.bin` as *Raw Binary*. Language **ARM v8 LE 32 Cortex**
   (`ARM:LE:32:Cortex`), base address **`0x80000000`**. Don't run auto-analysis yet.
2. **Memory Map → add blocks** for each `0x<exec>_*.bin` from the unpacker, at its exec
   address, initialised from that file. Add each ZERO region as an **uninitialised** block.
3. **Split** the MAIN block at `0x80170480` and clear *Execute* on the second half.
   It's the packed load image (section 3).
4. Add uninitialised **volatile** blocks for the peripherals (`0x40000000`, 256 MB),
   the Cortex-M system space (`0xE0000000`, 1 MB) and the FlexSPI XIP window
   (`0x60000000`), so MMIO accesses show up as addresses.
5. Set the **TMode** context register to 1 over every block (select all → *Set Register
   Values* → TMode = 1). Cortex-M only runs Thumb.
6. Create functions at every vector-table entry: `[0x80000004]` = Reset_Handler, and so on.
7. Turn on **ARM Aggressive Instruction Finder** in *Analysis Options*. A lot of the code
   is only reached through function-pointer tables in RW data. Then run auto-analysis.

On 2 cores, F3 MAIN analyses in about 5 minutes and yields about 2,900 functions.

---

## 5. Doing it in radare2

Ghidra's decompiler gives far more readable results, so it's the one I'd recommend. If you
prefer r2, the same preparation applies. Roughly (check the option names against your
r2 version):

```sh
cd out/main
r2 -a arm -b 16 -e asm.cpu=cortex -m 0x80000000 main_0x80000000.bin
```
```
on 0x801F4400_rw.bin   0x801F4400      # map the decompressed globals
on 0x00000000_copy.bin 0x00000000      # ITCM code
on 0x20000000_rw.bin   0x20000000      # DTCM data
on 0x20240000_copy.bin 0x20240000      # OCRAM
e anal.in=range
e anal.from=0x80000000
e anal.to=0x80170480                  # do NOT analyse the packed load image
af @ 0x80000414                       # Reset_Handler (from the vector table)
aac; aar; aav                         # calls, refs, pointer values
```

The essentials are `-b 16` (Thumb), the base address, and keeping analysis out of
`0x80170480..0x801BE454`. Without those three, r2's output looks the way you described.

---

## 6. Telling code from data, by eye

Once the layout is right, these patterns are reliable on this firmware:

- **Function starts**: `push {..., lr}` is `xx b5` (16-bit) or `2d e9 xx xx` (32-bit).
  Most functions begin with one.
- **Function ends**: `pop {..., pc}` (`xx bd`) or `bx lr` (`70 47`). Whatever follows
  is often a **literal pool**: aligned 32-bit words, usually addresses
  (`0x800xxxxx` code, `0x80xxxxxx` SDRAM, `0x40xxxxxx` peripherals), that `ldr rX, [pc, #..]`
  instructions read. Literal pools are *in the middle of code* and are the
  main source of bad disassembly in linear-sweep tools.
- **Function-pointer tables**: runs of odd values `0x800xxxx1`/`...x9` (Thumb bit set).
  The decompressed RW data has about 37,000 code pointers.
- **Strings**: UI strings are plain ASCII ("Push Keys.", "Calibration", "Low Battery!").
  Most are referenced by numeric *string ID*, not by pointer. F3 string IDs run 1..~550.

---

## 7. Memory map (i.MX RT1061 as used by the F3)

| Range | What |
|---|---|
| `0x00000000` | ITCM (fast code; F3 copies 0xCF0 bytes here) |
| `0x20000000` | DTCM (fast data; stacks) |
| `0x20200000`.. | OCRAM (boot stage 1 runs at `0x2020BC00`; MAIN copies ~85 KB of code to `0x20240000`) |
| `0x40000000`.. | Peripherals (uSDHC1 `0x402C0000`, SAI, LPUART, ...) |
| `0x60000000` | FlexSPI serial NOR, memory-mapped read (XIP); flash offset 0 = file 0x100 |
| `0x80000000` | SDRAM, 16 MB. MAIN code `0x80000000..0x801BE454`, RW `0x801F4400..0x802AD280`, .bss above |
| `0xE0000000` | Cortex-M7 system space (NVIC, SCB, SysTick, MPU, caches) |

---

## 8. Things that will mislead you

- **Loading the whole file at one base.** The four programs (and the headers) each need
  their own base. One base can line up at most one of them.
- **Reading initialised globals from the raw file.** You get compressed bytes. Always
  use the decompressed region.
- **ZI tables look empty.** Many handler/registration tables live in `.bss`
  (`0x802AD280+`), so they're zero in any static view and filled at runtime. That's
  expected, not a decoding error.
- **Ghidra "functions" inside the load image.** If you see functions between
  `0x80170480` and `0x801BE454`, the block is still marked executable.

---

## 9. Known gap in auto-analysis

About nine UI draw callbacks between `0x8001F7A0` and `0x800208B8` are only reached
through function pointers that screen-activation code stores into screen objects
(`movw/movt` pairs, e.g. `0x80020451` for the dialog screen, `0x80020631` for Set
Date/Time). Ghidra's auto-analysis doesn't create functions there. Create them by hand
(Disassemble at the address, then Create Function). Found pointers: 0x8001F7A1,
0x8001F9F9, 0x8001FA79, 0x8001FB89, 0x8001FD31, 0x8001FEA1, 0x80020031, 0x80020451,
0x80020631.

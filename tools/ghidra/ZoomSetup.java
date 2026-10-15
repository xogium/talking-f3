// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
// ZoomSetup.java -- Ghidra pre-script: rebuild the runtime memory map of a Zoom
// F3 / H4essential application image unpacked by f3_unpack.py.
//
//   analyzeHeadless <projdir> <name> -import <out>/main_0x<base>.bin \
//     -processor ARM:LE:32:Cortex -loader BinaryLoader -loader-baseAddr 0x<base> \
//     -scriptPath tools/ghidra -preScript ZoomSetup.java <out>
//
// Reads <out>/ghidra_blocks.txt and:
//  * adds each copied / decompressed region as an initialised block at its RUN address
//    (TCM code, initialised globals -- these are the bytes the CPU really sees);
//  * adds zero-init regions as uninitialised blocks so references to globals resolve;
//  * splits off the LOADONLY tail of the image and marks it non-executable data --
//    it holds the compressed/packed source bytes and must never be disassembled;
//  * fills SDRAM holes and adds peripheral / FlexSPI XIP space as uninitialised
//    volatile blocks (so MMIO accesses show as addresses, not garbage);
//  * forces Thumb mode (TMode=1) on every block -- Cortex-M has no ARM state; a
//    tool left in ARM mode decodes everything as nonsense;
//  * creates functions at every vector-table entry.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.lang.*;
import ghidra.program.model.listing.*;
import java.io.*;
import java.math.BigInteger;
import java.nio.file.*;
import java.util.*;

public class ZoomSetup extends GhidraScript {
  Memory mem;

  MemoryBlock block(String name, long start, long size, byte[] data, boolean x, boolean vol) throws Exception {
    Address a = toAddr(start);
    AddressSet want = new AddressSet(a, a.add(size - 1));
    if (mem.intersects(want)) { println("skip (overlaps) " + name); return null; }
    MemoryBlock b = (data != null)
        ? mem.createInitializedBlock(name, a, new ByteArrayInputStream(data), data.length, monitor, false)
        : mem.createUninitializedBlock(name, a, size, false);
    b.setRead(true); b.setWrite(!x || start < 0x20000000L); b.setExecute(x); b.setVolatile(vol);
    println(String.format("block %-14s 0x%08X +0x%X %s%s", name, start, size,
            data != null ? "init" : "uninit", x ? " exec" : ""));
    return b;
  }

  public void run() throws Exception {
    mem = currentProgram.getMemory();
    String dir = getScriptArgs()[0];
    MemoryBlock main = mem.getBlocks()[0];
    long mainStart = main.getStart().getOffset(), mainEnd = main.getEnd().getOffset() + 1;
    main.setName("MAIN"); main.setExecute(true); main.setWrite(false);

    for (String ln : Files.readAllLines(Paths.get(dir, "ghidra_blocks.txt"))) {
      String[] p = ln.trim().split("\\s+");
      if (p.length < 4 || p[0].equals("MAIN")) continue;
      long start = Long.decode(p[1]), size = Long.decode(p[2]);
      if (p[0].equals("LOADONLY")) {                  // split MAIN, mark the tail as data
        mem.split(main, toAddr(start));
        MemoryBlock t = mem.getBlock(toAddr(start));
        t.setName("LOAD_IMAGE"); t.setExecute(false); t.setWrite(false);
        println(String.format("block LOAD_IMAGE     0x%08X +0x%X data (packed sources)", start, size));
        continue;
      }
      byte[] data = p[3].equals("-") ? null : Files.readAllBytes(Paths.get(dir, p[3]));
      // Executable: anything in ITCM (0x0..), or a *copied* region (code relocated to TCM/OCRAM);
      // decompressed regions are initialised data.
      boolean exec = data != null && (start < 0x20000000L || p[3].endsWith("_copy.bin"));
      block(p[0], start, size, data, exec, false);
    }

    // Fill holes in SDRAM 0x80000000..0x81000000 (and before the image, e.g. H4e header).
    long cur = 0x80000000L;
    List<MemoryBlock> bs = new ArrayList<>(Arrays.asList(mem.getBlocks()));
    bs.sort(Comparator.comparingLong(b -> b.getStart().getOffset()));
    int gap = 0;
    for (MemoryBlock b : bs) {
      long s = b.getStart().getOffset(), e = b.getEnd().getOffset() + 1;
      if (e <= 0x80000000L || s >= 0x81000000L) continue;
      if (s > cur) block("SDRAM_gap" + (gap++), cur, s - cur, null, false, false);
      cur = Math.max(cur, e);
    }
    if (cur < 0x81000000L) block("SDRAM_gap" + gap, cur, 0x81000000L - cur, null, false, false);
    block("PERIPH",      0x40000000L, 0x10000000L, null, false, true);   // i.MX RT AIPS/AHB
    block("PPB",         0xE0000000L, 0x00100000L, null, false, true);   // NVIC, SCB, SysTick
    block("FLEXSPI_XIP", 0x60000000L, 0x01000000L, null, false, true);   // serial NOR window

    Register tm = currentProgram.getProgramContext().getRegister("TMode");
    for (MemoryBlock b : mem.getBlocks())
      if (b.isInitialized())
        currentProgram.getProgramContext().setValue(tm, b.getStart(), b.getEnd(), BigInteger.ONE);

    // Vector table: [0]=initial SP (in TCM/OCRAM), [1]=reset (Thumb pointer into the image).
    // Application images have it at their start (0x80000000); boot stage 1 has it after
    // the FlexSPI config block and IVT. Take the first 256-byte-aligned match.
    long vt = -1;
    for (long o = mainStart; o < Math.min(mainEnd, mainStart + 0x4000); o += 0x100) {
      long sp = getInt(toAddr(o)) & 0xFFFFFFFFL, rs = getInt(toAddr(o + 4)) & 0xFFFFFFFFL;
      if (sp >= 0x20000000L && sp < 0x20300000L && (sp & 3) == 0 && (rs & 1) == 1
          && (rs & ~1L) >= mainStart && (rs & ~1L) < mainEnd) { vt = o; break; }
    }
    if (vt < 0) { println("no vector table found"); vt = mainStart; }
    else println(String.format("vector table at 0x%08X", vt));
    for (int i = 1; i < 256; i++) {
      long v = getInt(toAddr(vt + 4L * i)) & 0xFFFFFFFFL;
      if (v == 0) continue;
      boolean inCode = (v < 0x10000L) || (v >= mainStart && v < mainEnd);
      if ((v & 1) == 0 || !inCode) break;
      Address fa = toAddr(v & ~1L);
      addEntryPoint(fa);
      if (getFunctionAt(fa) == null) createFunction(fa, i == 1 ? "Reset_Handler" : String.format("vec_%03d", i));
    }
    // Finds code only reachable through function-pointer tables. Safe now that the
    // packed load image is a non-executable block.
    setAnalysisOption(currentProgram, "ARM Aggressive Instruction Finder", "true");
    println("ZoomSetup done");
  }
}

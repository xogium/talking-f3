// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
// ExportAllC.java -- Ghidra post-script: write the decompiled C of every function
// to one text file, in address order, with callers listed above each function.
//   ... -postScript ExportAllC.java /path/to/out.c
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;

public class ExportAllC extends GhidraScript {
  public void run() throws Exception {
    String out = getScriptArgs()[0];
    DecompInterface di = new DecompInterface();
    di.toggleCCode(true); di.toggleSyntaxTree(false);
    di.openProgram(currentProgram);
    int n = 0, fail = 0;
    try (PrintWriter pw = new PrintWriter(new BufferedWriter(new FileWriter(out)))) {
      pw.println("/* Decompiled from " + currentProgram.getName() + " ("
                 + currentProgram.getLanguageID() + ") -- Ghidra " + getGhidraVersion() + " */");
      for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
        if (monitor.isCancelled()) break;
        if (f.isThunk() && f.getBody().getNumAddresses() <= 4) continue;
        StringBuilder cl = new StringBuilder();
        int k = 0;
        for (Reference r : getReferencesTo(f.getEntryPoint())) {
          if (!r.getReferenceType().isCall() && !r.getReferenceType().isJump()) continue;
          Function c = getFunctionContaining(r.getFromAddress());
          if (k++ < 12) cl.append(c == null ? r.getFromAddress().toString() : c.getName()).append(' ');
        }
        pw.println("\n/* ==== " + f.getName() + " @ " + f.getEntryPoint()
                   + "  size " + f.getBody().getNumAddresses()
                   + (k > 0 ? "  callers(" + k + "): " + cl : "") + " */");
        DecompileResults dr = di.decompileFunction(f, 90, monitor);
        if (dr.decompileCompleted()) pw.print(dr.getDecompiledFunction().getC());
        else { pw.println("/* decompile failed: " + dr.getErrorMessage() + " */"); fail++; }
        n++;
      }
    }
    println("ExportAllC: " + n + " functions (" + fail + " failed) -> " + out);
  }
}

#!/bin/sh
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
# decompile.sh -- unpack a Zoom firmware image and decompile it with Ghidra, headless.
#
#   tools/decompile.sh f3  F3SYSTEM.BIN     work/f3
#   tools/decompile.sh h4e H4essential.BIN  work/h4e
#
# Produces in <workdir>:
#   unpack/              regions, decompressed RW data, TCM code (see f3_unpack.py)
#   ghidra/              a Ghidra project you can open in the GUI afterwards
#   decompiled.c         every function, decompiled, in address order
#   analysis.log         Ghidra's log
# Needs: python3, Ghidra 11.x (set GHIDRA=/path/to/ghidra_11.x_PUBLIC), ~4 GB RAM.
# Takes ~5-10 min per image on 2 cores.
set -e
PRESET=$1; IMAGE=$2; WORK=$3
[ -n "$WORK" ] || { sed -n 2,13p "$0"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
GHIDRA=${GHIDRA:-/tmp/ghidra_11.3_PUBLIC}
mkdir -p "$WORK/ghidra"
python3 "$HERE/f3_unpack.py" --preset "$PRESET" "$IMAGE" "$WORK/unpack"
MAINBIN=$(ls "$WORK"/unpack/main_0x*.bin)
BASE=0x$(basename "$MAINBIN" .bin | sed 's/main_0x//')
"$GHIDRA/support/analyzeHeadless" "$WORK/ghidra" "$PRESET" \
  -import "$MAINBIN" -overwrite \
  -processor ARM:LE:32:Cortex -loader BinaryLoader -loader-baseAddr "$BASE" \
  -scriptPath "$HERE/ghidra" \
  -preScript ZoomSetup.java "$WORK/unpack" \
  -postScript ExportAllC.java "$WORK/decompiled.c" \
  -analysisTimeoutPerFile 3600 > "$WORK/analysis.log" 2>&1
grep -E "ZoomSetup|ExportAllC:|REPORT" "$WORK/analysis.log" | sed 's/^INFO  //'

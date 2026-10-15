#!/bin/sh
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
# Assemble the public repository (GitHub Pages serves its root): the patcher as index.html,
# the F3 guide, the documentation and all source. Never Zoom's firmware, never build output.
#   sh tools/make_public_repo.sh OUTDIR        (build dist/talking-f3-patcher.html first)
set -e
cd "$(dirname "$0")/.."
OUT=${1:?usage: make_public_repo.sh OUTDIR}
[ -f dist/talking-f3-patcher.html ] || { echo "build the patcher first (patcher/build_patcher.py)"; exit 1; }
python3 tools/spdx_headers.py --check
mkdir -p "$OUT"
# start clean, but keep the target's git history
find "$OUT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp dist/talking-f3-patcher.html "$OUT/index.html"
cp docs/Zoom_menu.md "$OUT/Zoom_menu.md"
cp README.md LICENSE TECHNICAL.md RE_REFERENCE.md HOW_TO_DECOMPILE.md METHOD.md EMULATION.md \
   F3_strings_all_langs.json .gitignore "$OUT/"
mkdir -p "$OUT/arm" "$OUT/tools/emu" "$OUT/tools/ghidra" "$OUT/patcher/src" "$OUT/patcher/wasm" \
         "$OUT/patcher/test" "$OUT/third_party"
cp arm/voice.c arm/voice.h arm/voice.ld arm/trampolines.S arm/thumb_branch.py arm/opus_glue.c \
   arm/opus_cfg.h arm/exports.c arm/build.sh "$OUT/arm/"
cp tools/*.py tools/*.sh tools/opus_tool.c "$OUT/tools/"
cp tools/emu/*.py tools/emu/README.md "$OUT/tools/emu/"
cp tools/ghidra/*.java "$OUT/tools/ghidra/"
cp patcher/README.md patcher/build_patcher.py patcher/export_data.py "$OUT/patcher/"
cp patcher/src/core.js patcher/src/page.html "$OUT/patcher/src/"
cp patcher/wasm/f3speak.c patcher/wasm/f3opus.c patcher/wasm/espeak_config.h \
   patcher/wasm/build_wasm.sh "$OUT/patcher/wasm/"
cp patcher/test/*.js "$OUT/patcher/test/"
cp -r third_party/opus third_party/sonic "$OUT/third_party/"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +
# safety: nothing firmware-like or built may be in the tree
if find "$OUT" -path "$OUT/.git" -prune -o -type f \( -iname "*.bin" -o -name "*.elf" -o -name "*.o" \) -print | grep -q .; then
  echo "ABORT: binary files in $OUT"; exit 1
fi
echo "public repository assembled in $OUT ($(find "$OUT" -path "$OUT/.git" -prune -o -type f -print | wc -l) files)"

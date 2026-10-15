#!/bin/sh
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
# Build one Opus bank per F3 UI language and join them into one flash blob.
# usage: tools/gen_all_banks.sh [kbps]   -> build/flash_bank_all/flash_bank.bin
set -e
cd "$(dirname "$0")/.."
KBPS=${1:-16}
for L in EN FR DE IT ES L5 L6; do  # pip: pypinyin pykakasi
  python3 tools/gen_flash_bank.py --kbps $KBPS --lang $L \
      --out build/banks/$L > build/banks_$L.log 2>&1 &
done
wait
mkdir -p build/flash_bank_all
python3 - <<'PY'
blob = bytearray()
for L in ["EN", "FR", "DE", "IT", "ES", "L5", "L6"]:
    b = open(f"build/banks/{L}/flash_bank.bin", "rb").read()
    blob += b; blob += b"\0" * ((-len(blob)) % 16)
    print(f"  {L}: {len(b)/1024:.0f} KB")
open("build/flash_bank_all/flash_bank.bin", "wb").write(blob)
print(f"all languages: {len(blob)/1048576:.2f} MB")
PY

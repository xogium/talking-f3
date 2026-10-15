#!/bin/sh
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
# Build the host Opus encoder/decoder helper (tools/opus_tool) from the vendored libopus.
set -e
cd "$(dirname "$0")/.."
O=third_party/opus
SRC="$(sed -n '/^SILK_SOURCES =/,/^$/p' $O/silk_sources.mk | grep '\.c' | tr -d '\\')
$(sed -n '/^SILK_SOURCES_FIXED =/,/^$/p' $O/silk_sources.mk | grep '\.c' | tr -d '\\')
$(sed -n '/^CELT_SOURCES =/,/^$/p' $O/celt_sources.mk | grep '\.c' | tr -d '\\')
src/opus.c src/opus_decoder.c src/opus_encoder.c src/extensions.c src/repacketizer.c
src/analysis.c src/mlp.c src/mlp_data.c"
FILES=""; for f in $SRC; do FILES="$FILES $O/$f"; done
gcc -O2 -w -DFIXED_POINT -DOPUS_BUILD -DVAR_ARRAYS -DHAVE_LRINTF -DHAVE_LRINT \
    -I$O/include -I$O/celt -I$O/silk -I$O/silk/fixed -I$O \
    tools/opus_tool.c $FILES -lm -o tools/opus_tool
echo "built tools/opus_tool"

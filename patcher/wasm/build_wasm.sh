#!/bin/sh
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
# Build the patcher's two WebAssembly modules and the espeak-ng data subset.
#   needs: python3 -m pip install ziglang ; git ; cmake + a C compiler (to compile espeak data)
# Output: patcher/wasm/out/{f3speak.wasm, f3opus.wasm, espeak-data/}
set -e
cd "$(dirname "$0")"
OUT=$PWD/out; mkdir -p $OUT
ES=${ESPEAK_SRC:-$PWD/espeak-ng-1.52.0}
if [ ! -d "$ES" ]; then git clone -q --depth 1 --branch 1.52.0 https://github.com/espeak-ng/espeak-ng.git "$ES"; fi
# 1) native build, only to compile the espeak-ng data (phoneme tables, dictionaries)
if [ ! -f "$ES/native/espeak-ng-data/phontab" ]; then
  cmake -S "$ES" -B "$ES/native" -DUSE_MBROLA=OFF -DUSE_LIBSONIC=OFF -DUSE_LIBPCAUDIO=OFF \
        -DUSE_ASYNC=OFF -DESPEAK_BUILD_MANPAGES=OFF -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build "$ES/native" -j8 >/dev/null
fi
# 2) data subset: the 7 F3 languages + all voice variants
D=$ES/native/espeak-ng-data; S=$OUT/espeak-data/espeak-ng-data
rm -rf $OUT/espeak-data; mkdir -p $S/lang/gmw $S/lang/roa $S/lang/sit $S/lang/jpx $S/voices
cp $D/phontab $D/phonindex $D/phondata $D/intonations $S/
for d in en fr de it es cmn ja; do cp $D/${d}_dict $S/; done
for f in gmw/en gmw/de roa/fr roa/it roa/es sit/cmn sit/cmn-Latn-pinyin jpx/ja; do cp $D/lang/$f $S/lang/$f; done
cp -r "$D/voices/!v" $S/voices/
# 3) espeak-ng -> WASI reactor (synchronous synthesis, callback collects samples)
L=$ES/src/libespeak-ng; U=$ES/src/ucd-tools/src
SRCS=""; for f in common mnemonics error ieee80 dictionary encoding intonation langopts numbers \
  phoneme phonemelist readclause setlengths soundicon spect ssml synthdata synthesize tr_languages \
  translate translateword voices wavegen speech espeak_api klatt compiledata compiledict; do SRCS="$SRCS $L/$f.c"; done
for f in case categories ctype proplist scripts tostring; do SRCS="$SRCS $U/$f.c"; done
mkdir -p cfg; cp espeak_config.h cfg/config.h
python3 -m ziglang cc -target wasm32-wasi -O2 -s -mexec-model=reactor -Icfg -I$ES/src/include -I$U/include -I$L \
  -DLIBESPEAK_NG_EXPORT=1 '-DPATH_ESPEAK_DATA="/espeak-ng-data"' -fwrapv -w f3speak.c $SRCS -o $OUT/f3speak.wasm
# 4) libopus encoder (same vendored 1.5.2 + fixed point as tools/opus_tool) -> WASI reactor
O=../../third_party/opus
F=""; for f in $(sed -n '/^SILK_SOURCES =/,/^$/p' $O/silk_sources.mk | grep '\.c' | tr -d '\\') \
  $(sed -n '/^SILK_SOURCES_FIXED =/,/^$/p' $O/silk_sources.mk | grep '\.c' | tr -d '\\') \
  $(sed -n '/^CELT_SOURCES =/,/^$/p' $O/celt_sources.mk | grep '\.c' | tr -d '\\') \
  src/opus.c src/opus_decoder.c src/opus_encoder.c src/extensions.c src/repacketizer.c src/analysis.c src/mlp.c src/mlp_data.c; do F="$F $O/$f"; done
python3 -m ziglang cc -target wasm32-wasi -O2 -s -mexec-model=reactor -w -DFIXED_POINT -DOPUS_BUILD -DVAR_ARRAYS \
  -DHAVE_LRINTF -DHAVE_LRINT -I$O/include -I$O/celt -I$O/silk -I$O/silk/fixed -I$O f3opus.c $F -o $OUT/f3opus.wasm
ls -la $OUT/*.wasm; du -sh $OUT/espeak-data

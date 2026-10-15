#!/bin/sh
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
# Build the voice module (Opus engine + libopus decoder) -> arm/voice<suffix>.bin/.elf
# usage: sh build.sh [suffix] [-DDIAG=1 ...]      e.g.  sh build.sh _probe -DOPUS_PROBE=1
# The product is built with no extra defines. Output level / chime / volume-follow are
# runtime settings in the .cfg block (patched by tools/build_flash_image.py or the patcher).
set -e
cd "$(dirname "$0")"
SUF="$1"; [ $# -gt 0 ] && shift
O=../third_party/opus
CPU="-mcpu=cortex-m7 -mthumb -mfloat-abi=hard -mfpu=fpv5-d16"
# libopus: fixed point, decode only, ARMv7E-M DSP inline asm, static pseudo-stack
OF="$CPU -O2 -ffunction-sections -fdata-sections -fno-common -w \
   -include $PWD/opus_cfg.h -DFIXED_POINT -DDISABLE_FLOAT_API -DOPUS_BUILD \
   -DNONTHREADSAFE_PSEUDOSTACK -DGLOBAL_STACK_SIZE=8000 -DOVERRIDE_OPUS_ALLOC_SCRATCH \
   -DHAVE_LRINTF -DOPUS_ARM_INLINE_EDSP -DOPUS_ARM_INLINE_MEDIA -DOPUS_ARM_ASM \
   -I$O/include -I$O/celt -I$O/silk -I$O/silk/fixed -I$O"
if [ ! -f opus_obj/.done ]; then
  rm -rf opus_obj; mkdir opus_obj
  SRC="$(sed -n '/^SILK_SOURCES =/,/^$/p' $O/silk_sources.mk | grep '\.c' | tr -d '\\')
$(sed -n '/^SILK_SOURCES_FIXED =/,/^$/p' $O/silk_sources.mk | grep '\.c' | tr -d '\\')
$(sed -n '/^CELT_SOURCES =/,/^$/p' $O/celt_sources.mk | grep '\.c' | tr -d '\\')
src/opus.c src/opus_decoder.c src/extensions.c"
  for f in $SRC; do arm-none-eabi-gcc $OF -c $O/$f -o opus_obj/$(echo $f | tr / _).o; done
  touch opus_obj/.done
fi
CF="$CPU -Os -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -Wall -Wextra \
    -I$O/include $*"
T=$(mktemp -d)
arm-none-eabi-gcc $CF -c voice.c       -o $T/voice.o
arm-none-eabi-gcc $CF -c exports.c     -o $T/exports.o
arm-none-eabi-gcc $CF -c opus_glue.c   -o $T/opus_glue.o
arm-none-eabi-gcc $CF -c trampolines.S -o $T/trampolines.o
arm-none-eabi-gcc $CPU -nostdlib -Wl,--gc-sections -Wl,--no-undefined \
    -Wl,-u,voice_exports -Wl,-u,tramp_audio_out -Wl,-u,g_cfg $EXTRA_LD \
    -T voice.ld $T/exports.o $T/voice.o $T/opus_glue.o $T/trampolines.o opus_obj/*.o \
    -o voice$SUF.elf -lgcc
arm-none-eabi-objcopy -O binary voice$SUF.elf voice$SUF.bin
rm -rf $T
echo "voice$SUF.bin: $(wc -c < voice$SUF.bin) bytes, _end 0x$(arm-none-eabi-nm voice$SUF.elf | awk '$3=="_end"{print $1}') $*"

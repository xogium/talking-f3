/* SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
 * SPDX-License-Identifier: MIT */
/* Module image: runtime 0x801BFD00 (file 0x3C0000 of F3SYSTEM.BIN). Everything incl. .bss
 * must end below 0x801F4400, where the firmware's initialised RW data starts; the image
 * builder checks this and zero-fills .bss in the image. */
MEMORY { VOICE (rwx) : ORIGIN = 0x801BFD00, LENGTH = 0x34700 }
SECTIONS {
  .exports 0x801BFD00 : { KEEP(*(.exports)) } > VOICE
  .cfg     0x801BFD20 : { KEEP(*(.cfg)) } > VOICE
  .text   : { *(.text* .rodata*) } > VOICE
  .data   : { *(.data*) }          > VOICE
  .bss    : { *(.bss* COMMON) }    > VOICE
  _end = .;
  /DISCARD/ : { *(.ARM.exidx* .comment .note*) }
}

/* SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
 * SPDX-License-Identifier: MIT */
    .syntax unified
    .thumb
/* The one detour: AudioProcess task, patched at 0x80010F3E (b.w here) -- just BEFORE
 * loop2, which copies the full 128-frame B2 -> the DMA output half.
 * At entry:
 *   r0 = B2  (CPU-side staging buffer loop2 reads from; safe to overwrite)
 *   r4 = DMA output half  (passed to the engine as a reserved/unused arg)
 *   r6 = task control block
 * We tick (init+poll) and, while speaking, overlay voice into all 128 frames of
 * B2; the firmware's own loop2 then carries it out the DMA-safe way. We preserve
 * r0 (=B2), loop2's source base. Run the displaced sub.w, return to 0x80010F42.
 * NOTE: loop2 is left STOCK -- we never widen its count (that overruns). */
    .section .text.tramp,"ax",%progbits
    .thumb_func
    .global tramp_audio_out
tramp_audio_out:
    push    {r0-r3, r12, lr}     @ save caller-saved (r0 = B2)
    bl      voice_tick           @ ensure_init() + voice_poll()
    ldr     r0, [sp, #0]         @ reload B2 (arg0 for fill)
    mov     r1, r4               @ arg1 = DMA output half (reserved; engine ignores it)
    bl      voice_fill_half      @ fill all 128 B2 frames with voice if active
    pop     {r0-r3, r12, lr}     @ restore r0 = B2 (loop2's source base)
    sub.w   r1, r4, #0x40        @ displaced original instruction (verbatim)
    ldr.w   pc, =0x80010F43      @ return to 0x80010F42 (thumb bit set)

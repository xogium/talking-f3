// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
#include <stdint.h>
#include "voice.h"
/* Jump table at the module base (0x801BFD00), followed by the settings block (.cfg at
 * 0x801BFD20, see voice.h). The firmware reaches the module only through tramp_audio_out;
 * the table documents the entry points and keeps them at stable addresses. */
__attribute__((section(".exports"), used))
void * const voice_exports[] = {
    (void *)voice_init,       /* [0] */
    (void *)voice_poll,       /* [1] */
    (void *)voice_fill_half,  /* [2] */
    (void *)voice_active,     /* [3] */
    (void *)voice_start,      /* [4] */
    (void *)voice_tick,       /* [5] */
};

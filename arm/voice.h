// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
#ifndef VOICE_H
#define VOICE_H
#include <stdint.h>
/* F3 talking firmware: voice engine interface. */

/* Settings the web patcher may change in a built image (section .cfg, fixed address
 * 0x801BFD20 = module base + 0x20). Layout is an ABI with tools/patcher: append only. */
#define VOICE_CFG_MAGIC 0x47464356u   /* 'VCFG' */
typedef struct {
    uint32_t magic;
    uint8_t  samp_shift;   /* output level: 16-bit sample << samp_shift (0..15) */
    uint8_t  chime;        /* 1 = startup chime */
    uint8_t  vol_follow;   /* 1 = follow the headphone VOLUME level */
    uint8_t  reserved;
} voice_cfg_t;

void voice_init(void);                          /* find banks, start the decode task */
void voice_tick(void);                          /* every audio tick: init, language, chime, poll */
void voice_poll(void);                          /* screen poll: decides what to say */
void voice_start(uint32_t clip_id);             /* start one clip (slot = string id) */
int  voice_active(void);                        /* 1 while a clip is playing */
int  voice_fill_half(int32_t *b2, int32_t *dma);/* fill B2 with voice; 0 = idle, B2 untouched */
void voice_dec_step(void);                      /* one step of the decode task (and emulator) */
#endif

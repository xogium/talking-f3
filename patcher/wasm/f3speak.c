// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
/* f3speak: espeak-ng as a WebAssembly (WASI reactor) synth library for the F3 patcher.
 * Synchronous mode; samples (22050 Hz mono s16) are collected into one growing buffer. */
#include <stdlib.h>
#include <string.h>
#include <espeak-ng/speak_lib.h>
#define EXPORT(n) __attribute__((export_name(n)))
static short *g_buf; static int g_len, g_cap, g_rate;
static int cb(short *wav, int n, espeak_EVENT *ev){
    (void)ev;
    if (!wav || n <= 0) return 0;
    if (g_len + n > g_cap){ int c = g_cap ? g_cap : 1 << 16; while (c < g_len + n) c *= 2;
        short *b = realloc(g_buf, (size_t)c * 2); if (!b) return 1; g_buf = b; g_cap = c; }
    memcpy(g_buf + g_len, wav, (size_t)n * 2); g_len += n;
    return 0;
}
EXPORT("f3_alloc") void *f3_alloc(int n){ return malloc((size_t)n); }
EXPORT("f3_free") void f3_free(void *p){ free(p); }
EXPORT("f3_init") int f3_init(const char *path){
    g_rate = espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, path, 0);
    if (g_rate <= 0) return g_rate;
    espeak_SetSynthCallback(cb);
    return g_rate;
}
EXPORT("f3_voice") int f3_voice(const char *name){ return espeak_SetVoiceByName(name); }
EXPORT("f3_param") int f3_param(int which, int value){   /* 1 rate, 3 pitch, 2 volume */
    return espeak_SetParameter((espeak_PARAMETER)which, value, 0);
}
EXPORT("f3_synth") int f3_synth(const char *utf8){
    g_len = 0;
    int r = espeak_Synth(utf8, strlen(utf8) + 1, 0, POS_CHARACTER, 0, espeakCHARS_UTF8, NULL, NULL);
    if (r != EE_OK) return -r;
    espeak_Synchronize();
    return g_len;
}
EXPORT("f3_buf") short *f3_buf(void){ return g_buf; }
/* soundicon.c references tmpnam (only for wav file sound icons, unused here) */
char *tmpnam(char *s){ (void)s; return 0; }

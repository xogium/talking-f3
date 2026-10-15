// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
/* opus_tool enc <bitrate> <frame_ms> [music] [rate=24000] < pcm_s16le > packets   ([u16 len][data]...)
 * opus_tool dec [rate=24000] < packets > pcm_s16le
 * rate: 16000 (default, wideband) or 24000 (super-wideband) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <opus.h>
static int FS = 16000;
int main(int argc, char **argv) {
    int err;
    for (int i = 2; i < argc; i++) if (!strncmp(argv[i], "rate=", 5)) FS = atoi(argv[i] + 5);
    if (FS != 8000 && FS != 16000 && FS != 24000) { fprintf(stderr, "rate must be 8000, 16000 or 24000\n"); return 1; }
    if (argc >= 4 && !strcmp(argv[1], "enc")) {
        int br = atoi(argv[2]), fms = atoi(argv[3]), fn = FS * fms / 1000;
        int music = 0; for (int i = 4; i < argc; i++) if (!strcmp(argv[i], "music")) music = 1;
        OpusEncoder *e = opus_encoder_create(FS, 1, music ? OPUS_APPLICATION_AUDIO : OPUS_APPLICATION_VOIP, &err);
        opus_encoder_ctl(e, OPUS_SET_BITRATE(br));
        opus_encoder_ctl(e, OPUS_SET_COMPLEXITY(10));
        opus_encoder_ctl(e, OPUS_SET_SIGNAL(music ? OPUS_SIGNAL_MUSIC : OPUS_SIGNAL_VOICE));
        opus_encoder_ctl(e, OPUS_SET_BANDWIDTH(FS >= 24000 ? OPUS_BANDWIDTH_SUPERWIDEBAND : FS >= 16000 ? OPUS_BANDWIDTH_WIDEBAND : OPUS_BANDWIDTH_NARROWBAND));
        int16_t pcm[960 * 3]; unsigned char pkt[1500];
        size_t n;
        for (;;) {
            memset(pcm, 0, sizeof pcm);
            n = fread(pcm, 2, fn, stdin);
            if (n == 0) break;
            int len = opus_encode(e, pcm, fn, pkt, sizeof pkt);
            unsigned char h[2] = { len & 255, len >> 8 };
            fwrite(h, 1, 2, stdout); fwrite(pkt, 1, len, stdout);
            if (n < (size_t)fn) break;
        }
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "dec")) {
        OpusDecoder *d = opus_decoder_create(FS, 1, &err);
        unsigned char h[2], pkt[1500]; int16_t pcm[960 * 3];
        while (fread(h, 1, 2, stdin) == 2) {
            int len = h[0] | h[1] << 8;
            if (fread(pkt, 1, len, stdin) != (size_t)len) break;
            int ns = opus_decode(d, pkt, len, pcm, 960 * 3, 0);
            fwrite(pcm, 2, ns, stdout);
        }
        return 0;
    }
    fprintf(stderr, "usage\n"); return 1;
}

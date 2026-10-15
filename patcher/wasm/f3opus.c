// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
/* f3opus: libopus encoder as WebAssembly for the F3 patcher (mono 8, 16 or 24 kHz, packets out) + decoder
 * (for the patcher's sample, so it plays at the chosen quality). */
#include <stdlib.h>
#include <opus.h>
#define EXPORT(n) __attribute__((export_name(n)))
EXPORT("op_alloc") void *op_alloc(int n){ return malloc((size_t)n); }
EXPORT("op_free") void op_free(void *p){ free(p); }
/* music = 0: speech (VOIP, SILK); 1: the chime (AUDIO) */
EXPORT("op_enc_new") OpusEncoder *op_enc_new(int rate, int bitrate, int music){
    int err;
    OpusEncoder *e = opus_encoder_create(rate, 1, music ? OPUS_APPLICATION_AUDIO : OPUS_APPLICATION_VOIP, &err);
    if (!e) return 0;
    opus_encoder_ctl(e, OPUS_SET_BITRATE(bitrate));
    opus_encoder_ctl(e, OPUS_SET_COMPLEXITY(10));
    opus_encoder_ctl(e, OPUS_SET_SIGNAL(music ? OPUS_SIGNAL_MUSIC : OPUS_SIGNAL_VOICE));
    opus_encoder_ctl(e, OPUS_SET_BANDWIDTH(rate >= 24000 ? OPUS_BANDWIDTH_SUPERWIDEBAND : rate >= 16000 ? OPUS_BANDWIDTH_WIDEBAND : OPUS_BANDWIDTH_NARROWBAND));
    return e;
}
EXPORT("op_enc_free") void op_enc_free(OpusEncoder *e){ opus_encoder_destroy(e); }
EXPORT("op_encode") int op_encode(OpusEncoder *e, const short *pcm, int n, unsigned char *out, int max){
    return opus_encode(e, pcm, n, out, max);
}
EXPORT("op_dec_new") OpusDecoder *op_dec_new(int rate){ int err; return opus_decoder_create(rate, 1, &err); }
EXPORT("op_dec_free") void op_dec_free(OpusDecoder *d){ opus_decoder_destroy(d); }
EXPORT("op_decode") int op_decode(OpusDecoder *d, const unsigned char *pkt, int len, short *pcm, int max){
    return opus_decode(d, pkt, len, pcm, max, 0);
}

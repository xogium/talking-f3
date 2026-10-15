// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
/* Minimal libc for the linked libopus decoder (it only needs these three).
 * Word loops when aligned: opus_decoder_init clears ~18 KB of state on every clip start. */
#include <stddef.h>
#include <stdint.h>
void *memcpy(void *d, const void *s, size_t n){
    unsigned char *a = d; const unsigned char *b = s;
    if ((((uintptr_t)a | (uintptr_t)b) & 3u) == 0){
        uint32_t *wa = (uint32_t*)a; const uint32_t *wb = (const uint32_t*)b;
        while (n >= 16){ wa[0] = wb[0]; wa[1] = wb[1]; wa[2] = wb[2]; wa[3] = wb[3]; wa += 4; wb += 4; n -= 16; }
        while (n >= 4){ *wa++ = *wb++; n -= 4; }
        a = (unsigned char*)wa; b = (const unsigned char*)wb;
    }
    while (n--) *a++ = *b++;
    return d;
}
void *memset(void *d, int c, size_t n){
    unsigned char *a = d;
    while (n && ((uintptr_t)a & 3u)){ *a++ = (unsigned char)c; n--; }
    uint32_t w = (unsigned char)c; w |= w << 8; w |= w << 16;
    uint32_t *wa = (uint32_t*)a;
    while (n >= 16){ wa[0] = w; wa[1] = w; wa[2] = w; wa[3] = w; wa += 4; n -= 16; }
    while (n >= 4){ *wa++ = w; n -= 4; }
    a = (unsigned char*)wa;
    while (n--) *a++ = (unsigned char)c;
    return d;
}
void *memmove(void *d, const void *s, size_t n){
    unsigned char *a = d; const unsigned char *b = s;
    if (a == b || n == 0) return d;
    if (a < b || a >= b + n) return memcpy(d, s, n);
    a += n; b += n;
    if ((((uintptr_t)a | (uintptr_t)b | n) & 3u) == 0){
        uint32_t *wa = (uint32_t*)a; const uint32_t *wb = (const uint32_t*)b;
        while (n >= 4){ *--wa = *--wb; n -= 4; }
        return d;
    }
    while (n--) *--a = *--b;
    return d;
}

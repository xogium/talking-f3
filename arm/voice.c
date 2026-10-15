// SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
// SPDX-License-Identifier: MIT
/* F3 talking firmware -- voice engine  (Zoom F3 v2.20, NXP i.MX RT1061, Cortex-M7)
 * ---------------------------------------------------------------------------------
 * Runs inside the stock firmware from a free SDRAM gap (0x801BFD00..0x801F4400) and speaks
 * what is on screen: menus, popups, dialogs, Date/Time, Finder, Playback, file INFO,
 * Versions, magnification, and an on-demand status on Stop. Clips are pre-synthesized
 * (espeak-ng), Opus-coded, one bank per UI language, read in place from flash (XIP).
 * See TECHNICAL.md for the full picture and RE_REFERENCE.md for every address used.
 *
 * Execution contexts
 *   AudioProcess task (FreeRTOS prio 30): one detour at 0x80010F3E (tramp_audio_out) calls
 *     voice_tick() (lazy init, language follow, chime, screen poll) and voice_fill_half()
 *     every DMA half (128 stereo int32 frames, at 2x the record rate). While speaking we
 *     fill ALL 128 frames of B2, which the firmware's own loop2 then copies to the DMA half;
 *     while idle we leave B2 alone, so monitoring is byte-identical to stock. loop2 is
 *     never patched. Nothing slow runs here: the fill only reads a PCM ring.
 *   VoiceDecode task (ours, prio 2): created at init with the firmware's xTaskCreate;
 *     decodes Opus into the ring, so decoding never competes with audio or recording.
 *
 * Safety: never writes flash, never touches the boot region; every pointer read from
 * firmware state is range-checked; unknown state = silence. */
#include <stdint.h>
#include "voice.h"

#define DMA_FRAMES  128u            /* stereo frames in the DMA output half (0x400 B) */

/* ---------------- settings the patcher may change ---------------------------
 * Fixed address (section .cfg, right after the export table at the module base), so the
 * web patcher can set them in the image without rebuilding. Read through volatile. */
__attribute__((section(".cfg"), used))
const volatile voice_cfg_t g_cfg = {
    .magic      = VOICE_CFG_MAGIC,
    .samp_shift = 13,   /* output level: 16-bit clip sample << samp_shift (13: peaks ~-21 dBFS) */
    .chime      = 1,    /* startup chime once the voice is ready */
    .vol_follow = 1,    /* scale the voice with the headphone VOLUME level */
};


static inline int ram_ptr_ok(uint32_t a, uint32_t align){
    if (a & (align-1)) return 0;
    if (a >= 0x20000000u && a < 0x20280000u) return 1;   /* DTCM + OCRAM */
    if (a >= 0x80000000u && a < 0x81000000u) return 1;   /* SDRAM (16 MB) */
    return 0;
}

/* ---------------- widget-4 label (fallback trigger for screens we don't map) ----
 * On-screen text draws via FUN_80057118(lang, widget, ..); widget 4's descriptor pointer
 * is at 0x802087b4 and its label string id at +4. It changes when an item is entered /
 * committed, so it covers screens outside the menu tree and the screens mapped below. */
#define WIDGET4_DESC_PP  (*(volatile uint32_t*)0x802087b4u)
static inline uint32_t focused_string_id(void){
    uint32_t desc = WIDGET4_DESC_PP;
    if (!ram_ptr_ok(desc, 2)) return 0;
    return (uint32_t)*(volatile uint16_t*)(desc + 4);
}

/* ---------------- headphone VOLUME follow ------------------------------------
 * Level = u16 @0x804BEBB8, 0..50 (FUN_80044550 get / FUN_80044980 set; VOLUME handler
 * FUN_80006220 steps 1 or 5; the popup shows level*2). The F3 applies it in the converter
 * (FUN_80051b18, register 0x37), which our B2 samples do NOT go through -- measured on
 * the device: the monitor in B2 peaks the same at VOLUME 100 and 50, and the voice stays
 * fixed without this. So we scale the voice: 1 dB per level, 50 = unity, 0 = -50 dB. */
#define VOL_LEVEL (*(volatile uint16_t*)0x804BEBB8u)
static const uint16_t g_vol_q16[50] = {
    207, 233, 261, 293, 328, 369, 414, 464, 521, 584,
    655, 735, 825, 926, 1039, 1165, 1308, 1467, 1646, 1847,
    2072, 2325, 2609, 2927, 3285, 3685, 4135, 4640, 5206, 5841,
    6554, 7353, 8250, 9257, 10387, 11654, 13076, 14672, 16462, 18471,
    20724, 23253, 26090, 29274, 32846, 36854, 41350, 46396, 52057, 58409};
static uint32_t g_home_seen;        /* the home screen has been shown since power-on */
static inline uint32_t vol_gain_q16(void){
    if (!g_cfg.vol_follow) return 65536u;
    uint32_t L = VOL_LEVEL;
    if (L == 0u && !g_home_seen) return 65536u;   /* settings not loaded yet (first boot,
                                                   * after a factory reset): full level */
    if (L >= 50u) return 65536u;
    return g_vol_q16[L];
}

/* ---------------- clip banks in flash -------------------------------------------
 * The banks sit in the image PAST code_length (the bootloader does not copy them to SDRAM)
 * and are read in place through the FlexSPI XIP window (0x60000000..). Bank layout:
 *   header (flash_hdr, 32 B) | index[nslots] {offset, nsamples} | clip data |
 *   r0: u16 hash of each built-in UI string | r1: u32 hash of each clip's text
 * Clip data = [u8 length][Opus packet]... (mono, 16 kHz, 10 ms frames). Slot = string id
 * (firmware strings < 590; 590..839 are our extra phrases, see gen_flash_bank.py). */
typedef struct { uint32_t offset; uint32_t nsamples; } clip_ent;
typedef struct { uint32_t magic0, magic1, rate, nslots, fmt, r0, r1, r2; } flash_hdr;
#define FB_MAGIC0  0x58563346u      /* 'F3VX' */
#define FB_MAGIC1  0x4B4E4142u      /* 'BANK' */
#define XIP_LO     0x60000000u
#define XIP_HI     0x60800000u      /* 8 MB flash window */
#define CLIP_MAX_ID 840u

static const flash_hdr *g_fh;       /* located once at startup */
static const clip_ent  *g_fidx;
static const uint8_t   *g_fbank;
static uint32_t         g_fnslots;

/* One bank per F3 UI language, back to back in flash. Header r2: bits 0..7 = language index
 * (the F3's own L: 0 EN 1 FR 2 DE 3 IT 4 ES 5 ZH 6 JA), bits 8..9 = year style. */
#define NLANG 7u
static const flash_hdr *g_banks[NLANG];
static uint32_t g_lang = 0xFFu;
static uint32_t g_year_style;                    /* from the active bank header */
static void bank_use(const flash_hdr *h){
    g_fh = h;
    g_fnslots = h->nslots;
    g_fidx  = (const clip_ent*)((const uint8_t*)h + sizeof(flash_hdr));
    g_fbank = (const uint8_t*)g_fidx + g_fnslots * sizeof(clip_ent);
    g_year_style = (h->r2 >> 8) & 3u;
}
static int is_bank(uint32_t a){
    return *(volatile uint32_t*)a == FB_MAGIC0 && *(volatile uint32_t*)(a+4u) == FB_MAGIC1;
}
/* Find the first bank (the image builder puts it at file 0x400000 = XIP 0x60400000, so look
 * there first; else scan), then walk the chain: each bank ends with its lookup table
 * (r1 + nslots*4) and the next one starts at the following 16-byte boundary. */
static const uint8_t *scan_flash(void){
    uint32_t a = 0;
    if (is_bank(XIP_LO + 0x400000u)) a = XIP_LO + 0x400000u;
    else for (uint32_t x = XIP_LO; x < XIP_HI - 8u; x += 4u) if (is_bank(x)){ a = x; break; }
    if (!a) return 0;
    uint32_t first = a;
    for (uint32_t n = 0; n < NLANG && a && a < XIP_HI - 32u && is_bank(a); n++){
        const flash_hdr *h = (const flash_hdr*)a;
        uint32_t L = h->r2 & 0xFFu;
        if (L < NLANG && !g_banks[L]) g_banks[L] = h;
        if (h->r1 == 0u || h->nslots > 4096u) break;             /* old/odd bank: no chain */
        a = (a + h->r1 + h->nslots * 4u + 15u) & ~15u;
    }
    return (const uint8_t*)first;
}


/* The monitor/DAC path is clocked at 2x the selected record rate (measured
 * across 48/96/192 k). The record rate lives at 0x2000a248; target twice it. */
#define FW_RATE (*(volatile uint32_t*)0x2000a248u)
static inline uint32_t valid_rate(uint32_t r){
    if (r==44100u||r==48000u||r==88200u||r==96000u||r==192000u) return r;
    return 48000u;
}

/* playback + rate-adaptive resample state (clip rate 16 kHz -> output rate) */
static const uint8_t *g_src;        /* flash: first packet of the active clip */
static uint32_t g_nsamp, g_pos;     /* clip length / samples consumed */
static int32_t  g_prev, g_cur;      /* consecutive samples (linear interp) */
static uint32_t g_acc, g_out, g_crate;
static int      g_active;

static int      g_inited = 0;
static uint32_t g_last_id;          /* widget-4 label last seen */

/* ---------------- Opus decoding (libopus 1.5.2, fixed point, decode only) -------
 * libopus's temporary arrays use a static pseudo-stack (g_oscratch). Peak memory use was
 * measured by decoding every bank in emulation, not guessed. */
#define FMT_OPUS  2u
#include "opus.h"
/* Decoding runs in OUR OWN low-priority FreeRTOS task ("VoiceDecode"), never in the audio
 * task: decoding inside AudioProcess (prio 30) crackled at 88.2 kHz and above (output tick
 * 0.73 ms or less; Casey, 2026-10-14). The decode task fills a 256 ms PCM ring; the audio
 * tick only copies samples out of it. Single producer (decode task) / single consumer
 * (audio task): the producer alone writes g_rw, the consumer alone writes g_rr and the
 * request fields. A new clip = consumer bumps g_req_gen; the producer resets its decoder,
 * drops what is in the ring (g_rw = g_rr: the consumer is not reading while it waits),
 * then publishes g_ack_gen. Firmware RTOS calls (v2.20):
 *   FUN_80096748 = xTaskCreate(fn, name, depth_words, param, prio, handle*) -> 1 = pdPASS
 *   FUN_80095d90 = vTaskDelay(ticks); SysTick 1 kHz (FUN_80018168(SystemCoreClock,1000))
 * Priority 25: below the recording path (AudioProcess 30, AudioSubProcess 27, StreamDrive 26)
 * and above the UI (buttons 23, display 18/19, waveform 22). At priority 2 (first version)
 * it starved during playback, when display and file reading keep the CPU busy: clips timed
 * out and the recording leaked between words (Casey, 2026-10-14). Its work is small (a few
 * percent of the CPU while speaking, at most two 10 ms frames, ~0.5 ms, per 1 ms wake) and
 * it sleeps as soon as the 256 ms ring is full. */
#define OP_FRAME_MAX 480u                     /* up to 20 ms at 24 kHz */
#define OP_STATE_B   18432u                   /* opus_decoder_get_size(1) = 17800 */
#define OP_SCRATCH_B 8192u                    /* pseudo-stack; full-bank peak 4184 */
#define OP_RING      4096u                    /* 256 ms at 16 kHz, 170 ms at 24 kHz (power of two) */
#define OP_TASK_PRIO 25u
#define OP_TASK_WORDS 0x500u                  /* 5 KB task stack; decode peak 1.9 KB at 16 kHz, 3.5 KB at 24 kHz */
#define OP_FRAMES_PER_WAKE 2u                 /* 20 ms of audio per 1 ms wake: bursts <= ~0.5 ms */
/* give up on a clip whose first data hasn't come after 1.5 s (in audio ticks: rate-dependent) */
#define OP_START_TIMEOUT_TICKS ((g_out * 3u / 2u) / DMA_FRAMES)
typedef int  (*x_task_create_t)(void (*)(void*), const char*, uint32_t, void*, uint32_t, void*);
typedef void (*v_task_delay_t)(uint32_t);
#define xTaskCreate_fw ((x_task_create_t)0x80096749u)
#define vTaskDelay_fw  ((v_task_delay_t)0x80095d91u)
static uint64_t g_ostate[OP_STATE_B/8];
static uint64_t g_oscratch[OP_SCRATCH_B/8];
char *opus_alloc_scratch(unsigned int n){ (void)n; return (char*)g_oscratch; }
static int16_t  g_ring[OP_RING];
static int16_t  g_ofr[OP_FRAME_MAX];
static volatile uint32_t g_rw, g_rr;          /* free-running indices */
static volatile uint32_t g_req_gen, g_ack_gen;
static const uint8_t * volatile g_req_src;
static volatile uint32_t g_req_n, g_req_rate;
static volatile uint32_t g_task_ok, g_task_alive;
static uint32_t g_owait;                      /* consumer: >0 = waiting for the first data */
static void *g_task_handle;
static volatile uint32_t g_olate, g_oerr, g_omaxwait;   /* diagnostics (OPUS_PROBE) */
#define DMB() __asm volatile("dmb" ::: "memory")
/* ---- diagnostic builds (all off in the product; enable with -D<NAME>=1) ----
 *   OPUS_PROBE  Stop status adds: worst decode time in us (528 MHz core, DWT cycle counter),
 *               late samples, worst clip-start wait in audio ticks
 *   MON_PROBE   Stop status adds: "VOLUME", the popup value, monitor peak in dB below 2^31
 *   LANG_PROBE  Stop status adds: banks found, F3 language, active bank, bank address byte
 *   SCR_PROBE   every screen change speaks the screen object index and its flag byte */
#ifndef OPUS_PROBE
#define OPUS_PROBE 0
#endif
#ifndef MON_PROBE
#define MON_PROBE 0
#endif
#ifndef LANG_PROBE
#define LANG_PROBE 0
#endif
#ifndef SCR_PROBE
#define SCR_PROBE 0
#endif
#if OPUS_PROBE
#define DWT_CYC (*(volatile uint32_t*)0xE0001004u)
static volatile uint32_t g_omaxcyc;
static void dwt_on(void){
    *(volatile uint32_t*)0xE000EDFCu |= 1u << 24;      /* DEMCR.TRCENA */
    *(volatile uint32_t*)0xE0001FB0u = 0xC5ACCE55u;    /* DWT lock access (M7) */
    *(volatile uint32_t*)0xE0001000u |= 1u;            /* DWT_CTRL.CYCCNTENA */
}
#endif
/* producer state (decode task only) */
static const uint8_t *g_opk; static uint32_t g_odec, g_onsamp;
/* One producer step: called by the task each wake (and directly by the emulator). */
void voice_dec_step(void){
    g_task_alive++;
    uint32_t gen = g_req_gen;
    if (gen != g_ack_gen){
        g_opk = g_req_src; g_onsamp = g_req_n; g_odec = 0;
        if (opus_decoder_init((OpusDecoder*)g_ostate, (opus_int32)g_req_rate, 1) != OPUS_OK) g_onsamp = 0;
        g_rw = g_rr;                           /* drop the previous clip's leftovers */
        DMB(); g_ack_gen = gen;
    }
    for (uint32_t k = 0; k < OP_FRAMES_PER_WAKE; k++){
        if (g_odec >= g_onsamp || g_req_gen != g_ack_gen) break;
        if (OP_RING - (g_rw - g_rr) < OP_FRAME_MAX) break;   /* ring full enough */
        uint32_t L = *g_opk;
#if OPUS_PROBE
        uint32_t c0 = DWT_CYC;
#endif
        int n = opus_decode((OpusDecoder*)g_ostate, g_opk + 1, (opus_int32)L, g_ofr, (int)OP_FRAME_MAX, 0);
#if OPUS_PROBE
        uint32_t dc = DWT_CYC - c0; if (dc > g_omaxcyc) g_omaxcyc = dc;
#endif
        g_opk += 1u + L;
        if (n <= 0 || n > (int)OP_FRAME_MAX){ g_oerr++; n = (int)(g_req_rate / 100u); for (int i = 0; i < n; i++) g_ofr[i] = 0; }
        uint32_t w = g_rw;
        for (int i = 0; i < n; i++) g_ring[(w + (uint32_t)i) & (OP_RING - 1u)] = g_ofr[i];
        g_odec += (uint32_t)n;
        DMB(); g_rw = w + (uint32_t)n;
    }
}
static void voice_dec_task(void *arg){
    (void)arg;
    for (;;){ voice_dec_step(); vTaskDelay_fw(1); }
}
static void op_task_start(void){
    if (opus_decoder_get_size(1) > (int)OP_STATE_B) return;
    g_task_ok = (xTaskCreate_fw(voice_dec_task, "VoiceDecode", OP_TASK_WORDS, 0,
                                OP_TASK_PRIO, &g_task_handle) == 1);
}
/* consumer side (audio task) */
/* the clip rate of a bank: 16 kHz (wideband, default), 24 kHz (super-wideband, the patcher's
 * higher qualities) or 8 kHz (narrowband, its smallest) */
static inline uint32_t bank_rate(void){
    uint32_t r = g_fh ? g_fh->rate : 16000u;
    return (r == 8000u || r == 24000u) ? r : 16000u;
}
static void op_start(const uint8_t *src, uint32_t n){
    g_req_src = src; g_req_n = n; g_req_rate = bank_rate(); DMB(); g_req_gen = g_req_gen + 1u;
    g_owait = 1;
}
/* 1 = data for the clip start is ready (prime the interpolator) */
static int op_ready(void){
    if (g_ack_gen != g_req_gen) return 0;
    uint32_t avail = g_rw - g_rr;
    uint32_t cush = (g_crate * 3u) / 100u;                /* 30 ms cushion */
    uint32_t need = g_nsamp < cush ? g_nsamp : cush;
    return avail >= need;
}
static inline int32_t op_next(void){
    g_pos++;
    if (g_rw == g_rr){ g_olate++; return 0; }            /* underrun: should not happen */
    int32_t s = g_ring[g_rr & (OP_RING - 1u)];
    DMB(); g_rr = g_rr + 1u;
    return s;
}

/* Find the banks and start the decode task. No banks, a format we can't play, or no
 * task -> the voice stays off (g_fh = 0) and the firmware behaves exactly as stock. */
void voice_init(void){
    g_active = 0; g_last_id = 0; g_nsamp = 0;
    g_fh = (const flash_hdr*)scan_flash();
    if (g_fh && g_fh->fmt != FMT_OPUS) g_fh = 0;
#if OPUS_PROBE
    if (g_fh) dwt_on();
#endif
    if (g_fh){ op_task_start(); if (!g_task_ok) g_fh = 0; }
    if (g_fh) bank_use(g_banks[0] ? g_banks[0] : g_fh);   /* English until the language is known */
    else { g_fnslots = 0; g_fidx = 0; g_fbank = 0; }
}
static inline int clip_ok(uint32_t id){
    if (g_fh == 0 || id == 0u || id >= g_fnslots) return 0;
    uint32_t n = g_fidx[id].nsamples;
    return (n > 0u && n <= 400000u);
}


/* ----- MENU-TREE poll (found 2026-10-13 in the correctly-unpacked RW data) -----
 * The F3 menu is a static tree of 36-byte item records in initialised RW data
 * (0x801F4400..0x802AD280):  +0x08 u16 string_id, +0x0C children[] (item*),
 * +0x10 s16 child count, +0x14 s16 top visible row.
 * Navigation state (scroll handler FUN_80061a00, redraw FUN_80028fe0):
 *   level = u8  @0x804BF76C
 *   depth = u8  @0x804BF76D + level
 *   node  = u32 @0x804BF774 + (level*7 + depth)*4          (current menu)
 *   row   = s16 @0x804BF838   (cursor row on screen, 0..2; keys 0x2B '+' / 0x2D '-')
 *   highlighted item = node->children[node->top + row] ; speak its string_id.
 * Everything is validated (static-tree address range, counts, indices) so a stale
 * or non-menu state is simply ignored. */
#define MT_STATE     0x804BF76Cu
#define MT_NODES     0x804BF774u
#define MT_ROW       (*(volatile int16_t*)0x804BF838u)
#define MT_LO        0x801F4400u           /* static menu records live in RW data */
#define MT_HI        0x802AD280u
#define MT_THROTTLE  0x0Fu                 /* evaluate every 16 audio ticks */
/* (start-up: voice_tick does nothing until the home screen or 12 s, see there) */
static inline int mt_rec_ok(uint32_t a){ return (a & 3u) == 0u && a >= MT_LO && a + 0x24u <= MT_HI; }
static uint32_t g_mt_node, g_mt_sel = 0xFFFFFFFFu, g_mt_tick, g_mt_title, g_mt_chk;
/* On-demand status: Stop pressed on the idle home screen (Stop does nothing there in the
 * stock firmware; keys reach a central dispatcher before any screen, so we read the raw
 * key state: u32 @0x80490BAC, active low, Stop = bit 3). Reads: remaining record time = u32 @0x80301680 (total seconds available) minus elapsed
 * seconds u32 @0x80546CB0 while recording (0xFFFFFFFF otherwise) -- the same maths the
 * home counter uses (FUN_800276c8 mode 1); battery level u8 @0x80545715 (0..4 bars,
 * 5 = external power; FUN_80035980 -> FUN_80004d60 icon); battery type u8 @0x804BEC02
 * (0 Alkaline 1 Ni-MH 2 Lithium = sids 67..69). */
#define STATUS_KEY_BIT 3
static volatile uint32_t g_status_req;
static int      g_mt_primed;

/* "selected": option lists (Sample Rate, Language, ...) carry flag 0x04 (and not 0x80)
 * in byte node+1; the firmware draws its check mark at child index s16 node+0x12 (the
 * committed value, written by the settings code). We announce "selected" exactly where
 * the screen shows the check mark. Clip 590 is the extra phrase "selected". */
#define SEL_CLIP 590u

/* small speech queue: the first clip starts now (interrupting), the rest follow */
#define SQ_N 100u                 /* room to spell a 40-character name with "capital"s */
static uint16_t g_sq[SQ_N];
static uint32_t g_sq_n;
static void say_clear(void){ g_sq_n = 0; }
static void say_add(uint32_t id){ if (clip_ok(id) && g_sq_n < SQ_N) g_sq[g_sq_n++] = (uint16_t)id; }
static void say_go(void){                      /* start the first queued clip now */
    if (!g_sq_n) return;
    uint32_t id = g_sq[0];
    for (uint32_t i = 1; i < g_sq_n; i++) g_sq[i-1] = g_sq[i];
    g_sq_n--; voice_start(id);
}

/* ----- runtime text (file names, levels, versions...) -----
 * The UI string table is writable RAM: string sid in language L is a UTF-16 buffer at
 * *(*(0x802A3D60 + L*4) + sid*4); L = *(u16*)*(u32*)0x80498360 (FUN_800274a0). The
 * firmware writes runtime text into placeholder strings ("****", "100", "99.99"...).
 * Each bank carries a 16-bit hash of every built-in string of its language (header r0):
 * if the live buffer still hashes to it we play the clip, otherwise we read the text. */
#define STR_TABLES  0x802A3D60u
#define STR_LANGPP  (*(volatile uint32_t*)0x80498360u)
#define CLIP_LETTER(c) (720u + (c))      /* 'A'..'Z' -> 720..745 */
#define CLIP_HUNDRED 746u
#define CLIP_THOUSAND 747u
#define CLIP_POINT  748u
#define CLIP_PERCENT 749u
#define CLIP_OF     750u
#define TXT_MAX     64u
#define CLIP_NUM(n) (600u + (n))
static const volatile uint16_t *str_ptr(uint32_t sid){
    uint32_t lp = STR_LANGPP;
    if (!ram_ptr_ok(lp, 2)) return 0;
    uint32_t L = *(volatile uint16_t*)lp;
    if (L > 6u || sid == 0u || sid > 600u) return 0;
    uint32_t arr = *(volatile uint32_t*)(STR_TABLES + L*4u);
    if (!ram_ptr_ok(arr, 4)) return 0;
    uint32_t p = *(volatile uint32_t*)(arr + sid*4u);
    if (!ram_ptr_ok(p, 2)) return 0;
    return (const volatile uint16_t*)p;
}
static uint32_t str_hash(const volatile uint16_t *p){
    uint32_t h = 0x811C9DC5u;
    for (uint32_t i = 0; i < TXT_MAX; i++){
        uint32_t c = p[i];
        if (!c) break;
        h = (h ^ (c & 0xFFu)) * 0x01000193u;
        h = (h ^ (c >> 8)) * 0x01000193u;
    }
    h = ((h >> 16) ^ h) & 0xFFFFu;
    return h ? h : 1u;
}
/* 1 if the firmware has replaced this string's built-in text at runtime */
static int str_dynamic(uint32_t sid){
    if (g_fh == 0 || g_fh->r0 == 0u || sid >= g_fnslots) return 0;
    uint32_t want = *(const uint16_t*)((const uint8_t*)g_fh + g_fh->r0 + sid*2u);
    const volatile uint16_t *p = str_ptr(sid);
    if (!want || !p) return 0;
    return str_hash(p) != want;
}
/* Numbers, language-neutral: whole-word clips for 100..900 (780+k) and 1000..9000 (789+k)
 * ("deux cents", "trescientos", "zweitausend", "三百"...), falling back to digit + "hundred"/
 * "thousand" for a bank without them. CLIP_FILLER (799) is the linking word some languages
 * need before a gap ("两千零五"); banks that don't need one have no clip 799, so it is skipped.
 * Year style comes from the bank header (r2 bits 8..9): 0 = English pairs ("twenty twenty-six"),
 * 1 = whole number ("deux mille vingt-six"), 2 = digit by digit ("二零二六"). */
#define CLIP_HUNDREDS(k)  (780u + (k))
#define CLIP_THOUSANDS(k) (789u + (k))
#define CLIP_FILLER 799u
static int clip_has(uint32_t id){ return g_fh && id < g_fnslots && g_fidx[id].nsamples != 0u; }
static void say_int(uint32_t n){                 /* 0..9999 */
    if (n > 9999u) return;
    if (n >= 1000u){
        uint32_t k = n / 1000u;
        if (clip_has(CLIP_THOUSANDS(k))) say_add(CLIP_THOUSANDS(k));
        else { say_add(CLIP_NUM(k)); say_add(CLIP_THOUSAND); }
        n %= 1000u; if (!n) return;
        if (n < 100u) say_add(CLIP_FILLER);
    }
    if (n >= 100u){
        uint32_t k = n / 100u;
        if (clip_has(CLIP_HUNDREDS(k))) say_add(CLIP_HUNDREDS(k));
        else { say_add(CLIP_NUM(k)); say_add(CLIP_HUNDRED); }
        n %= 100u; if (!n) return;
        if (n < 10u) say_add(CLIP_FILLER);
    }
    say_add(CLIP_NUM(n));
}
static void say_year(uint32_t v){                /* 2000..2099 */
    uint32_t yy = v - 2000u;
    if (g_year_style == 1u){ say_int(v); return; }
    if (g_year_style == 2u){ say_add(CLIP_NUM(2u)); say_add(CLIP_NUM(0u));
                             say_add(CLIP_NUM(yy / 10u)); say_add(CLIP_NUM(yy % 10u)); return; }
    if (yy < 10u){ say_add(717u); if (yy) say_add(CLIP_NUM(yy)); }
    else { say_add(CLIP_NUM(20u)); say_add(CLIP_NUM(yy)); }
}
/* Find an existing clip whose text equals p[a..b) ignoring ASCII case (bank lookup table,
 * header r1 = offset, u32 FNV-1a per slot over the lower-cased UTF-16). 0 = none. */
static uint32_t text_lookup(const volatile uint16_t *p, uint32_t a, uint32_t b){
    if (g_fh == 0 || g_fh->r1 == 0u || b <= a) return 0;
    uint32_t h = 0x811C9DC5u;
    for (uint32_t i = a; i < b; i++){
        uint32_t c = p[i];
        if (c >= 'A' && c <= 'Z') c += 32u;
        h = (h ^ (c & 0xFFu)) * 0x01000193u;
        h = (h ^ (c >> 8)) * 0x01000193u;
    }
    if (!h) h = 1u;
    const uint32_t *t = (const uint32_t*)((const uint8_t*)g_fh + g_fh->r1);
    for (uint32_t s = 1; s < g_fnslots; s++) if (t[s] == h && clip_ok(s)) return s;
    return 0;
}
static int is_sep(uint32_t c){ return c == ' ' || c == '/' || c == ','; }

/* Read a UTF-16 text: digit runs as numbers (runs of 5+ digits, e.g. date/time stamps,
 * as 2-digit pairs; digits after a decimal point one by one), letters spelled, '.' between
 * digits = "point", '%' = "percent",
 * a trailing ".ext" dropped, everything else skipped. */
static void say_text(const volatile uint16_t *p){
    uint32_t len = 0;
    while (len < TXT_MAX && p[len]) len++;
    uint32_t end = len;                          /* drop ".WAV"-style extension */
    for (uint32_t i = len; i-- > 0 && len - i <= 5u; ){
        if (p[i] == '.'){ int alpha = 1; for (uint32_t k = i+1; k < len; k++){ uint32_t c = p[k] | 0x20u; if (c < 'a' || c > 'z') alpha = 0; } if (alpha && i+1 < len) end = i; break; }
    }
    /* drop a trailing "_Tr<n>" track suffix (the F3 hides it on screen too) */
    { uint32_t e = end; while (e > 0 && p[e-1] >= '0' && p[e-1] <= '9') e--;
      if (e < end && e >= 3u && p[e-3] == '_' && p[e-2] == 'T' && p[e-1] == 'r') end = e - 3u; }
    int first = 1, frac = 0;
    { uint32_t w = text_lookup(p, 0, end); if (w){ say_add(w); return; } }   /* whole text has a clip */
    for (uint32_t i = 0; i < end; ){
        uint32_t c = p[i];
        if (i == 0 || is_sep(p[i-1])){                  /* longest run of words with a clip */
            uint32_t w = 0, wj = 0;
            for (uint32_t j = end; j > i; j--){
                if (j != end && !is_sep(p[j])) continue;    /* only cut at word boundaries */
                int alpha = 0;
                for (uint32_t k = i; k < j; k++){ uint32_t u = p[k] | 0x20u; if (u >= 'a' && u <= 'z'){ alpha = 1; break; } }
                if (!alpha) continue;                       /* pure numbers keep the number rules */
                if ((w = text_lookup(p, i, j)) != 0u){ wj = j; break; }
            }
            if (w){ say_add(w); i = wj; first = 0; continue; }
        }
        if (c >= '0' && c <= '9'){
            uint32_t j = i, v = 0;
            while (j < end && p[j] >= '0' && p[j] <= '9') j++;
            if (frac){                                   /* after a decimal point: digit by digit */
                for (uint32_t k = i; k < j; k++) say_add(CLIP_NUM(p[k]-'0'));
                frac = 0; i = j; continue;               /* ("2.21" = two point two one) */
            }
            uint32_t n = j - i;
            for (uint32_t k = i; k < j && n <= 4u; k++) v = v*10u + (p[k]-'0');
            if (n <= 4u && first && v == 0u && j < end && p[j] == ':'){ i = j + 1u; first = 0; continue; }  /* "000:05:12" */
            first = 0;
            if (n == 4u && v >= 2000u && v <= 2099u) say_year(v);   /* year, per language */
            else if (n == 2u && p[i] == '0'){ say_add(CLIP_NUM(0u)); say_add(CLIP_NUM(v)); }  /* "08", "05" */
            else if (n <= 4u) say_int(v);
            else {                               /* pairs, odd leading digit alone */
                uint32_t k = i;
                if (n & 1u){ say_add(CLIP_NUM(p[k]-'0')); k++; }
                for (; k < j; k += 2){                   /* "08" -> "zero eight" */
                    if (p[k] == '0') say_add(CLIP_NUM(0u));
                    say_add(CLIP_NUM((p[k]-'0')*10u + (p[k+1]-'0')));
                }
            }
            i = j;
            if (i + 1 < end && p[i] == '.' && p[i+1] >= '0' && p[i+1] <= '9'){ say_add(CLIP_POINT); i++; frac = 1; }
            continue;
        }
        first = 0;
        uint32_t u = c & ~0x20u;
        if (u >= 'A' && u <= 'Z' && c < 0x80u) say_add(CLIP_LETTER(u - 'A'));
        else if (c == '%') say_add(CLIP_PERCENT);
        i++;
    }
}
/* speak a UI string: runtime text if the firmware rewrote it, else its clip */
static void say_sid(uint32_t sid){
    if (str_dynamic(sid)){ const volatile uint16_t *p = str_ptr(sid); if (p) say_text(p); }
    else say_add(sid);
}

/* ----- popups (warnings / status messages) -----
 * Popup queue (FUN_800258d0 / FUN_80025840): 5 x s16 popup numbers @0x802AD61C,
 * head index u8 @0x802AD63A, "a popup is up" u8 @0x802AD638. Popup n (1..67) shows
 * the three lines of text entry t = u8 @(0x80208A54 + n*12): string ids at
 * 0x80208A56/58/5A + t*12 (on screen as widgets 0x73..0x75). "-" lines have no clip. */
#define PU_QUEUE   0x802AD61Cu
#define PU_HEAD    (*(volatile uint8_t*)0x802AD63Au)
#define PU_ACTIVE  (*(volatile uint8_t*)0x802AD638u)
#define PU_TABLE   0x80208A54u
#define PU_MAX     67u
static uint32_t g_pu_last;                     /* popup number last seen */
static uint32_t pu_read(void){                 /* 0 = no popup; else popup number */
    if (!PU_ACTIVE) return 0;
    uint32_t h = PU_HEAD;
    if (h >= 5u) return 0;
    int32_t n = *(volatile int16_t*)(PU_QUEUE + h*2u);
    if (n <= 0 || (uint32_t)n > PU_MAX) return 0;
    return (uint32_t)n;
}
static uint32_t pu_line(uint32_t n, uint32_t k){
    uint32_t t = *(volatile uint8_t*)(PU_TABLE + n*12u);
    if (t == 0u || t > PU_MAX) return 0;
    return *(volatile uint16_t*)(PU_TABLE + 2u + t*12u + k*2u);
}
static uint32_t g_pu_h[3];                     /* live hash of each popup line */
static uint32_t pu_line_hash(uint32_t n, uint32_t k){
    const volatile uint16_t *p = str_ptr(pu_line(n, k));
    return p ? str_hash(p) : 0u;
}
/* 1 if a line of popup n starts with the file name nm (up to its extension) */
static int pu_has_name(uint32_t n, const volatile uint16_t *nm){
    if (!nm[0] || nm[0] == '.') return 0;
    for (uint32_t k = 0; k < 3u; k++){
        const volatile uint16_t *p = str_ptr(pu_line(n, k));
        if (!p) continue;
        uint32_t i = 0;
        while (i < 64u && nm[i] && nm[i] != '.' && p[i] == nm[i]) i++;
        if (i == 64u || !nm[i] || nm[i] == '.') return 1;
    }
    return 0;
}
/* all = 1: whole popup (it just appeared); 0: only lines whose text changed since */
static int pu_say(uint32_t n, int all){
    uint32_t speak = 0;                            /* bit k = say line k */
    for (uint32_t k = 0; k < 3u; k++){
        uint32_t sid = pu_line(n, k), h = pu_line_hash(n, k);
        if (sid && (all || h != g_pu_h[k])) speak |= 1u << k;
        g_pu_h[k] = h;
    }
    if (!speak) return 0;                          /* nothing new: leave the queue alone */
    say_clear();
    for (uint32_t k = 0; k < 3u; k++) if (speak & (1u << k)) say_sid(pu_line(n, k));
    say_go();
    return 1;
}
/* ----- screens outside the menu tree -----
 * Current screen object pointer @0x8020A55C (FUN_80006ab8 get / FUN_80006af0 set);
 * screen objects are 32-byte records from 0x8020740C. Word 0 holds flags; bit 2 is set
 * once the screen's own init + first draw have run (activation code, e.g. 0x80008468),
 * and the switch routine clears it on leave. We only read a screen's state while it is
 * current AND bit 2 is set, so we never see half-initialised values. */
#define SCR_CUR     (*(volatile uint32_t*)0x8020A55Cu)
#define SCR_DLG     0x802074ECu        /* Execute/Cancel + OK/Cancel dialogs */
#define SCR_DT      0x8020750Cu        /* Set Date/Time */
static inline int scr_ready(uint32_t s){ return SCR_CUR == s && (*(volatile uint32_t*)s & 4u); }
#define SCR_MENU    0x8020742Cu        /* the menu tree screen */
#define SCR_HOME    0x8020764Cu        /* home screen (object 18) */
#define SCR_FINDER  0x8020748Cu        /* file list */
#define SCR_PLAY    0x8020762Cu        /* playback screen (INFO / DELETE soft keys) */
#define SCR_INFO    0x8020746Cu        /* file INFO (opened from playback) */
/* current file: DB index s16 @0x804C0586 (FUN_8002d590); name = UTF-16 @0x8049E6EC + i*0x84 */
#define CUR_FILE    (*(volatile int16_t*)0x804C0586u)
#define DB_NAME(i)  ((const volatile uint16_t*)(0x8049E6ECu + (uint32_t)(i)*0x84u))
/* INFO: page u8 @0x804BFA58 (0 Date/Time, 1 Format, 2 Length); label widget 0x15, values
 * widgets 0x16/0x17 (runtime text or clips); title copy = UTF-16 @0x804BF84C */
#define INFO_PAGE   (*(volatile uint8_t*)0x804BFA58u)
#define INFO_TITLE  ((const volatile uint16_t*)0x804BF84Cu)
#define SCR_VERS    0x8020760Cu        /* Versions (object 16; draw 0x80021168 shows widgets 57..62) */
/* widget -> its current string id (descriptor table 0x802087A4, sid at +4) */
static uint32_t wsid(uint32_t w){
    uint32_t d = *(volatile uint32_t*)(0x802087A4u + w*4u);
    return ram_ptr_ok(d, 2) ? *(volatile uint16_t*)(d + 4u) : 0u;
}
/* Finder (handler FUN_80029940, scroll FUN_8005e928): cursor row s16 @0x804C028E (0..2),
 * selected index s16 @0x804C0290, file count s16 @0x804BEA8E (file DB header). The three
 * rows are widgets 0x12..0x14 whose strings hold the file names (runtime text). */
#define FD_ROW      (*(volatile int16_t*)0x804C028Eu)
#define FD_POS      (*(volatile int16_t*)0x804C0290u)
#define FD_CNT      (*(volatile int16_t*)0x804BEA8Eu)
static uint32_t g_fd_cand, g_fd_said, g_scr_hold;
static uint32_t g_scr_last;            /* special screen we were on (0 = none) */

/* Dialog (handler FUN_8002a9a8, draw CB 0x80020450): type u8 @0x804C058A (1..10:
 * 1 Factory Reset, 2 Format, 3 Quick Test, 4 Full Test, 5 Delete, 6 Exit USB Audio I/F,
 * 7 Firmware Update, 8..10 "OK to disconnect ...?"). Focused button u8 @0x804C04F0
 * (0 = Execute/OK, 1 = Cancel; opens on Cancel). Title sid @0x80166ECC + t*2; per-type
 * texts @0x80166E48 + t*8: types 1..7 {Execute, Cancel}, 8..10 {line1, line2, OK, Cancel}. */
#define DLG_TYPE    (*(volatile uint8_t*)0x804C058Au)
#define DLG_BTN     (*(volatile uint8_t*)0x804C04F0u)
#define DLG_TITLES  0x80166ECCu
#define DLG_TEXTS   0x80166E48u
#define CLIP_RESET_NOTE 757u
static uint32_t g_dlg_btn;
static uint32_t dlg_btn_sid(uint32_t t, uint32_t b){
    return *(volatile uint16_t*)(DLG_TEXTS + t*8u + (t >= 8u ? 4u : 0u) + (b ? 2u : 0u));
}

/* Set Date/Time (handler FUN_8002ade8, editor FUN_80060350, Enter FUN_8005fe00):
 * focused position u8 @0x804C04FC (0..5), editing u8 @0x804C04FD, buffer: year u16
 * @0x804C04FE, month/day/hour/minute u8 @0x804C0500..03. Position -> field id via the
 * byte table @0x80166EE2 + date_format*6 (date format u8 @0x804BEBFC, 0..2): ids
 * 0 year, 1 month, 2 day, 3 hour, 4 minute, 5 = confirm. Extra clips: numbers 600+n,
 * months 700+m-1, labels 712..716, "two thousand" 717. */
#define DT_POS      (*(volatile uint8_t*)0x804C04FCu)
#define DT_EDIT     (*(volatile uint8_t*)0x804C04FDu)
#define DT_YEAR     (*(volatile uint16_t*)0x804C04FEu)
#define DT_B(i)     (*(volatile uint8_t*)(0x804C0500u + (i)))
#define DT_FMT      (*(volatile uint8_t*)0x804BEBFCu)
#define DT_ORDER    0x80166EE2u
#define CLIP_OK     228u
#define CLIP_EDIT   494u
#define CLIP_SETDT  56u
static uint32_t g_dt_pos, g_dt_edit, g_dt_val;
static uint32_t dt_field(void){
    uint32_t p = DT_POS, f = DT_FMT;
    if (p > 5u || f > 2u) return 0xFFu;
    return *(volatile uint8_t*)(DT_ORDER + f*6u + p);
}
static uint32_t dt_value(uint32_t id){
    switch (id){ case 0: return DT_YEAR; case 1: return DT_B(0); case 2: return DT_B(1);
                 case 3: return DT_B(2); case 4: return DT_B(3); default: return 0; }
}
static void dt_add_value(uint32_t id, uint32_t v){
    if (id == 0u){                                   /* year: "twenty twenty-six" */
        if (v < 2000u || v > 2099u) return;
        say_year(v);
    } else if (id == 1u){ if (v >= 1u && v <= 12u) say_add(700u + v - 1u); }
    else if (id <= 4u){ if (v < 100u) say_add(CLIP_NUM(v)); }
}
static void dt_add_field(uint32_t id){
    if (id <= 4u){ say_add(712u + id); dt_add_value(id, dt_value(id)); }
    else if (id == 5u) say_add(CLIP_OK);
}

/* Waveform magnification popup (home screen; FUN_800062d8 +/- , FUN_80005d28 open):
 * open channel u8 @0x80302508 (0 closed, 1 = input 1, 2 = input 2; closed by a 2 s
 * timer). Zoom index per channel = low byte of u16 @0x804BEBB4 + ch*2 (0..10 = x1..x1024);
 * label sid = u16 @0x80165140 + idx*2 (273..283, "× N"; each bank says it its own way).
 * Input names: sid 325 "Input1", 326 "Input2". */
#define ZM_OPEN     (*(volatile uint8_t*)0x80302508u)
#define ZM_IDX(ch)  (*(volatile uint8_t*)(0x804BEBB4u + (ch)*2u))
#define ZM_LABELS   0x80165140u
static uint32_t g_zm_last;                     /* (open<<8)|idx last spoken */

/* Name editor (screen object 5, handler FUN_8002a320, Enter FUN_8005ecb8, typing FUN_8005f1d8):
 * row u8 @0x804C02A4 (0 uppercase, 1 lowercase, 2 digits and symbols); focused key u16
 * @0x804C02A6: 0..28 = character (row*29 + key) of the table @0x80166FEC, 29 switch row,
 * 30 delete, 31 cursor left, 32 cursor right, 33 OK (Up/Down move it and wrap; it opens on OK).
 * Text: UTF-16 @0x804C02CC (40 characters max); cursor index = u16 @0x804C02A8 (position
 * in the 13-character window) + u16 @0x804C02AE (window scroll). Errors are popups. */
#define SCR_NAME    0x802074ACu
#define NE_ROW      (*(volatile uint8_t*)0x804C02A4u)
#define NE_KEY      (*(volatile uint16_t*)0x804C02A6u)
#define NE_WIN      (*(volatile uint16_t*)0x804C02A8u)
#define NE_SCROLL   (*(volatile uint16_t*)0x804C02AEu)
#define NE_TEXT     ((const volatile uint16_t*)0x804C02CCu)
#define NE_CHARS    ((const volatile uint16_t*)0x80166FECu)
#define NE_NCHARS   29u
#define NE_KEY_ROW  29u
#define NE_KEY_DEL  30u
#define NE_KEY_LEFT 31u
#define NE_KEY_RIGHT 32u
#define NE_KEY_OK   33u
#define CLIP_TITLE_NAME 22u          /* "User Defined Name" */
#define CLIP_OK_BTN 228u             /* "OK" */
#define CLIP_DELETE 250u             /* "Delete" */
/* our phrases (gen_flash_bank.py, KEYBOARD) */
#define CLIP_CAPITAL 800u
#define CLIP_SPACE  801u
#define CLIP_ROW(r) (802u + (r))     /* uppercase letters / lowercase letters / digits and symbols */
#define CLIP_CHARSET 805u
#define CLIP_CUR_L  806u
#define CLIP_CUR_R  807u
#define CLIP_END    808u
#define CLIP_EMPTY  809u
#define CLIP_SYM0   810u             /* 810.. : the symbols of NE_SYMS, in order */
#define CLIP_DELETED 830u
static const char NE_SYMS[] = "_-+=!#',;()[]{}$@^`~";
static uint16_t g_ne_txt[TXT_MAX];
static uint32_t g_ne_len, g_ne_row, g_ne_key, g_ne_pos;
static uint32_t ne_len(const volatile uint16_t *p){ uint32_t n = 0; while (n < TXT_MAX - 1u && p[n]) n++; return n; }
/* "capital" goes before the letter in English, German, Chinese, Japanese, after it in
 * French, Italian, Spanish ("A majuscule") */
static void say_char(uint32_t c, int cap){
    uint32_t u = c & ~0x20u;
    if (c >= 'A' && c <= 'Z'){
        uint32_t bl = g_fh ? (g_fh->r2 & 0xFFu) : 0u;          /* the voice's language */
        int after = (bl == 1u || bl == 3u || bl == 4u);
        if (cap && !after) say_add(CLIP_CAPITAL);
        say_add(CLIP_LETTER(c - 'A'));
        if (cap && after) say_add(CLIP_CAPITAL);
    }
    else if (u >= 'A' && u <= 'Z' && c < 0x80u) say_add(CLIP_LETTER(u - 'A'));
    else if (c >= '0' && c <= '9') say_add(CLIP_NUM(c - '0'));
    else if (c == ' ') say_add(CLIP_SPACE);
    else for (uint32_t i = 0; NE_SYMS[i]; i++) if ((uint32_t)(uint8_t)NE_SYMS[i] == c){ say_add(CLIP_SYM0 + i); break; }
}
static void ne_spell(const uint16_t *t, uint32_t n){
    if (!n){ say_add(CLIP_EMPTY); return; }
    for (uint32_t i = 0; i < n; i++) say_char(t[i], 1);
}
static void ne_say_key(uint32_t row, uint32_t key){
    if (key < NE_NCHARS && row <= 2u) say_char(NE_CHARS[row*NE_NCHARS + key], 0);
    else if (key == NE_KEY_ROW){ say_add(CLIP_CHARSET); if (row <= 2u) say_add(CLIP_ROW(row)); }
    else if (key == NE_KEY_DEL) say_add(CLIP_DELETE);
    else if (key == NE_KEY_LEFT) say_add(CLIP_CUR_L);
    else if (key == NE_KEY_RIGHT) say_add(CLIP_CUR_R);
    else if (key == NE_KEY_OK){ say_add(CLIP_OK_BTN); ne_spell(g_ne_txt, g_ne_len); }   /* OK: review the name */
}
static void ne_poll(void){
    const volatile uint16_t *tp = NE_TEXT;
    uint32_t n = ne_len(tp), row = NE_ROW, key = NE_KEY, pos = (uint32_t)NE_WIN + NE_SCROLL;
    if (row > 2u || key > NE_KEY_OK || pos > n) return;          /* mid-update: next poll */
    uint16_t now[TXT_MAX];
    for (uint32_t i = 0; i < n; i++) now[i] = tp[i];
    if (g_scr_last != SCR_NAME){                                /* just opened */
        g_scr_last = SCR_NAME;
        for (uint32_t i = 0; i < n; i++) g_ne_txt[i] = now[i];
        g_ne_len = n; g_ne_row = row; g_ne_key = key; g_ne_pos = pos;
        say_clear(); say_add(CLIP_TITLE_NAME);                 /* it opens on OK, which reads the name */
        say_add(CLIP_ROW(row)); ne_say_key(row, key); say_go();
        return;
    }
    uint32_t k = 0;
    while (k < n && k < g_ne_len && now[k] == g_ne_txt[k]) k++;
    int changed = (n != g_ne_len) || (k < n);
    if (changed){                                               /* typed or deleted */
        say_clear();
        if (n == g_ne_len + 1u) say_char(now[k], 1);            /* the character typed */
        else if (n + 1u == g_ne_len){ say_add(CLIP_DELETED); say_char(g_ne_txt[k], 1); }
        for (uint32_t i = 0; i < n; i++) g_ne_txt[i] = now[i];
        g_ne_len = n; g_ne_row = row; g_ne_key = key; g_ne_pos = pos;
        say_go();
        return;
    }
    if (row != g_ne_row){                                       /* character set switched */
        g_ne_row = row; g_ne_key = key; g_ne_pos = pos;
        say_clear(); say_add(CLIP_ROW(row)); say_go();
        return;
    }
    if (key != g_ne_key){                                       /* moved to another key */
        g_ne_key = key; g_ne_pos = pos;
        say_clear(); ne_say_key(row, key); say_go();
        return;
    }
    if (pos != g_ne_pos){                                       /* cursor moved: what is under it */
        g_ne_pos = pos;
        say_clear();
        if (pos < n) say_char(now[pos], 1); else say_add(CLIP_END);
        say_go();
    }
}

/* Returns 1 and fills node/sel/sid/title/chk if the menu state is valid. */
static int mt_read(uint32_t *node_o, uint32_t *sel_o, uint32_t *sid_o, uint32_t *title_o, uint32_t *chk_o){
    uint32_t L = *(volatile uint8_t*)MT_STATE;
    if (L >= 7u) return 0;
    uint32_t D = *(volatile uint8_t*)(MT_STATE + 1u + L);
    if (D >= 7u) return 0;
    uint32_t node = *(volatile uint32_t*)(MT_NODES + (L*7u + D)*4u);
    if (!mt_rec_ok(node)) return 0;
    int32_t cnt = *(volatile int16_t*)(node + 0x10u);
    int32_t top = *(volatile int16_t*)(node + 0x14u);
    int32_t row = MT_ROW;
    if (cnt <= 0 || cnt > 64 || top < 0 || row < 0 || row > 2) return 0;
    int32_t sel = top + row;
    if (sel >= cnt) return 0;
    uint32_t kids = *(volatile uint32_t*)(node + 0x0Cu);
    if ((kids & 3u) || kids < MT_LO || kids + (uint32_t)cnt*4u > MT_HI) return 0;
    uint32_t child = *(volatile uint32_t*)(kids + (uint32_t)sel*4u);
    if (!mt_rec_ok(child)) return 0;
    *node_o = node; *sel_o = (uint32_t)sel;
    *sid_o = *(volatile uint16_t*)(child + 8u);
    *title_o = *(volatile uint16_t*)(node + 8u);
    uint32_t fl = *(volatile uint8_t*)(node + 1u);
    *chk_o = ((fl & 0x84u) == 0x04u) ? (uint32_t)(int32_t)*(volatile int16_t*)(node + 0x12u) : 0xFFFFu;
    return 1;
}






void voice_start(uint32_t id){
    if (g_fh == 0 || id == 0u || id >= g_fnslots) return;
    const clip_ent *e = &g_fidx[id];
    uint32_t n = e->nsamples;
    if (n == 0u || n > 400000u) return;           /* unmapped / implausible */
    g_src   = g_fbank + e->offset;
    g_nsamp = n; g_pos = 0;
    op_start(g_src, n);                     /* the decode task picks it up */
    g_crate = bank_rate();
    g_out = 2u * valid_rate(FW_RATE); g_acc = 0; g_prev = g_cur = 0;
    g_active = 1;                           /* B2 = silence until the first data arrives */
}
int voice_active(void){ return g_active; }

/* Start the next queued clip from inside the audio fill, so a sequence ("26, zero 8, 15")
 * plays back to back -- otherwise the F3's own audio leaks between clips. */
static int voice_next_queued(void);


/* MON_PROBE: peak |sample| of the F3's own monitor mix in B2 while the voice is idle.
 * Full scale is 2^31 (SAI1 TX: 32-bit words, MSB first; config @0x20003880). */
#if MON_PROBE
static volatile uint32_t g_mon_peak;
static void mon_scan(const int32_t *b2){
    uint32_t pk = g_mon_peak;
    for (uint32_t i = 0; i < 2u*DMA_FRAMES; i++){
        int32_t v = b2[i];
        uint32_t a = (v < 0) ? (uint32_t)(-(int64_t)v) : (uint32_t)v;
        if (a > pk) pk = a;
    }
    g_mon_peak = pk;
}
/* dB below 2^31, rounded: 6.02 dB per bit + 20log10 of the 4-bit mantissa */
static uint32_t db_below_fs(uint32_t pk){
    static const uint8_t frac10[16] = {0,5,10,15,19,23,27,31,35,38,41,44,47,50,53,55};
    if (pk == 0u) return 999u;
    uint32_t n = 31u - (uint32_t)__builtin_clz(pk);            /* pk in [2^n, 2^(n+1)) */
    uint32_t m = (n >= 4u) ? ((pk >> (n - 4u)) & 15u) : ((pk << (4u - n)) & 15u);
    int32_t d10 = (int32_t)(31u - n) * 602 / 10 - (int32_t)frac10[m];   /* tenths of dB */
    return (uint32_t)((d10 + 5) / 10);
}
#endif

/* Fill one DMA half. Speaking: all 128 frames of B2 (dma arg unused). Idle: touch nothing,
 * so the firmware's own mix passes byte-identical to stock. */
int voice_fill_half(int32_t *b2, int32_t *dma){
    (void)dma;
    if (!g_active){
#if MON_PROBE
        if (ram_ptr_ok((uint32_t)b2, 4)) mon_scan(b2);
#endif
        return 0;
    }
    if (!ram_ptr_ok((uint32_t)b2,4)) return 0;
    if (g_owait){                                   /* clip start: wait for decoded data */
        if (op_ready()){
            g_cur = op_next(); g_prev = g_cur;
            if (g_owait > g_omaxwait) g_omaxwait = g_owait;
            g_owait = 0;
        }
        else if (++g_owait > OP_START_TIMEOUT_TICKS){        /* no data: give up cleanly */
            g_owait = 0; g_active = 0; say_clear(); return 0;
        }
    }
    {   /* the record rate can change while a clip plays (SAMPLE RATE menu): follow it, or the
         * rest of the clip comes out too fast / too slow and pitched (Casey, 2026-10-15) */
        uint32_t o = 2u * valid_rate(FW_RATE);
        if (o != g_out){ g_out = o; g_acc = 0; }
    }
    uint32_t g = vol_gain_q16();
    for (uint32_t f = 0; f < DMA_FRAMES; f++){
        int32_t out;
        if (g_active && !g_owait){
            uint32_t frac8 = (g_acc << 8) / g_out;         /* 0..255, 32-bit divide */
            int32_t s = g_prev + (((g_cur - g_prev) * (int32_t)frac8) >> 8);
            out = (int32_t)(((int64_t)s * (int32_t)g) >> 16) << (g_cfg.samp_shift & 15u);
            g_acc += g_crate;
            while (g_acc >= g_out){
                g_acc -= g_out;
                g_prev = g_cur;
                if (g_pos < g_nsamp) g_cur = op_next();
                else if (voice_next_queued()) { g_acc = 0; break; }   /* seamless: next clip now */
                else { g_active = 0; break; }
            }
        } else {
            out = 0;                                /* waiting / just finished: silence */
        }
        b2[2*f] = out; b2[2*f+1] = out;
    }
    return 1;
}

/* The screen poll (every MT_THROTTLE+1 audio ticks). Order: Stop status, popups,
 * magnification, Playback, file INFO, Finder, Versions, dialogs, Date/Time, menu tree,
 * then the widget-4 fallback. Each screen is read only while it is current AND its
 * init+draw flag is set (scr_ready), and runtime values must be stable for one poll. */
void voice_poll(void){
#if SCR_PROBE
    { static uint32_t last; uint32_t sc = SCR_CUR;
      if (sc != last){ last = sc; uint32_t idx = (sc - 0x8020740Cu) / 32u;
          say_clear(); say_int(idx <= 99u ? idx : 99u);
          say_int(ram_ptr_ok(sc, 4) ? (*(volatile uint32_t*)sc & 0xFFu) : 999u); say_go(); return; } }
#endif
    /* The poll runs every MT_THROTTLE+1 ticks, except that a newly opened Playback screen is
     * handled on the very next tick, so "Play" takes over the output before the file is heard. */
    uint32_t t = g_mt_tick++;
    int play_new = (g_scr_last != SCR_PLAY) && scr_ready(SCR_PLAY);
    if (!play_new && (t & MT_THROTTLE) != 0u) return;
    if (g_sq_n && !g_active) say_go();                  /* continue a queued sequence */
    uint32_t node = 0, sel = 0, sid = 0, title = 0, chk = 0xFFFFu;
    int ok = mt_read(&node, &sel, &sid, &title, &chk);
    uint32_t wid = focused_string_id();
    uint32_t pu  = pu_read();
    {   /* Stop on the idle home screen (not recording, not playing) */
        static uint32_t prev_dn;
        uint32_t dn = (~(*(volatile uint32_t*)0x80490BACu) >> STATUS_KEY_BIT) & 1u;
        if (dn && !prev_dn && SCR_CUR == SCR_HOME && *(volatile int16_t*)0x80301676u == 0
            && *(volatile uint32_t*)0x803016A8u == 0u) g_status_req = 1u;
        prev_dn = dn;
    }
    if (g_status_req){                                  /* on-demand home status */
        g_status_req = 0;
        uint32_t total = *(volatile uint32_t*)0x80301680u, el = *(volatile uint32_t*)0x80546CB0u;
        uint32_t rem = (el != 0xFFFFFFFFu && el < total) ? total - el : (el == 0xFFFFFFFFu ? total : 0u);
        say_clear();
        say_add(37u);                                   /* "Remaining Time" */
        if (rem < 360000u){
            uint32_t h = rem / 3600u, mi = (rem % 3600u) / 60u;
            if (h){ say_int(h); say_add(751u); }
            say_int(mi); say_add(752u);
        }
        uint32_t lv = *(volatile uint8_t*)0x80545715u, bt = *(volatile uint8_t*)0x804BEC02u;
        say_add(753u);                                  /* "Battery" */
        if (lv == 5u) say_add(754u);                    /* "external power" */
        else if (lv <= 4u){ say_int(lv); say_add(CLIP_OF); say_int(4u); }
        if (bt <= 2u) say_add(67u + bt);                /* Alkaline / Ni-MH / Lithium */
#if OPUS_PROBE
        { uint32_t us = g_omaxcyc / 528u; say_int(us > 9999u ? 9999u : us);
          say_int(g_olate > 9999u ? 9999u : g_olate);
          say_int(g_omaxwait > 9999u ? 9999u : g_omaxwait); }
#endif
#if LANG_PROBE
        { uint32_t nb = 0, al = 0xFFu, lp = STR_LANGPP, fl = 99u;
          for (uint32_t i = 0; i < NLANG; i++){ if (g_banks[i]) nb++; if (g_banks[i] == g_fh) al = i; }
          if (ram_ptr_ok(lp, 2)) fl = *(volatile uint16_t*)lp;
          say_int(nb); say_int(fl); say_int(al == 0xFFu ? 99u : al);
          say_int((((uint32_t)g_fh) >> 16) & 0xFFu); }
#endif
#if MON_PROBE
        { uint32_t L = VOL_LEVEL; say_add(139u);         /* "VOLUME" */
          say_int(L > 50u ? L : 2u*L);
          say_int(db_below_fs(g_mon_peak)); g_mon_peak = 0u; }
#endif
        say_go();
        return;
    }
    if (!g_mt_primed){
        g_mt_primed = 1; g_last_id = wid; g_pu_last = pu;
        if (ok){ g_mt_node = node; g_mt_sel = sel; g_mt_title = title; g_mt_chk = chk; }
        return;
    }
    if (pu != g_pu_last){                               /* popup appeared / changed */
        g_pu_last = pu;
        if (pu) { pu_say(pu, 1); return; }
    } else if (pu){                                     /* same popup: a live line changed */
        if (pu_say(pu, 0)) return;                      /* (e.g. VOLUME level while pressing +/-) */
    }
    if (pu){                                            /* popup up: nothing else to say */
        /* Skipping files in Playback appears to show a popup with the file's name and format
         * (Casey heard "20260805, 96 kHz 32 bit float, 20260805": popup, then our own name
         * announcement once it closed). If a popup line shows the current file's name, it has
         * just been read: count the file as announced so it isn't said a second time. */
        if (g_scr_last == SCR_PLAY && scr_ready(SCR_PLAY)){
            int32_t idx = CUR_FILE;
            if (idx >= 0 && idx <= 999 && pu_has_name(pu, DB_NAME(idx)))
                g_fd_cand = g_fd_said = ((uint32_t)idx << 16) ^ str_hash(DB_NAME(idx));
        }
        return;
    }

    /* ---- waveform magnification popup ---- */
    {
        uint32_t ch = ZM_OPEN, zm = 0;
        if (ch >= 1u && ch <= 2u){
            uint32_t idx = ZM_IDX(ch - 1u);
            if (idx <= 10u){
                zm = (ch << 8) | idx;
                if (zm != g_zm_last){
                    uint32_t lab = *(volatile uint16_t*)(ZM_LABELS + idx*2u);
                    say_clear();
                    if ((g_zm_last >> 8) != ch) say_add(324u + ch);   /* "Input1"/"Input2" on open */
                    say_add(lab); say_go();
                }
            }
        }
        g_zm_last = zm;
        if (zm) return;
    }

    /* ---- Playback: say the file name on entry / when the file changes ---- */
    if (scr_ready(SCR_PLAY)){
        int fresh = (g_scr_last != SCR_PLAY);
        if (fresh){                       /* say "Play" at once: the voice takes the output */
            g_scr_last = SCR_PLAY; g_fd_said = 0xFFFFFFFFu; g_fd_cand = 0xFFFFFFFEu;
            say_clear(); say_add(18u); say_go();                  /* before playback is heard */
            return;
        }
        int32_t idx = CUR_FILE;
        if (idx < 0 || idx > 999) return;
        uint32_t key = ((uint32_t)idx << 16) ^ str_hash(DB_NAME(idx));
        if (key != g_fd_cand){ g_fd_cand = key; return; }        /* stable for one poll */
        if (key == g_fd_said) return;
        int first = (g_fd_said == 0xFFFFFFFFu);
        g_fd_said = key;
        if (!first) say_clear();          /* first name: queue it right after "Play" */
        if (DB_NAME(idx)[0]) say_text(DB_NAME(idx));
        if (!g_active) say_go();
        return;
    }
    /* ---- file INFO pages ---- */
    if (scr_ready(SCR_INFO)){
        int fresh = (g_scr_last != SCR_INFO);
        if (fresh){ g_scr_last = SCR_INFO; g_fd_said = 0xFFFFFFFFu; g_fd_cand = 0xFFFFFFFEu; }
        uint32_t pg = INFO_PAGE;
        if (pg > 2u) return;
        uint32_t key = pg;
        for (uint32_t w = 0x15u; w <= 0x17u; w++){
            uint32_t sd = wsid(w); const volatile uint16_t *t = sd ? str_ptr(sd) : 0;
            key = key*31u + sd + (t ? str_hash(t) : 0u);
        }
        if (key != g_fd_cand){ g_fd_cand = key; return; }
        if (key == g_fd_said) return;
        int first = (g_fd_said == 0xFFFFFFFFu);
        g_fd_said = key;
        say_clear();
        if (first && INFO_TITLE[0]) say_text(INFO_TITLE);
        for (uint32_t w = 0x15u; w <= 0x17u; w++){ uint32_t sd = wsid(w); if (sd) say_sid(sd); }
        say_go();
        return;
    }
    /* ---- Finder (file list) ---- */
    if (scr_ready(SCR_FINDER)){
        int32_t row = FD_ROW, pos = FD_POS, cnt = FD_CNT;
        int fresh = (g_scr_last != SCR_FINDER);
        if (fresh){ g_scr_last = SCR_FINDER; g_fd_said = 0xFFFFFFFFu; g_fd_cand = 0xFFFFFFFEu; }
        if (row < 0 || row > 2 || cnt < 0 || cnt > 999) return;
        const volatile uint16_t *nm = str_ptr(wsid(0x12u + (uint32_t)row));
        uint32_t key = ((uint32_t)pos << 16) ^ (nm ? str_hash(nm) : 0u);
        if (key != g_fd_cand){ g_fd_cand = key; return; }         /* wait one poll: stable */
        if (key == g_fd_said) return;
        int first = (g_fd_said == 0xFFFFFFFFu);
        g_fd_said = key;
        say_clear();
        if (first) say_add(17u);                                   /* "Finder" */
        if (cnt == 0){ say_go(); return; }
        if (nm) say_text(nm);
        if (first && pos >= 0){ say_int((uint32_t)pos + 1u); say_add(CLIP_OF); say_int((uint32_t)cnt); }
        say_go();
        return;
    }
    /* ---- Versions screen: read the three labels with their values ---- */
    if (scr_ready(SCR_VERS)){
        if (g_scr_last != SCR_VERS){ g_scr_last = SCR_VERS; g_scr_hold = 0; g_fd_cand = 0; }
        uint32_t h = 0;
        for (uint32_t w = 60u; w <= 62u; w++){ const volatile uint16_t *p = str_ptr(wsid(w)); if (p) h = h*31u + str_hash(p); }
        if (g_scr_hold) return;                                    /* already read */
        if (h != g_fd_cand){ g_fd_cand = h; return; }              /* wait until values settle */
        g_scr_hold = 1;
        say_clear();
        for (uint32_t k = 0; k < 3u; k++){ say_sid(wsid(57u + k)); say_sid(wsid(60u + k)); }
        say_go();
        return;
    }
    /* ---- name editor (Rec File Name > User Defined Name) ---- */
    if (scr_ready(SCR_NAME)){ ne_poll(); return; }
    /* ---- dialog screen ---- */
    if (scr_ready(SCR_DLG)){
        uint32_t t = DLG_TYPE, b = DLG_BTN ? 1u : 0u;
        if (t < 1u || t > 10u) return;
        if (g_scr_last != SCR_DLG){                     /* dialog just opened */
            g_scr_last = SCR_DLG; g_dlg_btn = b;
            say_clear();
            say_add(*(volatile uint16_t*)(DLG_TITLES + t*2u));
            if (t == 1u) say_add(CLIP_RESET_NOTE);       /* Factory Reset: "the F3 then switches itself off" */
            if (t >= 8u){ say_add(*(volatile uint16_t*)(DLG_TEXTS + t*8u));
                          say_add(*(volatile uint16_t*)(DLG_TEXTS + t*8u + 2u)); }
            say_add(dlg_btn_sid(t, b));
            say_go();
        } else if (b != g_dlg_btn){                     /* moved between the buttons */
            g_dlg_btn = b;
            say_clear(); say_add(dlg_btn_sid(t, b)); say_go();
        }
        return;
    }
    /* ---- Set Date/Time screen ---- */
    if (scr_ready(SCR_DT)){
        uint32_t id = dt_field();
        if (id > 5u) return;
        uint32_t e = DT_EDIT ? 1u : 0u, v = dt_value(id);
        if (g_scr_last != SCR_DT){                      /* screen just opened */
            g_scr_last = SCR_DT;
            say_clear(); say_add(CLIP_SETDT); dt_add_field(id); say_go();
        } else if (DT_POS != g_dt_pos){                 /* moved to another field */
            say_clear(); dt_add_field(id); say_go();
        } else if (e != g_dt_edit){                     /* Enter: start / finish editing */
            say_clear(); if (e) say_add(CLIP_EDIT); else dt_add_field(id); say_go();
        } else if (v != g_dt_val){                      /* value changed while editing */
            say_clear(); dt_add_value(id, v); say_go();
        }
        g_dt_pos = DT_POS; g_dt_edit = e; g_dt_val = v;
        return;
    }
    if (g_scr_last){                                    /* left a special screen */
        g_scr_last = 0;
        if (SCR_CUR == SCR_MENU) g_mt_sel = 0xFFFFFFFFu;   /* back in the menu: re-read the row */
    }
    if (ok && node != g_mt_node){                       /* entered / left a menu */
        g_mt_node = node; g_mt_sel = sel; g_mt_title = title; g_mt_chk = chk; g_last_id = wid;
        say_clear(); say_add(title); say_add(sid); if (sel == chk) say_add(SEL_CLIP); say_go();
        return;
    }
    if (ok && sel != g_mt_sel){                         /* scrolled: interrupt, stay responsive */
        g_mt_sel = sel; g_mt_chk = chk; g_last_id = wid;
        say_clear(); say_add(sid); if (sel == chk) say_add(SEL_CLIP); say_go();
        return;
    }
    if (ok && chk != g_mt_chk){                         /* value committed on this row */
        g_mt_chk = chk;
        if (sel == chk){ say_clear(); say_add(SEL_CLIP); say_go(); }
        return;
    }
    if (wid != g_last_id){                              /* widget-4 fallback (other screens) */
        g_last_id = wid;
        if (!(ok && wid == g_mt_title)){ say_clear(); say_sid(wid); say_go(); }
    }
    return;
}


static int voice_next_queued(void){
    if (!g_sq_n) return 0;
    say_go();                                     /* pops the queue and calls voice_start */
    return g_active;
}

static void ensure_init(void){ if(!g_inited){ voice_init(); g_inited = 1; } }
/* Startup chime (clip 756), once the voice can really be heard: decode task alive, home
 * screen shown for CHIME_SETTLE_MS, VOLUME level loaded (non-zero; earlier it reads 0 and
 * the follow-gain made the chime inaudible). While it plays the poll is held, so nothing
 * cuts it off; afterwards the poll speaks whatever is current. No home screen within 30 s
 * (USB mode...) -> no chime. */
#define CHIME_CLIP 756u
#define CHIME_SETTLE_MS 400u
#define CHIME_GIVEUP_MS 30000u
static uint32_t g_chime_done, g_chime_playing, g_chime_home, g_chime_age;
static inline uint32_t ticks_per_s(void){ return (2u * valid_rate(FW_RATE)) / DMA_FRAMES; }
/* Follow the F3's UI language: switch to that language's bank (English if it has none). */
static void lang_follow(void){
    if (!g_fh) return;
    uint32_t lp = STR_LANGPP;
    if (!ram_ptr_ok(lp, 2)) return;
    uint32_t L = *(volatile uint16_t*)lp;
    if (L >= NLANG || L == g_lang) return;
    const flash_hdr *h = g_banks[L] ? g_banks[L] : g_banks[0];
    g_lang = L;
    if (!h || h == g_fh) return;
    g_active = 0; say_clear(); g_owait = 0;  /* stop the old language mid-sentence */
    bank_use(h);
}
/* Nothing at all happens until the F3 has finished starting: no flash reads, no decode task,
 * no speech until the home screen appears (or 12 s, for starts that never reach it). During
 * its audio set-up (FUN_8000aa30) the firmware reads calibration data from flash with FlexSPI
 * IP commands (FUN_8001b438/8001b428); a diagnostic build that started decoding right then
 * (reading the clip banks through the same FlexSPI, from a higher-priority task) froze the F3
 * at "SD card access". */
static uint32_t g_boot_ticks;
void voice_tick(void){
    if (!g_inited){
        if (SCR_CUR != SCR_HOME && ++g_boot_ticks < 12u * ((2u * valid_rate(FW_RATE)) / DMA_FRAMES)) return;
    }
    ensure_init();
    lang_follow();
    if (!g_home_seen && SCR_CUR == SCR_HOME) g_home_seen = 1u;
    if (!g_chime_done && g_fh && !g_cfg.chime) g_chime_done = 1u;
    if (!g_chime_done && g_fh){
        uint32_t tps = ticks_per_s();
        int ready = (g_task_alive != 0u);
        if (++g_chime_age > (CHIME_GIVEUP_MS / 1000u) * tps) g_chime_done = 1u;
        else if (ready && SCR_CUR == SCR_HOME && VOL_LEVEL != 0u){
            if (++g_chime_home >= (CHIME_SETTLE_MS * tps) / 1000u){
                g_chime_done = 1u;
                if (CHIME_CLIP < g_fnslots && g_fidx[CHIME_CLIP].nsamples){
                    voice_start(CHIME_CLIP);
                    if (g_active) g_chime_playing = 1u;
                    return;
                }
            }
        } else g_chime_home = 0u;
    }
    if (g_chime_playing){
        if (g_active) return;               /* chime still playing: hold the poll */
        g_chime_playing = 0u;
    }
    voice_poll();
}
#ifdef EMU_TEST   /* emulator-only entry points (never in a shipped build) */
uint32_t voice_t_int(uint32_t n){ say_clear(); say_int(n); return g_sq_n; }
uint32_t voice_t_year(uint32_t v){ say_clear(); say_year(v); return g_sq_n; }
const uint16_t *voice_t_q(void){ return g_sq; }
#endif

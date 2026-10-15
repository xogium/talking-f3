# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""f3emu -- run the talking F3's voice module, inside a real built F3SYSTEM.BIN, in the
Unicorn CPU emulator. See EMULATION.md for the set-up and a walk-through.

What is real: the module's code and data, the clip banks, and the F3 firmware's own code
and initialised data (menu tree, string tables, screen objects). What is simulated: the
F3 state that the firmware would set while running (current screen, button bits, volume,
language, file names...), which a test writes into RAM itself, and the FreeRTOS calls,
which are stubbed. The emulator runs the module's three entry points the way the F3 does:

    voice_dec_step()      the decode task's work (the real task calls it every 1 ms)
    voice_tick()          once per audio buffer, from the hook in the audio task
    voice_fill_half(b2)   then fills the 128-frame stereo buffer b2 if speaking

Typical use:

    from f3emu import F3Emu
    e = F3Emu("F3SYSTEM.BIN", "arm/voice.elf")      # a built image + the module's ELF
    e.boot()                                         # home screen, engine started, chime done
    e.press_stop(); e.run(1.5)                       # Stop on the home screen, 1.5 s of audio
    print(e.words())                                 # ['Remaining Time', '1', 'hours', ...]
    e.save_wav("status.wav")                         # what the headphones would have heard
"""
import os, struct, subprocess, sys, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
UNPACK = os.environ.get("F3_UNPACK", os.path.join(ROOT, "build", "unpack"))

# ---- firmware addresses (F3 v2.20; see RE_REFERENCE.md) ----
REC_RATE   = 0x2000A248      # u32 record rate; output = 2x
LANG_PTR   = 0x80498360      # -> u16 UI language (0 EN 1 FR 2 DE 3 IT 4 ES 5 ZH 6 JA)
BUTTONS    = 0x80490BAC      # u32 raw buttons, active low; Stop = bit 3
SCR_CUR    = 0x8020A55C      # current screen object
VOLUME     = 0x804BEBB8      # u16 headphone level 0..50
REC_STATE  = 0x80301676      # s16, 0 = idle
PLAYING    = 0x803016A8      # u32 playback flag
REC_TOTAL  = 0x80301680      # u32 recordable seconds
REC_ELAPSED = 0x80546CB0     # u32 elapsed seconds, 0xFFFFFFFF when idle
BATTERY    = 0x80545715      # u8 bars 0..4, 5 = external power
XTASKCREATE = 0x80096748     # FreeRTOS xTaskCreate (stubbed: "task created")
SCREENS = {"menu": 0x8020742C, "info": 0x8020746C, "finder": 0x8020748C, "name": 0x802074AC,
           "dialog": 0x802074EC, "datetime": 0x8020750C, "versions": 0x8020760C,
           "playback": 0x8020762C, "home": 0x8020764C}
LANGS = ["EN", "FR", "DE", "IT", "ES", "L5", "L6"]
SCRATCH_LANG = 0x20030000    # where the stub language value lives
B2 = 0x20010000              # the audio buffer handed to voice_fill_half
FRAMES = 128

def _need(path, what):
    if not os.path.exists(path):
        sys.exit(f"f3emu: {what} not found: {path}\n(see EMULATION.md, 'Set-up')")
    return path

class F3Emu:
    def __init__(self, image, elf, rec_rate=48000, unpack=UNPACK):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR
        self.img = open(_need(image, "image"), "rb").read()
        self.syms = self._nm(_need(elf, "module ELF"))
        rw = open(_need(os.path.join(unpack, "0x801F4400_rw.bin"), "unpacked RW data"), "rb").read()
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.mem_map(0x20000000, 0x80000)           # DTCM / OCRAM (stack, buffers)
        mu.mem_map(0x80000000, 0x1000000)         # SDRAM
        mu.mem_map(0x60000000, 0x800000)          # flash, read in place (XIP)
        mu.mem_map(0xE0000000, 0x100000)          # Cortex-M system space (DWT, for probes)
        mu.mem_write(0x60000000, self.img)
        cl = struct.unpack_from("<I", self.img, 0x7FA2F8)[0]
        mu.mem_write(0x80000000, self.img[0x200300:0x200300 + cl])   # MAIN + module, as booted
        mu.mem_write(0x801F4400, rw)              # what __scatterload would have unpacked
        self.faults, self.spoken, self.audio = [], [], []
        self.rate = rec_rate
        # xTaskCreate stub: report success and return; the test runs the task body itself
        def task_create(uc, addr, size, _):
            uc.reg_write(UC_ARM_REG_R0, 1); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        mu.hook_add(UC_HOOK_CODE, task_create, begin=XTASKCREATE, end=XTASKCREATE + 1)
        start = self.sym("voice_start") & ~1      # every clip that starts = one spoken word
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, s, d: self.spoken.append(uc.reg_read(UC_ARM_REG_R0)),
                    begin=start, end=start)
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, lambda uc, acc, a, s, v, d: (self.faults.append(hex(a)), False)[1])
        # the F3's state at power-on: idle, English, volume 30, nothing pressed
        self.w32(REC_RATE, rec_rate); self.w32(LANG_PTR, SCRATCH_LANG); self.w16(SCRATCH_LANG, 0)
        self.w32(BUTTONS, 0xFFFFFFFF); self.w16(VOLUME, 30); self.w32(REC_TOTAL, 3600)
        self.w32(REC_ELAPSED, 0xFFFFFFFF); self.w8(BATTERY, 4)
        self._texts = {}

    # ---- memory helpers ----
    def _nm(self, elf):
        out = {}
        for line in subprocess.check_output(["arm-none-eabi-nm", elf], text=True).splitlines():
            p = line.split()
            if len(p) >= 3: out[p[2]] = int(p[0], 16)
        return out
    def sym(self, name):
        if name not in self.syms: raise KeyError(f"symbol {name} not in the ELF")
        return self.syms[name]
    def w8(self, a, v): self.mu.mem_write(a, struct.pack("<B", v))
    def w16(self, a, v): self.mu.mem_write(a, struct.pack("<H", v & 0xFFFF))
    def w32(self, a, v): self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    def r32(self, a): return struct.unpack("<I", bytes(self.mu.mem_read(a, 4)))[0]
    def var(self, name): return self.r32(self.sym(name))      # read a module variable
    def wtext(self, a, text): self.mu.mem_write(a, (text + "\0").encode("utf-16-le"))

    # ---- running ----
    def call(self, name, r0=0, r1=0, stack=0x20040000):
        from unicorn import UcError
        from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1
        mu = self.mu
        mu.reg_write(UC_ARM_REG_SP, stack); mu.reg_write(UC_ARM_REG_LR, 0x20000001)  # return = stop
        mu.reg_write(UC_ARM_REG_R0, r0); mu.reg_write(UC_ARM_REG_R1, r1)
        try: mu.emu_start(self.sym(name) | 1, 0x20000000, count=50_000_000)
        except UcError as e: self.faults.append(f"{name}: {e}")
        return mu.reg_read(UC_ARM_REG_R0)
    def ticks_per_second(self): return 2 * self.rate // FRAMES
    def tick(self, keep_audio=True):
        """One audio buffer: decode step, voice_tick, voice_fill_half (as on the F3)."""
        self.call("voice_dec_step", stack=0x20060000)            # the decode task's own stack
        self.call("voice_tick")
        self.mu.mem_write(B2, b"\0" * (FRAMES * 8))              # the F3's own mix: silence here
        self.call("voice_fill_half", B2, 0)
        if keep_audio:
            shift = 13
            fr = struct.unpack("<%di" % (2 * FRAMES), bytes(self.mu.mem_read(B2, FRAMES * 8)))
            self.audio.extend(max(-32768, min(32767, s >> shift)) for s in fr[0::2])
    def run(self, seconds, keep_audio=True):
        for _ in range(int(seconds * self.ticks_per_second())): self.tick(keep_audio)

    # ---- the F3's state ----
    def screen(self, name_or_addr, ready=True):
        """Make a screen current (by name from SCREENS, or object address). ready = its
        'initialised and drawn' flag (bit 2), which the engine waits for."""
        a = SCREENS.get(name_or_addr, name_or_addr)
        self.w32(a, 6 if ready else 2); self.w32(SCR_CUR, a)
    def language(self, key):
        self.w16(SCRATCH_LANG, LANGS.index(key) if isinstance(key, str) else key)
    def press_stop(self, hold=0.3):
        self.w32(BUTTONS, 0xFFFFFFF7); self.run(hold); self.w32(BUTTONS, 0xFFFFFFFF)
    def boot(self, settle=3.0):
        """Home screen, engine started, start-up chime played; clears what was said."""
        self.screen("home"); self.run(settle, keep_audio=False)
        self.clear()

    # ---- results ----
    def clear(self): self.spoken.clear(); self.audio.clear()
    def words(self, lang=None):
        """What was said, as text: each started clip id -> its text in the bank plan."""
        lang = lang or LANGS[struct.unpack("<H", bytes(self.mu.mem_read(SCRATCH_LANG, 2)))[0]]
        if lang not in self._texts:
            sys.path.insert(0, os.path.join(ROOT, "tools"))
            import gen_flash_bank as g
            self._texts[lang] = {sid: e["text"] for sid, e in g.bank_plan(lang)["slots"].items()}
        t = self._texts[lang]
        return [t.get(i, f"#{i}") for i in self.spoken]
    def save_wav(self, path, normalize=False):
        """The voice as the headphones get it (left channel), at the output rate. Its level
        follows the simulated VOLUME (30 of 50 by default); normalize=True scales it to
        -3 dBFS for listening."""
        a = self.audio
        if normalize and a:
            pk = max(1, max(abs(x) for x in a)); a = [int(x * 23197 / pk) for x in a]
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(2 * self.rate)
            w.writeframes(struct.pack("<%dh" % len(a), *a))

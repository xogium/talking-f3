<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Zoom F3 v2.20: reverse-engineering reference

Addresses and structures used by the talking firmware, all verified on the device or by
disassembly of the correctly unpacked image (`tools/decompile.sh`). Runtime addresses unless
marked "file". See `TECHNICAL.md` for how they fit together.

## Image

| Address | What |
|---|---|
| file 0x000000-0x2001FF | BOOT region (never modified) |
| file 0x200300 | MAIN start = runtime 0x80000000 (`runtime = file - 0x200300 + 0x80000000`) |
| file 0x2002FC | checksum, big-endian sum of bytes [0x200300, EOF) |
| file 0x7FA2F8 | code_length (LE), stock 0x1BE454 |
| file 0x7FA2FC | version, ASCII "0220" |
| flash 0x7FA000 | "Dual AD Calibration" record (FUN_8001b468 erases/writes the sector); keep banks below 0x7F9000 |
| flash 0x7FB000 / 0x7FD000 | settings, two alternating 8 KB copies (FUN_8005da08 load, FUN_8005da98 save) |
| 0x402A8000 | FlexSPI controller; firmware flash commands via FUN_80034068 (IP commands, no locking) |
| 0x80000884 | `__scatterload`, table 0x801703F4 (RW data compressed in the file) |
| 0x801F4400-0x802AD280 | initialised RW data (menu tree, widgets, screen objects, string table pointers) |
| 0x802AD280-0x805C7368 | zero-initialised data |
| 0x801BFD00-0x801F4400 | unused SDRAM gap: the voice module (file 0x3C0000) |
| 0x60000000 | FlexSPI XIP window; file offset X is readable at 0x60000000 + X |
| 0x801F4568 | SystemCoreClock = 528000000 |

## RTOS (FreeRTOS)

| Address | What |
|---|---|
| 0x80096748 | `xTaskCreate(fn, name, depth_words, param, prio, handle*)`, returns 1 on success |
| 0x80095D90 | `vTaskDelay(ticks)`; tick 1 kHz (SysTick set by 0x80018168) |
| tasks | ApTimer 31, AudioProcess 30, AudioSubProcess 27, StreamDrive 26, GpioExpander 24, EventPort (buttons) 23, LcdDriver 19, LcdCycle 18, AppCycle 16, USB 14, AudioSubProcessStream 12 |

## Audio

| Address | What |
|---|---|
| 0x80010EC2 | AudioProcess task body (entry 0x80010E90) |
| 0x80010F3E (file 0x21123E) | the hook site, original `a4 f1 40 01` = `sub.w r1, r4, #0x40` |
| 0x80010F42-0x80010F80 | loop2: copies all 128 frames B2 -> DMA half (never patch) |
| control block 0x2000A248 | +0x0C B1, +0x10 B2; +0x00 record rate (output = 2x) |
| 0x20004B20 / 0x20004F20 | DMA output halves, 128 stereo int32 frames each |
| 0x20003880 | SAI1 TX config: 32-bit words, MSB first (full scale 2^31) |
| 0x804BEBB8 | headphone VOLUME level u16, 0..50 (popup shows x2) |
| 0x80051B18 | converter register write; VOLUME = register 0x37 |

## UI state

| Address | What |
|---|---|
| 0x80498360 | pointer to u16 current UI language (0 EN, 1 FR, 2 DE, 3 IT, 4 ES, 5 ZH, 6 JA) |
| 0x802A3D60 | per-language string table pointers: string n = `*(*(0x802A3D60 + L*4) + n*4)` (UTF-16) |
| 0x802087A4 | widget descriptor table; string id at descriptor + 4; widget 4 = 0x802087B4 |
| 0x8020740C | screen objects, 32 bytes each; word 0 bit 2 = initialised and drawn |
| 0x8020A55C | current screen object pointer |
| screen objects | index: address. 1: 742C menu, 2: 744C USB file transfer, 3: 746C file INFO, 4: 748C Finder, 5: 74AC name editor, 6: 74CC a system screen (shared draw 0x80020030), 7: 74EC dialogs, 8: 750C Set Date/Time, 10/12/13: 754C/758C/75AC timecode, 15: 75EC timecode/BT info, 16: 760C Versions, 17: 762C playback, 18: 764C home |
| 0x80490BAC | raw button state u32, active low; Stop = bit 3 |
| 0x80301676 | recorder state s16 (0 = idle) |
| 0x803016A8 | playback flag u32 |
| 0x80301680 / 0x80546CB0 | recordable seconds / elapsed seconds while recording (0xFFFFFFFF idle) |
| 0x80545715 | battery bars u8, 0..4, 5 = external power |
| 0x804BEC02 | battery type u8 (strings 67-69: Alkaline, Ni-MH, Lithium) |

## Menu tree

36-byte records in RW data: +0x01 flags (0x04 and not 0x80 = option list with a check
mark), +0x08 u16 string id, +0x0C children (pointer array), +0x10 s16 count, +0x12 s16
checked value, +0x14 s16 top visible row.

| Address | What |
|---|---|
| 0x804BF76C | level u8 |
| 0x804BF76D + level | depth u8 |
| 0x804BF774 + (level*7 + depth)*4 | current node |
| 0x804BF838 | cursor row s16 (0..2) |
| 0x80061A00 | scroll handler (keys 0x2B / 0x2D) |

## Screens outside the menu

| Address | What |
|---|---|
| 0x802AD61C | popup queue, 5 x s16 popup numbers; head u8 0x802AD63A; active u8 0x802AD638 |
| 0x80208A54 | popup table: entry t = u8 at +n*12; lines = u16 string ids at 0x80208A56 + t*12 + k*2 |
| 0x804C058A | dialog type u8 (1 Factory Reset, 2 Format, 3 Quick Test, 4 Full Test, 5 Delete, 6 Exit USB Audio I/F, 7 Firmware Update, 8-10 "OK to disconnect") |
| 0x804C04F0 | dialog focused button (0 Execute/OK, 1 Cancel) |
| 0x80166ECC / 0x80166E48 | dialog title ids / button and text ids |
| 0x804C04FC / 0x804C04FD | Set Date/Time focused field / edit mode |
| 0x804C04FE, 0x804C0500-03 | year u16, month, day, hour, minute |
| 0x80166EE2 + format*6 | field order per date format (format u8 0x804BEBFC) |
| 0x80302508 | magnification popup open: 0, 1 = input 1, 2 = input 2 |
| 0x804BEBB4 + ch*2 | magnification index (0..10 = x1..x1024); labels at 0x80165140 |
| 0x804C0586 | current file index s16 |
| 0x8049E6E8 | file database, 0x84-byte entries, UTF-16 name at +4 |
| 0x804BEA8E | file count s16 |
| 0x804BFA58 | INFO page u8 (0 date/time, 1 format, 2 length); title copy at 0x804BF84C |
| 0x804C028E / 0x804C0290 | Finder cursor row / selected index |
| widgets 0x15-0x17 | INFO label and values |
| widgets 0x12-0x14 | Finder rows |
| widgets 57-62 | Versions labels (SYSTEM, BOOT, CHECKSUM) and values (screen 760C, draw 0x80021168) |

## Name editor (Rec File Name > User Defined Name)

| Address | What |
|---|---|
| 0x802074AC | screen object 5; handler FUN_8002a320 (5 = Enter, 7 = Up/Down keys 0x2B/0x2D) |
| 0x804C02A4 | character set u8: 0 uppercase, 1 lowercase, 2 digits and symbols |
| 0x804C02A6 | focused key u16: 0..28 character, 29 switch set, 30 delete, 31 cursor left, 32 cursor right, 33 OK |
| 0x80166FEC | character table, 3 rows x 29 UTF-16: `A-Z _ - space`, `a-z _ - space`, `1234567890+=!#',;()[]{}$@^\`~ space` |
| 0x804C02CC | text, UTF-16, up to 40 characters (mode 2); Enter on a character inserts it at the cursor (FUN_8005f1d8) |
| 0x804C02A8 / 0x804C02AE | cursor position in the 13-character window / window scroll; cursor index = sum |
| 0x804C058E | editor mode u8 (2 = user defined name; 0 and 1 unused stubs in the F3) |

## Recording names and playback position

| Address | What |
|---|---|
| 0x804BEBBA | Rec File Name mode u8: 0 date, 1 user defined name |
| 0x804BEBBC | user defined name, UTF-16 |
| 0x804BEA94 | base name of the last file scan, UTF-16 (the date string in date mode; FUN_80036688) |
| 0x804BEBA8 | take number s16 the next recording gets (FUN_80037a60); name = base + "_NNN" if above 0 (FUN_80032ee8) |
| 0x8054527A | u8 1 while fast-forwarding / rewinding in Playback (FUN_800346d0 case 10 sets, case 0xd clears) |
| 0x80301698 | playback position u64, samples (FUN_80009530) |
| 0x80302158 | playing file's length u64, samples (FUN_80009420) |
| 0x80301CD8 | playing file's sample rate u32 (FUN_80009588) |
| 0x80545280 | elapsed seconds shown on the Playback screen (widget 7, string 284) |

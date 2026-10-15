<!-- SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Emulator tests

The voice module runs in the Unicorn CPU emulator against the F3 firmware's real code and
data. `f3emu.py` is the reusable harness; `example_*.py` show how to drive a screen and read
what was said; `emu_*.py` are the regression tests run before every build.

Set-up, a walk-through and how to read the results: **EMULATION.md** at the top of the
project.

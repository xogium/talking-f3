#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""Add the project's SPDX copyright and licence header to its own source and documentation
files (idempotent: files that already have an SPDX-License-Identifier are left alone).
Third-party code (third_party/) and generated files are never touched.
  python3 tools/spdx_headers.py [--check]"""
import os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COPY = "SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>"
LIC = "SPDX-License-Identifier: MIT"

FILES = (
    ["README.md", "TECHNICAL.md", "RE_REFERENCE.md", "HOW_TO_DECOMPILE.md", "METHOD.md",
     "EMULATION.md", "docs/Zoom_menu.md", ".gitignore"]
    + ["arm/" + f for f in ("voice.c", "voice.h", "voice.ld", "trampolines.S", "thumb_branch.py",
                            "opus_glue.c", "opus_cfg.h", "exports.c", "build.sh")]
    + ["patcher/" + f for f in ("README.md", "build_patcher.py", "export_data.py", "src/core.js",
                                "src/page.html", "wasm/f3speak.c", "wasm/f3opus.c",
                                "wasm/espeak_config.h", "wasm/build_wasm.sh")]
)
def collect():
    out = list(FILES)
    for d, exts in (("tools", (".py", ".sh", ".c")), ("tools/emu", (".py", ".md")),
                    ("tools/ghidra", (".java",)), ("patcher/test", (".js",))):
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            out += [f"{d}/{f}" for f in sorted(os.listdir(p)) if f.endswith(exts)]
    return [f for f in dict.fromkeys(out) if os.path.isfile(os.path.join(ROOT, f))]

def header(path, text):
    ext = os.path.splitext(path)[1] or os.path.basename(path)
    lines = text.split("\n")
    if ext in (".py", ".sh", ".gitignore"):
        i = 0
        while i < len(lines) and (lines[i].startswith("#!") or "coding" in lines[i][:30] and lines[i].startswith("#")):
            i += 1
        return "\n".join(lines[:i] + ["# " + COPY, "# " + LIC] + lines[i:])
    if ext in (".c", ".h", ".js", ".java"):
        return "// " + COPY + "\n// " + LIC + "\n" + text
    if ext in (".S", ".ld"):
        return "/* " + COPY + "\n * " + LIC + " */\n" + text
    if ext == ".md":
        return "<!-- " + COPY + "\n     " + LIC + " -->\n\n" + text
    if ext == ".html":                       # after the doctype, so the page stays in standards mode
        if lines[0].lower().startswith("<!doctype"):
            return "\n".join([lines[0], "<!-- " + COPY, "     " + LIC + " -->"] + lines[1:])
        return "<!-- " + COPY + "\n     " + LIC + " -->\n" + text
    raise ValueError(path)

def main():
    check = "--check" in sys.argv; missing = []
    for f in collect():
        p = os.path.join(ROOT, f); t = open(p, encoding="utf-8").read()
        if "SPDX-License-Identifier" in t[:600]: continue
        missing.append(f)
        if not check: open(p, "w", encoding="utf-8").write(header(f, t))
    print(("missing headers: " if check else "added headers: ") + (", ".join(missing) or "none"))
    sys.exit(1 if check and missing else 0)

if __name__ == "__main__": main()

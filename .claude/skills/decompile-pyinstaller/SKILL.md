---
name: decompile-pyinstaller
description: >-
  Reverse-engineer a PyInstaller-packaged Python application (a Mach-O / ELF /
  PE "onefile" or "onedir" bootloader) back to readable Python source. Use this
  whenever you need to understand, audit, or interoperate with a closed-source
  app that turns out to be PyInstaller-frozen Python — e.g. "decompile this
  .app / .exe", "how does this packaged Python tool work", "recover the source
  from this binary", "extract the .pyc and decompile it", or when you spot
  PyInstaller/pyinstxtractor/pycdc/.pyc/CArchive/PYZ in the task. Trigger even
  if the user doesn't name PyInstaller but describes a Python GUI/CLI app
  shipped as a single binary they want to read the logic of. Captures the
  two-decompiler fallback (pycdc → decompyle3) and the non-obvious gotchas that
  otherwise cost hours.
allowed-tools:
  - Read(*)
  - Write(*)
  - Grep(*)
  - Glob(*)
  - AskUserQuestion(*)
  # Broad Bash is needed: this skill drives a chain of external RE tools
  # (pyinstxtractor, pycdc/cmake build, uv, decompyle3) plus binary inspection
  # (file, xxd/od, grep) with dynamically-constructed paths.
  - Bash(*)
---

# Decompile a PyInstaller App

PyInstaller doesn't compile Python to machine code — it bundles the **`.pyc`
bytecode** plus a Python interpreter into one binary with a small C bootloader.
So "decompiling" such an app is really **extract the archive → decompile the
bytecode**, and the logic comes back as near-original Python. This skill is the
proven path through that, including the parts that fail silently.

## Ethical / legal boundary (read first)

This procedure is for **interoperability and personal reverse-engineering of
software you legitimately possess** — understanding a protocol, auditing
behavior, fixing compatibility. That use is broadly defensible.

What is **not** OK, and this skill will not help with: **redistributing** the
recovered proprietary source, the extracted bytecode, or the vendor's binary
(e.g. committing `decompiled/` to a public repo). Keep RE artifacts local; if a
repo grows out of the work, publish only your own original analysis and
`.gitignore` the vendor's code. If the target isn't the user's to analyze, stop
and say so.

## The procedure

Five steps. Steps 1–4 are the spine; step 5 is where the payoff is.

### 1. Extract the CArchive with `pyinstxtractor`

```bash
python3 pyinstxtractor.py /path/to/TheApp        # the bootloader binary
# → writes ./TheApp_extracted/
```

Get the tool from <https://github.com/extremecoders-re/pyinstxtractor> (single
file, no install). On macOS the binary is usually
`TheApp.app/Contents/MacOS/TheApp`; on Windows it's the `.exe`; ELF on Linux.

**The gotcha that saves the most time:** an app's *own* modules are frequently
sitting as **top-level `.pyc` files directly in the extracted dir** (PyInstaller
puts collected scripts in the CArchive root), **not** inside the encrypted
`PYZ-00.pyz_extracted/`. So even when pyinstxtractor warns
`[!] Warning: This may not be a pyinstaller archive` or skips PYZ extraction
(it runs under whatever Python you have, not the target's), you may already have
everything you need. **Look at the top level first** before fighting PYZ
decryption:

```bash
ls TheApp_extracted/*.pyc                         # the app's modules, often here
```

PYZ holds the stdlib + third-party deps; you usually don't need them to
understand the app's own logic.

### 2. Identify the target Python version from the `.pyc` magic

The decompiler **must** match the bytecode's Python version, so read it off the
4-byte magic header before choosing a tool:

```bash
xxd -l 4 TheApp_extracted/main.pyc                # e.g. 42 0d 0d 0a
```

`42 0d 0d 0a` = **Python 3.7** (observed in the wild). Magic numbers change
every minor (and even between alphas), so don't guess — look the value up in
CPython's `Lib/importlib/_bootstrap_external.py` (`MAGIC_NUMBER`) for the exact
minor. The version drives the venv in step 4.

> Some pyinstxtractor versions strip the magic header off extracted `.pyc`s. If
> a file is missing its header, prepend the correct 16-byte (3.7+) header before
> decompiling, or pass the version explicitly to the decompiler.

### 3. Primary decompile: `pycdc` (Decompyle++)

`pycdc` is C++ and version-agnostic-ish; it's the best first pass and produces
the cleanest output:

```bash
git clone https://github.com/zrax/pycdc && cd pycdc && cmake . && make
./pycdc  /path/to/TheApp_extracted/main.pyc  > main.py
```

Decompile each module you care about. For most files this is the whole job.

### 4. Fallback for files `pycdc` chokes on: version-matched `decompyle3`

`pycdc` throws on some constructs — you'll see `Unsupported opcode`,
`std::bad_cast`, or `end of stream` and a truncated/empty output. Don't try to
fix pycdc; switch decompilers. `decompyle3` / `uncompyle6` are **Python** tools
that are pickier about matching the *exact* interpreter version — so run them in
a throwaway venv pinned to the target version (step 2):

```bash
uv venv --python 3.8 .venv-dec                    # match the TARGET version
.venv-dec/bin/pip install decompyle3              # or: uncompyle6
.venv-dec/bin/decompyle3 TheApp_extracted/hard_file.pyc > hard_file.py
```

> `uv` makes the version-matched interpreter trivial to obtain — that's why it's
> the recommended driver. A 3.7 target often decompiles fine under a 3.8 venv;
> if it doesn't, pin the exact minor.

**Read the output from the BOTTOM.** decompyle3 prepends a parser/grammar dump
and diagnostics; the **actual reconstructed source is at the tail of the file**.
`tail -n +<n>` or scroll to the bottom — don't conclude it failed because the
top looks like noise.

Two decompilers, version-matched venv, read-from-the-tail: that trio is the part
people rediscover the hard way.

### 5. Mine the recovered source

Now grep for what you came for — the structured facts hide in plain code:

```bash
grep -rnE 'VID|PID|0x[0-9A-Fa-f]{4}|baud|CRC|MAGIC|password|api[_-]?key' decompiled/
grep -rn 'def cmd_|CMD_|struct.pack|bytearray\(' decompiled/   # protocol/byte layouts
```

Constants (VID/PID, ports, CRC polynomials), command tables, and frame/byte
layouts are the high-value targets. Capture findings with a confidence marker
(confirmed-in-source vs inferred) so later verification knows what to re-check.

## When you can't install tools yet — zero-download recon

If you're blocked from fetching external tools (sandbox, approval pending), you
can still mine **string/constant-level** intel without anything external: scan
the binary for embedded **zlib streams** (PyInstaller compresses bytecode) and
inflate them in pure Python to recover module names and string constants. This
won't give control flow, but it surfaces the module map and vocabulary so you
know what you're dealing with before the full decompile. It's a useful first
pass to justify the heavier toolchain.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| pyinstxtractor "Skipping pyz extraction" / wrong Python | Harmless — the app's modules are usually top-level `.pyc` anyway (step 1). |
| pycdc output empty / `std::bad_cast` / `end of stream` | Switch to decompyle3 in a version-matched venv (step 4). |
| decompyle3: "Unsupported Python version" | The venv Python ≠ target. Re-pin with `uv venv --python <exact-minor>`. |
| Output looks like grammar garbage | You're reading the head; the real source is at the **tail** (step 4). |
| `.pyc` won't load: bad magic | Header stripped on extraction — prepend the correct magic/header for the target version (step 2). |
| Decompiled names are mangled / `MACROKey=(13,)` junk | Decompiler artifact on enums/edge constructs — cross-check the raw bytecode (`pydisasm`) for that symbol. |

## Companion: identifying the target hardware (optional follow-on)

RE of a device-control app usually continues into "which USB/serial device is
this?". The macOS-specific traps (when `system_profiler` returns nothing; node
names that lie) are written up in
[`references/macos-usb-device-id.md`](references/macos-usb-device-id.md) — read
it if the work moves from the binary to the physical device.

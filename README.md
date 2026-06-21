# cyberboard-cli

<p align="center">
  <img src="assets/hero.jpg" alt="cyberboard-cli — write CyberBoard R4 config from the terminal" width="420">
</p>

![status](https://img.shields.io/badge/status-research%20%2F%20WIP-yellow) ![platform](https://img.shields.io/badge/platform-macOS-blue) ![target](https://img.shields.io/badge/target-CyberBoard%20R4-blue) ![protocol](https://img.shields.io/badge/protocol-reverse--engineered-purple) ![transport](https://img.shields.io/badge/transport-USB%20CDC%20serial-success) ![license](https://img.shields.io/badge/license-MIT-green)

A protocol knowledge base — and a planned CLI — for writing **AngryMiao
CyberBoard R4** configuration **without the official AM Master app**.

The goal: manage your keymap and LED display as **separate, version-controllable
sources**, and write them straight to the board from the command line — robustly,
without AM Master's flaky connection.

> **Status:** the write protocol has been fully reverse-engineered and the
> encoding is verified against real config data. The CLI itself is not yet
> implemented — this repo currently ships the **research** (a self-contained
> protocol spec under [`.claude/rules/`](.claude/rules/)) plus the verification
> tooling. Live-hardware capture is the only remaining gap before a write PoC.

## Why

The official setup has three problems this project fixes:

- **Keymap and LED live in one JSON file.** Applying a community LED animation
  overwrites your keymap. This project keeps them apart and recombines them only
  at build time, so "swap just the LED" is safe.
- **AM Master's connection is flaky** — writes succeed or fail at random. The
  root causes are now identified (see the protocol doc) and are fixable on the
  CLI side.
- **It's inflexible** — no partial updates, no scripting, no diffing.

## What we know (headline findings)

All reverse-engineered from AM Master 1.3.7 (decompiled locally; the decompiled
sources are **not** redistributed here — see *Legal*):

- **Transport is USB CDC serial (pyserial) @ 9600 baud.** HID is detection-only.
- **No encryption on the config path** — the AES in the app is just PyInstaller
  bytecode obfuscation.
- **Frames are a fixed 64 bytes:** `[0]` category, `[1]` subcommand,
  `[2..62]` payload, `[63]` **CRC-8** (poly `0x07`).
- **LED model:** `frames` = the 40×5 = 200-px top display; `keyframes` = the
  90 per-key backlights. Slots 1/2/3 = pages 5/6/7. *(Empirically verified:
  active pages always pack to exactly 200 px / 90 px — see
  [`_re/verify_encoding.py`](_re/verify_encoding.py).)*
- **Send sequence and full command table** are documented in
  [`.claude/rules/30-write-protocol.md`](.claude/rules/30-write-protocol.md).

## Repository layout

| Path | What |
|---|---|
| [`.claude/rules/`](.claude/rules/) | The protocol & schema knowledge base (Japanese) — start at `00-overview.md` |
| `.claude/rules/30-write-protocol.md` | The definitive write-protocol spec (transport, frames, CRC, command table, send order) |
| [`_re/verify_encoding.py`](_re/verify_encoding.py) | Standalone encoder that re-derives the byte packing and checks it against real config JSON (no device needed) |
| `_re/zscan.py` | Pure-Python zlib brute-scanner used in the first static-analysis pass |

> Confidence is marked throughout: 🟢 source-confirmed · 🟡 strong inference ·
> 🔴 needs live-hardware capture.

## Roadmap

- **M0 — Protocol analysis** ✅ decompiled; encoding verified against real data.
  Remaining: live serial capture to confirm the wire bytes.
- **M1 — Full write** of a known-good config (the merger's outputs) over the
  reverse-engineered sequence.
- **M2 — Read-back + diff** for verification.
- **M3 — Custom schema → IR build** (keymap / LED kept separate).
- **M4 — Partial writes** (LED slot only) + connection hardening.

## Legal

This is an independent interoperability project. The reverse-engineering was done
on a locally-owned copy of AM Master for the sole purpose of interoperating with
hardware the author owns. **The vendor's app, its installer, its extracted
bytecode, and the decompiled sources are deliberately excluded from this repo**
(see `.gitignore`); only original analysis and first-party tooling are published.
All trademarks belong to their respective owners. "AngryMiao" and "CyberBoard"
are trademarks of AngryMiao.

## Acknowledgements

- [`angrymiao-cyberboard-config-merger`](https://github.com/GeneralD/angrymiao-cyberboard-config-merger)
  and [`miaomerge`](https://github.com/GeneralD/miaomerge) — sibling tools that
  merge/composite LED animations into a writable JSON (writing still relies on
  AM Master; that's the gap this project closes).

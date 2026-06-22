# cyberboard-cli

<p align="center">
  <img src="assets/hero.jpg" alt="cyberboard-cli — write CyberBoard R4 config from the terminal" width="420">
</p>

![status](https://img.shields.io/badge/status-CLI%20usable%20·%20WIP-success) ![platform](https://img.shields.io/badge/platform-macOS-blue) ![target](https://img.shields.io/badge/target-CyberBoard%20R4-blue) ![python](https://img.shields.io/badge/python-%3E%3D3.11-blue) ![install](https://img.shields.io/badge/install-uv%20%2F%20pip-blue) ![protocol](https://img.shields.io/badge/protocol-reverse--engineered-purple) ![transport](https://img.shields.io/badge/transport-USB%20CDC%20serial-success) ![license](https://img.shields.io/badge/license-MIT-green)

A CLI — and the protocol knowledge base behind it — for writing **AngryMiao
CyberBoard R4** configuration **without the official AM Master app**.

The goal: manage your keymap and LED display as **separate, version-controllable
sources**, and write them straight to the board from the command line — robustly,
without AM Master's flaky connection.

> **Status:** the write protocol is fully reverse-engineered, and the `cyberboard`
> CLI is implemented and installable (see **Install** below). Writing and keymap
> read-back are **verified on real R4 hardware**; keymap authoring (TOML) and LED
> display authoring (GIF / declarative recipes) work today. Still WIP: per-key LED
> authoring, the MCP server, and the Claude plugin. The self-contained protocol
> spec lives under [`.claude/rules/`](.claude/rules/) (Japanese).

## Install

Requires **Python ≥ 3.11**. Dependencies are split into a small core plus
optional extras, so a keymap-only or device-only setup stays lean:

- **core** — `pyserial`, for device I/O (`devices` / `read` / `write` / `doctor`).
- **`[led]`** — `pillow`, for LED authoring (`led` / `anim`).
- **`[verify]`** — `jsonschema`, for strict schema validation in `verify`
  (it falls back to basic checks without it).
- **`[all]`** — everything (`pillow` + `jsonschema`).

Not on PyPI yet, so install straight from git (the default branch is `main`):

```sh
# Run once, no install (ephemeral) — with LED authoring:
uvx --from 'cyberboard-cli[led] @ git+https://github.com/GeneralD/cyberboard-cli' cyberboard --help

# Install as a persistent tool (uv):
uv tool install 'git+https://github.com/GeneralD/cyberboard-cli'                              # core only
uv tool install 'cyberboard-cli[led] @ git+https://github.com/GeneralD/cyberboard-cli'        # + LED

# Or pipx / pip into a venv:
pipx install 'cyberboard-cli[led] @ git+https://github.com/GeneralD/cyberboard-cli'
pip install 'cyberboard-cli[led] @ git+https://github.com/GeneralD/cyberboard-cli'
```

From a clone, run it without installing via uv:

```sh
uv run --extra led cyberboard --help     # LED commands need --extra led; device commands don't
```

## Usage

`cyberboard <command>` — run `cyberboard <command> --help` for each command's options.

| Command | What |
|---|---|
| `devices` / `device` | List connected boards / show one device's detail |
| `doctor` | Non-destructive connectivity health check |
| `build` | `keymap.toml` → IR config (`--dump` for the reverse) |
| `verify` | Validate an IR config against the schema |
| `led` | GIF ⇄ IR display codec (`gif2ir` / `ir2gif` / `recipe`) |
| `anim` | Render declarative LED animations (`render` / `preview`) |
| `read` | Read config back from the device (`keymap`) |
| `write` | Write an IR config to the device |
| `set-time` | Set the device RTC clock |

```sh
cyberboard devices                                              # find your board
cyberboard anim preview -r examples/led/text-scroll.json -o preview.gif   # author an LED animation
cyberboard build -k keymap.toml -b base.json -o config.json     # build a config from a TOML keymap
cyberboard write config.json --execute                          # write it (omit --execute for a dry run)
```

## MCP server

The same operations are available to MCP clients (Claude, editors, agents) via a
stdio server that wraps the CLI — so the MCP surface never drifts from the CLI.

```sh
pip install 'cyberboard-cli[mcp]'    # or: uv tool install 'cyberboard-cli[mcp] @ git+https://github.com/GeneralD/cyberboard-cli'
cyberboard-mcp                       # serves over stdio
```

Point a client at the `cyberboard-mcp` command (stdio). Example client config:

```json
{ "mcpServers": { "cyberboard": { "command": "cyberboard-mcp" } } }
```

Tools: `list_devices` · `device_info` · `doctor` · `verify` · `build_keymap` ·
`render_animation` · `preview_animation` · `gif_to_ir` · `ir_to_gif` ·
`read_keymap` · `write_config`. `write_config` is destructive and defaults to a
dry run (pass `execute=true` to actually write). LED tools need the `[led]`
extra in the same environment.

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

Done:

- **M0 — Protocol analysis** ✅ decompiled; encoding verified; wire bytes
  confirmed by live serial handshake on a real R4.
- **M1 — Full write** ✅ a known-good config writes over the reverse-engineered
  sequence (LED visually confirmed on hardware).
- **M2 — Read-back + diff** ✅ for the keymap (write → read → 1400/1400 match).
  LED has no read-back path, so it's authored from source.
- **M3 — Keymap build** ✅ `keymap.toml` → IR with lossless round-trip.
- **M5 — LED display authoring** ✅ GIF ⇄ IR codec + declarative animation recipes.

Productization (in progress): a unified `cyberboard` CLI core (done), standalone
packaging (this), then an MCP server and a Claude plugin that all call the same
core — plus per-key LED authoring and a sprite/vision LED design loop.

> Note: partial writes are **not** supported by firmware (`JSON_START` erases the
> whole config), so "swap just the LED" is done by read → merge → full write, not
> by a partial write.

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

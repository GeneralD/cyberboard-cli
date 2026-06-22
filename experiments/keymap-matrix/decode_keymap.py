#!/usr/bin/env python3
"""Decode a CyberBoard keymap: keycode format, layer structure, matrix layout.

Establishes the physical-key <-> matrix-index map WITHOUT press-testing: the
base layer (0) holds standard keycodes at each physical position, so decoding it
reveals the layout directly. The matrix is 25 columns x 8 rows = 200; the
physical index is `row * 25 + col`.

Usage:
  decode_keymap.py CONFIG.json            # full grid + per-layer summary
  decode_keymap.py CONFIG.json --layer 1  # one layer's grid
Reads the key_layer from any official/IR config, or a cb_read.py --json dump.
"""
from __future__ import annotations

import argparse
import json

COLS, ROWS = 25, 8

# --- HID usage-id -> name, page 0x07 (keyboard/keypad) ---
HID07 = {0x04 + i: c for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
HID07.update({0x1E + i: str((i + 1) % 10) for i in range(10)})  # 1..9,0
HID07.update({
    0x28: "Ent", 0x29: "Esc", 0x2A: "Bsp", 0x2B: "Tab", 0x2C: "Spc", 0x2D: "-",
    0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\", 0x33: ";", 0x34: "'", 0x35: "`",
    0x36: ",", 0x37: ".", 0x38: "/", 0x39: "Cap", 0x46: "PrSc", 0x47: "ScLk",
    0x48: "Pause", 0x49: "Ins", 0x4A: "Home", 0x4B: "PgUp", 0x4C: "Del",
    0x4D: "End", 0x4E: "PgDn", 0x4F: "Rgt", 0x50: "Lft", 0x51: "Dwn", 0x52: "Up",
    0x53: "NumLk", 0x65: "App",
})
HID07.update({0x3A + i: f"F{i + 1}" for i in range(12)})  # F1..F12
HID07.update({0xE0: "LCt", 0xE1: "LSh", 0xE2: "LAl", 0xE3: "LGu",
              0xE4: "RCt", 0xE5: "RSh", 0xE6: "RAl", 0xE7: "RGu"})
# page 0x0C (consumer / media)
HID0C = {0xB5: "Nxt", 0xB6: "Prv", 0xB7: "Stop", 0xCD: "Ply", 0xE2: "Mut",
         0xE9: "Vl+", 0xEA: "Vl-", 0x70: "Br+", 0x6F: "Br-"}


def decode(code: str) -> str:
    """`#MMPPUUUU` -> short name. MM=modifier, PP=usage page, UUUU=usage id."""
    mm, pp, uuuu = int(code[1:3], 16), int(code[3:5], 16), int(code[5:9], 16)
    if pp == 0 and uuuu == 0:
        return "."
    if pp == 0x07:
        name = HID07.get(uuuu, f"07:{uuuu:x}")
    elif pp == 0x0C:
        name = HID0C.get(uuuu, f"c{uuuu:x}")
    elif pp == 0x92:
        name = f"Fn{uuuu:x}"  # AM vendor page (names live in the web UI, not here)
    else:
        name = f"{pp:x}:{uuuu:x}"
    return f"M{mm:x}+{name}" if mm else name


def layers_of(config: dict) -> list[list[str]]:
    return [ly["layer"] for ly in config["key_layer"]["layer_data"]]


def grid(layer: list[str]) -> str:
    out = []
    for r in range(6):  # physical keys live in rows 0-5
        cells = [decode(layer[r * COLS + c]) for c in range(15)]
        out.append(f"row{r} (idx {r*COLS:3}-{r*COLS+14:3}): " + " ".join(f"{c:>5}" for c in cells))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--layer", type=int, default=None)
    args = ap.parse_args()

    layers = layers_of(json.load(open(args.config)))
    used = sorted({i for ly in layers for i, c in enumerate(ly) if c != "#00000000"})
    print(f"layers={len(layers)}  keys/layer={len(layers[0])}  "
          f"physical keys={len(used)}  matrix={COLS}x{ROWS} (index = row*{COLS} + col)")

    targets = [args.layer] if args.layer is not None else range(len(layers))
    for li in targets:
        pages = sorted({c[3:5] for c in layers[li] if c != "#00000000"})
        print(f"\n=== layer {li}  (usage-pages: {pages}) ===")
        print(grid(layers[li]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

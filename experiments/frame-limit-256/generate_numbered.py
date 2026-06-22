#!/usr/bin/env python3
"""Generate (and optionally write) a config whose LED slots render their own
frame index as a number — the tool that proved the 256-frame playback ceiling.

Each display frame draws its index with a 3x5 font on the 40x5 matrix, so you
can VISUALLY count how many frames the device actually plays: watch a slot count
up and note the value before it loops. We author N (e.g. 300, the official
editor's max) frames per slot; the device loops at 255 => only 256 (2^8) play.

This is the reproducible evidence artifact for .claude/rules/90 (2026-06-22).

Usage:
  generate_numbered.py --frames 300 --slots 5,6,7 --out config.json [--write]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
from cb_device import list_devices  # noqa: E402
from cb_write import plan, write_config  # noqa: E402
from cb_protocol import crc_ok  # noqa: E402

SRC = Path(__file__).resolve().parent / "base.json"
W, H = 40, 5
OFF = "#000000"
# distinct color per slot so each Custom LED slot is identifiable on the board
SLOT_COLORS = {5: "#FFFFFF", 6: "#00FFFF", 7: "#FFFF00"}
FONT = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
}


def render(num: int, on: str) -> list[str]:
    grid = [[OFF] * W for _ in range(H)]
    s = str(num)
    x0 = max(0, (W - (len(s) * 4 - 1)) // 2)
    for di, ch in enumerate(s):
        gx = x0 + di * 4
        for row in range(H):
            for col in range(3):
                if FONT[ch][row][col] == "1" and gx + col < W:
                    grid[row][gx + col] = on
    return [grid[y][x] for y in range(H) for x in range(W)]


def numbered(n: int, on: str) -> dict:
    return {"valid": 1, "frame_num": n, "frame_data": [{"frame_index": i, "frame_RGB": render(i, on)} for i in range(n)]}


def minimal(n_pixels: int) -> dict:
    return {"valid": 1, "frame_num": 1, "frame_data": [{"frame_index": 0, "frame_RGB": [OFF] * n_pixels}]}


def make_config(base: dict, frames: int, slots: list[int], speed_ms: int) -> dict:
    d = copy.deepcopy(base)
    for pg in d["page_data"]:
        idx = pg["page_index"]
        if idx in slots:
            pg["valid"] = True
            pg["speed_ms"] = speed_ms
            pg["frames"] = numbered(frames, SLOT_COLORS.get(idx, "#FFFFFF"))
            pg["keyframes"] = minimal(90)
        elif idx in (5, 6, 7):
            pg["valid"] = True
            pg["frames"] = minimal(200)
            pg["keyframes"] = minimal(90)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--slots", default="5,6,7", help="page indices, comma-separated")
    ap.add_argument("--speed", type=int, default=200)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "three-slots-300frames.json"))
    ap.add_argument("--base", default=str(SRC),
                    help="base config to layer the numbered slots onto (default: the neutral skeleton; "
                         "pass the live config when --write so the keymap is preserved)")
    ap.add_argument("--write", action="store_true", help="also write to the connected board")
    args = ap.parse_args()

    base = json.load(open(args.base))
    slots = [int(s) for s in args.slots.split(",")]
    cfg = make_config(base, args.frames, slots, args.speed)
    json.dump(cfg, open(args.out, "w"))
    fp = plan(cfg)
    print(f"frames/slot={args.frames}  slots={slots}  data_frames={fp.total}  saved={args.out}")

    if not args.write:
        print("(not written — pass --write to push to the board)")
        return 0

    port = next(d.port for d in list_devices() if d.is_cyberboard)
    t0 = time.time()
    ok, reply = write_config(port, fp.frames)
    print(f"port {port}  ack={ok}  rev[2]={reply[2] if len(reply) >= 3 else None}  crc={'ok' if crc_ok(reply) else 'bad'}  {time.time()-t0:.1f}s")
    print(f"-> each of slots {slots} loops at 255 (256 frames) despite {args.frames} authored.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

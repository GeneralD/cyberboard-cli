#!/usr/bin/env python3
"""B2 experiment: is a PARTIAL write (one section only) possible, or does a
JSON transaction replace the whole config?

The CLI's headline goal is to manage keymap and LED separately. The protocol
looks like it might allow it: JSON_START -> sections ([4,*]/[5,*] LED,
[6,7] keymap, ...) -> JSON_END. So can we send only the LED sections and have
the firmware keep the existing keymap?

Method — exploit the read-back asymmetry. The keymap has a read path ([6,9]);
LED frames do not. So:
  1. read the keymap (before)
  2. send an LED-only transaction (slot1 -> solid magenta, visible) that OMITS
     key_layer / exchange / swap
  3. read the keymap (after) — AFTER a settle delay (see note)
  4. if the keymap survived unchanged, the firmware does section-wise partial
     updates; if it was erased, a transaction replaces everything.

RESULT (R4, 2026-06-22): the keymap came back ALL #FFFFFFFF — i.e. flash-erased
(NOR erases to 0xFF). So JSON_START erases the config region, each section
reprograms its slice, and OMITTED sections stay erased. => NO partial write.

Settle-delay note: reading the keymap immediately after JSON_END returned all
#00000000 (zeros) on the restore write — the flash commit had not finished.
Waiting ~2s then reading gave the correct 1400/1400. Always settle before a
read-back verify.

DESTRUCTIVE + RECOVERABLE: this erases the keymap. Restore with
  cb_write.py <known-good>.json --execute
Run from the repo root.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from cb_device import list_devices  # noqa: E402
from cb_write import (  # noqa: E402
    uncertainty_frames, page_control_frames, word_page_frames,
    rgb_frame_frames, key_frame_frames, write_config,
)
from cb_read import read_keymap  # noqa: E402
from cb_protocol import crc_ok  # noqa: E402

BASE = ROOT / "experiments" / "frame-limit-256" / "base.json"  # neutral skeleton
MAGENTA = "#FF00FF"
SETTLE_S = 2.0


def main() -> int:
    port = next((d.port for d in list_devices() if d.is_cyberboard), None)
    if port is None:
        print("No CyberBoard found.")
        return 1
    print(f"port: {port}")

    before = read_keymap(port)
    flat_before = [c for ly in before for c in ly]
    print(f"baseline keymap: {len(flat_before)} keys, "
          f"{sum(1 for c in flat_before if c != '#00000000')} mapped")

    cfg = json.load(open(BASE))
    for pg in cfg["page_data"]:
        if pg["page_index"] == 5:
            pg["valid"] = True
            pg["frames"] = {"valid": 1, "frame_num": 1,
                            "frame_data": [{"frame_index": 0, "frame_RGB": [MAGENTA] * 200}]}
    pages = cfg["page_data"]
    led_only = (
        *uncertainty_frames(pages),
        *page_control_frames(pages),
        *word_page_frames(pages),
        *rgb_frame_frames(pages),
        *key_frame_frames(pages),
    )
    bad = sum(1 for f in led_only if not (len(f) == 64 and crc_ok(f)))
    print(f"LED-only transaction: {len(led_only)} frames (keymap OMITTED), crc_bad={bad}")

    t0 = time.time()
    ok, reply = write_config(port, led_only)
    print(f"ACK={ok}  rev[2]={reply[2] if len(reply) >= 3 else None}  {time.time()-t0:.1f}s")

    time.sleep(SETTLE_S)  # flash commit must finish before read-back
    after = read_keymap(port)
    flat_after = [c for ly in after for c in ly]
    n = min(len(flat_before), len(flat_after))
    mism = sum(1 for i in range(n) if flat_before[i] != flat_after[i])
    erased = sum(1 for c in flat_after if c == "#FFFFFFFF")
    print(f"\nafter keymap: {erased}/{len(flat_after)} keys = #FFFFFFFF (flash-erased)")
    print(f"keymap diff vs before: {mism}/{n} changed")

    print("\n=== VERDICT ===")
    if mism == 0:
        print("keymap PRESERVED => partial write WORKS (section-wise updates).")
    elif erased > n * 0.9:
        print("keymap ERASED to 0xFF => NO partial write: a transaction replaces")
        print("the whole config; omitted sections are left flash-erased.")
    else:
        print("keymap CHANGED (not cleanly erased) => inspect further.")
    print("restore with: cb_write.py <known-good>.json --execute")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""dump — pull the device's current config into one provenance-labelled IR file.

The two halves of a CyberBoard config have asymmetric readability (see
cb_store): the keymap can be read straight off the device ([6,9] get_key_msg),
but the LED display / per-key frames cannot be read back at all — the only
record of them is the last full IR we wrote, kept locally in the store. So a
faithful dump is a *hybrid*: a live keymap stitched onto the stored LED state,
with each half labelled by where it came from so the result is never mistaken
for a clean live readout.

Provenance is emitted both as a `_provenance` block inside the IR (so the file
is self-describing) and as a one-line summary on stderr:

    keymap : live | stored@<ts> | unknown
    led    : last-written@<ts> | unknown

When the device is offline the keymap falls back to the stored copy (clearly
labelled `stored@<ts>`); with neither a device nor a stored config there is
nothing to dump and the command fails cleanly.

Usage:
    cb_dump.py [PORT] [-o FILE]      # -o omitted => stdout
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cb_store
from cb_device import DeviceInfo, list_devices, probe
from cb_read import read_keymap


def _keymap_fragment(layers: list[list[str]]) -> dict:
    """Wrap read-back layers in the key_layer shape the IR / schema expect."""
    return {
        "valid": 1,
        "layer_num": len(layers),
        "layer_data": [{"layer": layer} for layer in layers],
    }


def _resolve_device(port: str | None) -> DeviceInfo | None:
    """The target device: the named port, else the first auto-detected board."""
    if port is not None:
        return probe(port, full=True)
    boards = [d for d in list_devices(full=True) if d.is_cyberboard]
    return boards[0] if boards else None


def _file_ts(path: Path) -> str:
    """ISO8601 (UTC, second precision) of a file's last-modified time."""
    stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return stamp.isoformat(timespec="seconds")


def _stored_product_id() -> str | None:
    """The sole stored device key, or None when there are zero or several.

    Single-device is the supported case (the R4 has no per-unit identity), so an
    offline dump can unambiguously target the one device dir if exactly one
    exists; we refuse to guess between several.
    """
    devices = cb_store.store_root() / "devices"
    if not devices.is_dir():
        return None
    keys = [d.name for d in devices.iterdir() if d.is_dir()]
    return keys[0] if len(keys) == 1 else None


def dump_ir(device: DeviceInfo | None, *, stored_pid: str | None) -> tuple[dict, dict]:
    """Compose the hybrid IR and its provenance block.

    Raises ValueError with a user-facing message when there is nothing to dump.
    """
    product_id = device.product_id if device is not None else stored_pid
    if not product_id:
        raise ValueError(
            "no device connected and no stored config found — nothing to dump.\n"
            "  connect the R4 by wire, or run a write first to populate the store."
        )

    current = cb_store.load_current(product_id)
    cur_ts = _file_ts(cb_store.current_path(product_id)) if current is not None else None

    # --- keymap half: live read off the device, else the stored copy ---
    if device is not None:
        keymap = _keymap_fragment(read_keymap(device.port))
        keymap_prov = "live"
        version = device.version
        cb_store.record_seen(product_id, version=version)
    elif current is not None and "key_layer" in current:
        keymap = current["key_layer"]
        keymap_prov = f"stored@{cur_ts}"
        version = (cb_store.load_meta(product_id) or {}).get("version")
    else:
        keymap = None
        keymap_prov = "unknown"
        version = (cb_store.load_meta(product_id) or {}).get("version")

    # --- LED / body half: only the last full IR we wrote knows it ---
    if current is not None:
        ir = copy.deepcopy(current)
        ir.pop("_provenance", None)  # never nest a prior dump's provenance
        led_prov = f"last-written@{cur_ts}"
    else:
        ir = {}
        led_prov = "unknown"

    if keymap is not None:
        ir["key_layer"] = keymap

    if not ir:
        raise ValueError(
            f"nothing to dump for {product_id}: device not connected and no stored config.\n"
            "  connect the R4 by wire, or run a write first to populate the store."
        )

    prov = {
        "keymap": keymap_prov,
        "led": led_prov,
        "product_id": product_id,
        "version": version,
        "dumped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return {"_provenance": prov, **ir}, prov


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dump the device's current config (hybrid: live keymap + stored LED).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("port", nargs="?", help="serial port (default: auto-detect)")
    ap.add_argument("-o", "--output", metavar="FILE", help="write IR to FILE (default: stdout)")
    args = ap.parse_args()

    device = _resolve_device(args.port)
    if device is None and args.port is not None:
        print(f"dump: no CyberBoard responded on {args.port}; trying the stored config.",
              file=sys.stderr)

    try:
        out, prov = dump_ir(device, stored_pid=_stored_product_id())
    except ValueError as e:
        print(f"dump: {e}", file=sys.stderr)
        return 1

    if prov["keymap"] != "live":
        print("dump: device not connected — keymap is the stored copy, not a live read.",
              file=sys.stderr)
    print(f"dump: keymap={prov['keymap']}, LED={prov['led']}, product_id={prov['product_id']}",
          file=sys.stderr)

    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"dump: wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

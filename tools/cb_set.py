#!/usr/bin/env python3
"""set — edit one setting in place (read -> merge -> full write -> auto-snapshot).

The firmware has no partial write (JSON_START erases the whole config flash), so
"changing one key" means: read the device's *live* keymap ([6,9]), swap the one
position, keep the LED untouched from the stored full IR (current.json — LED
can't be read back), and full-write the merged result through cb_write.

Like cb_write it is **dry-run by default** (prints the frame plan + the single
change); pass `--execute` to actually write. On execute it snapshots the
outgoing config *before* writing (JSON_START erases flash, so a failed write
leaves the device bad — the pre-edit live-keymap+LED combo exists nowhere else
and is the only recovery point), then after a successful write + settle it
verifies the change via a [6,9] read-back, points current.json at what it wrote,
and snapshots the new config too. So both the before and after states stay in
`history` and the rollback is reversible (`restore`).

  cb_set.py key <layer> <pos> <val> [PORT] [--device CB04]            # dry-run
  cb_set.py key <layer> <pos> <val> [PORT] [--device CB04] --execute  # write it
      <layer> = 1..7   <pos> = r{row}c{col} or an R4 alias (esc, a, caps, ...)
      <val>   = a readable name (lctrl, volup, ...) or raw #MMPPUUUU, or '.' to clear
"""
from __future__ import annotations

import argparse
import copy
import sys
import time

import cb_store
import keycode
import keymap_alias

# Time to let the device commit the flash before we probe / read back. The write
# path settles asynchronously: probing too soon reads a half-committed state
# (see .claude/rules/30-write-protocol.md §5a).
SETTLE_SECONDS = 2.0


def edit_key(ir: dict, layer: int, pos: str, value: str) -> tuple[dict, int, str, str]:
    """Return (new_ir, idx, old_code, new_code) for the one-key edit.

    `ir` must be a clean full IR (no _provenance). Raises ValueError / KeyError
    with a user-facing message on a bad layer, position, or value.
    """
    layers = (ir.get("key_layer") or {}).get("layer_data") or []
    if not (1 <= layer <= len(layers)):
        raise ValueError(
            f"layer {layer} out of range (1..{len(layers)})" if layers
            else "this config has no keymap layers to edit"
        )
    idx = keymap_alias.resolve_position(pos)  # raises KeyError / ValueError
    row = layers[layer - 1].get("layer") or []
    if not (0 <= idx < len(row)):
        raise ValueError(f"{pos!r} -> matrix index {idx} out of range (0..{len(row) - 1})")
    new_code = keycode.name_to_code(value)  # raises KeyError / ValueError
    new_ir = copy.deepcopy(ir)
    new_ir["key_layer"]["layer_data"][layer - 1]["layer"][idx] = new_code
    return new_ir, idx, row[idx], new_code


def _keymap_matches(readback: list[list[str]], key_layer: dict) -> bool:
    """True iff the read-back keymap equals key_layer's layers (case-normalized).

    Compares every layer, not just the edited cell — a partial/corrupt write can
    leave the target key right while other keys land wrong. A truncated [6,9]
    read yields short/missing layers, which simply fail the equality (never an
    IndexError). Both sides are upper-cased (read_keymap emits uppercase; stored
    codes may not), mirroring cb_read's --compare normalization.
    """
    want = [[c.upper() for c in (layer.get("layer") or [])]
            for layer in (key_layer.get("layer_data") or [])]
    got = [[c.upper() for c in layer] for layer in readback]
    return got == want


def _print_plan(fp, label: str) -> list[int]:
    """Print the frame plan and return the indices of any malformed frames."""
    import cb_write

    print(label)
    print(f"frame plan ({fp.total} data frames; JSON_END total = {fp.total}):")
    for name, count in fp.sections:
        print(f"  {name:16} {count:>5}")
    bad = [i for i, f in enumerate(fp.frames) if not (len(f) == 64 and cb_write.crc_ok(f))]
    print(f"  {'all 64B + CRC ok':16} {'yes' if not bad else f'NO ({len(bad)} bad)'}")
    return bad


def _cmd_key(args) -> int:
    import cb_dump
    import cb_read
    import cb_write

    stored_pid = args.device or cb_store.sole_device()
    device = cb_dump._resolve_device(args.port)
    if device is None and args.port is not None:
        print(f"set key: no CyberBoard responded on {args.port}; trying the stored config.",
              file=sys.stderr)

    # Gather the outgoing config: live keymap when the device is attached, else
    # the stored copy (a dry-run preview still works offline). Reuses dump's
    # hybrid merge so the keymap base is the device truth, not a stale file.
    try:
        gathered, prov = cb_dump.dump_ir(device, stored_pid=stored_pid)
    except (ValueError, OSError) as e:
        print(f"set key: {e}", file=sys.stderr)
        return 1
    pid = prov["product_id"]

    outgoing = {k: v for k, v in gathered.items() if k != "_provenance"}
    # A full write must carry the LED (page_data) too, but LED can't be read
    # back — so without a stored full IR there is no baseline to preserve, and
    # planning a write from a keymap-only IR would crash on page_data (even a
    # dry run). Fail cleanly first.
    if prov["led"] == "unknown" or "page_data" not in outgoing:
        print(f"set key: no stored full config for {pid} — LED can't be read back, so a full "
              "write needs a saved baseline. Run `cyberboard dump` or a write first.",
              file=sys.stderr)
        return 1
    try:
        new_ir, idx, old_code, new_code = edit_key(outgoing, args.layer, args.pos, args.value)
    except (KeyError, ValueError) as e:
        print(f"set key: {e}", file=sys.stderr)
        return 1

    fp = cb_write.plan(new_ir)
    bad = _print_plan(fp, f"set key {pid}: layer {args.layer} {args.pos} (idx {idx})")
    print(f"  change: {keycode.code_to_name(old_code)} ({old_code}) "
          f"-> {keycode.code_to_name(new_code)} ({new_code})")
    print(f"  keymap base: {prov['keymap']}, LED: {prov['led']}")

    if not args.execute:
        print("\n(dry-run — nothing sent. re-run with --execute to write.)")
        return 0 if not bad else 1

    if bad:
        print("refusing to write: malformed frames present.", file=sys.stderr)
        return 1
    # An execute must edit the *live* keymap, never a stale stored copy, and
    # needs a device to write to.
    if device is None or prov["keymap"] != "live":
        print("set key --execute needs the device connected (it reads the live keymap, "
              "then writes the merged config back).", file=sys.stderr)
        return 1
    port = device.port

    # Re-probe right before the destructive write. dump_ir read the live keymap
    # earlier, but the device could be unplugged or the serial node reused since;
    # JSON_START erases config flash *first*, so a swapped-in board would be
    # clobbered before the post-write probe could notice. Verify identity now and
    # refuse if the port is no longer the expected board.
    before = cb_write.probe(port, full=True)
    if not (before and before.is_cyberboard and before.product_id == pid):
        found = before.product_id if (before and before.is_cyberboard) else "no CyberBoard"
        print(f"refusing to write: {port} now has {found}, not {pid}.", file=sys.stderr)
        return 1

    # Persist the before-image *now*, before the write. JSON_START erases the
    # whole config flash, so a write that fails partway leaves the device bad;
    # `outgoing` (live keymap + stored LED) exists nowhere else and is the only
    # recovery point, so record it before risking the write — not on success.
    before_snap = cb_store.snapshot(pid, outgoing)
    print(f"\nport: {port}")
    print(f"snapshot (before): {before_snap.stem}")
    print(f"writing {fp.total} frames (~{fp.total * cb_write.WRITE_DELAY:.0f}s minimum)...")

    ok, reply = cb_write.write_config(port, fp.frames)
    crc = "ok" if cb_write.crc_ok(reply) else "bad/none"
    print(f"JSON_END reply ({len(reply)}B, crc {crc}): {reply.hex()}")
    print(f"ACK (byte[2]==1): {ok} -> {'SUCCESS' if ok else 'FAILED'}")
    if not ok:
        print("device did not ACK; before-snapshot kept for recovery, current.json unchanged.",
              file=sys.stderr)
        return 1

    time.sleep(SETTLE_SECONDS)
    after = cb_write.probe(port, full=True)
    print(f"after:  {after.product_id if after else 'NO RESPONSE'} / {after.version if after else '?'}")
    if not (after and after.is_cyberboard and after.product_id == pid):
        print("device not the expected CyberBoard after write; not recording current.",
              file=sys.stderr)
        return 1

    # Confirm the write landed via the [6,9] read-back — the only readable half
    # (LED can't be read back). Compare the *whole* keymap, not just the edited
    # cell: a partial/corrupt write could leave the target right yet other keys
    # wrong, and a truncated read fails the match instead of crashing.
    readback = cb_read.read_keymap(port)
    if not _keymap_matches(readback, new_ir["key_layer"]):
        print("read-back keymap does not match what we wrote; not recording current.",
              file=sys.stderr)
        return 1
    print(f"read-back OK: full keymap matches (layer {args.layer} idx {idx} = "
          f"{keycode.code_to_name(new_code)})")

    # Point current.json at what we wrote (current must equal the last full IR we
    # wrote, or dump / diff report a stale LED), then snapshot the new state so
    # it's a navigable history point too. Sequential locked steps — never nested
    # (cb_store's flock is per-fd; nesting would self-deadlock).
    cb_store.save_current(pid, new_ir, version=after.version)
    after_snap = cb_store.snapshot(pid, new_ir)
    print(f"snapshot (after):  {after_snap.stem}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Edit one setting in place (read -> merge -> full write -> snapshot).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="what", required=True)

    k = sub.add_parser("key", help="reassign one key (live keymap -> edit -> full write)")
    k.add_argument("layer", type=int, help="layer 1..7 (1 = default)")
    k.add_argument("pos", help="key position: r{row}c{col} or an R4 alias (esc, a, caps, ...)")
    k.add_argument("value", help="new value: a readable name, raw #MMPPUUUU, or '.' to clear")
    k.add_argument("port", nargs="?", help="serial port (default: auto-detect)")
    k.add_argument("--device", metavar="PRODUCT_ID",
                   help="stored device to merge LED from (default: sole stored)")
    k.add_argument("--execute", action="store_true", help="actually write (default: dry-run)")
    k.set_defaults(func=_cmd_key)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

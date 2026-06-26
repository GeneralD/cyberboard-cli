#!/usr/bin/env python3
"""restore — re-write a past snapshot to the device (undo / rollback).

The firmware has no partial write (JSON_START erases the whole config flash), so
"rolling back" means full-writing a past snapshot back over the device. We keep
timestamped snapshots under the store's history/ (see cb_store); restore picks
one — `latest`, or a snapshot timestamp (stem or leading prefix) — and writes it
through cb_write.

Like cb_write it is **dry-run by default** (prints the frame plan); pass
`--execute` to actually write. After a successful write it waits ~2s for the
device to settle, then records the restore itself as a new snapshot and refreshes
current.json — so the rollback is in history too (you can roll back a rollback),
and `dump`/`diff current` keep telling the truth about what's on the device.

Snapshot resolution is pure stdlib; the actual write pulls in pyserial via
cb_write, so a dry-run still works without a device attached.

Usage:
  cb_restore.py <ref> [PORT] [--device CB04]            # dry-run: show the plan
  cb_restore.py <ref> [PORT] [--device CB04] --execute  # write it back
      <ref> = 'latest'  or a history snapshot timestamp (stem or leading prefix)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cb_store

# Time to let the device commit the flash before we probe / read back. The
# write path settles asynchronously: probing too soon reads a half-committed
# state (see .claude/rules/30-write-protocol.md §5a).
SETTLE_SECONDS = 2.0


def resolve_snapshot(ref: str, pid: str) -> Path:
    """The history snapshot `ref` names for device `pid`. Raises ValueError.

    `latest` = the newest snapshot; otherwise `ref` matches a snapshot stem, or
    a leading prefix of one (a longer timestamp disambiguates).
    """
    history = cb_store.list_history(pid)  # newest first
    if not history:
        raise ValueError(f"no snapshots for {pid} to restore")
    if ref == "latest":
        return history[0]
    matches = [s for s in history if s.stem == ref or s.stem.startswith(ref)]
    if not matches:
        raise ValueError(f"{ref!r} matches no snapshot of {pid} (try 'latest' or a timestamp)")
    if len(matches) > 1:
        raise ValueError(
            f"snapshot ref {ref!r} is ambiguous ({len(matches)} matches for {pid}); "
            "use a longer timestamp"
        )
    return matches[0]


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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-write a past snapshot to the device (undo / rollback).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("ref", help="'latest' or a history snapshot timestamp (stem or prefix)")
    ap.add_argument("port", nargs="?", help="serial port (default: auto-detect)")
    ap.add_argument("--device", metavar="PRODUCT_ID",
                    help="device whose snapshots to restore (default: sole stored)")
    ap.add_argument("--execute", action="store_true",
                    help="actually write (default: dry-run)")
    args = ap.parse_args()

    pid = args.device or cb_store.sole_device()
    if pid is None:
        print("restore: no single stored device found (use --device PRODUCT_ID)",
              file=sys.stderr)
        return 1

    try:
        snap = resolve_snapshot(args.ref, pid)
        ir = json.loads(snap.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        print(f"restore: {e}", file=sys.stderr)
        return 1

    import cb_write

    fp = cb_write.plan(ir)
    bad = _print_plan(fp, f"restore {pid}: {snap.stem}")

    if not args.execute:
        print("\n(dry-run — nothing sent. re-run with --execute to write.)")
        return 0 if not bad else 1

    if bad:
        print("refusing to write: malformed frames present.", file=sys.stderr)
        return 1

    port = cb_write._resolve_port(args.port)
    if port is None:
        print("No CyberBoard found.", file=sys.stderr)
        return 1

    before = cb_write.probe(port, full=True)
    print(f"\nport: {port}")
    print(f"before: {before.product_id if before else '?'} / {before.version if before else '?'}")
    print(f"writing {fp.total} frames (~{fp.total * cb_write.WRITE_DELAY:.0f}s minimum)...")

    ok, reply = cb_write.write_config(port, fp.frames)
    crc = "ok" if cb_write.crc_ok(reply) else "bad/none"
    print(f"JSON_END reply ({len(reply)}B, crc {crc}): {reply.hex()}")
    print(f"ACK (byte[2]==1): {ok} -> {'SUCCESS' if ok else 'FAILED'}")
    if not ok:
        print("device did not ACK; not recording a snapshot.", file=sys.stderr)
        return 1

    time.sleep(SETTLE_SECONDS)
    after = cb_write.probe(port, full=True)
    print(f"after:  {after.product_id if after else 'NO RESPONSE'} / {after.version if after else '?'}")
    if not (after and after.is_cyberboard):
        print("device not responding after write; not recording a snapshot.", file=sys.stderr)
        return 1

    # The rollback is itself a write, so record it as a fresh snapshot AND as the
    # current HEAD (current.json must equal the last full IR we wrote, or dump /
    # diff would report a stale LED — the firmware can't read LED back). Two
    # sequential locked steps: cb_store's flock is per-fd, so nesting them in one
    # process would self-deadlock (cb_store.snapshot docstring).
    new_snap = cb_store.snapshot(pid, ir)
    cb_store.save_current(pid, ir, version=after.version)
    print(f"recorded restore as snapshot {new_snap.stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

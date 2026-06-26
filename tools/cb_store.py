#!/usr/bin/env python3
"""Device-scoped state store: where the CLI keeps each keyboard's config + history.

This is the foundation the stateful commands (`dump` / `get` / `set` / `history` /
`restore` / `diff`) build on. The firmware does NOT support partial writes
(`JSON_START` erases the whole config flash), so every edit is read -> merge ->
full-write; and the LED display/per-key frames cannot be read back from the
device at all. The practical consequence is that the *last full IR we wrote* is
the only source of truth for LED state — so we persist it here, keyed per device,
and snapshot it on every write to make rollback possible (= "git for keyboard").

Storage root resolution ladder (first that is set wins):

    $CYBERBOARD_DATA_DIR  >  $XDG_DATA_HOME/cyberboard-cli  >  ~/.local/share/cyberboard-cli

Layout::

    <root>/devices/<product_id>/current.json   # last full IR we wrote (LED source of truth)
    <root>/devices/<product_id>/meta.json       # product_id, version, last_seen
    <root>/devices/<product_id>/history/...      # ISO8601 snapshots (added in a later issue)

Device identity: the R4 exposes no unique per-unit serial (the USB serial string
is a shared dummy, product_id/version are identical across all R4s), so we key on
`product_id` (e.g. `CB04`) and treat the single-device case as the supported one.

Pure stdlib — no pyserial / Pillow — so it loads in a core-only install.

Usage::

    cb_store.py path [--device CB04]   # print resolved store root / device dir
    cb_store.py --selftest             # round-trip self-test in a temp dir
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

APP = "cyberboard-cli"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def store_root() -> Path:
    """Resolve the storage root via the ladder (env override > XDG > home default)."""
    env = os.environ.get("CYBERBOARD_DATA_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / APP
    return Path.home() / ".local" / "share" / APP


def _safe_key(product_id: str) -> str:
    """Guard the device key so it can't escape the devices/ dir (path traversal)."""
    key = (product_id or "").strip()
    if not _SAFE_KEY.match(key):
        raise ValueError(
            f"invalid product_id key {product_id!r} (expected [A-Za-z0-9_-]+, e.g. 'CB04')"
        )
    return key


def device_dir(product_id: str, *, create: bool = False) -> Path:
    """`<root>/devices/<product_id>/`. Create it (and parents) when `create`."""
    d = store_root() / "devices" / _safe_key(product_id)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def current_path(product_id: str) -> Path:
    return device_dir(product_id) / "current.json"


def meta_path(product_id: str) -> Path:
    return device_dir(product_id) / "meta.json"


@contextlib.contextmanager
def device_lock(product_id: str):
    """Exclusive per-device advisory lock (flock on `<device_dir>/.lock`).

    Holds for a whole compound write so two concurrent CLI processes can't
    interleave the current.json + meta.json pair (or, later, a snapshot+save
    sequence) and leave them describing different states. fcntl is Unix-only,
    which matches the macOS/Linux serial-port target.
    """
    lock_path = device_dir(product_id, create=True) / ".lock"
    with open(lock_path, "w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, obj: object) -> None:
    """Write JSON atomically: temp file in the same dir, then os.replace().

    Same-directory temp keeps the rename atomic (no cross-filesystem copy), so a
    crash mid-write never leaves a half-written current.json.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict | None:
    """Parsed JSON object, or None if the file is absent."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_current(product_id: str) -> dict | None:
    """The last full IR we wrote for this device, or None if we've never written it."""
    return _read_json(current_path(product_id))


def load_meta(product_id: str) -> dict | None:
    return _read_json(meta_path(product_id))


def _update_meta(product_id: str, *, version: str | None = None) -> dict:
    """Merge-update meta.json (product_id, version, last_seen). Returns the new meta."""
    meta = load_meta(product_id) or {}
    meta["product_id"] = _safe_key(product_id)
    if version is not None:
        meta["version"] = version
    meta["last_seen"] = _now_iso()
    _atomic_write_json(meta_path(product_id), meta)
    return meta


def record_seen(product_id: str, *, version: str | None = None) -> dict:
    """Note that we observed this device (updates meta only, not current.json).

    Use from read-only commands (`dump` / `get`) so last_seen tracks reality even
    when nothing is written.
    """
    with device_lock(product_id):
        return _update_meta(product_id, version=version)


def save_current(product_id: str, ir: dict, *, version: str | None = None) -> Path:
    """Persist `ir` as this device's current full config and refresh meta.

    Returns the path to current.json. (Snapshotting into history/ is a separate
    concern, added by the auto-snapshot issue, so writers can compose the two.)
    """
    path = current_path(product_id)
    with device_lock(product_id):
        _atomic_write_json(path, ir)
        _update_meta(product_id, version=version)
    return path


def _check(cond: bool, msg: str) -> None:
    """Self-test guard. Explicit raise (not `assert`) so `-O` can't strip it."""
    if not cond:
        raise RuntimeError(f"cb_store self-test failed: {msg}")


def _selftest() -> int:
    """Round-trip the store in an isolated temp dir; verify the ladder + persistence."""
    import shutil

    saved = {k: os.environ.get(k) for k in ("CYBERBOARD_DATA_DIR", "XDG_DATA_HOME")}
    tmp = Path(tempfile.mkdtemp(prefix="cb_store_selftest_"))
    try:
        # --- ladder: env override wins ---
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ["CYBERBOARD_DATA_DIR"] = str(tmp / "envroot")
        _check(store_root() == tmp / "envroot", "CYBERBOARD_DATA_DIR should win")

        # --- ladder: XDG when no explicit override ---
        os.environ.pop("CYBERBOARD_DATA_DIR", None)
        os.environ["XDG_DATA_HOME"] = str(tmp / "xdg")
        _check(store_root() == tmp / "xdg" / APP, "XDG_DATA_HOME/<app> should be used")

        # --- ladder: home default when neither is set ---
        os.environ.pop("XDG_DATA_HOME", None)
        _check(store_root() == Path.home() / ".local" / "share" / APP, "home default")

        # --- round-trip current + meta under an env root ---
        os.environ["CYBERBOARD_DATA_DIR"] = str(tmp / "root")
        pid = "CB04"
        _check(load_current(pid) is None, "no current before first write")
        ir = {"page_num": 8, "key_layer": {"layer_num": 7}, "marker": "ピカチュウ"}
        path = save_current(pid, ir, version="AM_CB040.N40.R1.01.50")
        _check(path == (tmp / "root" / "devices" / "CB04" / "current.json"), "current path")
        _check(load_current(pid) == ir, "current round-trips byte-for-byte")
        meta = load_meta(pid)
        _check(bool(meta) and meta["product_id"] == "CB04", "meta records product_id")
        _check(meta["version"] == "AM_CB040.N40.R1.01.50", "meta records version")
        _check("last_seen" in meta, "meta records last_seen")

        # --- record_seen updates meta only, leaves current intact ---
        record_seen(pid, version="AM_CB040.N40.R1.01.51")
        _check(load_current(pid) == ir, "record_seen must not touch current.json")
        _check(load_meta(pid)["version"] == "AM_CB040.N40.R1.01.51", "record_seen bumps version")

        # --- path traversal is rejected ---
        for bad in ("../evil", "a/b", "", "CB 04"):
            try:
                device_dir(bad)
            except ValueError:
                continue
            raise RuntimeError(f"cb_store self-test failed: unsafe key {bad!r} accepted")

        print("cb_store self-test: OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                    help="run the round-trip self-test in a temp dir and exit")
    sub = ap.add_subparsers(dest="cmd")
    p_path = sub.add_parser("path", help="print the resolved store root / device dir")
    p_path.add_argument("--device", metavar="PRODUCT_ID",
                        help="show this device's dir instead of the root (e.g. CB04)")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if args.cmd == "path":
        if not args.device:
            print(store_root())
            return 0
        try:
            print(device_dir(args.device))
        except ValueError as e:
            print(f"cb_store: {e}", file=sys.stderr)
            return 2
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

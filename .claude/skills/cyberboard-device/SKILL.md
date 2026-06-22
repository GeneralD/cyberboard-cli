---
name: cyberboard-device
description: >-
  Detect and inspect a physically-connected AngryMiao CyberBoard over USB CDC
  serial — list devices and read their identity/status (product_id, firmware
  version, page count) without modifying any keyboard config. Use whenever you
  need to answer "is the board connected", "which serial port is it on", "what
  firmware is on the R4", "show device info", or before any write so you've
  confirmed the right device. READ-ONLY and safe to run anytime the hardware is
  plugged in. Backed by tools/cb_device.py, the reusable foundation the CLI's
  `devices` / `device info` commands are built on.
allowed-tools:
  - Read(*)
  - Grep(*)
  # uv (venv + pyserial), the device script, and ioreg/hidutil for cross-check.
  - Bash(*)
---

# CyberBoard Device Detection & Info

Identify and read status from a connected CyberBoard. Everything here is
**read-only** — it sends only identity/status query frames ([1,1], [1,2],
[2,6]); it never writes config. Confirmed working on real R4 hardware
(see `.claude/rules/30-write-protocol.md` §7 and `90-research-log.md`).

## Why probe-by-identity (not by node name)

macOS device-node names lie: a co-resident monitor can expose its own
`/dev/cu.usbmodem*` control port, and the R4's HID/serial enumerate under
Apple's VID `0x05AC` (not the `0x3151` the decompiled app suggested). So the
reliable identification is: **open each candidate serial port and ask it who it
is** — only a device returning a CRC-valid `CB*` product_id counts. This is
also the fix for AM Master's flaky detection.

## Steps

### 1. Ensure the pyserial environment

`tools/cb_device.py` needs `pyserial`. Use a uv venv (no global install):

```bash
cd <repo-root>
uv venv --python 3.12 .venv 2>/dev/null || true
uv pip install --python .venv/bin/python -q pyserial
```

### 2. List / inspect

```bash
# Enumerate connected boards (add --all for fw + page count)
.venv/bin/python tools/cb_device.py list --all

# Full detail for one board (auto-detects the port if omitted)
.venv/bin/python tools/cb_device.py info --json
```

Expected on a wired R4: `product_id=CB04`, `version=AM_CB040.N40.R1.01.50`,
`pages=3`, `port=/dev/cu.usbmodem*`.

### 3. If nothing is found

- Confirm the board is wired to its **body USB**, not the wireless dongle, with
  a **data-capable** cable.
- Cross-check the raw USB tree (some envs return an empty `system_profiler`):

  ```bash
  ioreg -p IOUSB -l -w0 | grep -iE '"idVendor"|"idProduct"|"USB Product Name"|"USB Serial Number"'
  hidutil list | grep -i cyber
  ```

  A real R4 shows `idVendor=0x05AC (1452)`, `idProduct=0x0256 (598)`,
  Product `CYBERBOARD`, Vendor `AngryMiao`.

## Notes

- `tools/cb_protocol.py` holds the wire primitives (`build_frame`, `crc8`,
  `crc_ok`, `parse_string_reply`) — **the same code the write path will reuse**,
  so keep additions there generic.
- The dongle (`*_DONGLE_*` product_id) is detected and flagged, not treated as
  the wired board.

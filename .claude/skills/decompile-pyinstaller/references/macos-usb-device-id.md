# Identifying a USB / Serial Device on macOS

Companion to `decompile-pyinstaller`. When reverse-engineering a device-control
app, you eventually need to find the actual hardware and its transport. macOS
has two traps that waste time; here's the reliable path.

## Trap 1: `system_profiler SPUSBDataType` can return nothing

It's the "official" USB lister, but in sandboxes, over SSH, or under certain
permission states it prints an **empty result with exit 0** — looking like "no
USB devices" when devices are clearly attached. Don't trust an empty
`system_profiler`. Use `ioreg` (always works, no special entitlement):

```bash
# Vendor/Product IDs, names, and serials of attached USB devices
ioreg -p IOUSB -l -w0 | grep -iE \
  '\+\-o |"idVendor"|"idProduct"|"USB Vendor Name"|"USB Product Name"|"USB Serial Number"'
```

For HID specifically (keyboards, mice, custom HID), `hidutil` lists vendor /
product / usage page:

```bash
hidutil list | grep -i '<name-or-vendor>'
```

Cross-check decompiled constants here: if the app hardcoded `VENDOR_ID=12625`
(`0x3151`), search the `ioreg`/`hidutil` output for that value to confirm the
device is the one the app talks to.

## Trap 2: the `/dev/cu.usbmodem*` node name lies

A control app often opens a serial port — but **the device node name is not a
reliable identity**. Other peripherals expose CDC-serial control interfaces too.
A real example: a monitor enumerated as `/dev/cu.usbmodemABC1234567892`, whose
underlying device was an LG "USB Controls" interface (VID `0x043E`) — nothing to
do with the target keyboard. A naive "open the first `cu.usbmodem*`" would grab
the monitor.

So **identify by probing, not by name**:

1. Enumerate candidates: `ls /dev/cu.usbmodem*` (use `cu.*`, not `tty.*` — see
   below).
2. For each candidate, open it and send the app's *identity* command (whatever
   the decompiled source revealed — e.g. a "get product id" request), then match
   the **reply** against the expected product code. Only the device that answers
   correctly is the target.

This mirrors what robust firmware tools do, and it's immune to node-name
reshuffling across reboots / hub changes.

## `cu.*` vs `tty.*`

Always open `/dev/cu.*` (call-up), never `/dev/tty.*`. Opening a `tty.usbmodem*`
blocks on DCD (carrier detect) until the line is asserted, which manifests as
"the app hangs / can't connect intermittently" — a classic flakiness source.
`cu.*` doesn't wait on DCD.

## Quick reference

| Goal | Command |
|---|---|
| List USB devices (when system_profiler is empty) | `ioreg -p IOUSB -l -w0 \| grep -iE '"idVendor"\|"idProduct"\|"USB Product Name"\|"USB Serial Number"'` |
| List HID devices | `hidutil list` |
| Find serial nodes | `ls /dev/cu.usbmodem*` |
| Confirm a hardcoded VID/PID is present | grep the decompiled constant against `ioreg` output |

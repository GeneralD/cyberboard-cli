#!/usr/bin/env python3
"""Empirically verify the decompiled write-protocol encoding (no device needed).

Ports the byte-packing logic from the decompiled TransJsonCmd.py / JsonToCmd.py
and runs it over a real merger sample JSON, asserting self-consistency:
- frames (40x5 display): each animation frame -> 11 RGB_FRAME usb frames
- keyframes (per-key 90): each frame -> 5 KEY_FRAME usb frames
- every payload byte lands in cmd[0..62]; CRC-8 occupies cmd[63]
- frame_RGB element counts match 200 (display) / 90 (per-key)

This validates the claims in .claude/rules/30-write-protocol.md before they ossify.
"""
import json
import sys


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def crc8(data: bytes) -> int:
    """CRC-8, poly 0x07, init 0x00, no reflection (== PyPI `crc8` default)."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def rgb_to_bytes(s: str) -> bytes:
    return bytes.fromhex(s[1:7])          # "#RRGGBB" -> 3 bytes


def finalize(cmd: bytearray) -> bytearray:
    check(len(cmd) == 64, f"frame must be 64 bytes, got {len(cmd)}")
    cmd[63] = crc8(bytes(cmd[0:63]))
    return cmd


def rgb_frame_frames(page_index, frame_index, rgb_list):
    """cmd_rgb_frame_info_send chunking: 200px*3=600B -> 11 usb frames."""
    blob = b"".join(rgb_to_bytes(c) for c in rgb_list)
    check(len(blob) == 600, f"display frame must be 600B (200px), got {len(blob)}")
    out = []
    for i in range(11):
        chunk = blob[i * 56:(i + 1) * 56] if i < 10 else blob[i * 56:600]
        cmd = bytearray(64)
        cmd[0] = 4
        cmd[1] = page_index
        fi = int(frame_index).to_bytes(2, "big")
        cmd[2], cmd[3] = fi[1], fi[0]     # little-endian on the wire
        cmd[4] = i
        for k, byte in enumerate(chunk):
            check(5 + k <= 62, "RGB payload overran cmd[62]")
            cmd[5 + k] = byte
        out.append(finalize(cmd))
    return out


def key_frame_frames(page_index, frame_index, rgb_list):
    """cmd_key_frame_send chunking: 90px*3=270B -> 5 usb frames."""
    blob = b"".join(rgb_to_bytes(c) for c in rgb_list)
    check(len(blob) == 270, f"per-key frame must be 270B (90px), got {len(blob)}")
    out = []
    for i in range(5):
        chunk = blob[i * 56:(i + 1) * 56] if i < 4 else blob[i * 56:270]
        cmd = bytearray(64)
        cmd[0] = 5
        cmd[1] = page_index
        cmd[2] = frame_index & 0xFF
        cmd[3] = i
        for k, byte in enumerate(chunk):
            check(4 + k <= 62, "KEY payload overran cmd[62]")
            cmd[4 + k] = byte
        out.append(finalize(cmd))
    return out


def main() -> None:
    path = sys.argv[1]
    cfg = json.load(open(path))
    total = 0
    print(f"file: {path}\n")
    for page in cfg["page_data"]:
        pi = page["page_index"]
        frames = page.get("frames", {})
        keyframes = page.get("keyframes", {})
        fd = frames.get("frame_data", []) if frames.get("frame_num", 0) else []
        kd = keyframes.get("frame_data", []) if keyframes.get("frame_num", 0) else []
        # only frames/keyframes with full-size frame_RGB are real animation frames
        fd = [f for f in fd if len(f.get("frame_RGB", [])) == 200]
        kd = [f for f in kd if len(f.get("frame_RGB", [])) == 90]
        rgb_n = key_n = 0
        for f in fd:
            rgb_n += len(rgb_frame_frames(pi, f["frame_index"], f["frame_RGB"]))
        for f in kd:
            key_n += len(key_frame_frames(pi, f["frame_index"], f["frame_RGB"]))
        if fd or kd:
            print(f"page {pi}: display frames={len(fd)} -> {rgb_n} usb "
                  f"(expect {len(fd)*11}); per-key frames={len(kd)} -> {key_n} usb "
                  f"(expect {len(kd)*5})")
            check(rgb_n == len(fd) * 11 and key_n == len(kd) * 5, "FRAME COUNT MISMATCH")
        total += rgb_n + key_n
    print(f"\nOK: all frames packed in-bounds, CRC-8 applied. "
          f"RGB+KEY usb frames = {total}")


if __name__ == "__main__":
    main()

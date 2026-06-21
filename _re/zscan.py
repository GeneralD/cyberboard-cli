#!/usr/bin/env python3
"""Brute-scan a binary for embedded zlib streams and decompress them.

PyInstaller stores the app's Python modules in a PYZ archive as individual
zlib-compressed marshalled code objects. We can't unmarshal 3.7 code objects
under a newer interpreter, but decompressing the streams and running `strings`
over the result surfaces the source-level string/bytes constants (function
names, AES keys if literal, VID/PID, opcodes, error messages).

Pure stdlib, read-only on the input. No network, no external tools.
"""
import sys
import zlib


def valid_zlib_header(b0: int, b1: int) -> bool:
    if (b0 & 0x0F) != 8:          # deflate compression method
        return False
    if (b0 >> 4) > 7:             # window size <= 32K
        return False
    if ((b0 << 8) | b1) % 31 != 0:  # FCHECK
        return False
    return True


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    data = open(src, "rb").read()
    n = len(data)
    results = []
    i = 0
    while i < n - 1:
        if valid_zlib_header(data[i], data[i + 1]):
            try:
                d = zlib.decompressobj()
                dec = d.decompress(data[i:], 5_000_000)
                if len(dec) >= 40:
                    consumed = len(data[i:]) - len(d.unused_data)
                    results.append((i, consumed, dec))
                    i += max(consumed, 1)
                    continue
            except Exception:
                pass
        i += 1

    with open(dst, "wb") as f:
        for off, consumed, dec in results:
            f.write(b"\n==== @%d compressed=%d decompressed=%d ====\n"
                    % (off, consumed, len(dec)))
            f.write(dec)

    print("streams:", len(results),
          "decompressed_total:", sum(len(d) for _, _, d in results))


if __name__ == "__main__":
    main()

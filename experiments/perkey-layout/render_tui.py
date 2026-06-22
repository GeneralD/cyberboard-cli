#!/usr/bin/env python3
"""Proof-of-concept TUI renderer for CyberBoard R4 lighting.

Renders to the terminal in truecolor:
- per-key (in-switch) backlight, using the physical layout extracted from the web UI
  (r4-perkey-layout.json). Demo coloring = rainbow by x position.
- display (40x5) of an IR config page, exact (1:1 pixel map).

Usage:
  render_tui.py                         # per-key rainbow demo
  render_tui.py --config C.json --page 5 --frame 0   # also render that display frame
"""
from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path

ESC = "\x1b"
RESET = f"{ESC}[0m"


def bg(r: int, g: int, b: int, s: str = "  ") -> str:
    return f"{ESC}[48;2;{r};{g};{b}m{s}{RESET}"


def hsv(h: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.85, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def render_perkey(layout: dict, px_per_char: int = 9, key_chars: int = 3) -> str:
    leds = layout["leds"]
    rows = sorted(layout["rows_y"])
    maxx = max(l["x"] + l["w"] for l in leds)
    width = maxx // px_per_char + key_chars + 1
    lines = []
    for ry in rows:
        row_leds = [l for l in leds if min(rows, key=lambda r: abs(r - l["y"])) == ry]
        cells: list[tuple[int, int, int] | None] = [None] * width
        for l in row_leds:
            col = l["x"] // px_per_char
            color = hsv(l["x"] / maxx)
            for c in range(col, min(col + key_chars, width)):
                cells[c] = color
        lines.append("".join(bg(*c, "██") if c else "  " for c in cells))
    return "\n".join(lines)


def render_display(config: dict, page_index: int, frame: int, w: int = 40, h: int = 5) -> str:
    page = next(p for p in config["page_data"] if p.get("page_index") == page_index)
    rgb = page["frames"]["frame_data"][frame]["frame_RGB"]
    px = [tuple(int(rgb[i][k:k + 2], 16) for k in (1, 3, 5)) for i in range(w * h)]
    return "\n".join("".join(bg(*px[y * w + x]) for x in range(w)) for y in range(h))


def render_png(layout: dict, out: Path, config: dict | None, page_index: int, frame: int,
               key_h: int = 28, scale: int = 4, disp_px: int = 14) -> None:
    """PNG proof (also the seed of the GIF export). Needs Pillow."""
    from PIL import Image, ImageDraw

    leds = layout["leds"]
    rows = sorted(layout["rows_y"])
    maxx = max(l["x"] + l["w"] for l in leds)
    pk_w = (maxx + 8) * scale
    pk_h = (max(rows) + key_h + 8) * scale
    disp_h = 5 * disp_px + (2 * disp_px if config else 0)
    img = Image.new("RGB", (max(pk_w, 40 * disp_px), pk_h + disp_h), (18, 18, 22))
    d = ImageDraw.Draw(img)
    for l in leds:
        x0, y0 = l["x"] * scale, l["y"] * scale
        d.rounded_rectangle([x0, y0, x0 + l["w"] * scale, y0 + key_h * scale],
                            radius=3 * scale, fill=hsv(l["x"] / maxx))
    if config:
        page = next(p for p in config["page_data"] if p.get("page_index") == page_index)
        rgb = page["frames"]["frame_data"][frame]["frame_RGB"]
        oy = pk_h + disp_px
        for i in range(200):
            r, g, b = (int(rgb[i][k:k + 2], 16) for k in (1, 3, 5))
            x, y = (i % 40) * disp_px, oy + (i // 40) * disp_px
            d.rectangle([x, y, x + disp_px - 1, y + disp_px - 1], fill=(r, g, b))
    img.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", type=Path,
                    default=Path(__file__).parent / "r4-perkey-layout.json")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--page", type=int, default=5)
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--png", type=Path, help="also write a PNG render")
    args = ap.parse_args()

    layout = json.loads(args.layout.read_text())
    config = json.loads(args.config.read_text()) if args.config else None
    print("\n  per-key (in-switch) backlight — physical layout, rainbow demo:\n")
    print(render_perkey(layout))
    if config:
        print(f"\n  display 40x5 — {args.config.name} page{args.page} frame{args.frame}:\n")
        print(render_display(config, args.page, args.frame))
    print()
    if args.png:
        render_png(layout, args.png, config, args.page, args.frame)
        print(f"  wrote {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

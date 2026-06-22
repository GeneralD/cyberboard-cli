#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Codec between an animated GIF and the IR display layer (40x5 = 200px per frame).

    cb_led.py gif2ir -i art.gif -b base.json --slot 1 -o config.json   # GIF -> IR slot
    cb_led.py ir2gif -i config.json --slot 1 -o art.gif [--recipe ...] # IR slot -> GIF
    cb_led.py recipe  art.gif [--set "..."]                            # GIF comment R/W

The display panel is a 40x5 grid; each frame is 200 `#RRGGBB` strings in row-major
order (index = y*40 + x, top-left origin — confirmed by render_tui.py). A slot is a
Custom LED page: slot 1/2/3 == page_index 5/6/7 (.claude/rules/10).

Pure file->file (no device I/O), like cb_build. `gif2ir` patches ONLY the display
`frames` of the chosen page in a complete base IR — JSON_START erases the whole flash
so the written config must be complete (90 续8), and per-key `keyframes` are kept from
the base (the GIF<->keyframes-90 index map is still unresolved — 90 续15). The firmware
plays at most 256 frames/slot (90 续5), so gif2ir caps at 256 and reports the drop.

The GIF is the community-shareable interchange artifact; its generation recipe/prompt
lives in the GIF Comment Extension (GIF has no EXIF) — `ir2gif --recipe` embeds it,
`recipe` reads/writes it. The IR JSON stays official-schema-clean (no recipe field).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

W, H = 40, 5
PIXELS = W * H  # 200
MAX_FRAMES = 256  # firmware playback cap per slot (90 续5)


def _warn(msg: str) -> None:
    print(f"cb_led: {msg}", file=sys.stderr)


def _slot_to_page(slot: int) -> int:
    if slot not in (1, 2, 3):
        raise SystemExit(f"cb_led: --slot must be 1, 2 or 3 (got {slot})")
    return slot + 4  # slot 1/2/3 -> page_index 5/6/7


def _page(config: dict, page_index: int) -> dict:
    try:
        return next(p for p in config["page_data"] if p.get("page_index") == page_index)
    except StopIteration:
        raise SystemExit(f"cb_led: config has no page_index {page_index}")


def _hex_px(s: str) -> tuple[int, int, int]:
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


# --- GIF -> IR -------------------------------------------------------------------

def _gif_frames(path: Path, resample: str) -> tuple[list[list[str]], int | None]:
    """Return (per-frame 200-hex lists downsampled to 40x5, first-frame duration ms)."""
    from PIL import Image

    modes = {"nearest": Image.Resampling.NEAREST, "lanczos": Image.Resampling.LANCZOS,
             "box": Image.Resampling.BOX}
    filt = modes[resample]
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    duration = im.info.get("duration")  # ms; per the first frame
    frames: list[list[str]] = []
    for i in range(n):
        im.seek(i)  # sequential forward seek composites GIF disposal in Pillow
        rgb = im.convert("RGB")
        if rgb.size != (W, H):
            rgb = rgb.resize((W, H), filt)
        raw = rgb.tobytes()  # RGB triples; stable across Pillow versions
        frames.append(["#%02x%02x%02x" % (raw[j], raw[j + 1], raw[j + 2])
                       for j in range(0, len(raw), 3)])
    return frames, (int(duration) if duration else None)


def gif2ir(args: argparse.Namespace) -> int:
    base = json.loads(Path(args.base).read_text())
    page_index = _slot_to_page(args.slot)
    page = _page(base, page_index)

    frames, gif_ms = _gif_frames(Path(args.input), args.resample)
    if len(frames) > MAX_FRAMES:
        _warn(f"GIF has {len(frames)} frames; firmware plays only {MAX_FRAMES}/slot "
              f"— dropping {len(frames) - MAX_FRAMES} (90 续5)")
        frames = frames[:MAX_FRAMES]

    page["frames"] = {
        "valid": 1,
        "frame_num": len(frames),
        "frame_data": [{"frame_index": i, "frame_RGB": f} for i, f in enumerate(frames)],
    }
    page["valid"] = True
    speed = args.speed_ms if args.speed_ms is not None else gif_ms
    if speed is not None:
        page["speed_ms"] = speed
    if args.lightness is not None:
        page["lightness"] = args.lightness

    Path(args.output).write_text(json.dumps(base, ensure_ascii=False, indent=2))
    note = f", speed_ms={page['speed_ms']}" if speed is not None else ""
    print(f"cb_led: slot {args.slot} (page {page_index}) <- {len(frames)} display frames"
          f"{note}; keyframes kept from base -> {args.output}")
    from PIL import Image  # report embedded recipe, if any
    comment = Image.open(args.input).info.get("comment")
    if comment:
        text = comment.decode("utf-8", "replace") if isinstance(comment, bytes) else comment
        print(f"cb_led: embedded recipe: {text}")
    return 0


# --- IR -> GIF -------------------------------------------------------------------

def ir2gif(args: argparse.Namespace) -> int:
    from PIL import Image

    config = json.loads(Path(args.input).read_text())
    page_index = _slot_to_page(args.slot)
    page = _page(config, page_index)
    fd = page.get("frames", {}).get("frame_data", [])
    if not fd:
        raise SystemExit(f"cb_led: page {page_index} has no display frames")

    scale = args.scale
    imgs: list[Image.Image] = []
    for fr in fd:
        rgb = fr["frame_RGB"]
        if len(rgb) != PIXELS:
            raise SystemExit(f"cb_led: frame {fr.get('frame_index')} has {len(rgb)} px, "
                             f"expected {PIXELS}")
        img = Image.new("RGB", (W, H))
        img.putdata([_hex_px(s) for s in rgb])
        imgs.append(img.resize((W * scale, H * scale), Image.Resampling.NEAREST))

    duration = args.speed_ms if args.speed_ms is not None else page.get("speed_ms", 100)
    save_kw: dict = dict(save_all=True, append_images=imgs[1:], duration=duration,
                         loop=0, disposal=2)
    if args.recipe:
        save_kw["comment"] = args.recipe.encode("utf-8")
    imgs[0].save(args.output, **save_kw)
    rec = " + recipe" if args.recipe else ""
    print(f"cb_led: slot {args.slot} (page {page_index}) -> {len(imgs)} frames "
          f"@ {W * scale}x{H * scale}, {duration}ms/frame{rec} -> {args.output}")
    return 0


# --- recipe (GIF Comment Extension) ---------------------------------------------

def recipe(args: argparse.Namespace) -> int:
    from PIL import Image, ImageSequence

    im = Image.open(args.input)
    if args.set is None:
        comment = im.info.get("comment")
        if not comment:
            print("cb_led: (no recipe embedded)")
            return 0
        print(comment.decode("utf-8", "replace") if isinstance(comment, bytes) else comment)
        return 0
    # rewrite preserving every frame + timing
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    durations = []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        durations.append(im.info.get("duration", 100))
    frames[0].save(args.input, save_all=True, append_images=frames[1:],
                   duration=durations, loop=im.info.get("loop", 0), disposal=2,
                   comment=args.set.encode("utf-8"))
    print(f"cb_led: recipe set on {args.input}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="GIF <-> IR display-layer (40x5) codec")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g2i = sub.add_parser("gif2ir", help="GIF -> IR display frames (patched into a base)")
    g2i.add_argument("-i", "--input", required=True, help="source animated GIF")
    g2i.add_argument("-b", "--base", required=True, help="complete base IR config JSON")
    g2i.add_argument("--slot", type=int, required=True, help="1, 2 or 3 (page 5/6/7)")
    g2i.add_argument("-o", "--output", required=True, help="output IR config JSON")
    g2i.add_argument("--resample", choices=("nearest", "lanczos", "box"),
                     default="nearest", help="downscale filter to 40x5 (default nearest)")
    g2i.add_argument("--speed-ms", type=int, dest="speed_ms",
                     help="override page speed_ms (default: from GIF, else base)")
    g2i.add_argument("--lightness", type=int, help="override page lightness 0-100")
    g2i.set_defaults(func=gif2ir)

    i2g = sub.add_parser("ir2gif", help="IR display frames -> GIF (visual confirmation)")
    i2g.add_argument("-i", "--input", required=True, help="IR config JSON")
    i2g.add_argument("--slot", type=int, required=True, help="1, 2 or 3 (page 5/6/7)")
    i2g.add_argument("-o", "--output", required=True, help="output animated GIF")
    i2g.add_argument("--scale", type=int, default=16, help="pixel scale-up (default 16)")
    i2g.add_argument("--speed-ms", type=int, dest="speed_ms",
                     help="override frame duration ms (default: page speed_ms)")
    i2g.add_argument("--recipe", help="recipe/prompt text to embed in GIF comment")
    i2g.set_defaults(func=ir2gif)

    rec = sub.add_parser("recipe", help="read/write a GIF's embedded recipe (comment)")
    rec.add_argument("input", help="GIF file")
    rec.add_argument("--set", help="set the recipe text (default: print it)")
    rec.set_defaults(func=recipe)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

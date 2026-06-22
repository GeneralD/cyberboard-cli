#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Deterministic recipe renderer for the ① display layer (40x5 = 200px per frame).

    cb_anim.py render  -r recipe.json -b base.json -o config.json [--gif art.gif]
    cb_anim.py preview -r recipe.json -o art.gif [--scale 16]

A *recipe* is a small declarative JSON document. A deterministic renderer expands
it to 40x5xN frames — the AI/author only picks knobs, no raw code runs (whitelisted
effects). The frames feed cb_led's shared transforms: `render` patches them into a
complete base IR (display `frames` only; per-key `keyframes` kept from base, like
gif2ir), `preview` writes just the GIF for a fast visual loop.

Recipe shape (a single effect, or a `sequence` of segments concatenated):

    { "slot": 1, "speed_ms": 80,
      "sequence": [
        { "effect": "text_scroll", "text": "HELLO", "fg": "#00ff88" },
        { "effect": "solid", "color": "#000000", "frames": 8 },
        { "effect": "text_scroll", "text": "WORLD", "fg": "#ff0066", "gap": 40 }
      ] }

The four authoring knobs the user asked for map cleanly onto this:
  ① seamless loop  — text_scroll `gap: 0` (default) tiles toroidally, no seam.
  ② length         — text via `step` (px/frame), solid via `frames`.
  ③ MAX256         — firmware plays <=256 frames/slot (90 续5); we warn + truncate.
  ④ concatenate    — `sequence` appends short clips into one slot (≈ merger combine).

The whole recipe JSON is embedded in the output GIF's Comment (GIF has no EXIF), so
the artifact carries its own generator — the same convention cb_led uses (10/40).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cb_led  # shared: frames_to_page, frames_to_gif, W, H, PIXELS, MAX_FRAMES

W, H, PIXELS, MAX_FRAMES = cb_led.W, cb_led.H, cb_led.PIXELS, cb_led.MAX_FRAMES
FONT_PATH = Path(__file__).resolve().parent / "fonts" / "tom-thumb.bdf"


def _warn(msg: str) -> None:
    print(f"cb_anim: {msg}", file=sys.stderr)


def _color(s: str) -> str:
    """Normalize a '#RRGGBB' string (also accepts without '#'); raise on garbage."""
    h = s.lstrip("#")
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise SystemExit(f"cb_anim: bad color {s!r} (want #RRGGBB)")
    return "#" + h.lower()


# --- BDF font (tom-thumb) --------------------------------------------------------

_FONT: tuple[dict, int] | None = None


def _font() -> tuple[dict, int]:
    """Parse the bundled BDF once -> ({codepoint: glyph}, font_ascent)."""
    global _FONT
    if _FONT is not None:
        return _FONT
    if not FONT_PATH.exists():
        raise SystemExit(f"cb_anim: font not found: {FONT_PATH}")
    glyphs: dict[int, dict] = {}
    ascent = 5
    cur: dict | None = None
    lines = iter(FONT_PATH.read_text().splitlines())
    for ln in lines:
        if ln.startswith("FONT_ASCENT"):
            ascent = int(ln.split()[1])
        elif ln.startswith("STARTCHAR"):
            cur = {"enc": -1, "dwidth": 0, "bbx": (0, 0, 0, 0), "rows": []}
        elif ln.startswith("ENCODING") and cur is not None:
            cur["enc"] = int(ln.split()[1])
        elif ln.startswith("DWIDTH") and cur is not None:
            cur["dwidth"] = int(ln.split()[1])
        elif ln.startswith("BBX") and cur is not None:
            cur["bbx"] = tuple(int(v) for v in ln.split()[1:5])
        elif ln.startswith("BITMAP") and cur is not None:
            cur["rows"] = [int(next(lines).strip(), 16) for _ in range(cur["bbx"][1])]
        elif ln.startswith("ENDCHAR") and cur is not None:
            glyphs[cur["enc"]] = cur
            cur = None
    _FONT = (glyphs, ascent)
    return _FONT


def _text_strip(text: str, spacing: int) -> tuple[list[list[bool]], int]:
    """Render `text` to an H-row ink mask; width includes one trailing `spacing`
    column run so the strip tiles evenly across a seamless wrap. Returns (mask, w)."""
    glyphs, ascent = _font()
    advances = [(glyphs.get(ord(ch)), (glyphs.get(ord(ch)) or {}).get("dwidth", 3))
                for ch in text]
    width = sum(dw for _, dw in advances) + spacing * len(advances)
    width = max(width, 1)
    mask = [[False] * width for _ in range(H)]
    x = 0
    for g, dw in advances:
        if g and g["rows"]:
            gw, gh, xo, yo = g["bbx"]
            top = ascent - (gh + yo)  # rows above baseline; tom-thumb fits 5px
            for ry in range(gh):
                bits = g["rows"][ry]
                for cx in range(gw):
                    if bits & (1 << (7 - cx)):
                        yy, xx = top + ry, x + xo + cx
                        if 0 <= yy < H and 0 <= xx < width:
                            mask[yy][xx] = True
        x += dw + spacing
    return mask, width


# --- effects (procedural family) -------------------------------------------------

def _effect_text_scroll(seg: dict) -> list[list[str]]:
    """Horizontal marquee. gap=0 -> seamless toroidal tiling (no seam, ①)."""
    text = seg.get("text")
    if not text:
        raise SystemExit("cb_anim: text_scroll needs a non-empty 'text'")
    fg = _color(seg.get("fg", "#00ff88"))
    bg = _color(seg.get("bg", "#000000"))
    spacing = int(seg.get("spacing", 1))
    step = max(1, int(seg.get("step", 1)))
    gap = max(0, int(seg.get("gap", 0)))
    direction = seg.get("direction", "left")
    if direction not in ("left", "right"):
        raise SystemExit(f"cb_anim: text_scroll direction must be left/right, got {direction!r}")

    mask, ink_w = _text_strip(text, spacing)
    strip_w = ink_w + gap  # gap columns (blank) appended for the loop seam
    nframes = math.ceil(strip_w / step)
    if strip_w % step:
        _warn(f"text_scroll {text!r}: strip width {strip_w} not divisible by step {step} "
              f"— loop may jitter at the wrap")

    frames: list[list[str]] = []
    for i in range(nframes):
        shift = i * step
        off = (-shift if direction == "right" else shift) % strip_w
        flat = [bg] * PIXELS
        for y in range(H):
            row = mask[y]
            base = y * W
            for x in range(W):
                sx = (off + x) % strip_w
                if sx < ink_w and row[sx]:
                    flat[base + x] = fg
        frames.append(flat)
    return frames


def _effect_solid(seg: dict) -> list[list[str]]:
    """A static color held for N frames — useful as a separator/segment (②/④)."""
    color = _color(seg.get("color", "#000000"))
    n = max(1, int(seg.get("frames", 1)))
    return [[color] * PIXELS for _ in range(n)]


EFFECTS = {
    "text_scroll": _effect_text_scroll,
    "solid": _effect_solid,
}


# --- recipe -> frames ------------------------------------------------------------

def _render_recipe(recipe: dict) -> tuple[int, int, list[list[str]]]:
    """Expand a recipe to (slot, speed_ms, frames). Caps at MAX_FRAMES with a
    generation-time warning that names the overflow (advisor: warn early, ③)."""
    slot = int(recipe.get("slot", 1))
    speed = int(recipe.get("speed_ms", 100))
    segments = recipe.get("sequence") or [recipe]  # single-effect convenience
    frames: list[list[str]] = []
    for k, seg in enumerate(segments):
        eff = seg.get("effect")
        fn = EFFECTS.get(eff)
        if fn is None:
            raise SystemExit(f"cb_anim: segment {k} has unknown effect {eff!r} "
                             f"(have: {', '.join(sorted(EFFECTS))})")
        frames.extend(fn(seg))
    if len(frames) > MAX_FRAMES:
        _warn(f"recipe expands to {len(frames)} frames > {MAX_FRAMES}/slot "
              f"— truncating to {MAX_FRAMES} (firmware playback cap, 90 续5)")
        frames = frames[:MAX_FRAMES]
    return slot, speed, frames


# --- subcommands -----------------------------------------------------------------

def render(args: argparse.Namespace) -> int:
    recipe = json.loads(Path(args.recipe).read_text())
    slot, speed, frames = _render_recipe(recipe)
    if args.slot is not None:
        slot = args.slot
    base = json.loads(Path(args.base).read_text())
    page = cb_led.frames_to_page(base, slot, frames, speed)
    Path(args.output).write_text(json.dumps(base, ensure_ascii=False, indent=2))
    print(f"cb_anim: slot {slot} (page {page['page_index']}) <- "
          f"{page['frames']['frame_num']} display frames, speed_ms={speed}; "
          f"keyframes kept from base -> {args.output}")
    if args.gif:
        cb_led.frames_to_gif(frames, args.gif, args.scale, speed,
                             json.dumps(recipe, ensure_ascii=False))
        print(f"cb_anim: preview -> {args.gif}")
    return 0


def preview(args: argparse.Namespace) -> int:
    recipe = json.loads(Path(args.recipe).read_text())
    _slot, speed, frames = _render_recipe(recipe)
    n = cb_led.frames_to_gif(frames, args.output, args.scale, speed,
                             json.dumps(recipe, ensure_ascii=False))
    print(f"cb_anim: {n} frames @ {W * args.scale}x{H * args.scale}, "
          f"{speed}ms/frame -> {args.output}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Recipe -> IR display-layer (40x5) renderer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="recipe -> IR frames patched into a base (+ optional GIF)")
    r.add_argument("-r", "--recipe", required=True, help="recipe JSON")
    r.add_argument("-b", "--base", required=True, help="complete base IR config JSON")
    r.add_argument("-o", "--output", required=True, help="output IR config JSON")
    r.add_argument("--slot", type=int, help="override recipe slot (1/2/3 = page 5/6/7)")
    r.add_argument("--gif", help="also write a preview GIF here")
    r.add_argument("--scale", type=int, default=16, help="GIF pixel scale-up (default 16)")
    r.set_defaults(func=render)

    p = sub.add_parser("preview", help="recipe -> GIF only (fast visual loop, no base)")
    p.add_argument("-r", "--recipe", required=True, help="recipe JSON")
    p.add_argument("-o", "--output", required=True, help="output animated GIF")
    p.add_argument("--scale", type=int, default=16, help="pixel scale-up (default 16)")
    p.set_defaults(func=preview)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

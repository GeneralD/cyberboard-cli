"""BDF font loader for the 40×5 LED display renderer.

Parses the bundled tom-thumb (Fixed4x6, 5px, MIT) BDF once and caches it.

The glyph dict structure mirrors the BDF parser output exactly:
    {
        "enc":   int,              # Unicode codepoint
        "dwidth": int,             # advance width in pixels
        "bbx":   (gw, gh, xo, yo),
        "rows":  [int, ...],       # one int per row, BDF hex byte (MSB first, left-aligned)
    }

Bit reading: bit `cx` (0-indexed from left) is present when
    `bits & (1 << (7 - cx))` is non-zero.
"""
from __future__ import annotations

from pathlib import Path

FONT_PATH = Path(__file__).resolve().parent / "fonts" / "tom-thumb.bdf"

# ---------------------------------------------------------------------------
# Parser & cache
# ---------------------------------------------------------------------------

_FONT: tuple[dict, int] | None = None


def font() -> tuple[dict, int]:
    """Return ({codepoint: glyph}, font_ascent), parsed from BDF and cached."""
    global _FONT
    if _FONT is not None:
        return _FONT
    if not FONT_PATH.exists():
        raise SystemExit(f"cb_font: font not found: {FONT_PATH}")
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


def text_strip(text: str, spacing: int, H: int) -> tuple[list[list[bool]], int]:
    """Render `text` to an H-row ink mask using the loaded font.

    Width includes one trailing `spacing` column run so the strip tiles
    evenly across a seamless wrap.  Returns (mask, width).
    """
    glyphs, ascent = font()
    advances = [
        (glyphs.get(ord(ch)), (glyphs.get(ord(ch)) or {}).get("dwidth", 3))
        for ch in text
    ]
    width = sum(dw for _, dw in advances) + spacing * len(advances)
    width = max(width, 1)
    mask = [[False] * width for _ in range(H)]
    x = 0
    for g, dw in advances:
        if g and g["rows"]:
            gw, gh, xo, yo = g["bbx"]
            top = ascent - (gh + yo)
            for ry in range(gh):
                bits = g["rows"][ry]
                for cx in range(gw):
                    if bits & (1 << (7 - cx)):
                        yy, xx = top + ry, x + xo + cx
                        if 0 <= yy < H and 0 <= xx < width:
                            mask[yy][xx] = True
        x += dw + spacing
    return mask, width

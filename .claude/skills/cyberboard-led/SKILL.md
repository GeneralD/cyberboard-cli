---
name: cyberboard-led
description: >-
  Interactively author an AngryMiao CyberBoard Custom LED display animation
  (slot 1/2/3 = the 40x5 top dot-matrix) and optionally write it to the board.
  Use when the user wants to "make / design / create a CyberBoard LED display
  or animation", "put scrolling text / a rainbow / stripes on the keyboard
  screen", "change slot 1/2/3", or "turn this GIF into a keyboard animation".
  Drives the choice of effect, colors, speed, and seamless-loop options through
  AskUserQuestion, shows a preview each round, iterates, then writes on explicit
  confirmation. Wraps tools/cb_anim.py (procedural recipes) and tools/cb_led.py
  (GIF import). Runs in the main conversation (interactive — do NOT fork).
allowed-tools:
  - AskUserQuestion
  - SendUserFile
  - Read(*)
  - Write(*)
  # uv (pillow for rendering, pyserial for the write path) + the LED scripts.
  - Bash(*)
---

# CyberBoard LED Display Authoring (interactive)

Build a Custom LED **display** animation for slot 1/2/3 and — on explicit
confirmation — write it to a connected R4. This skill is the **interactive
layer**: it gathers choices with `AskUserQuestion`, renders a preview, shows it
with `SendUserFile`, and loops until the user is happy. The heavy lifting is the
deterministic CLI substrate (`tools/cb_anim.py`, `tools/cb_led.py`,
`tools/cb_write.py`) — this skill only orchestrates it in dialogue.

Respond in the user's language (日本語). Keep each question focused; one
decision at a time beats a wall of options.

## Scope — which LED

This skill authors the **display** layer only: the 40×5 = 200-pixel top
dot-matrix screen (IR field `frames`). The **per-key** in-switch backlight
(`keyframes`, 90 LEDs) is a separate system whose index map is still unresolved
(`.claude/rules/90-research-log.md` 续15-16) — it is **kept from the base
untouched**, never authored here.

## Hard facts to honor (do not let the user trip on these)

- **Slot ↔ page**: slot 1/2/3 == `page_index` 5/6/7. The user picks a slot; the
  tools handle the page.
- **Frame cap**: firmware plays at most **256 frames/slot** (`90` 续5). The
  renderer warns and truncates — surface that warning to the user, never hide it.
- **A write replaces the WHOLE config** (`90` 续8): `JSON_START` erases the
  entire config flash, so a write must send a **complete base IR**. You cannot
  patch only the LED. Therefore every write path is **base + this slot's new
  display frames → full write**. Per-key `keyframes` and the keymap ride along
  from the base.
- **LED has no read-back** (`90` 续3): the final correctness check is the user
  **looking at the board**. Say so; don't claim success from an ACK alone.
- **Writing is outward-facing**: always confirm explicitly before
  `cb_write.py --execute`. Default to dry-run first.

## 0. Environment (once per session)

```bash
cd <repo-root>
uv venv --python 3.12 .venv 2>/dev/null || true
uv pip install --python .venv/bin/python -q pillow pyserial
```

`cb_anim.py` / `cb_led.py` need `pillow`; the write path (`cb_write.py`) needs
`pyserial`. Prefer `uv run tools/<script>.py …` (PEP 723 auto-installs pillow)
for the pure file→file steps.

## 1. Ask what to create (AskUserQuestion)

Two decisions: **slot** and **source**. Offer the source archetypes:

| Choice | Route | Good for |
|---|---|---|
| テキスト横スクロール | `cb_anim` `text_scroll` | messages, labels — seamless via `gap:0` |
| 模様(虹 / ストライプ / グラデ) | `cb_anim` `hue_cycle`/`stripes`/`gradient_scroll` | ambient patterns; all seamless by construction |
| 連結(短いのを繋ぐ) | `cb_anim` `sequence` | a longer clip from several segments |
| GIF を取り込む | `cb_led` `gif2ir` | existing dot-art / community GIFs |

Effect parameters and defaults live in `examples/led/README.md` — read it before
asking, so the questions match the real knobs.

## 2. Gather parameters (AskUserQuestion, per effect)

Ask only what the chosen effect uses. Examples:

- **text_scroll**: `text`, `fg`/`bg`, `speed_ms`, `direction` (left/right),
  seamless? (`gap:0`) vs scroll-off-and-repeat (`gap:40`), `step` (smoothness).
- **hue_cycle**: `spread` (0 = whole strip breathes, 360 = rainbow fills the
  width), `cycle_frames` (length), `direction`.
- **stripes**: `colors[]`, `band_width`, `slant` (0 vertical / 1+ diagonal),
  `direction`.
- **gradient_scroll**: `colors[]` (≥2), `width`, `slant`, `direction`.

Write the recipe to a JSON file (e.g. `led/<name>.json`) so it is reproducible
and reviewable — the recipe is the source of truth, the GIF carries a copy in
its Comment.

## 3. Preview → show → iterate

```bash
uv run tools/cb_anim.py preview -r led/<name>.json -o /tmp/<name>.gif --scale 12
# (GIF import path: uv run tools/cb_led.py ir2gif -i config.json --slot N -o /tmp/<name>.gif)
```

Then `SendUserFile` `/tmp/<name>.gif` (status `normal`) and ask with
`AskUserQuestion`: keep, or adjust which knob? Loop back to step 2 on changes.
For your own sanity-check (the GIF only animates in the user's client), you can
also stack frames into a montage PNG and `Read` it.

## 4. Prepare a complete base IR

A write needs a full base (see Hard facts). Ask the user for a **base config
JSON** — their current/exported full config, a saved one, or a merger output. If
they only want to change the LED and keep their keymap, the base must already
contain that keymap (the device keymap can be read via `cb_read.py`, but the LED
pages cannot be read back, so a file base is required).

## 5. Render to IR

```bash
# procedural recipe -> patch the slot into the base
uv run tools/cb_anim.py render -r led/<name>.json -b <base.json> -o config.json --gif /tmp/<name>.gif
# OR GIF import -> patch the slot
uv run tools/cb_led.py gif2ir -i art.gif -b <base.json> --slot <N> -o config.json
```

Then validate before any device contact:

```bash
uv run --with jsonschema tools/cb_verify.py config.json
```

## 6. Confirm, then write

Show the plan (dry-run prints the frame plan) and get an explicit go-ahead:

```bash
uv run tools/cb_write.py config.json              # dry-run: shows the frame plan
uv run tools/cb_write.py config.json --execute    # ONLY after the user confirms
```

`--execute` is outward-facing — confirm every time, even on a re-run.

## 7. Verify on the board

LED frames cannot be read back. Ask the user to switch the display to the Custom
LED slot and **look** — does it match the preview? If not, iterate from step 2.
(The keymap, if it was part of the write, *can* be verified:
`cb_read.py keymap --compare config.json`, after a ~2s settle, `90` 续8.)

## Notes

- The deterministic substrate is shared with the planned CLI/MCP layers
  (roadmap epic #1): this skill must stay a thin orchestrator and push any new
  logic down into `tools/*.py`, not into the prose here.
- Background and protocol detail: `.claude/rules/40-cli-spec.md` (LED authoring
  section) and `10`/`30`. Effect catalog: `examples/led/README.md`.
- Device detection/safety is the sibling `cyberboard-device` skill
  (`.claude/skills/cyberboard-device/SKILL.md`) — run it first if you're unsure
  the right board is connected.

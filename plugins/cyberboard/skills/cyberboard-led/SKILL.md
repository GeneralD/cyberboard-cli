---
name: cyberboard-led
description: >-
  Interactively author a Custom LED *display* animation for the AngryMiao
  CyberBoard R4 and write it to the board. Pick a slot and an effect, tune it
  through a Japanese AskUserQuestion dialogue, preview the result as a GIF,
  iterate, then write it on explicit confirmation. Use whenever the user wants
  to "make / change the LED animation", "set the keyboard's screen", "put
  text / a pattern / a GIF on the CyberBoard display", or similar. Orchestrates
  the `cyberboard` CLI (`anim` / `led` / `write`). Converses in Japanese; every
  write is confirmed first because it overwrites the whole config.
allowed-tools:
  - AskUserQuestion
  - SendUserFile
  - Read(*)
  - Write(*)
  - Bash(*)
---

# CyberBoard LED Display Authoring (interactive)

Author and write a **Custom LED display animation** — the 40×5 top screen —
for a connected CyberBoard R4 by orchestrating the `cyberboard` CLI. This
skill is the user-facing, conversational front end; all the real work is the
CLI (`anim` / `led` / `write`), so the behaviour never drifts from the
command line.

> **Converse with the user in Japanese throughout** — every AskUserQuestion
> prompt, option label, explanation, and confirmation. (Command names and
> flags stay as-is.)

## Scope

- **Display layer only** — the 40×5 = 200-px top matrix (`frames`). Slots
  **1 / 2 / 3 = page_index 5 / 6 / 7** (Custom LED 1–3).
- **Per-key backlight (`keyframes`, the 90 in-switch LEDs) is out of scope** —
  there is no GIF↔key index map yet. It rides along **unchanged** from the
  base config; this skill never touches it.
- Keymap authoring is a different skill — this one only changes the screen.

## Prerequisites

The package must be installed with the LED extra (`anim` / `led` need Pillow):

```sh
pip install 'cyberboard-cli[led]'
# or:  uv tool install 'cyberboard-cli[led] @ git+https://github.com/GeneralD/cyberboard-cli'
```

`write` (device I/O) only needs the core, but you'll already have it.

## Hard facts — never violate these

- **slot 1 / 2 / 3 ⇔ page_index 5 / 6 / 7.** Nothing else is a Custom LED slot.
- **Firmware plays at most 256 frames per slot.** The CLI warns and truncates
  past that — surface the warning to the user, don't hide it.
- **A write replaces the WHOLE config.** `JSON_START` erases the config flash,
  so every write needs a **complete base IR**. Sending only the LED would wipe
  the keymap. → always render into a full base, then write that base.
- **The display has NO read-back path.** You cannot read the current animation
  off the board. So (a) the base config must already carry the user's *current*
  LED setup, and (b) the only final check is **looking at the board**.
- **Every write is outward-facing and destructive → confirm first, every
  time.** Never run `write --execute` without an explicit user "はい / 書き込む".

## The preview loop is GIF-based — do NOT use `led play` as your own preview

When **you (the agent)** want to show the user what an animation looks like,
render a GIF and send it:

```sh
cyberboard anim preview -r recipe.json -o preview.gif   # recipe → GIF, no base needed
```

then `SendUserFile preview.gif`. Iterate by editing the recipe and re-rendering.

`cyberboard led play` plays an animation **in a terminal** with half-block
characters — but under a non-TTY (how your Bash runs) it prints a *single
static frame*, so it is useless as your preview step. Mention it to the **user**
as something *they* can run at their own terminal if they want to watch it live:
`cyberboard led play -i preview.gif` (Ctrl-C to stop). Don't wire it into the
skill's own render loop.

## Steps

### 1. Choose slot + what to make (AskUserQuestion)

Ask, in Japanese, two things (one question each, or combined):

- **どのスロット?** 1 / 2 / 3(= Custom LED 1–3 / page 5–7)。
- **何を作る?**
  - **テキスト横スクロール** — 文字を流す(`text_scroll`)
  - **模様マーキー** — 虹サイクル / ストライプ / グラデ流し(`hue_cycle` / `stripes` / `gradient_scroll`)
  - **GIF を取り込む** — 手持ちの GIF を 40×5 に取り込む(`led gif2ir`)

### 2. Gather per-effect parameters (Japanese dialogue)

Collect the knobs for the chosen effect from the **Effect catalog** below.
Offer sensible defaults so the user can just accept them. Key choices worth
surfacing explicitly:

- **継ぎ目なしループ?** → `gap: 0`(`HELLOHELLO…` のように途切れず一周)。
  画面外まで流して間を空けたいなら `gap: 40`。
- **長さ / なめらかさ** → `step` を小さく(=長い・なめらか)。`solid` の `frames`。
- **速度** → `speed_ms`(1 フレームの表示 ms)。

### 3. Preview → iterate

Write the recipe with the Write tool, render a GIF, send it, repeat until OK:

```sh
cyberboard anim preview -r recipe.json -o preview.gif --scale 16
```

`SendUserFile preview.gif` と一緒に「OK / 調整しますか?」と聞く。調整なら
recipe を直して再プレビュー。GIF 取込の場合はこのステップで `led gif2ir`
の出力 IR を `cyberboard led ir2gif -i config.json --slot N -o preview.gif`
で GIF 化して見せる。

### 4. Prepare a complete base IR (mandatory)

A write needs a **full** config to merge into. The user supplies this:

- **Their own exported config** — ask them for a complete config JSON
  exported from **AM Master** or the official web UI
  (diy.angrymiao.com → export). This is the base; it carries their current
  keymap *and* their current LED for the other slots.
- **Why it's required:** `JSON_START` erases everything and the display can't
  be read back — so the base must already hold what should survive the write.
- **Optional keymap refresh:** if the board is connected, you can pull the
  *keymap* off the device and reconcile it, but **the LED half cannot be read
  back** — it only ever comes from the base file:

  ```sh
  cyberboard read keymap --json          # keymap only; LED is NOT readable
  ```

If the user has no base config at all, stop and explain they must export one
first (there is no way to reconstruct the LED layer from the device).

### 5. Render into the base → verify → confirm → write

```sh
cyberboard anim render -r recipe.json -b base.json -o config.json --slot N --gif preview.gif
cyberboard verify config.json          # schema check before touching hardware
cyberboard write config.json           # DRY RUN (no --execute) — shows the frame plan
```

Show the dry-run plan. Then **ask for explicit confirmation in Japanese**
(「実機に書き込みます。よろしいですか?」). Only on a clear yes:

```sh
cyberboard write config.json --execute
```

(For the **GIF import** path, replace the render line with
`cyberboard led gif2ir -i art.gif -b base.json --slot N -o config.json`.)

### 6. Final check on the board (no read-back)

After a successful write, tell the user to **switch the keyboard display to
the Custom LED slot and look at it** — that is the only way to confirm the
display, since it can't be read back. Optionally suggest they run
`cyberboard led play -i preview.gif` at their own terminal for a side-by-side.

## Effect catalog (recipe JSON)

A recipe is a JSON object. Top-level keys: `slot` (1/2/3), `speed_ms`
(default 100), and **either**:

- a single effect — an **`"effect"`** key naming it, with that effect's
  parameters **flat at the top level**; **or**
- **`"sequence"`** — an array of segment objects (each its own `"effect"` +
  params), concatenated into one slot's animation.

The `"effect"` key is required on every segment (and on a single-effect
recipe). Parameters are flat, not nested under the effect name.

### `text_scroll` — scroll a string (procedural, no artwork)

| key | default | meaning |
|---|---|---|
| `text` | (required) | the string to scroll (tom-thumb 5-px font) |
| `fg` / `bg` | `#00ff88` / `#000000` | text / background colour |
| `step` | 1 | px moved per frame — smaller = smoother & longer |
| `spacing` | 1 | px between glyphs |
| `gap` | 0 | trailing blank px per loop. **`0` = seamless tiling**; `40` = scroll fully off then back |
| `direction` | `left` | `left` / `right` |

### `solid` — hold one colour for N frames

| key | default | meaning |
|---|---|---|
| `color` | `#000000` | the colour |
| `frames` | 1 | how many frames to hold (use between segments) |

### `hue_cycle` — rainbow cycle ("pattern rotation" as a marquee)

The hue wheel is periodic, so it's **seamless by construction**.

| key | default | meaning |
|---|---|---|
| `saturation` / `value` | `1.0` / `1.0` | each 0–1 |
| `cycle_frames` | 60 | frames for one full 360° turn (length = smoothness) |
| `spread` | 0 | degrees of hue spread across the 40-px width — `0` = whole panel pulses one colour, `360` = a full rainbow spans the width |
| `direction` | `left` | `left` / `right` |

### `stripes` — sliding colour bands (diagonal optional)

period = `len(colors) × band_width` → tiles seamlessly.

| key | default | meaning |
|---|---|---|
| `colors` | (required, ≥1) | band colours |
| `band_width` | 4 | px per band |
| `step` | 1 | px moved per frame |
| `slant` | 0 | x-shift per row — `0` = vertical bands, `1+` = diagonal |
| `direction` | `left` | `left` / `right` |

### `gradient_scroll` — a closed-loop gradient scrolling sideways

`colors[-1] → colors[0]` closes the loop → seamless.

| key | default | meaning |
|---|---|---|
| `colors` | (required, ≥2) | gradient stops |
| `width` | 40 | px for one full loop |
| `step` | 1 | px moved per frame |
| `slant` | 0 | diagonal gradient (x-shift per row) |
| `direction` | `left` | `left` / `right` |

## Recipe examples (small, inline)

Seamless scrolling text (slot 1) — single effect, params flat:

```json
{
  "slot": 1,
  "speed_ms": 80,
  "effect": "text_scroll",
  "text": "AM CYBERBOARD R4",
  "fg": "#00ff88",
  "bg": "#000000",
  "gap": 0
}
```

Two clips joined into one slot (green HELLO → red WORLD), via `sequence`:

```json
{
  "slot": 2,
  "speed_ms": 90,
  "sequence": [
    { "effect": "text_scroll", "text": "HELLO", "fg": "#22ff66", "gap": 40 },
    { "effect": "solid", "color": "#000000", "frames": 6 },
    { "effect": "text_scroll", "text": "WORLD", "fg": "#ff4444", "gap": 40 }
  ]
}
```

Rainbow that spans the panel and flows left (`hue_cycle`):

```json
{ "slot": 3, "speed_ms": 60, "effect": "hue_cycle", "cycle_frames": 90, "spread": 360 }
```

## Notes

- Keep temp files (recipes, preview GIFs, the rendered `config.json`) in a
  scratch dir; only the final `config.json` matters for the write.
- If `cyberboard` isn't found, point the user at **Prerequisites** above.
- For exact, current flags run `cyberboard anim --help`, `cyberboard led --help`,
  `cyberboard write --help` — this catalog is the authoring reference; the CLI
  is the source of truth for options.

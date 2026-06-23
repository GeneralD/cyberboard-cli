---
name: cyberboard-led
description: >-
  Interactively author a Custom LED *display* animation for the AngryMiao
  CyberBoard R4 and write it to the board. Choose an effect, tune it
  through a Japanese AskUserQuestion dialogue, preview the result as a GIF,
  iterate, then pick a slot and write it on explicit confirmation. Use whenever the user wants
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

## To judge motion yourself, use `montage` (a GIF reads as one still frame)

When **you** need to *evaluate* an animation (the おまかせ vision loop, 3b), a GIF
is useless: the Read tool shows only its **first frame**. Render a **montage** —
frames tiled top-to-bottom, time going downward — and Read that:

```sh
cyberboard anim montage -r recipe.json -o sheet.png   # tall PNG; then Read it
```

It appends a wrap-seam pair `[last, first]` under an orange band, so you can see
whether the loop closes cleanly. **montage = for you to judge; GIF = to show the
user** (they can open it animated, or run `led play` themselves).

## Steps

### 1. Choose what to make (AskUserQuestion)

Ask, in Japanese:

- **何を作る?**
  - **テキスト横スクロール** — 文字を流す(`text_scroll`)
  - **模様マーキー** — 虹サイクル / ストライプ / グラデ流し(`hue_cycle` / `stripes` / `gradient_scroll`)
  - **キャラ / 絵を縦に流す** — スプライト画像を 40px 幅で縦スクロール(`sprite`)
  - **GIF を取り込む** — 手持ちの GIF を 40×5 に取り込む(`led gif2ir`)

  **どのスロット(1/2/3)に書き込むかは後で聞きます(手順 4a)。** アニメーションの設計は
  スロット非依存なので、まず「何を作るか」を決めましょう。

  **効果ファミリーは意図から先に決める** — 文字なら `text_scroll`、模様なら
  marquee 系、絵 / キャラなら `sprite`。ユーザーが細かいパラメータでなく
  「いい感じに」「ネオンっぽく」のような**雰囲気**で頼んだら、ファミリーだけ決めて
  **手順 3b のおまかせデザイン(vision ループ)**で詰める。画像 / AI 生成の確認は
  **`sprite` を選んだときだけ**(手順 2b)— テキストや模様では尋ねない。

### 2. Gather per-effect parameters (Japanese dialogue)

Collect the knobs for the chosen effect from the **Effect catalog** below.
Offer sensible defaults so the user can just accept them. Key choices worth
surfacing explicitly:

- **継ぎ目なしループ?** → `gap: 0`(`HELLOHELLO…` のように途切れず一周)。
  画面外まで流して間を空けたいなら `gap: 40`。
- **長さ / なめらかさ** → `step` を小さく(=長い・なめらか)。`solid` の `frames`。
- **速度** → `speed_ms`(1 フレームの表示 ms)。

### 2b. Prepare the sprite artwork (`sprite` only)

`sprite` scrolls an external picture fitted to 40-px wide. **Ask, every time,
how to get the art (AskUserQuestion — don't decide silently):**

- **手持ちの画像を使う** — user gives a path (PNG / GIF …). Most reliable.
- **AI に生成させる** — make a picture with the `image-generator` agent
  (Codex / gpt-image-2). ⚠ **state up front that it shrinks to 40-px wide so
  fine detail gets coarse**, then let them choose. **Offer this option only when
  Codex is available and ChatGPT-logged-in** (not API-key mode); if it's
  unavailable, omit the option entirely — don't surface a dead choice.
- **PIL で手続き的に描く** — draw a simple shape / icon with Pillow. Works
  anywhere `[led]` is installed (Pillow is already a dependency), and 40-px-friendly.

Whatever produces the art, feed it to a `sprite` recipe and confirm how it
**looks at 40 px** in the **3b vision loop** below.

### 3. Preview → iterate

Write the recipe with the Write tool, render a GIF, send it, repeat until OK:

```sh
cyberboard anim preview -r recipe.json -o preview.gif --scale 16
```

`SendUserFile preview.gif` と一緒に「OK / 調整しますか?」と聞く。調整なら
recipe を直して再プレビュー。**GIF 取込は base が必須**(`gif2ir` の `-b base.json`)
なので、この段階ではまず手元の元 GIF をそのまま見せて確認し、40×5 へ変換した
正確な preview は **手順 4 で base とスロットを確定した後**に `led gif2ir` の出力 IR を
`cyberboard led ir2gif -i config.json --slot N -o preview.gif` で GIF 化して見せる。
(`gif2ir` には `-b base.json` と `--slot N` の両方が必要。)

### 3b. おまかせデザイン(vision ループ)

When the user delegates the look ("いい感じに" / a vibe rather than exact knobs),
**you iterate by looking at a montage and self-critiquing, 2–3 rounds**, before
showing the user. (A GIF reads as one still frame — judge with `montage`, above.)

1. Build a recipe from the intent (the effect family is fixed in step 1).
2. `cyberboard anim montage -r recipe.json -o sheet.png` → **Read `sheet.png`.**
3. **Critique against falsifiable criteria — each one can *fail*; "looks fine"
   is not a verdict.** Fix whatever fails, then go back to 2.

   - **All families (loop):** does the wrap pair `[last, first]` under the orange
     band continue cleanly (a 1-px step), or is there a jump / step?
   - **`text_scroll`:** is the text **legible at 40 px** — is `fg`↔`bg` contrast
     enough? *(A dark colour on black fails: e.g. `#330033` on black is unreadable;
     `#cc44ff` on black passes.)* Are glyphs inside 5 px (no clipped descenders)?
   - **patterns (`hue_cycle` / `stripes` / `gradient_scroll`):** does the wrap
     frame truly match frame 0 (no visible seam band)? Any colour banding?
   - **`sprite`:** is the subject still recognizable after the 40-px width-fit
     (not mush)? Is the loop blank→blank (`gap >= 5`), not edge→edge? Did 256-frame
     truncation cut the art's bottom (if so, raise `step`)?
4. Converge in **2–3 rounds**. Then **`SendUserFile` the GIF + the montage** and
   ask 「これで書き込みますか?」 → on a clear yes, continue to **step 4 (Choose the
   slot + prepare a complete base IR)** onward.

> If every round self-rates "OK", the criteria aren't doing their job. They are
> meant to *fail* — that's how the loop improves instead of rubber-stamping.

### 4. Choose the slot + prepare a complete base IR

#### 4a. Choose the slot (AskUserQuestion)

**どのスロットに書き込みますか?** と聞く(初めてスロットを聞く場所はここ)。

- **スロット 1** — Custom LED 1 (page 5)
- **スロット 2** — Custom LED 2 (page 6)
- **スロット 3** — Custom LED 3 (page 7)

> `anim preview` / `anim montage` はスロット不要なので手順 1–3 では尋ねなかった。
> `anim render` の `--slot N` と `led gif2ir` の `--slot N` で使う。

#### 4b. Prepare a complete base IR (mandatory)

A write needs a **full** config to merge into. The user supplies this:

- **Their own exported config** — ask them for a complete config JSON
  exported from **AM Master** or the official web UI
  (diy.angrymiao.com → export). This is the base; it carries their current
  keymap *and* their current LED for the other slots.
- **Why it's required:** `JSON_START` erases everything and the display can't
  be read back — so the base must already hold what should survive the write.
- **Optional keymap reconcile:** if the board is connected, diff the base's
  keymap against what's actually on the device (so a base exported earlier
  isn't stale). **The LED half cannot be read back** — only the keymap:

  ```sh
  cyberboard read keymap --compare base.json   # diff device keymap vs base; LED is NOT readable
  ```

If the user has no base config at all, stop and explain they must export one
first (there is no way to reconstruct the LED layer from the device).

### 5. Render into the base → verify → confirm → write

`N` は手順 4a で確定したスロット番号。`--slot N` はレシピ内の `"slot"` フィールドを
上書きするので、recipe に `"slot"` が書かれていなくても問題ない。

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

A recipe is a JSON object. Top-level keys: `slot` (1/2/3, **optional** — default 1;
can be overridden at render time with `--slot N` so the recipe need not contain it), `speed_ms`
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

### `sprite` — scroll a picture/character vertically (needs artwork)

Fits a tall sprite image to **40 px wide** (height kept proportional) and scrolls
a **5-px window** down it. Unlike the procedural effects it **loads an external
image** (animated GIF → first frame). See **2b** for how to get the art.

| key | default | meaning |
|---|---|---|
| `sprite` | (required) | image path (CWD-relative; PNG / GIF …). Scaled to 40-px wide, height proportional (≥5 px) |
| `step` | 1 | px moved per frame — smaller = smoother & longer |
| `gap` | 0 | trailing blank rows. **A clean loop wants `>= 5`** (scroll the art fully off to `bg`, then back). `0` only tiles cleanly if the art tiles vertically |
| `direction` | `up` | `up` (content rises) / `down` |
| `bg` | `#000000` | colour of the `gap` rows |
| `resample` | `nearest` | width-fit interpolation: `nearest` (pixel-art) / `box` / `lanczos` |

> **The seam rule is the reverse of `text_scroll`.** For arbitrary art `gap:0`
> joins top and bottom edges → a jump on non-tiling art. A tall sprite with small
> `step` easily passes 256 frames → the CLI warns and truncates (the art's bottom
> never shows); raise `step` to fit.

## Recipe examples (small, inline)

> **`"slot"` is optional in recipes** — it defaults to 1 and is overridden by `--slot N` at
> render time. The examples below include it for clarity, but you can omit it and pass `--slot`
> on the command line instead.

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

A character scrolling up (slot 1) — needs an image; clean loop via `gap`:

```json
{ "slot": 1, "speed_ms": 70, "effect": "sprite", "sprite": "char.png", "gap": 6, "direction": "up" }
```

## Notes

- Keep temp files (recipes, preview GIFs, the rendered `config.json`) in a
  scratch dir; only the final `config.json` matters for the write.
- If `cyberboard` isn't found, point the user at **Prerequisites** above.
- For exact, current flags run `cyberboard anim --help`, `cyberboard led --help`,
  `cyberboard write --help` — this catalog is the authoring reference; the CLI
  is the source of truth for options.

# LED レシピ例(`cb_anim`)

宣言的レシピ → 40×5 ディスプレイ(① ディスプレイ層)のアニメ。決定論的レンダラが
40×5×N フレームへ展開し、cb_led の共有変換で IR(`frames`)へ焼く / GIF プレビューを出す。

```sh
# プレビュー GIF(base 不要・高速イテレーション用)
uv run --extra led cyberboard anim preview -r examples/led/text-scroll.json -o /tmp/preview.gif

# 完全な base IR の slot へ焼き込み(per-key keyframes は base 由来で維持)+ プレビュー同時出力
uv run --extra led cyberboard anim render -r examples/led/sequence.json -b <base.json> -o config.json --gif /tmp/preview.gif
# config.json を実機へ: uv run cyberboard write config.json --execute
```

> LED 系(`anim` / `led`)は Pillow が要るので `--extra led`。デバイス I/O(`write` /
> `read` / `devices`)は pyserial が core 依存なので追加 extra 不要。インストール後は
> `uv run` を省いて `cyberboard …` で起動できる(`pip install -e '.[led]'` / `uv sync --extra led`)。

## レシピ書式

単一エフェクト、または `sequence`(短いクリップを連結 → 1 slot の長いアニメ)。

| キー | 既定 | 意味 |
|---|---|---|
| `slot` | 1 | 1/2/3 = page 5/6/7(Custom LED) |
| `speed_ms` | 100 | 1 フレームの表示時間(ms) |
| `sequence` | — | セグメント配列。省略時はトップレベル自体を 1 セグメントとして扱う |

### エフェクト `text_scroll`(手続き的=絵は不要)

| キー | 既定 | 意味 |
|---|---|---|
| `text` | (必須) | スクロールする文字列(tom-thumb 5px フォント) |
| `fg` / `bg` | `#00ff88` / `#000000` | 文字色 / 背景色 |
| `step` | 1 | 1 フレームの移動量(px)。小さいほど滑らか=長い |
| `spacing` | 1 | 字間(px) |
| `gap` | 0 | 1 周の末尾に足す空白(px)。**`0`=継ぎ目なしタイリング**(`HELLOHELLO…`)。`40`=画面外まで流れて空白→再入 |
| `direction` | `left` | `left` / `right` |

### エフェクト `solid`(単色を N フレーム保持)

| キー | 既定 | 意味 |
|---|---|---|
| `color` | `#000000` | 色 |
| `frames` | 1 | 保持フレーム数(区切り・間に使う) |

### エフェクト `hue_cycle`(虹サイクル=「模様回転」を marquee 解釈)

色相環は周期的 → **構造的に継ぎ目なし**(1 周で frame0 に戻る)。`spread` で「全面が同色で
明滅」から「幅いっぱいの虹が流れる」へ。8:1 アスペクトでは幾何回転が破綻するので marquee 化。

| キー | 既定 | 意味 |
|---|---|---|
| `saturation` / `value` | `1.0` / `1.0` | 彩度 / 明度(各 0–1) |
| `cycle_frames` | 60 | 1 周(360°)のフレーム数。長さ=滑らかさ |
| `spread` | 0 | 幅 40px に渡る色相の回転量(度)。`0`=全面同色で明滅、`360`=虹が幅いっぱい |
| `direction` | `left` | 流れる向き `left` / `right` |

### エフェクト `stripes`(色帯のスライド・斜め可)

period = `len(colors) × band_width` で modulo タイリング → **継ぎ目なし**。

| キー | 既定 | 意味 |
|---|---|---|
| `colors` | (必須) | 帯の色(≥1) |
| `band_width` | 4 | 1 帯の幅(px) |
| `step` | 1 | 1 フレームの移動量(px) |
| `slant` | 0 | 1 行ごとの x シフト。`0`=縦帯、`1+`=斜め帯 |
| `direction` | `left` | `left` / `right` |

### エフェクト `gradient_scroll`(閉ループグラデの横流し)

`colors[-1]→colors[0]` で閉じたグラデを横スクロール → **継ぎ目なし**。

| キー | 既定 | 意味 |
|---|---|---|
| `colors` | (必須・≥2) | グラデのストップ色 |
| `width` | 40 | 1 周分の px 幅 |
| `step` | 1 | 1 フレームの移動量(px) |
| `slant` | 0 | 斜めグラデ(行ごとの x シフト) |
| `direction` | `left` | `left` / `right` |

## 上限

firmware は **1 slot あたり 256 フレームまで**再生(`90` 続5)。超過分は生成時に警告して切り捨て。
レシピ JSON は出力 GIF の Comment に埋め込まれ、GIF 自体が生成元を持ち運ぶ。

# LED レシピ例(`cb_anim`)

宣言的レシピ → 40×5 ディスプレイ(① ディスプレイ層)のアニメ。決定論的レンダラが
40×5×N フレームへ展開し、cb_led の共有変換で IR(`frames`)へ焼く / GIF プレビューを出す。

```sh
# プレビュー GIF(base 不要・高速イテレーション用)
uv run --extra led cyberboard anim preview -r examples/led/text-scroll.json -o /tmp/preview.gif

# モンタージュ PNG(縦に時間が進む静止画 → GIF を1枚目しか出さないビューアでも動き/ループを確認)
uv run --extra led cyberboard anim montage -r examples/led/sprite-scroll.json -o /tmp/sheet.png

# 完全な base IR の slot へ焼き込み(per-key keyframes は base 由来で維持)+ プレビュー同時出力
uv run --extra led cyberboard anim render -r examples/led/sequence.json -b <base.json> -o config.json --gif /tmp/preview.gif
# config.json を実機へ: uv run cyberboard write config.json --execute
```

`montage` は各フレームを上から下へ並べた縦長 PNG を出す。GIF は多くのビューア(Read ツール
含む)で**先頭フレームしか表示されない**ため、動き・ループ・継ぎ目の判断には montage を使う。
フレームが多い時は最大 `--max`(既定 24)枚へ等間隔サンプリング(先頭・末尾は必ず含む)し、
末尾にオレンジ帯 + 巻き戻りペア `[末尾, 先頭]` を並べてループの繋ぎ目を直接見られる(`--no-seam` で省略)。

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

### エフェクト `sprite`(キャラ縦スクロール=絵を縦に流す)

縦長のスプライト画像を、幅 40px に合わせて(縦=スクロール軸はアスペクト比を保ったまま)
**5px の窓で縦にスクロール**する。`text_scroll` などの手続き系と違い**外部の絵を読み込む**
(アニメ GIF は先頭フレーム)。例 `examples/led/sprite-scroll.json` + `examples/led/sprite.png`。

> **継ぎ目の意味が `text_scroll` と逆**: 任意の絵では `gap:0` の巻き戻りは画像の上端と下端を
> 直接つなぐので、**縦にタイルしない絵では段差(ジャンプ)になる**。**綺麗なループは `gap>=5`**
> (絵を完全に画面外=`bg` まで流してから再入。空白↔空白の接合が継ぎ目なし)。`gap:0` は
> 絵が縦にタイルする場合のみ継ぎ目なし。

| キー | 既定 | 意味 |
|---|---|---|
| `sprite` | (必須) | スプライト画像パス(CWD 基準。PNG / GIF 等)。幅 40px に縮小、高さ比例(≥5px 必須) |
| `step` | 1 | 1 フレームの移動量(px)。小さいほど滑らか=長い |
| `gap` | 0 | 末尾に足す空白行。**綺麗なループは `>=5`**(上記)。`0`=タイル前提 |
| `direction` | `up` | `up`(内容が上へ昇る)/ `down` |
| `bg` | `#000000` | `gap` 行の背景色 |
| `resample` | `nearest` | 幅合わせの補間 `nearest`(ドット絵向き)/ `box` / `lanczos` |

> 縦長スプライト × `step` 小は容易に 256 フレーム超 → 生成時に警告し**後半フレームを切り捨て**
> (ループが完走せず、絵やループの一部が出なくなる)。全部出したいなら `step` を上げる。

## 上限

firmware は **1 slot あたり 256 フレームまで**再生(`90` 続5)。超過分は生成時に警告して切り捨て。
レシピ JSON は出力 GIF の Comment に埋め込まれ、GIF 自体が生成元を持ち運ぶ。

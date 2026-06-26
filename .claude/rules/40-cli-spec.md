# 自作 CLI 仕様(叩き台)

> ステータス: **叩き台**。プロトコル確定(`30`)前なので書き込み部は暫定。
> 設計の核は「**独自スキーマ → 中間表現(純正JSON)→ 書き込み**」の3層分離。

## 設計方針

### レイヤ分離(最重要)

```text
[独自スキーマ]      keymap.* と led.* を別ファイルで管理(ユーザーが編集)
      │ build
      ▼
[中間表現 IR]       純正互換 JSON(= 既存資産・merger 出力と同形)
      │ write
      ▼
[デバイス]          HID 経由で書き込み(CMD_* チャンク送信)
```

- **なぜ IR を挟むか**:
  1. **書き込み経路を既知の正解で検証できる**。merger の `outputs/*.json` は
     「純正アプリが実際に書けた設定」。これを CLI で書いて通れば、「書き込み実装の正しさ」と
     「自作スキーマ生成の正しさ」を**分離してテスト**できる(advisor 指摘)。
  2. 既存の merger / コミュニティ JSON 資産をそのまま流用できる。
  3. プロトコル変更に強い(IR↔デバイスだけ直せばよい)。

### キーマップと LED の分離(ユーザーの主目的)

独自スキーマでは **keymap と LED を別ソース**として持ち、build 時に IR へ合成。
これにより「LED だけ差し替え」「キーマップだけ変更」が安全にできる。

> **部分書き込みは firmware が非対応 🟢(実機確定 2026-06-22, `90` 続8 /
> `experiments/partial-write/`)**: LED セクションだけ送って keymap を省略すると、
> keymap は**全て `#FFFFFFFF`= フラッシュ消去状態**になった。**`JSON_START` が設定
> フラッシュ領域を消去**し、各セクションが自領域を再書込、**送らなかったセクションは
> 0xFF のまま残る** = **1 トランザクション = 設定全体の置換**。
> → **分離管理は必ず「read → merge → フル書き込み」で実現**(合成は build 側の責務):
>
> - **LED だけ変更・keymap 維持**: `[6,9]` で keymap 読戻し → (読んだ keymap + 新 LED)で
>    フル書込。**今すぐ可能**。
> - **keymap だけ変更・LED 維持**: **LED は読み戻せない**ため LED の IR を**ソースに保持** →
>    (新 keymap + 保持 LED)でフル書込。
> ⚠ **書込直後の read-back は settle 遅延が必要**: フル書込直後の keymap 読戻しは全 `#00000000`
> を返した(commit 未完了)。**~2 秒待つ**と 1400/1400 一致。検証読戻し前に必ず待つ。

### ステートフルなデバイス設定管理(state store / `cb_store.py`)— epic #45

「キーマップ/LED を直接コマンドで編集」+「毎操作で更新履歴を保存しロールバック可能に」する
機能群(= "git for keyboard")。実体は上の制約どおり **read → merge → フル書き込み**、加えて
**書いたフル IR を個体ごとにローカル保存**する。LED は読み戻せないので、**最後に書いた IR が
LED の唯一の真実**= これを保持しないと「keymap だけ変更・LED 維持」が成立しない。

- **保存ルート解決ラダー**(先に設定されたものが勝つ):
  `$CYBERBOARD_DATA_DIR` > `$XDG_DATA_HOME/cyberboard-cli` > `~/.local/share/cyberboard-cli`。
- **レイアウト**: `<root>/devices/<product_id>/` に `current.json`(最後に書いた full IR =
  LED の source of truth)/ `meta.json`(product_id, version, last_seen)/ `history/<ISO8601>.json`
  (自動スナップ 🟢 issue #47)。
- **個体キー = `product_id`(例 `CB04`)単一機割り切り** 🟢: R4 の USB シリアルはダミー(全個体
  同一・実機確認 2026-06-26)、product_id/version も全 R4 共通 → 電気的に2台を区別できないため
  個体識別はせず product_id をキーにする。`_safe_key` で path traversal を弾く。
- **`cb_store.py`(🟢 実装済み, issue #46)**: pure stdlib(serial/PIL 不要 = core)。公開 API =
  `store_root` / `device_dir` / `load_current` / `save_current`(原子的書込 + meta 更新)/
  `load_meta` / `record_seen`(read 系が last_seen のみ更新)。CLI は `cyberboard store path
  [--device CB04]` / `cyberboard store --selftest`。書込は per-device flock で current+meta を排他。
- **自動スナップショット(🟢 実装済み, issue #47)**: `snapshot(product_id, ir)` が
  `history/<ISO8601>.json`(`:`→`-`・マイクロ秒 + 衝突ガード)へ保存し、保持上限を超えた古い順に
  prune。`list_history`(新しい順)/ 上限 = `CYBERBOARD_HISTORY_MAX`(既定 50)。flock は per-fd ゆえ
  `snapshot` と `save_current` は**入れ子にせず順次**呼ぶ(writer は before-snapshot → save の2ステップ、
  自己デッドロック回避)。
- これを叩く `dump`(provenance 付きハイブリッド: keymap=ライブ / LED=stored)/ `get` / `set key`
  / `set led` / `history` / `restore` / `diff` は epic #45 の各 issue(#48-#54)で実装。

## 独自スキーマ案

### キーマップ `keymap.toml`(v1 仕様)

> 設計確定 2026-06-22。advisor レビュー反映。`90` 続10-12 / `experiments/keymap-matrix/` が裏付け。

#### モデル: toml は **完全な base への差分パッチ**(全置換は build 側で吸収)

`JSON_START` が設定フラッシュを全消去する(部分書込 非対応, 続8)以上、**`build` は必ず
完全な IR を生成**しなければならない(200×7 全位置 + LED 全ページ + swap/exchange/macro)。
よって **keymap.toml は「base IR に対する上書き(差分)」だけを持つ**:

```text
build = base IR(完全・必須) + keymap.toml の override → 完全 IR → フル書込
```

- **base は完全 IR 設定ファイルが必須**(`outputs/*.json` 等)。LED はここから引き継ぐ
  (または別の `led.toml` ソースから合成)。**LED は読み戻せない**ので base 無しに device
  だけからフル設定は再構成できない(キーマップは `[6,9]` で読めるので任意で base へ反映可)。
- 省略したレイヤ/位置/機能は **base のまま不変**(差分のみ適用)。

#### 2 つの名前空間(位置 と 値 を分離)

**① 位置(`[layer.N]` テーブルのキー側)** — 「どの物理キーか」:

- **座標 `r{row}c{col}`**(row 0-7, col 0-24)。matrix index = `row*25 + col`。
  ⚠ これは **matrix 座標であって物理位置ではない**(英字段は一致するが最下段 row5 はズレる, 続12)。
- **別名(alias)**: R4 プリセット別名表の可読名(`esc` / `a` / `space` …)。alias → 座標 → index。
  別名は**参照 layer0 の機能に紐づく**ため、物理位置が未確定な最下段でも頑健。
- 解決順: **まず座標パターン `r\d+c\d+` を試し**、ヒットしなければ別名表を引く。
  → 座標直書き `r5c0` は「物理 左から1番目」と勘違いしやすい唯一の落とし穴(別名なら安全)。

**② 値(`=` の右側)** — 「そのキーが何を出すか」:

- **可読名**: 標準キー = **小文字トークン**(0x07 `a`/`esc`/`space`/`lctrl`…、0x0C `volup`/`play`…
  = ①位置別名と同一語彙)。ベンダー = **0x92 ラベル**(`Fn2`/`Layer3`/`BT1`…)。大小無視で受ける。
- **生パススルー `#MMPPUUUU`**(8 hex リテラル)を**第一級の値**とする。未解読の 0x92 /
  MM 修飾ビット / tab_key / 名前の付かないコードを**そのまま無損失で表現**できる
  = device dump とラウンドトリップ可能(下記)。0x92 は CLI が解釈せず passthrough(続12 方針)。
- 空き = 省略(base 維持)or 明示クリア `"."` / `"#00000000"`。
- **実装済み 🟢**(`90` 続13): `tools/keycode.py` = `name_to_code` / `code_to_name`。標準キーは
  自作クリーン名(UI ラベルは標準キーをキーキャップ面 HTML `!<br/>1` で持ち逆引き不可)、ベンダーは
  権威 UI ラベルの**一意サブセット**(Layer1-7/Fn1-7/LED/PCB/BT/system)。表に無いコード・MM≠00・
  未解読ベンダーは**生 `#…` へ落として無損失**(`code→name→code` は常に恒等)。

#### レイヤは **1-indexed**(`[layer.1]`〜`[layer.7]`)

公式 UI と同じ layer1-7。内部の配列 index は N−1。**デフォルトは layer1**(続11)。

```toml
[meta]
product = "R4"
base = "outputs/merged_20250916_161615.json"  # 完全 IR base(必須)
# refresh_keymap_from_device = true           # 任意: [6,9] で実機 keymap を base に反映

[layer.1]                  # = 配列 index 0 = デフォルトレイヤ
caps  = "lctrl"            # Caps 位置を LCtrl 化(別名 caps → r3c0 → idx75)
r3c0  = "lctrl"            # ↑ と等価(座標直書き)。大小無視なので "LCtrl" でも可

[layer.2]                  # = 配列 index 1
caps  = "Fn2"              # 0x92 ラベルも値に書ける(機能でアンカー)
esc   = "#00920A01"        # 生パススルー(未解読ベンダー=電源キー。名前無しでも無損失)

[[swap_key]]                # TOML 配列テーブルは 1 行 1 キー(詰め書き不可)
input = "a"
out   = "b"

[[exchange_key]]
input = ["a", "b"]
out   = ["b", "a"]

[[macro]]
input       = "m"
out         = ["h", "i"]
interval_ms = [0, 100]

[[fn_key]]
input = "p"
out   = "up"
```

- swap/exchange/macro/fn_key の値も **②値の名前空間**(可読名 or `#…`)で書く。
  **swap/exchange は R 系列 write が送る**が、**macro/fn_key は送らない**(`30` §5)→ IR には
  入るが当面デバイスへ届かない(build が警告)。placeholder(全 `#00000000`)エントリは dump 時に
  除外し、`*_num` は実エントリ数で再計算(工場 exchange=placeholder 7 件/num=0 を再現)。
- 内蔵テーブル: 可読名 ↔ `#MMPPUUUU`(`10` / `decode_keymap.py` の HID07/HID0C + 0x92 ラベル)、
  別名 ↔ 座標(R4 プリセット。layer0 デコードから生成、最下段は要押し試験 🔴)。
- **別名表 = 実装済み 🟢**(2026-06-22, `90` 続13): `presets/r4-keymap-aliases.json`(81 別名)+
  生成器 `tools/keymap_alias.py`。**工場出荷 config の layer0 から機械生成**(merged 等のリマップ済み
  config は不可 — `idx75` が Caps でなく LCtrl になる等)。別名は**機能でアンカー**するので最下段でも
  正しい(例 `lctrl→r5c0`=idx125 は物理 5 番目だが機能で確定)。`resolve_position(token)` =
  座標 `r\d+c\d+` 優先 → 別名表。座標→index・範囲チェック・round-trip 自己テスト済み。

#### ラウンドトリップ検証(無損失スキーマの副産物)

生パススルー(②)で**スキーマが無損失**なら、
`toml → build → IR → write → [6,9] read → de-build → toml` が**差分ゼロ**になるはず。
既に実証済みの「write→read→diff 1400/1400」(M2)を**1 段上へ持ち上げた検証**になる。
→ スキーマ設計時点でこのラウンドトリップを成立条件にする(= 生パススルーが必須になる根拠)。

### LED: GIF を交換フォーマットにする(`cb_led.py` 🟢 実装済み)

**display(40×5)は GIF と相互変換する**。コミュニティ JSON を継ぎ接ぎする代わりに、
**5×40 ドット絵アニメ GIF を作る/共有する**のを主軸にする(`90` 続15 のアイデア確定)。
GIF は人間も AI も直接扱え、目視確認も容易。生成レシピ/プロンプトは **GIF Comment
Extension** に同梱(GIF に EXIF は無い)→ 設定そのものが再現可能なソースになる。

```text
cb_led.py gif2ir -i art.gif -b base.json --slot 1 -o config.json  # GIF → IR(slot へ patch)
cb_led.py ir2gif -i config.json --slot 1 -o art.gif [--recipe …]  # IR slot → GIF(目視確認)
cb_led.py play   -i art.gif [--loop N|--once] [--scale 2]         # ターミナルで再生(半角ブロック)
cb_led.py play   -i config.json --slot 1                          # IR slot をターミナルで再生
cb_led.py recipe  art.gif [--set "…"]                             # GIF コメント R/W
```

- **slot 1/2/3 = page_index 5/6/7**。display フレーム = 200px(`index = y*40 + x` row-major)。
- **gif2ir は display `frames` だけ patch**し、**per-key `keyframes` は base から維持**
  (GIF↔keyframes-90 の index マップ未解明, `90` 続15)。base は完全 IR 必須(JSON_START 全消去)。
- **256 cap**: firmware は 1 slot 256 フレームまで再生(`90` 続5)→ 超過分は drop して警告
  (silent cap 禁止)。任意サイズ GIF は 40×5 へ自動ダウンサンプル(`--resample nearest|box|lanczos`、
  既定 nearest=ドット絵向き)。`speed_ms` は GIF の duration から(or `--speed-ms`)。
- **ラウンドトリップ**: `ir2gif` → `gif2ir`。**低色数アニメは可逆**(全フレーム横断 ≤256 色なら
  GIF パレットに収まる)、keyframes 維持・recipe 往復・schema pass。⚠ **リッチ色(>256 色/横断)は
  GIF グローバルパレットで色が削られ、連続同一フレームは Pillow が coalesce する**(`90` 続17)→
  ir2gif は**ビューア**であって、リッチ素材の可逆フォーマットは IR JSON 自体。
- **同じ物理マップが双方向**(描画↔サンプル)に使える(`experiments/perkey-layout/render_tui.py`
  が TUI/PNG で実証)。display は 1:1 マップ既知なので今すぐ可。per-key も同型だが index マップ待ち。
- **`play` でターミナル再生**(`90` 続22、issue #12): GIF か IR slot を**半角上ブロック `▀`(U+2580)**で
  truecolor 描画。fg=上ピクセル/bg=下ピクセル → 1 テキスト行=縦 2px、40×5=**40 文字 × 3 行**(最下行は
  上半分=5 行目のみ・下半分は端末背景)。`render_tui.py` の `48;2;r;g;b` 背景描画を半角ブロック化したもの。
  ノブ: `--once`/`--loop N`(既定=無限)/`--fps`/`--speed-ms`/`--scale`(横複製で拡大)/`--resample`。
  **非 TTY(パイプ)は 1 フレーム静止へ縮退**、`Ctrl-C` でカーソル復元して終了。**IR slot 再生は pillow 不要**
  (GIF 入力のみ `[led]`)。256 cap 準拠。デバイス I/O 無しの純粋表示。

### LED: 宣言的レシピでアニメ生成(`cb_anim.py` 🟢 実装済み)

GIF を「取り込む」だけでなく、**宣言的レシピから 40×5 アニメを生成**する(`90` 続17)。
コミュニティ作品の3原型(テキスト横スクロール / キャラ縦スクロール / 模様回転)のうち、
**手続き的に書けるもの(text/pattern)はパラメータだけで生成**でき、AI/作者はノブを選ぶだけ
(ホワイトリスト式エフェクト=生コードは走らない)。**スプライト的なもの(キャラ)だけ**
後段のデザインエージェント+vision ループの価値が出る(advisor 指摘:3原型は対等でない)。

```text
cb_anim.py render  -r recipe.json -b base.json -o config.json [--gif art.gif]  # レシピ→IR(+GIF)
cb_anim.py preview -r recipe.json -o art.gif [--scale 16]                       # レシピ→GIF のみ(高速)
cb_anim.py montage -r recipe.json -o sheet.png [--scale 8] [--max 24] [--no-seam]   # レシピ→縦長 PNG(動き/ループ確認)
```

- **共有変換**: cb_anim はフレーム列(200-hex)を生成し、cb_led の `frames_to_page`
  (display `frames` へ patch・per-key 維持・256 cap)/ `frames_to_gif` を呼ぶ。**コーデックは
  cb_led に一本化**(gif2ir/ir2gif と同じ経路 → IR 構築ロジックが二重化しない)。
- **出力は IR が正**(書込対象)。GIF は共有/プレビュー用で recipe JSON を Comment に同梱。
  我々の生成物は色数が少ない(text=2色等、全フレーム横断 ≤256 色)ので GIF も可逆
  (cb_anim text の `ir2gif→gif2ir` で 18000/18000 実証)。**リッチ色アニメ(>256 色/横断)は
  GIF パレットで色が削られ可逆でない**(`90` 続17 で訂正)→ 書込対象は IR を直接吐く。
- **レシピ書式**(単一エフェクト or `sequence` で連結):
  - `text_scroll`(手続き的): `text` / `fg` / `bg` / `step`(px/frame) / `spacing` / `gap` /
    `direction`。**`gap:0`=継ぎ目なしトーラスタイリング**(`HELLOHELLO…`)、`gap:40`=画面外まで
    流れて再入。フォントは **tom-thumb(5px, MIT, vendored `tools/fonts/`)**。40×5 で legibility 実描画確認済。
  - `solid`(単色を N フレーム保持): `color` / `frames`。区切り・連結の間に使う。
  - `hue_cycle` / `stripes` / `gradient_scroll`(手続き的・模様 marquee, `90` 続18)。
  - `sprite`(スプライト系=外部の絵を読込, `90` 続25): `sprite`(画像パス・必須)/ `step` /
    `gap` / `direction`(`up`/`down`)/ `bg` / `resample`。縦長画像を幅 40px 合わせ・高さ比例で
    5px 窓を縦スクロール。**継ぎ目は text_scroll と逆**: 任意の絵は `gap:0`=上端↔下端ジャンプ、
    **綺麗なループは `gap>=5`**(空白↔空白接合)。`gap:0` は縦タイルする絵のみ継ぎ目なし。
- **ユーザー要望の4ノブが揃う** 🟢(`90` 続17): ①継ぎ目なしループ=`gap:0`(seamless 実証:
  wrap フレームが 1px ずつ連続シフト、段差ゼロ)/ ②長さ=`step`(text)・`frames`(solid)/
  ③MAX256=生成時に警告して truncate(firmware 真値)/ ④短いの連結=`sequence`(merger `combine` 同型)。
- **`montage` = 動きを「見る」プリミティブ** 🟢(`90` 続26, #6 前半→後半の橋渡し): レシピを縦長
  PNG(時間=下方向)に展開。GIF は Read ツール等で**先頭フレームしか出ない**ので、動き・ループ・
  継ぎ目の vision 判断にはこれを使う。`--max`(既定 24)枚へ等間隔サンプリング(**先頭・末尾は必ず
  含む**、no silent drop)+ 末尾にオレンジ帯 + 巻き戻りペア `[末尾,先頭]` を隣接表示でループ繋ぎ目を
  直接確認(`--no-seam` で省略)。`frames_to_montage` は cb_led(コーデックの家)に置き共有。
  **後段の LED デザイン agent(#6 後半)が動きを目視するための土台**(advisor: GIF 単体では motion を
  判定できない)。
- 例: `examples/led/{text-scroll,sequence,sprite-scroll}.json`(sprite は `examples/led/sprite.png` 同梱)。

### LED `led.toml`: 複数ソース合成(`cb_ledtoml.py` 🟢 実装済み)

GIF 単体を超えて「複数ソースを slot ごとに合成」する toml マニフェスト。`90` 続28、issue #19。

```text
cyberboard compose -m led.toml [-b base.json] -o config.json   # マニフェスト → 完全 IR
```

```toml
[meta]
base = "exported-config.json"   # 完全 IR base(必須。-b でも可)

[[slot]]
index = 1                        # 1/2/3 -> page 5/6/7
speed_ms = 70                    # 任意・スロット全体(省略時は最初の gif の duration)
lightness = 100                  # 任意
resample = "nearest"            # 任意(gif ソース用 nearest|lanczos|box)
sources = [                      # 順に連結。1 個 = replace / 複数 = combine / slot 省略 = keep
  { recipe = "text-scroll.json" },        # cb_anim レシピ(エフェクト展開)
  { gif = "logo.gif" },                   # 40×5 ダウンサンプル(led gif2ir と同じ)
  { config = "other.json", slot = 2 },    # 別 IR の slot の display frames(slot 省略時=外側 index)
]
```

- **keep / replace / combine を `sources` で表現**: スロット省略 = keep、ソース 1 個 = replace、
  複数 = combine(連結)。miaomerge の action triplet を包含しつつ異種ソース混在 + recipe 統合に拡張。
- **ソース種別**(各 entry に 1 つ): `recipe`(`cb_anim.EFFECTS` で展開・cap なし=compose 層が cap を一元管理)
  / `gif`(`cb_led._gif_frames`)/ `config`(別 IR の page から `frame_RGB` 抽出)。パスは**マニフェスト相対**。
- **display `frames`(200px)のみ合成**、per-key `keyframes` は base 維持(gif2ir 不変条件)。base は完全 IR 必須
  (LED は読み戻し不可)。出力は完全 IR(`write`/`verify` 可)。
- **256 cap は compose 層で per-source 報告**(silent cap 禁止): どのソースが full / truncated / DROPPED かを
  stdout に列挙 + 末尾 drop 数を warn。`cb_led.frames_to_page` には ≤256 を渡すので二重 cap/警告にならない。
- **参照実装**: `miaomerge`(merger の Tauri/Rust 版)の `merge_configurations.rs`。アクション
  `keep`/`replace`(置換)/`combine`(連結+`frame_num`再計算)。**`frames`(200px)しか合成しない**点も同じ。
- **検証済み 🟢**(`90` 続28, `tmp/verify_compose.py` 26 アサート): roundtrip(`config` ソースで slot を
  バイト一致再現)/ combine 合計 / 256 cap + per-source 報告 / keyframes 維持 / keep / gif ソース / エラー系。
- 例: `examples/led/compose.toml`(コミット可能な recipe ソースのみ。combine/replace/keep を実演)。

## CLI コマンド構成(案)

```text
ambctl devices                 # 接続デバイス列挙(product_id/version/pages/port)
ambctl device info [PORT]      # 1台の詳細(未指定なら自動検出)
ambctl build  -k keymap.toml -l led.toml -o config.json   # 独自→IR(純正JSON)
ambctl verify config.json      # IRスキーマ検証(書き込まない)
ambctl write  config.json [--section keymap|led|all] [--slot 1,2,3] [--dry-run]
ambctl read   -o dump.json     # デバイス→IR 読み戻し(cmd_get_* 利用)
ambctl diff   dump.json config.json   # 書き込み前後の差分確認
cyberboard keymap show [CONFIG] [--layer N] [--corners round|square] [--color auto|always|never]  # keymap をキーボード型 ASCII グリッドで表示(カテゴリ別カラー + ⌘⌥⌃⇧/矢印 記号)
cyberboard keymap edit CONFIG [--layer N] [--corners round|square] [-o OUT]  # 対話的 TUI でキーをクリック→再割当(同じカラー表示・[tui] extra)
```

- **`devices` / `device info` は実装済みの土台あり**🟢: `tools/cb_device.py`(+ 共有コア
  `tools/cb_protocol.py`)。実機 R4 で動作確認済み(`90` 2026-06-22)。
  `list`/`info --json` を持ち、これをそのまま CLI サブコマンドへ昇格できる。
  プロジェクトローカル skill = [`cyberboard-device`](../skills/cyberboard-device/SKILL.md)。
- **`keymap show` 実装済み 🟢**(`tools/cb_keymap.py`, `90` 続31, issue #38): keymap を
  **キーボード型 ASCII グリッド**で表示する読み取り専用レンダラ。物理レイアウト再現
  (function/media ストリップ / 右ナビ列 Home/End/PgUp/PgDn / ワイド Space / 逆 T 字矢印)+
  丸角(既定 `╭╮╰╯`、`--corners square` で戻せる)。CONFIG 省略=R4 デフォルトスケルトン、
  指定=layer を `#MMPPUUUU` デコードして流し込み(短縮ラベル: HID `0x07`/`0x0C` テーブル、
  `0x92`=`Fn<hex>`、未割当=空セル)。**#37(TUI キーマップ編集)の描画土台**。旧 `decode_keymap.py`
  (フラット表、wiki 送り)を置換。
- **`keymap edit` 実装済み 🟢**(`tools/cb_keymap_tui.py` + `cb_keymap.cell_geometry()`, `90` 続32,
  issue #37): **Textual** 製の対話的 TUI。`show` と同じ box-drawing グリッドを描き、各キーを
  **クリック→モーダルで新しい値を入力**(`keycode.name_to_code` で可読名 or 生 `#MMPPUUUU` を解決)→
  変更キーは**黄ハイライト**、`s` で保存(`-o` 省略=in-place)、`←/→` でレイヤ切替。描画は
  `cb_keymap.render()` を再利用し、`cell_geometry()`(matrix index → box 矩形)で hit-test するので
  **`show` と座標がずれない**(render() と突合 = 82 cell / bad 0)。`textual` は遅延 import →
  未導入なら `pip install 'cyberboard-cli[tui]'` の clean hint。**ヘッドレステスト**
  (`App.run_test()` + `pilot.click`)で renderer / クリック→モーダル / 再割当+変更マーク /
  空クリック no-op / 不正名却下 / 保存→再読込永続 の 6 ステップ pass。
- **カテゴリ別カラー + 記号化 実装済み 🟢**(`tools/cb_keymap.py`(構造/描画)+ `cb_keymap_color.py`
  (分類/着色)+ `cb_keymap_tui.py`(編集 TUI)、`90` 続33, issue #37 完了): keymap グリッドを
  **キー種別で着色**(mod=cyan / F+メディア=pink / nav=green / 英数=white / 記号=grey /
  0x92 ベンダー=purple、未割当=dim)。modifier は **⌘⌥⌃⇧ + L/R**、矢印は **←→↑↓** にコンパクト記号化
  (`cb_keymap.decode()` と skeleton 既定の両方)。**色の分類器(keycode→カテゴリ)+ 着色は
  `cb_keymap_color.py` に集約**し `show` と TUI が共有 — `cb_keymap.render()` はプレーンのまま返し、
  着色は **`cell_geometry()` 駆動の後段**で `show` は ANSI を、TUI は Rich style を**セル span に
  オーバレイ**(変更キーの黄ハイライトは最後に重ねて優先)。ANSI を `_box` に通すと `len()` が
  ずれて右クラスタが崩れる罠を回避(plain と ANSI 除去後がバイト一致で検証)。`show --color
  auto`(既定)=TTY のみ着色・`NO_COLOR` 尊重、`always`/`never` で強制。xterm-256 index を ANSI と
  Rich で共有(truecolor 不使用)。
- **ユーザー向け対話 LED 作成 skill = プラグイン側 🟢**(`90` 続24 / 続27, issue #2 / #6 後半):
  `plugins/cyberboard/skills/cyberboard-led/SKILL.md`。`cyberboard anim/led/write` を
  オーケストレーションし AskUserQuestion で slot/効果を選ばせ preview 反復→明示確認→書込。
  プラグインは cache コピーされ repo 非参照ゆえ効果カタログ/例を**自己完結 inline**。
  preview は GIF ベース(`led play` は非 TTY で 1 枚=ユーザー端末向け)。base IR は利用者が export。
  **続27 で全効果デザイナー化**: text/模様/sprite 全部 + **おまかせデザイン vision ループ**
  (`anim montage` を Read→falsifiable 基準で自己批評→改訂)。sprite の絵は手持ち/AI 生成/PIL を毎回選択。
- `write` は段階的に: 接続確立 → (必要なら read で現状退避) → 送信 → **read で検証**。
- `--dry-run` は実送信せずチャンク列を表示。
- 堅牢化(`30` §6): 列挙条件の厳密化(usage/経路)+ 明示リトライ + 各段で読み戻し検証。
- **公式の `pages_num` 書込ゲートを持たない=優位** 🟢(`30` §6-7, `90` 続9): 公式は書込前に
  `cmd_check_pages` でページ数を読み、`pages_num∈{0,3}` 以外だと 404 拒否 or silent no-op
  になる(中古/初期化前の個体が「いきなり書けない」元凶)。`cb_write.py` はこのゲートを持たず
  `JSON_START`→フル config→`JSON_END` を**無条件送出** → **公式が拒否する個体でも書きにいける**
  (pages_num=0 個体での実証は未。構造上は回避)。書込後の read-back は settle 遅延 ~2s 必須。

## 技術選定(更新)

- 言語: **Python で PoC**(純正ロジックをほぼ直訳でき最短で「書ければ勝ち」)→
  確定後に Rust/Go へ移植も可。
- **トランスポート = シリアル**: `pyserial`。`/dev/cu.usbmodem*` を開く(**`tty.*` 不可**, §接続)。
  9600/8N1, `JSON_START..JSON_END` 手順、各フレーム 5ms 間隔(`30` §5)。
- **検出**🟢: `pyserial` で `cu.usbmodem*` 列挙 → 各候補へ `[1,1]` 投げ **CRC有効な
  product_id 応答**で同定(R4=`CB04`、`*_DONGLE_*` は除外)。実機確認済み(`tools/cb_device.py`)。
  ⚠️ 実機 R4 は **HID も `0x05AC:0x0256`**(`0x3151` は出ない)→ HID/VID ベース検出は当てにせず
  **シリアル `[1,1]` プローブを正**とする(`30` §1a)。
- **フレーム生成**: 64B 固定 + **CRC-8(poly 0x07)**。暗号化なし(`tinyaes` 不要)。
  `TransJsonCmd` のロジックをそのまま移植。

## マイルストーン

1. **M0**: プロトコル解析 — **逆コンパイルは完了**(frame/CRC/送信順序/検出すべて取得済み、
   `30`)。残るは**実機キャプチャでの裏取り**のみ。
   - **エンコード部は実データ検証済み**(`_re/verify_encoding.py`)。merger 出力/ソースの
     LED フレームが過不足なく 64B フレーム列へ詰まることを確認(`90` 2026-06-21)。
2. **M1**: 既知正解(merger `outputs/*.json`)を CLI で**フル書き込み** — ✅✅ **完全達成**
   (`tools/cb_write.py`, 実機 R4, 3826 フレーム, `JSON_END` rev[2]==1。`90` 2026-06-22 続2)。
   - **LED 目視確認済み** 🟢: slot1 を緑ベタ塗りに書込→実機で緑表示を確認(no-op 曖昧性も排除)。
   - **キーマップは自動検証済み** 🟢: write→read([6,9])→diff **1400/1400 一致**(`90` 続3)。
   - **既知正解の妥当性は LED 部について確認済み**(M0 の検証)。`outputs/*.json` を
     write 対象にできる。`sources/*.json` は**旧スキーマ**(`tab_key` 系、`spotlight_frames`/
     `hatsu` 無し)なので、IR は 1.3.7 系(`tab_key_li`/`spotlight_frames`/`HATSU`)を
     基準にしつつ旧形は欠損をデフォルト補完で受ける(`10` IR データモデル参照)。
   - **`tools/cb_write.py`**: デフォルト dry-run(プラン表示のみ)/ `--execute` で実書き込み。
     送信順・chunking・総フレーム数は逆コンパイル原典から忠実移植(デコンパイルバグは
     `90` 続2 の通り修復)。
3. **M2**: `read` 読み戻し + `diff` 検証 — ✅ **キーマップ達成**(`tools/cb_read.py`:
   `[6,9]` で 7 レイヤ dump / `--compare CFG` で diff。実機 1400/1400 一致。`90` 続3)。
   - **LED の読み戻し経路は未発見** 🔴 → LED は「書込んだ IR を正」とするか目視。
     残課題: LED read 変種の探索([4,*]/[5,*] や別カテゴリ、`Central.py` の HID 経路)。
4. **M3**: 独自スキーマ → IR の `build`(keymap/LED 分離) — ✅ **keymap 達成**
   (`tools/cb_build.py`, `90` 続14)。
   - **keymap.toml v1 仕様 確定**(2026-06-22, 本書 §独自スキーマ案)。base IR への差分パッチ /
     位置(座標 `r{row}c{col}` + R4 別名)と値(可読名 + 生 `#MMPPUUUU` passthrough)の 2 名前空間 /
     1-indexed `[layer.1-7]` / 無損失=ラウンドトリップ検証可。
   - 内蔵テーブル: ②値 codec `tools/keycode.py`(可読名↔`#MMPPUUUU`)+ ①位置 `tools/keymap_alias.py`
     (`presets/r4-keymap-aliases.json` 81 別名 ↔ 座標)。最下段 row5 の物理対応のみ要押し試験 🔴。
   - **`cb_build.py`**: `-k keymap.toml [-b base] -o config.json`(build)/ `--dump config.json [--full]`
     (IR→toml)。純粋 file→file。**ラウンドトリップ実証**: 工場 dump(--full)を別 base 上で build →
     **key_layer 1400/1400 完全一致** + swap/macro/fn 再現(`build(dump(C)) == C`)。schema 検証 pass。
   - LED `led.toml` ソースからの合成は **M5 で達成**(`cb_ledtoml.py` compose、下記)。build は keymap 専任、
     LED は base 継承 or compose で合成、と責務分離(「keymap だけ変更」は build で成立)。
5. **M4**: 堅牢化(接続安定化)。部分書込は firmware 非対応(続8)のため不要 —
   分離管理は「read→merge→フル書込」で M3 build が吸収する。
6. **M5**: LED オーサリング — ✅ **GIF↔IR コーデック達成**(`tools/cb_led.py`, `90` 続16)。
   - **`cb_led.py`**: `gif2ir`(GIF→IR slot patch)/ `ir2gif`(IR slot→GIF 目視確認)/
     `recipe`(GIF Comment R/W)。純粋 file→file。display 200px(`index=y*40+x`)、slot 1/2/3=
     page 5/6/7。**ラウンドトリップ実証**: merged slot1 → ir2gif → gif2ir(別 base)→ **display
     13200/13200 px 一致** + keyframes 維持 + recipe 往復 + schema pass。256 cap(超過 drop 警告)、
     任意サイズ GIF は 40×5 ダウンサンプル、speed_ms は GIF duration 由来。
   - **宣言的レシピ生成 達成**(`tools/cb_anim.py`, `90` 続17): レシピ→40×5 アニメを決定論的に
     展開し cb_led 共有変換で IR/GIF 出力。`text_scroll`(手続き的、tom-thumb 5px フォント)+
     `solid`。`render`(→IR+GIF)/ `preview`(→GIF のみ)。**4 ノブ実証**: ①継ぎ目なしループ
     (`gap:0` seamless)/ ②長さ(`step`/`frames`)/ ③MAX256(警告+truncate)/ ④連結(`sequence`)。
     cb_led を `frames_to_page`/`frames_to_gif` にリファクタしコーデック一本化。例 `examples/led/`。
     模様 marquee(`hue_cycle`/`stripes`/`gradient_scroll`, `90` 続18)も追加。
   - **キャラ縦スクロール(sprite)達成**(`tools/cb_anim.py`, `90` 続25, #6 前半): 縦長スプライト画像を
     幅 40px 合わせ・高さ比例で 5px 窓を縦スクロール。`sprite`/`step`/`gap`/`direction`(`up`/`down`)/
     `bg`/`resample`。**継ぎ目は text_scroll と逆**(任意の絵は `gap>=5` が綺麗なループ)。256 cap は
     sprite 特化警告(絵の下端が切れる→step を上げよ)。**montage 目視で空間正しさ確定**(赤マーカー線が
     1px/frame 上昇/下降・gap=bg 黒帯)。例 `examples/led/sprite-scroll.json` + 自作 `sprite.png`。
   - **ターミナル再生 達成**(`cb_led play`, `90` 続22、issue #12): GIF/IR slot を半角上ブロック `▀` で
     truecolor 再生(fg=上px/bg=下px → 40×5 を 40 文字 × 3 行)。`--once`/`--loop`/`--fps`/`--scale`、
     非 TTY 静止縮退、Ctrl-C 復元。IR slot は pillow 不要。書込前確認・コミュニティ GIF プレビューが端末で完結。
   - **montage 達成**(`cb_anim montage` + `cb_led.frames_to_montage`, `90` 続26, #6 前半→後半の橋渡し):
     レシピ→縦長 PNG(時間=下方向)。GIF は Read 等で先頭フレームのみ→動き/ループ/継ぎ目の vision 判断用。
     `--max`(既定 24)等間隔サンプリング(先頭・末尾必ず含む・no silent drop)+ 末尾にオレンジ帯 +
     巻き戻りペア `[末尾,先頭]` 隣接でループ繋ぎ目を直接確認(`--no-seam`)。**後段 LED デザイン agent の
     目視土台**。sprite/text 両 montage を Read で目視確認(時間下方向・等間隔・seam 帯・1px ステップ)。
   - **per-key(keyframes)GIF は未対応** 🔴: web 抽出の物理配置はあるが(`experiments/perkey-layout/`
     83 LED + `render_tui.py`)、**web-index ↔ keyframes-90 の対応が未確定**(export 相関パス要)。
     display は 1:1 マップ既知なので今すぐ可、per-key だけがこのマップ待ち。
   - **LED デザイン vision ループ 達成**(`plugins/cyberboard/skills/cyberboard-led/SKILL.md`, `90` 続27,
     issue #6 後半): **おまかせデザイン** = エージェントが `anim montage` を Read して**falsifiable な
     ファミリー別基準で自己批評**(全: 巻き戻り 1px か段差か / text: 40px 可読性・グリフ 5px 内 / 模様:
     wrap=frame0・バンディング / sprite: 縮小で判別可・`gap>=5`・256 切れ)→改訂 2〜3 周→GIF+montage 提示→
     明示確認→書込。**全効果デザイナー**(text/模様/sprite 全部)。新規 CLI コードなし(既存 `anim`/`led`/
     `write` をオーケストレーション)。skill 367 行(400 制限内 = inline、超過なら `plugins/cyberboard/agents/`
     へ抽出)。sprite を効果カタログ + 「何を作る?」へ追加、**2b** で絵の用意(手持ち / AI 生成=Codex 可用時のみ
     40px 粗化明示 / PIL 手続き)を**毎回選ばせる**。dogfood 実証: `#330033` 暗紫が legibility 基準で落ち→
     `#cc44ff` で通過 = ループ収束(rubber-stamp せず)。
   - **`led.toml` 複数ソース合成 達成**(`tools/cb_ledtoml.py`, `90` 続28, issue #19): `cyberboard compose
     -m led.toml [-b base] -o config.json`。per-slot `sources` リスト(複数=combine / 1 個=replace /
     省略=keep)で miaomerge の action triplet を包含 + 異種ソース(recipe/gif/config)混在。`cb_led.
     frames_to_page` で 256 cap + frame_index 振り直し + keyframes 維持。256 cap は compose 層で per-source
     報告(silent cap 禁止)。`tmp/verify_compose.py` 26 アサート(roundtrip バイト一致ほか)pass。
     例 `examples/led/compose.toml`。
   - 🔴 残: **judge-panel 並列(v2)**(N パラメータ変種を montage→vision で選抜 → ultracode 並列。
     その時ループを `plugins/cyberboard/agents/` の forked subagent へ抽出)/ TUI エディタ。

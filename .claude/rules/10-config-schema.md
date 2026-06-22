# 純正設定 JSON のスキーマ(キーマップ + LED)

純正アプリ / [diy.angrymiao.com](https://diy.angrymiao.com/) ライブラリが扱う設定
JSON の構造。**1 ファイルにキーマップと LED 表示が同居している**(= ユーザーの不満の
根源)。出典: `angrymiao-cyberboard-config-merger/sources/*.json`(実測)。

## トップレベル構造

```jsonc
{
  "product_info": { "product_info_addr": "product_info_addr", "product_id": "CB_XX" },
  "page_num": 8,
  "page_data": [ /* 8 ページ。LED ディスプレイ設定 */ ],

  // --- ここから下がキーマップ設定(LED とは独立に扱いたい部分) ---
  "key_layer":   { "valid": 2, "layer_num": 7, "layer_data": [ /* 7層 */ ] },
  "Fn_key":      [ /* {Fn_key_index, input_key, out_key} */ ],      "Fn_key_num": 5,
  "MACRO_key":   [ /* {MACRO_key_index, input_key, out_key[], intvel_ms[]} */ ], "MACRO_key_num": 3,
  "swap_key":    [ /* {swap_key_index, input_key, out_key} */ ],    "swap_key_num": 4,
  "exchange_key":[ /* {exchange_index, input_key[], out_key[]} */ ],"exchange_num": 0,
  "tab_key":     [],  "tab_key_num": 0,
  "macro_key":   []   // 小文字。空。MACRO_key(大文字)とは別物
}
```

> サンプルの `product_id` は `"CB_XX"`(placeholder)。**実機 R4 の product_id は `CB04`**
> (`CommonDefine.G_KB_SERIES_DESCRIPTION_KV`: CB02=R2 … CB04=R4 … CB06=R6, HATSU=HATSU)。
> デバイスからは `cmd_product_id_send`([1,1])の応答で取得できる(→ `30` §7)。
>
> **コード上に存在する追加フィールド**(サンプル JSON には無いが他製品/将来用):
> 各ページの `spotlight_frames`(= car light / スポットライト灯, `CMD_CAR_*`)、
> トップレベル `hatsu`(HATSU 製品の page/line データ)。R4 での有無は要確認。

## キーマップ部

### キーコード表記 `#MMPPUUUU`(4バイト・8桁hex)🟡

例 `#00070029`, `#00070004`。実測での裏取り(`swap_key`):
`#00070004`(a) ↔ `#00070005`(b)、`#00070007`(d) ↔ `#00070008`(e)。

- **`PP` = HID Usage Page**。実データで出現 🟢(`90` 続10): `0x07`=Keyboard/Keypad /
  `0x0C`=Consumer(メディア。`0xB6`=Prev, `0xCD`=Play/Pause, `0xE9`=Vol+…) /
  `0x92`=**AM ベンダー独自機能**(公式 web JS の UI 表示ラベル表から解読 🟢 `90` 続11-12):
  `0x0Cxx`=レイヤー/Fn(`0C0F-0C15`=**Layer1-7 永続**、`0C20`/**`0C0B`**/`0C22-0C26`=**Fn1-7 momentary**
  ※Fn2 だけ変則 `0C0B`、`0C0D/0C0E/0C1A-0C1F`=LFn/RFn 系)、`0x01xx`=ディスプレイ LED(on-off/明るさ±/
  速度±/次/回転/BT1-3/2.4G)、`0x09xx`=PCB(per-key 灯)モード+NP ゾーン、`0x0Axx`=Reset/Battery。
  詳細表は `experiments/keymap-matrix/`(生表 `_re/keycode_labels.json` ローカル)。
  ⚠ Esc + 下段特定キーの**電源 ON コンボ**等、firmware ハードワイヤの**移動不可キーはブラックボックス扱い**
  (詳細解明せず)。CLI は 0x92 を**解釈せず passthrough**(保存・送信のみ)。
- **`UUUU` = HID Usage ID**。`0x04`='a', `0x05`='b', `0x29`=Esc, `0x13`='p' …(USB HID
  仕様の標準キーコード)。
- **`MM` = 修飾キー bitmask(推定)**。通常キーは `00`。Shift/Ctrl 等の同時押しが
  ここに乗ると見られる(要確認)。
- **`#00000000` = 未割り当て / 空**。

### `key_layer` — レイヤ別リマップ行列

```jsonc
{
  "valid": 2,
  "layer_num": 7,                 // 7 レイヤ(Fn レイヤ含む)
  "//": "键层设置，按键矩阵大小预留为25*8…",  // キー行列は 25×8 = 200 で固定確保
  "layer_data": [
    { "layer": [ "#00070029", "#0007003A", /* … 計 200 要素 */ ] },
    /* layer 1..6 */
  ]
}
```

- `layer[i]` = 物理マトリクス位置 i(25×8=200)に割り当てる HID キーコード。
- **R4 の物理配列マップ確定** 🟢(`90` 続10, `experiments/keymap-matrix/`): **`index = row*25 + col`**
  (各行が 25 ごとに始まる)。物理キー **81 個**は **row 0-5 / col 0-14** に分布、row 6-7 と
  右端の余剰列は未使用。右端列(col14)= Del/Home/End/PgUp/PgDn のナビ列。**layer 0 をデコード
  すると物理レイアウトそのもの**(押し試験不要でマップ導出可)。`decode_keymap.py` で可視化。
- レイヤ: **7 つ対等**(配列 index 0-6 = 公式 layer1-7、**デフォルト layer1=index0**)。レイヤー遷移は
  キーコードで:**fnN=momentary / layerN=永続**(`0x0Cxx`、下記)。「layer1 が Fn 専用」ではない。

### その他のキー機能(input → out)

| フィールド | 形 | 意味 |
|---|---|---|
| `Fn_key` | `{Fn_key_index, input_key:str, out_key:str}` | Fn 同時押しでの差し替え |
| `swap_key` | `{swap_key_index, input_key:str, out_key:str}` | キー入れ替え |
| `exchange_key` | `{exchange_index, input_key:[str], out_key:[str]}` | 交換(配列・複数) |
| `MACRO_key` | `{MACRO_key_index, input_key:str, out_key:[str], intvel_ms:[int]}` | マクロ(キー列 + 各間隔ms) |
| `tab_key` | (サンプル空) | 不明 |

> `Fn_key` / `swap_key` / `exchange_key` の機能差は要確認。プロトコル側は
> `CMD_FN_KEY` / `CMD_SWAP_KEY` / `CMD_EXCHANGE_KEY` / `CMD_TAB_KEY` / `CMD_MACRO_KEY`
> と 1:1 対応(→ `30-write-protocol.md`)。

## LED ディスプレイ部 `page_data`(8 ページ)

ページ構成(`"//"` の中国語コメント実測):

| index | `"//"` | 役割 | サンプル valid |
|---|---|---|---|
| 0 | 电池界面 | バッテリー | 1 |
| 1 | 马赛克界面 | モザイク | 1 |
| 2 | 时间界面 | 時刻 | 1 |
| 3 | 文字界面 | テキスト | 0 |
| 4 | 流光界面 | 流光(ストリーマ) | 0 |
| 5 | 自定义界面1 | **Custom LED 1 = スロット1** | true |
| 6 | 自定义界面2 | **Custom LED 2 = スロット2** | true |
| 7 | 自定义界面3 | **Custom LED 3 = スロット3** | true |

> ユーザーの言う「LED ディスプレイ設定のスロット 1/2/3」= **page 5/6/7(Custom LED 1-3)**。
> (merger の CLAUDE.md は page4 を「动画界面」と記すが、実ファイルは「流光界面」。実値優先。)

### 各ページの構造

```jsonc
{
  "//": "自定义界面1",
  "valid": true,            // ページ有効(0/1 または true/false が混在)
  "page_index": 5,
  "lightness": 100,         // 明るさ 0-100
  "speed_ms": 100,          // アニメ速度(ms/フレーム)
  "color": { "default": false, "back_rgb": "#000000", "rgb": "#000000" },
  "word_page": { "valid": 0, "word_len": 0, "unicode": [ /* 文字コード */ ] },
  "frames":    { "valid": 1, "frame_num": 3,   "frame_data": [ /* 確定フレーム */ ] },
  "keyframes": { "valid": 1, "frame_num": 123, "frame_data": [ /* キーフレーム */ ] }
}
```

### `frames` と `keyframes`(重要・一部未解明)

- `frame_data[]` の各要素 = `{ frame_index:int, frame_RGB:[str] }`。
- `frame_RGB` の色 = `"#RRGGBB"`(6桁hex → 3バイト)。
- **`frames` = 上部 LED ディスプレイ(40×5=200px)** 🟢。`frame_RGB` 200要素=600B。
  プロトコルでは `CMD_RGB_FRAME [4,page_index]` で 1フレームを 11 USBチャンク
  (56B×10+40B)送信(`JsonToCmd`/`TransJsonCmd` で確認)。
- **`keyframes` = 各キーのバックライト(90キー)** 🟢。`frame_RGB` 90要素=270B。
  プロトコルでは `CMD_KEY_FRAME [5,page_index]` で 5 USBチャンク(56B×4+46B)送信。
  → サンプルで keyframes が 90 要素だった理由はこれ(=キー数 90)。**「補間」ではない**。
- **実データ検証済み 🟢**(`_re/verify_encoding.py`, `90` 2026-06-21):merger の
  `outputs/merged_*.json` ほか複数で、能動ページ(5/6/7)の display は例外なく 200px、
  per-key は 90px。宣言 `frame_num` と実フレーム数も完全一致。
- **非能動ページ(0-4)の `frames`/`keyframes` は `frame_num=0` で `frame_RGB` 長1の
  プレースホルダ**(静的単色)。書き込み時は能動ページのみ送出すればよい。
- `valid` は `0/1/2` を取りうる。書き込み前に `change_dict` が `0→False / 非0→True`
  へ正規化(`KBSerialOption.change_dict`)。意味の詳細(1 と 2 の差)は要確認。
- フレーム数の事前申告は `CMD_UNCERTAINTY [2,1]`(page_index, word_num, frame_num,
  key_frame_num)で送る(→ `30-write-protocol.md`)。

### マトリクス寸法

- LED ディスプレイ = **40×5 = 200 画素**(merger: `LED_WIDTH=40, LED_HEIGHT=5`)。
- **フレーム数上限 = 256(2^8)** 🟢(実機確定 2026-06-22, `90` 続5)。各 display フレームに
  index を**数字描画**して目視: N=400 を書くと **ACK は通るが再生は 0–255 でループ=256 枚で頭打ち**。
  → **firmware の再生 index/カーソルが 8 ビット**。ACK 経路は 16 ビット(`frame_num`・display
  `frame_index` とも 2B 送出)だが内部 uint8 で切る = **ACK ≠ 実格納**の実例。
  - **merger `MAX_FRAMES=300` も AM Master の "~300" も不正確**(真値 256 を捉えぬ過大マージン)。
    AM Master の「300 超で書けない」は自前 UI ガード。我々のツールは迂回送信できるが firmware が 256 で切る。
    **公式 UI 作成の 300 枚設定でも 256 で頭打ち**(`90` 続6、256〜299 赤マーカーが出ず)。
  - **per-slot 確定** 🟢(`90` 続5): 2 スロット×各 200 枚=合計 400 でも両方フル再生 →
    256 は各スロット独立。3 スロット合計 256×3=768 枚使える。
  - 未確定🔴: 「未格納」か「再生カーソルのみ 8bit ラップ」か(LED read 経路が無く外部から区別不可。
    実用上はどちらも「使えるのは 256 枚」)。
  - **ライティング(= per-key `keyframes`)は別系統・別上限** 🟡(`90` 続7): 純正 UI は
    1 アニメ **100 フレーム**まで(display の 300 とは別)。ただし **100 は UI 作成上限で
    firmware 上限ではない** — 既知正解は page7 keyframes=123 で ACK 成功(merger combine で超過)。
    per-key `frame_index` は **1B 送出**=構造上限 256。真の再生上限は未検証🔴(90 キーしか無く
    数字描画で数えられない)。**schema は 100 を enforce せず 256 維持**(123 の既知正解を弾かぬため)。
  - **スキーマ enforcement** 🟢(`90` 続6): `schemas/cyberboard-config.schema.json` の
    `frame_num`=`maximum:256` / `frame_data`=`maxItems:256`。`cb_verify` が 256 超を書込前に弾く。

## IR データモデル(`CyberBoardJson.py`)🟢

純正のデータクラス階層(`_re/decompiled/CyberBoardJson.py`)。CLI の IR 層はこれと
**同じ JSON キー**を出力すればよい。`cyber_board_json_from_dict` が入口。

```text
CyberBoardJson
├─ page_num: int
├─ page_data: [PageDatum]
│    ├─ valid, page_index, lightness, speed_ms
│    ├─ color: Color { default, back_rgb, rgb }
│    ├─ word_page: WordPage { valid, word_len, unicode[] }
│    ├─ frames: { valid, frame_num, frame_data:[{frame_index, frame_rgb[]}] }      ← 200px表示
│    ├─ keyframes: { valid, frame_num, frame_data:[{frame_index, frame_rgb[]}] }   ← 各キー灯90
│    └─ spotlight_frames: { valid, frame_num, frame_data:[{frame_index, frame_light[]}] } ← 任意
├─ exchange_key: [ExchangeKey { exchange_index, input_key[], out_key[] }]
├─ tab_key_li: [TabKeyLi]
├─ Fn_key_num / Fn_key: [FnKey { Fn_key_index, input_key, out_key }]
├─ swap_key_num / swap_key: [SwapKey { swap_key_index, input_key, out_key }]
├─ key_layer: KeyLayer { valid, layer_num, layer_data:[{ layer[] }] }
└─ HATSU: Hatsu { page_num, page_data[], line_data[] }  ← HATSU製品のみ
```

> JSON キーの大小に注意: `Fn_key` / `MACRO_key` / `HATSU`(大文字)、`swap_key` /
> `exchange_key` / `key_layer` / `tab_key_li`(小文字)。`MACROKey` クラスは存在するが
> R系列の送信順には現れない(→ `30` §5 注記)。

## 関連

- このスキーマを**キーマップ / LED で分離**して個別管理するのが自作 CLI の狙い →
  `40-cli-spec.md`。
- 各フィールドがどのコマンドで書かれるか → `30-write-protocol.md`。

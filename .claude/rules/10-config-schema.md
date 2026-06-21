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

- **`PP` = HID Usage Page**。`07` = Keyboard/Keypad。
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
- 製品ごとに「カスタム行列データの位置」が異なる(コメント記載)→ R4 の物理配列との
  対応マップが別途必要(要確認)。

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
- 最大フレーム数 = **300**(merger: `MAX_FRAMES=300`)。

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

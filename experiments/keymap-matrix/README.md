# キーマップ解明: フォーマット / レイヤ / matrix マップ

CyberBoard R4 のキーマップ(`key_layer`)の構造を実データから確定した記録。
CLI の `keymap.toml`(人間可読名 ↔ HID コード ↔ 物理位置)の土台になる。

## (A) キーコード・フォーマット `#MMPPUUUU`(4 バイト)

| フィールド | 桁 | 意味 |
|---|---|---|
| `MM` | `[1:3]` | 修飾キー bitmask(通常キーは `00`) |
| `PP` | `[3:5]` | **HID usage page** |
| `UUUU` | `[5:9]` | **HID usage id** |

- `#00000000` = 未割り当て。
- **usage page の種類**(実データで出現):
  - `0x07` = Keyboard/Keypad(標準キー。`0x04`=A … `0x29`=Esc …)
  - `0x0C` = Consumer(メディア。`0xB6`=Prev, `0xCD`=Play/Pause, `0xE9`=Vol+ …)
  - `0x92` = **AM ベンダー独自 Fn**(後述。名前は JS UI 側にあり Python には無い)

## (B) レイヤ構造 = 7 レイヤ(公式 UI と一致)

- `key_layer.layer_num = 7`、各レイヤ `layer[200]`(25×8)。
- **layer 0 = ベース**(標準キー + メディアの上段)。
- **layer 1 = Fn レイヤ**(上段が `0x92` の AM 独自機能に化ける)。
- **layer 2-6 = 追加レイヤ**(公式 UI で 7 まで編集可。サンプルでは未カスタムの複製)。

## (C) matrix マップ 🟢 — `index = row * 25 + col`

各行が **25 ごと**に始まる(`0,25,50,75,100,125…`)= **25 列 × 8 行 = 200**。
物理キー(81 個)は **row 0-5 / col 0-14** に分布、row 6-7 は未使用。
**layer 0 をデコードすると物理レイアウトそのもの**(押し試験不要でマップ確定)。

```text
row0 (idx   0-14):  Esc  F1 F2 F3 F4 F5 F6  Prv Ply Nxt Mut Vl- Vl+  Del  Home
row1 (idx  25-39):   `   1 2 3 4 5 6 7 8 9 0  -  =  \           End
row2 (idx  50-64):  Tab  Q W E R T Y U I O P  [  ]  Bsp         PgUp
row3 (idx  75-89):  LCt  A S D F G H J K L ;  '  .  Ent         PgDn
row4 (idx 100-114): LSh  _ Z X C V B N M , . /  RSh  Up
row5 (idx 125-139): Fn   LAl LGu _ _ _ Spc _ _ _ RGu RAl  Lft Dwn Rgt
```

- **右端列(col 14)= ナビ列**: Home/End/PgUp/PgDn(idx 14/39/64/89)。
- 空欄 = その matrix セルが未使用(ワイドキー Space=idx131 は 1 セル / ISO 余剰位置等)。
- 上記は**標準レイアウトのデコード結果**(個体のカスタム次第で内容は変わるが、**位置=物理マップ
  は不変**)。`row5 col0` が Fn、`row3 col0` が LCtrl 等はこのサンプルの割り当て。

## (D) 設定できるキー機能の種類(`CyberBoardJson` クラス + builder)

| 種類 | JSON | 送信 | 内容 |
|---|---|---|---|
| **key_layer** | `key_layer` | `[6,8]`+`[6,7]` | レイヤ別リマップ行列(7×200)。本体 |
| **Fn_key** | `Fn_key` | `[6,4]`※ | Fn 同時押しでの差し替え |
| **swap_key** | `swap_key` | `[6,6]` | キー入れ替え(input↔out) |
| **exchange_key** | `exchange_key` | `[6,1]` | 交換(配列 in/out) |
| **MACRO_key** | `MACRO_key` | `[6,5]`※ | マクロ(キー列 + 各間隔 ms) |
| **tab_key** | `tab_key` | — | 用途不明 🔴 |
| **press_hold** | — | `[6,13]`+`[6,11]` | 長押し(タップ/ホールドで別動作) |
| **change_key** | — | `[6,11]` | 単キー変更(ライブ編集) |

※ Fn_key/MACRO_key は R 系列の標準送信順には**現れない**(`30` §5 注記)。R 系列では
リマップは `key_layer`(7 レイヤ)+ swap/exchange で表現される模様。

## 未解明 🔴

- **AM 独自 Fn(0x92)の各コードの意味**(0x100-0x108, 0x130, 0x900-0x903, 0xa01, 0x0b…)。
  Python バックエンドに無く、**QtWebEngine の JS UI 側**で定義 → app の web 資産から要抽出。
- `tab_key` / press_hold / change_key の正確なフィールド書式と UI 上の機能名。

## 再現

```bash
python experiments/keymap-matrix/decode_keymap.py <config>.json
python experiments/keymap-matrix/decode_keymap.py <config>.json --layer 1
# デバイスから読んで解析する場合:
uv run --with pyserial python tools/cb_read.py keymap --json > /tmp/dump.json
python experiments/keymap-matrix/decode_keymap.py /tmp/dump.json
```

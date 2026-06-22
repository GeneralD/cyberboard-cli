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

- `key_layer.layer_num = 7`、各レイヤ `layer[200]`(25×8)。**7 つは対等**で、配列 index 0-6 =
  公式 UI の **layer1-7**(1-indexed)。**デフォルトは layer1(= 配列 index 0)**。
- レイヤー遷移は**キーコードで行う**(任意のキーに置ける。下記 (E) の 0x0Cxx):
  **`fnN` = 押している間だけ(momentary)/ `layerN` = 永続(toggle)**。
- ※ 「layer 1 が Fn 専用レイヤ」ではない。サンプルで配列 index 1 の上段に AM 機能が並ぶのは
  その config の作り(= layer2 をそう設定しただけ)。layer は全部自由にリマップ可能。

## (C) matrix マップ — `index = row * 25 + col`

各行が **25 ごと**に始まる(`0,25,50,75,100,125…`)= **25 列 × 8 行 = 200**🟢。
物理キー(81 個)は **row 0-5 / col 0-14** に分布、row 6-7 は未使用。
**英字段(row1-4)は matrix 列順=物理位置 が一致**(layer 0 が QWERTY 順に綺麗に読める)🟢。

> ⚠ **最下段(row5)は列順=物理位置 が未確定** 🟡。ユーザー観察では下段の物理「左から五番目」が
> matrix の `idx125`(=私が col0 と置いたキー)に当たるらしく、**下段は matrix 列と物理位置がズレる**。
> ワイドキー(Space)や特別キーの都合と思われる。下段の正確な物理対応は**押し試験で要確定**(未実施)。
> 英字ブロックの「デコード=物理レイアウト」は成立するが、**下段については過信しない**。

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
- 上記は**標準レイアウトのデコード結果**(個体のカスタム次第で内容は変わる)。英字段の index↔物理は
  不変だが、**下段(row5)の物理位置は上記の見た目通りとは限らない**((C) の留保参照)。
  `row5 col0` の中身(サンプルでは Fn2)、`row3 col0` が LCtrl 等は割り当て例。

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

## (E) AM 独自機能 page 0x92 = 解読済み 🟢

公式 UI 本体は **<https://diy.angrymiao.com/keyboard/>**(Vue SPA、QtWebEngine がリモート
ロード。app はインポート + 書込専用、web はエクスポート専用、編集は両方可)。その `app.js` の
**UI 表示ラベル表(`"#code":{text,desc}`、187 エントリ)**が権威ソース(生表は `_re/keycode_labels.json`
= gitignore 下)。⚠ 別に内部定数表(`r1/r2`、レガシー名 `KEY_FN`/`KEY_LEDSWITCH` 等)もあるが、
**表示名とは別物**。`#00920C0B` は内部名 `KEY_FN` だが **UI 表示は `Fn2`**(下記が正)。

**レイヤー/Fn 機構**(UUUU=0x0Cxx):

| UI ラベル | keycode | 動作 |
|---|---|---|
| Layer1〜Layer7 | `0C0F`〜`0C15` | **永続**切替 |
| Fn1〜Fn7 | `0C20` / **`0C0B`** / `0C22` / `0C23` / `0C24` / `0C25` / `0C26` | **momentary**(押下中のみ)。**Fn2 だけ変則 `0C0B`** |
| LFn / RFn 系 | `0C0D`(LFnS)/`0C0E`(RFn)/`0C21`(RFn3)/`0C1A-0C1F`(LFn1,3-7) | 左/右別の Fn 系統 |

**機能キー**(UI ラベル):

| 系統 | 例(keycode=ラベル) |
|---|---|
| ディスプレイ LED(上部40×5) | `0100`Next LED / `0101`On-Off / `0102-0103`Light± / `0104-0105`Speed± / `0140`Rotation / `0106-0108`BT_1-3 / `0130`2_4G |
| PCB(per-key 灯=ライティング) | `0900`Next PCB / `0901-0902`Light± / `0903`On-Off / `0904-0905`Speed± / `0920`SAT / `0921`Light / `091F`Color |
| NP(灯ゾーン・詳細不明) | `090B-090C`Light± / `090D`On-Off / `090E`Color / `090F`Next NP |
| その他 | `0922`Win/Mac / `0910`・`0A04`Battery / `0A02`Reset / `1300`Touch Sen |

> **firmware 特別キーはブラックボックス扱い**(本プロジェクト方針): Esc(idx0)+ 下段の特定キーが
> **電源 ON コンボ**になっており、これら「移動不可(リマップ不可)」キーは firmware にハードワイヤ
> された役割を持つ(電源 OFF 時はキーマップ自体が無効)。内部名 `KEY_FN` 等はこの firmware 内部表現。
> **その詳細仕様は解明しない**。CLI は **0x92 コードを解釈せずそのまま保存・送信(passthrough)** し、
> `keymap.toml` では独自可読名(例 `Fn2`/`Layer3`/`BT1`/`LedLight+`)へ機械的にマップするのみ。
> ラベルは USB HID 標準外の AM 独自 page(0x92)で、公式 web JS から逆引きした相互運用情報
> (生の app ソースはコミットせず `_re/` ローカルのみ)。

## 未解明 🔴

- `tab_key` / press_hold / change_key の正確なフィールド書式と UI 上の機能名。
- MM(修飾 bitmask)の具体ビット割当。

## 再現

```bash
python experiments/keymap-matrix/decode_keymap.py <config>.json
python experiments/keymap-matrix/decode_keymap.py <config>.json --layer 1
# デバイスから読んで解析する場合:
uv run --with pyserial python tools/cb_read.py keymap --json > /tmp/dump.json
python experiments/keymap-matrix/decode_keymap.py /tmp/dump.json
```

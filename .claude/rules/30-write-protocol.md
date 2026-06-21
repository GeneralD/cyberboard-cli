# 書き込みプロトコル(USB CDC シリアル / 64Bフレーム / CRC-8)— 本丸

> **確度**: 🟢 逆コンパイル済みソースで確認 / 🟡 強い推定 / 🔴 実機キャプチャ要
> 出典: `_re/decompiled/`, `_re/dc3/`(AM_Master 1.3.7 を pyinstxtractor +
> pycdc / decompyle3 で逆コンパイルした原典)。バイト構造・送信順序は 🟢。
> 「実機が我々の生成バイトを受理するか」だけが未検証(実機テストで確定)。

## 0. 最重要結論

1. **トランスポートは USB CDC シリアル(pyserial)**。HID ではない。
   HID は**デバイス検出専用**。設定は **9600 baud のシリアルポート**に 64B フレームを流す。
2. **設定書き込み経路に暗号化は一切無い**(AES は PyInstaller の難読化のみ)。
   → アドバイザー最重要懸念は解消。**実装難易度は低い**。
3. **接続不安定の原因が特定できた**(§6)。CLI 側で確実に潰せる。

## 1. デバイス識別

### 1a. HID(検出専用 / `hid.enumerate`)

| 役割 | VID | PID |
|---|---|---|
| キーボード(key) | `0x3151`(12625) | `0x4015`(16405) |
| マウス | `0x3151` | `0x402A`(16426) |
| ドングル(無線) | `0x3151` | `0x5007`(20487) |
| AM35(MediaTek系) | `0x0E8D`(3725) | `0x0880`(2176) |
| AM35 ドングル | `0x0E8D` | `0x0703`(1795) |
| オーディオ/TWS(別製品) | `0x0E8D` | `0x0101`, usage_page `0xFFA0`, usage `1` |

`hid.enumerate(VID,PID)` の戻りが空か否かで接続状態(`*_CON` フラグ)を判定するだけ。

### 1b. シリアル(設定転送の実体 / `serial.tools.list_ports`)

macOS では **`vid==0x05AC`(1452, Apple)かつ `pid in {0x024F(591), 0x0256(598)}`** の
COM を候補にする(`_get_serial_port_set` / `check_ports`)。
→ この狭い vid/pid 固定マッチが**不安定の主因の一つ**(§6)。

### 1c. ファーム更新(別系統)

- キーボード本体: **Nordic nRF**(DFU)。`vid==0x1915`(6421), `pid==0x521F`(21023),
  description に "DFU", manufacturer "Nordic Semiconductor"。nrfutil(`nordicsemi.dfu`)。
- MediaTek 系: `Comm.py` のシリアル IAP(VID `0x0E8D`, CRC-16/X-25)。`AM_TOOL/MTK_*`。
- **いずれも設定書き込みとは無関係**。

## 2. フレーム形式(64バイト固定)🟢

すべてのコマンドは `bytearray(64)`:

```text
byte[0]   = カテゴリ(コマンド群)
byte[1]   = サブコマンド(※ category 4/5/8/9 では page_index/line_index)
byte[2..62] = ペイロード(コマンドごとに定義)
byte[63]  = CRC-8(先頭 63 バイト [0:63] に対して)
```

- **CRC-8 = PyPI `crc8` パッケージのデフォルト**(多項式 `0x07`, init `0x00`,
  反転なし, xorout `0x00` = CRC-8/SMBUS 系)🟢。
  `c=crc8.crc8(); c.update(cmd[0:63]); cmd[63]=c.get()`。
- 数値は**コマンドごとにエンディアンが違う**(下記)。`int_to_bytes` は big-endian 2B
  だが、多くの箇所で `[1],[0]` の順に詰めて**リトルエンディアン化**している。要注意。
- **キーコード `#MMPPUUUU` は 4 バイト**(`key_to_bytes`/`rgba_to_bytes` = `bytes.fromhex(s[1:9])`)。
- 色 `#RRGGBB` は 3 バイト(`rgb_to_bytes` = `fromhex(s[1:7])`)。

> **CMDType enum(0〜25)とワイヤ値は別物**。enum はログ/`CMD_DESCRIBE`/進捗用。
> 実際にデバイスへ送るのは下表の `[category, subcommand]`。混同しないこと。

## 3. コマンド表(ワイヤの byte0/byte1)🟢

### カテゴリ 1 — 制御/製品

| byte0,1 | 関数 | 内容 |
|---|---|---|
| `1,1` | cmd_product_id_send | product_id 問い合わせ |
| `1,2` | cmd_product_info_send | バージョン問い合わせ |
| `1,3` | cmd_set_time_send | 時刻設定([2:6]=epoch BE, [6]=tz符号, [7]=tz時) |
| `1,4` | cmd_update_send | ファーム更新モードへ |
| `1,5` | **cmd_json_start_send** | **転送開始** |
| `1,6` | **cmd_json_end_send** | **転送終了**([2:6]=総フレーム数 BE) |
| `1,7` | cmd_dongle_update_send | ドングル更新 |

### カテゴリ 2 — ページ/メタ

| byte0,1 | 関数 | 内容 |
|---|---|---|
| `2,1` | cmd_uncertainty_info_send | **フレーム数マニフェスト**([2]=page_num, 各6B: page_index, word_num, frame_num(LE 2B), key_frame_num(LE 2B)) |
| `2,2` | cmd_page_control_send | ページ表示設定(valid/page_index/lightness/speed_ms(LE)/color.default/back_rgb/rgb) |
| `2,3` | cmd_hatsu_*_uncertainty | HATSU 専用 |
| `2,4` | cmd_hatsu_*_control | HATSU 専用 |
| `2,5` | send_useful_directives | valid 一括([2]=page, [3:]=pages) |
| `2,6` | cmd_check_pages | **ページ数問い合わせ**(応答 [2]=pages_num) |

### カテゴリ 3 — テキスト

| `3,1` | cmd_word_page_info_send | 文字ページ([2]=frame_index,[3]=page_index,[4]=valid,[5]=word_len,[6:]=unicode 2B×) |

### カテゴリ 4 — LED ディスプレイ(40×5=200px)

| `4, page_index` | cmd_rgb_frame_info_send | [2:4]=frame_index(LE), [4]=usb_chunk_idx, [5:61]=RGB 56B。1フレーム=600B を **11チャンク**(56×10+40) |

### カテゴリ 5 — 各キーバックライト(90キー)

| `5, page_index` | cmd_key_frame_send | [2]=frame_index, [3]=usb_chunk_idx, [4:60]=RGB 56B。1フレーム=270B を **5チャンク**(56×4+46) |

### カテゴリ 6 — キー機能

| byte0,1 | 関数 | 内容 |
|---|---|---|
| `6,1` | cmd_exchange_key_send | [2]=exchange_num,[3]=index,[4:]=input_key 4B×, [24:]=out_key 4B× |
| `6,4` | cmd_fn_key_send | Fn キー(※ R系列の送信順には**含まれない**。§5 注記) |
| `6,5` | cmd_macro_key_send | マクロ(※ R系列順には無い。HATSU のみ) |
| `6,6` | cmd_swap_key_cmd | swap(各9B: index, input 4B, out 4B) |
| `6,7` | cmd_key_layer_info_send | **キーマップ本体**([2]=usb_chunk_idx, [3:]=layer bytes 60B/チャンク) |
| `6,8` | cmd_key_layer_control_info_send | [2]=layer_num |
| `6,9` | cmd_get_key_msg | 読み出し |
| `6,10` | cmd_get_key_macro | 読み出し |
| `6,11` | cmd_j_change_key | 単キー変更([2]layer,[3]row,[4]index,[5:9]old,[9:13]new) |
| `6,13` | cmd_press_hold | 長押しキー |
| `6,14` | cmd_get_anykey | 読み出し |
| `6,15` | cmd_get_flash | 読み出し(フラッシュ) |
| `6,17` | cmd_reset | リセット |

### カテゴリ 8/9/10/11/12

- `8,page_index` hatsu_page_frame / `9,line_index` hatsu_line_frame(HATSU 専用)
- `10,1` ドングル([2]=1 change_info / 2 dongle_confirm / 3 key_confirm, [3:12]=mac)
- `11,1` cmd_change_dongle_color([2]mode,[3]speed,[4:7]rgb,[7]onoff)
- `12,1` car_light_info / `12,2` car_light_data(spotlight。R4 に有無は要確認)

## 4. キーマップのバイト化(`key_layer`)🟢

- `layer_data[*].layer[*]`(各 `#MMPPUUUU` = 4B)を**全レイヤ連結** → **60B チャンク**で
  `[6,7]` 送信([2]=チャンク番号)。送信前に `[6,8]` で layer_num を通知。
- 1レイヤ = 200キー × 4B = 800B、7レイヤ = 5600B → 60B 単位で約 94 チャンク。
  (docstring の "25*8*3*4/15" 等は別製品/別表現。実装は上記 60B 刻み)

## 5. 送信シーケンス(R系列 = CyberBoard R2〜R6)🟢

`json_down()`:

```text
serial.Serial(com_json, baudrate=9600, timeout=10, write_timeout=1)
└ send_start()          → cmd_json_start_send [1,5] → 応答 read(64), rev[2]==1 で成功
└ if product_id=="HATSU": send_hatsu_all()
  else:                   send_r_series_all():
        1. send_uncertainty_info        [2,1]   フレーム数マニフェスト
        2. send_page_info               [2,2]   ページ表示設定(ceil(page_num/4)枚)
        3. send_word_page_info          [3,1]
        4. send_rgb_frame_info          [4,pi]  LEDディスプレイ(ページ×フレーム×11)
        5. send_key_frame_info          [5,pi]  各キー灯(ページ×フレーム×5)
        6. send_exchange_key            [6,1]
        7. send_swap_key                [6,6]
        8. send_key_layer_control_info  [6,8]
        9. send_key_layer_info          [6,7]   キーマップ(60Bチャンク)
       10. send_ph_key (任意, try)      [6,13]+[6,11]
       11. send_car_light_info/data(任意)[12,1]/[12,2]
└ send_end(send_cmd_count) → cmd_json_end_send [1,6] (総フレーム数) → rev[2]==1 成功
                             rev[2]==2 なら応答待ちループ(1秒間隔)
```

- 各フレーム送出 = `send_cmd`: **`time.sleep(com_write_delay=0.005)` → `serial.write(cmd)`**。
  バルクのデータフレームは**応答を読まず**5ms間隔で投げっぱなし。整合性は最後の
  `JSON_END` の**総フレーム数照合**で検証(数が合わないと `rev[2]!=1`)。
- `send_start`/`send_end`/各種 `get_*` だけが `read(64)` で応答を読む。
- **注記**: R系列の順序に `cmd_fn_key_send`/`cmd_macro_key_send` が**無い**。Fn/マクロが
  `key_layer`/`exchange` 経由で表現されるのか、この版で未送出なのかは要確認 🔴。

## 6. 接続の不安定さ — 根本原因(特定済み)と対策

純正アプリが「繋がる/繋がらない」のムラを出す原因(`KBSerialOption`):

1. **狭い vid/pid 固定マッチ**: シリアル候補を `vid==0x05AC && pid∈{0x024F,0x0256}` だけで
   絞る。OS/ファーム差でこの値がずれると**ポートを見つけられない**。
2. **`_get_serial_port_set` の壊れた制御フロー**(逆コンパイル上、`if pid==598: pass` の
   ネスト崩れ)→ ポート集合の取りこぼし・ホットプラグ検出の誤動作。
3. **`com_status` レース**: 転送中(`com_status!=0`)は `get_key_name` が即 return →
   検出スキップ。タイミング次第で見つからない。
4. **リトライ設計**: `get_com_info` は SerialException で `sleep(5)`×最大5回 → 失敗時に
   遅く、5回で諦める。
5. **macOS の `/dev/tty.*` ブロッキング疑い** 🟡: `tty.usbmodem*` を開くと DCD 待ちで
   ブロックしうる。`cu.usbmodem*` を使うべき。これが「接続できない」体感の有力因。
6. **ポート取り違え**: ドングル(`CB_DONGLE_1`/`AM_DONGLE_1`)を掴むと `check_dongle` が
   `com_json=None` にする。複数 AM デバイス併用時に誤選択。

### CLI 側の堅牢化方針 🟢(設計)

- **`/dev/cu.usbmodem*` を列挙**(tty は使わない)。vid/pid に依存せず、各候補へ
  `cmd_product_id_send()`([1,1])を投げ、**応答の product_id で本物を同定**(R4 = `CB04`)。
- ドングル product_id(`*_DONGLE_*`)は除外 or 別経路。
- 9600/8N1、適切な open timeout、**指数バックオフ + 明示リトライ**、確実な close、
  排他オープン。
- 送出は 5ms 間隔を踏襲(詰めすぎると下位機が取りこぼす可能性)。
- **各段で読み戻し検証**(`cmd_check_pages`/`cmd_get_*`)。

## 7. 応答(リプライ)フォーマット 🟢/🟡

- 応答も 64B。`read(64)`。`rev[2]` が結果コード(`1`=成功, `2`=待機して再読、等)。
- `cmd_product_id_send` 応答: `[2]`=長さ, `[3:3+len]`=product_id(ascii。例 `CB04`,
  `CB_DONGLE_1`)。
- `cmd_product_info_send` 応答: `[3:5+len]`=バージョン文字列(utf-8, `\x00` 除去)。
- `cmd_check_pages` 応答: `[2]`=pages_num(0 か 3)。
- 応答にも CRC-8 が載っているはず(要確認 🔴)。

## 8. 残課題(実機確定が必要)

1. **実機 USB/HID(シリアル)キャプチャ**で §3〜5 を裏取り(macOS: `cu` を `screen`/
   `pyserial` で観測、or `IORegistry`/`ioreg`、Wireshark+USBPcap は Win)。
2. Fn/マクロの扱い(§5 注記)。
3. R4 実機の **product_id 実値**(`CB04`?)、pages_num(3?)、シリアル vid/pid 実値。
4. spotlight(car_light)が R4 に存在するか。
5. 応答コードの全集合。
6. 物理キー位置 ↔ `layer[0..199]`(25×8)対応マップ。

# 調査ログ(append-only)

新しい発見は**上に**追記。確定したら該当 rule(`10`〜`40`)へ反映する。

---

## 2026-06-22 — 🎉 実機 R4 で読み取りハンドシェイク成功(プロトコル疎通確認)

ユーザーが R4 を有線接続。`ioreg`/`hidutil` で同定 → `pyserial` で 64B フレームを実送信し、
正しい応答を取得。**最大の 🔴(実機が我々のバイトを受理するか / CRC poly)が解消**。

### デバイス同定(実機)

- USB: `idVendor=0x05AC`(1452, Apple), `idProduct=0x0256`(598), Product=`CYBERBOARD`,
  Vendor=`AngryMiao`。シリアルノード = **`/dev/cu.usbmodem212204`**(ioreg location
  `0x02122000` と一致、world RW で sudo 不要)。
- **HID も `0x05AC:0x0256` で列挙**(`hidutil`)。デコンパイル表の `0x3151:0x4015` は
  **出現せず** → 旧世代/ドングル用と推定。**R4 検出を `0x3151` 前提にすると失敗する**。
- 同環境に LG モニタ `cu.usbmodemABC1234567892` が併存 → ノード名選択の危険を再確認。

### 実送信した read-only クエリ(`_re/probe_product_id.py` / `probe_reads.py`)

`pyserial`(`uv` venv)で 9600/8N1、`reset_input_buffer` → write → `read(64)`:

| 送信 | 応答(hex 抜粋) | デコード |
|---|---|---|
| `[1,1]` product_id | `01 01 04 43423034 … fd` | **`CB04`**(len=4) |
| `[1,2]` product_info | `01 02 16 414d5f43423034… 9e` | 版 **`AM_CB040.N40.R1.01.50`**(len=0x16) |
| `[2,6]` check_pages | `02 06 03 … 2c` | **pages_num=3** |

### 確定事実(→ `30` §0/§1/§2/§7/§8 反映済み)

- **トランスポート = USB CDC シリアル @9600 が実機で応答**(理論でなく実証)。
- **CRC-8 poly0x07 が双方向で正しい**: 我々の送信フレームが受理され応答が返り、かつ
  応答の `[63]` も同 CRC で検証 OK。→ `crc8` pkg 既定という推定が**実機確定**。
- **64B フレーム / カテゴリ・サブコマンド / 応答フォーマット**を実機確認。
  query 応答 = `[0,1]`=コマンドエコー, `[2]`=長さ, `[3:3+len]`=ascii, `[63]`=CRC-8。
- **R4: product_id=`CB04`, 版=`AM_CB040.N40.R1.01.50`, pages_num=3**。
- 旧メモ修正: product_info は `[3:5+len]` でなく `[2]`=len / `[3:3+len]`(product_id と同形)。

### 次にやること

- **M1 本丸 = 書き込み経路の実機テスト**: 既知正解(merger `outputs/*.json`)を
  `JSON_START[1,5]`→各セクション→`JSON_END[1,6]` で実送信し、反映/永続を確認。
  読み取りは確認済みなのでフレーム生成は実機互換 = リスク低。
- CLI: `devices`(列挙)+ `device info`(詳細)サブコマンドは上記プローブがそのまま実装になる
  (`40` 反映)。
- 書き込み系 `rev[2]` 応答コード、Fn/マクロ、物理キー↔layer マップ。

---

## 2026-06-21 — miaomerge 解析 + 実機USBスキャン(初)

### miaomerge(`GeneralD/miaomerge`)= merger の Tauri リライト

- **正体**: React19 + Tauri v2(Rust, clean architecture)。依存は `tauri-plugin-fs/dialog` +
  `serde` のみ。**serial/hid/usb 一切なし** → LED マージ→JSON 保存まで。**書き込みは非対応**
  (純正アプリ依存のまま)。= Python merger の機能等価リライト。
- **我々への価値**: `build`/LED 合成ステップ(`40` M3/M4)の**型付き参照実装**。Rust なので
  将来 Rust 移植時はこちらから移植する方が楽。マージ算法(`src-tauri/src/usecase/
  merge_configurations.rs` + `domain/entity/led_configuration.rs`):
  - アクション `keep`(無変更)/`replace`(対象ページの `frames` を source で置換)/
    `combine`(`frame_data` を連結し `frame_num` 再計算)。スロット = page 5/6/7。
  - **注意**: merge は `frames`(200px 表示)のみ操作。`keyframes`(各キー灯90)は base の
    まま。→ 我々の build で per-key も合成したいなら**両方**扱う必要あり。
  - 1スロット 1-300 フレーム検証(= merger `MAX_FRAMES=300`)。
- **スキーマ裏取り(独立確認)**: `frame_RGB`(大文字)↔`frame_rgb` の serde rename、
  `valid`/`frame_index` は数値/文字列/bool 混在を許容(bool→1/0。= `change_dict` 正規化)、
  `#[serde(flatten)] other` で **LED 以外のプロパティ(Fn_key/MACRO_key/key_layer 等)は
  base から丸ごと保持** — ファイル単位では既に「分離」が成立している点も確認。

### 実機USBスキャン(CyberBoard 未接続だが収穫あり)

- `ioreg -p IOUSB -l` で取得(注: この環境では `system_profiler SPUSBDataType` が 0 行を返す。
  **`ioreg` か `hidutil list` を使うこと**)。
- **CyberBoard(期待 HID VID `0x3151`)は現状ツリーに不在** = 未接続(or ドングル未挿)。
  接続中の非Apple HID キーボードは別製品「Onihhkb RGB」(VID `0x45d4` PID `0x160`)のみ。
- **重要な誤検出例**: `/dev/cu.usbmodemABC1234567892` が存在するが、これは **LG モニタの
  "USB Controls"**(VID `0x043E` LG, serial `ABC123456789`)。CyberBoard ではない。
  → `30` §6 の「ポート取り違え」が実環境で再現。**ノード名で選ばず `[1,1]` product_id
  プローブで同定**する設計判断の正しさが裏付けられた(naive な `cu.usbmodem*` 列挙は
  モニタを掴む)。

### 次にやること

- **R4 を有線接続**(ドングルでなく本体USB)してもらい再スキャン →
  実 VID/PID・シリアルノード名・`CB04` 応答を一発確定。

---

## 2026-06-21 — エンコード仕様の実データ検証(ハード不要)

逆コンパイルで得たバイト詰めロジックを**転記でなく実装して実データで再現**し、
`30`/`10` の 🟢 主張を裏取り(advisor 指摘 #1 = M1 前半)。

### やったこと

- `_re/verify_encoding.py` を作成 — `TransJsonCmd`/`JsonToCmd` の chunking を移植
  (`crc8` poly0x07, `rgb_to_bytes`, rgb_frame=600B→11chunk, key_frame=270B→5chunk)。
- merger の `outputs/merged_*.json`(=純正が実際に書けた既知正解)+ `sources/*.json`
  複数で実行。全ページのフレームを 64B フレームへ詰め直し、全 index が `cmd[0..62]`
  に収まり CRC-8 が `[63]` に載ることを確認。

### 確定した事実(→ `10`/`30` 反映済み)

- **能動ページ(5/6/7)では display フレームは常に厳密に 200px(600B→11 USBチャンク)、
  per-key フレームは常に 90px(270B→5 USBチャンク)** — 複数ファイルで例外なし。
  「frames=200px ディスプレイ / keyframes=各キー灯90個」が**実データで再現確認**された。
- **宣言 `frame_num` == `frame_data` 要素数 == 200/90 フルサイズ数**(黙ったドロップ無し)。
  例: merged 出力 page6 は display 125 / per-key 42 と完全一致。
- **非能動ページ(0-4)は `frame_num=0` かつ `frame_RGB` 長 1 のプレースホルダ**
  (= 静的単色を 1 要素で持つ)。書き込み時は除外対象。
- merger 出力 1 本で RGB+KEY = 計 3719 USBフレーム規模(参考: 送信量の桁感)。
- JSON キーは `frame_RGB`(大文字)。純正 `from_dict` が `frame_rgb`(小文字, `TransJsonCmd`
  参照)へ写像している点も整合。

### 次にやること(実機が要る分のみ残)

- **実機 USB/シリアルキャプチャ**で実バイト列と照合(CRC poly0x07 は `crc8` pkg 既定
  からの推定、要観測)。
- ユーザー実機で 10 秒: `system_profiler SPUSBDataType` + `ls /dev/cu.*` を本ログへ貼付
  → 実 VID/PID(`0x05AC` シリアル照合の真偽)・シリアルノード名・有線/ドングルが一発確定。

---

## 2026-06-21 — 逆コンパイル突破(プロトコル全容解明)

ユーザー承認のもと外部 RE ツールを使用。

### やったこと

- `pyinstxtractor` で `AM_Master` を展開 → アプリ独自モジュールは**トップレベルに直接
  `.pyc`**(PYZ 不要)。Python 3.7(magic `42 0d 0d 0a`)。
- `pycdc`(Decompyle++ をソースビルド)で逆コンパイル → `_re/decompiled/`。
- pycdc 失敗分(`KBSerialOption`, `Central`)は `uv` の Python3.8 + `decompyle3` で取得
  → `_re/dc3/`(末尾に完全ソース)。
- `CommonDefine / GlobalInfo / Comm / HidDevice / JsonToCmd / TransJsonCmd /
  KBSerialOption / Central` を精読。

### 確定した重大事実(→ `30-write-protocol.md` 全面改訂)

- **トランスポート = USB CDC シリアル(pyserial)@9600**。HID は検出専用。
  (`KBSerialOption.send_cmd` = `self.serial.write(cmd)`)
- **設定書き込みに暗号化なし**(AES は PyInstaller 難読化のみ)。アドバイザー最優先懸念 解消。
- **フレーム = 64B 固定**: `[0]`cat `[1]`sub `[2..62]`payload `[63]`**CRC-8(poly 0x07, `crc8` pkg)**。
- **コマンド表(byte0/byte1)を全取得**。CMDType enum(0-25)とワイヤ値は別物。
- **送信順序(R系列)を全取得**: START→uncertainty→page→word→rgb_frame→key_frame→
  exchange→swap→key_layer_control→key_layer→(ph_key/car_light)→END。
- **frames=40×5=200px ディスプレイ(`[4,*]`×11chunk)/ keyframes=各キー灯90個
  (`[5,*]`×5chunk)** — `10` の積年の疑問が解決。
- 製品コード **R4=`CB04`**。検出は `[1,1]` 応答 product_id。`cmd_check_pages [2,6]` で pages_num。
- VID/PID: HID key `0x3151:0x4015`、MediaTek `0x0E8D`、Nordic DFU `0x1915`、
  macOS シリアル照合 `0x05AC:{0x024F,0x0256}`。
- **接続不安定の根本原因を特定**(`30` §6): 狭い vid/pid 固定マッチ / `_get_serial_port_set`
  の壊れた制御フロー / `com_status` レース / 5回で諦めるリトライ / `tty.*` DCDブロック疑い。

### 次にやること

- **実機 USB/シリアルキャプチャ**で送信バイト列を裏取り(macOS `cu.usbmodem*`)。
- Python PoC: `cu.usbmodem*` 列挙→`[1,1]`で R4 同定→既知正解(merger `outputs/*.json`)を
  フル書き込み(M1)。
- Fn/マクロが R系列順に無い件の確認。応答コード全集合。物理キー↔layer index マップ。

---

## 2026-06-21 — 初回調査(静的解析・外部ツール無し)

### やったこと

- 純正アプリ `AM_Master.app`(PyInstaller / Mach-O x86_64 / Python 3.7 / PySide2)の構造把握。
- merger ツール(`angrymiao-cyberboard-config-merger`)のソースと設定 JSON 実構造を解析。
- 自作スクリプト `_re/zscan.py` で `AM_Master` 実行ファイル内の **zlib ストリームを
  ブルートスキャン**(40 本 / 約 388KB 展開)。外部DL・実行なしで**文字列定数レベル**を抽出。

### 判明(確度は各 rule 参照)

- 設定 JSON は**キーマップ + LED が同居**(`10-config-schema.md`)。
- LED スロット 1/2/3 = `page_data` の index 5/6/7。LED マトリクスは 40×5=200px。
- キーコード `#MMPPUUUU` = HID usage page(07)+ usage id(+ 修飾推定)。
- アプリ独自モジュール: `HidDevice / Comm / JsonToCmd / TransJsonCmd / CyberBoardJson /
  Central / KBCheckServiceManage / KBSerialOption`(`20-am-master-internals.md`)。
- **コマンド体系を網羅取得**(`CMD_KEY_LAYER/FN/MACRO/SWAP/EXCHANGE/TAB_KEY`,
  `CMD_HATSU_LINE/PAGE_*`, `CMD_WORD_PAGE`, `CMD_RGB_FRAME`, `CMD_JSON_START/END`,
  読み戻し `cmd_get_flash/check_pages/read_cmd_rev` 等)(`30-write-protocol.md`)。
- フレームヘッダ体系(`Json_Send_Frame_Head` 等)、**CRC は CRC-8**、`chunk_size` 概念あり。
- デバイス識別: `AM35`(本体)/ `AM35_D`(ドングル)/ `CBR5`、`DeviceStateManager` で
  `am35_connected` / `am35_dongle_connected` を管理。`Default_USBD_Usage` で usage 選別の気配。
- AES は 2 系統(PyInstaller PYZ 難読化 / デバイス通信)。後者の鍵静的/動的は**未判定**。
- `AM_TOOL/` は MediaTek ファーム書き込み資材(別系統・対象外)。CyberBoard は MTK SoC。

### ブロッカー / 次にやること

- **正規逆コンパイルが未実施**。数値定数(VID/PID/report長/CRC poly/**AES鍵・モード**)・
  制御フロー・バイトレイアウトは `.pyc` の逆コンパイルが必要。
- `pyinstxtractor` / `pycdc`(or `uv` で Python3.8 + `decompyle3`)の**取得・実行は
  auto-mode 分類器でブロック**された(外部コードの取得・実行が未承認のため)。
  → **ユーザーに承認可否を確認する**(承認されれば一気に確定可能)。
- 承認後の優先順:
  1. AES 鍵の静的/動的判定(`Comm.py` / `JsonToCmd.py` / `Cipher`)
  2. VID/PID/usage/report-ID/report長(`HidDevice.py`)
  3. 接続シーケンス・リトライ・タイムアウト(`Central.py` / `KBCheckServiceManage.py`)
  4. Frame_Head 実バイト + chunk_size + payload レイアウト + CRC-8 poly(`Comm.py`)
  5. 読み戻し応答フォーマット
- 最終確定は**実機 USB/HID キャプチャ**で(現状はすべて静的解析の仮説)。

### 成果物

- `_re/zscan.py`(自作 zlib ブルートスキャナ)
- `_re/decompressed.bin`(展開済みストリーム。`strings` で再mine可)
- `.claude/rules/00,10,20,30,40,90`(本ナレッジ群)

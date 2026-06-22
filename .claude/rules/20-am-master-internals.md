# AM Master 内部構造(解析メモ)

## パッケージング

- 配布: `AM_Master_mac_1.3.7.pkg`(257 MB)→ 展開 `AM_Master_mac_1.3.7_extracted/`
  - `Distribution`, `Resources`, `AM_Master.app`
- 本体: `AM_Master.app/Contents/MacOS/`
  - `AM_Master` — **Mach-O 64-bit x86_64**(PyInstaller ブートローダ、27 MB)。
    Intel バイナリ(Apple Silicon では Rosetta 実行)。
  - `Python` — Python **3.7** 共有ライブラリ。
  - PySide2 / Qt 一式(QtWebEngine 含む = Electron 的に web UI を内包)。
  - ネイティブ拡張:
    - `hid.cpython-37m-darwin.so` — **USB HID 通信**(hidapi)
    - `tinyaes.cpython-37m-darwin.so` — **AES**
    - `crcmod` — **CRC**(実際の使用は CRC-8、`30` 参照)
    - `cryptography`, `_cffi_backend`, `libssl/libcrypto 1.1` — TLS/署名(API 通信用)
  - `AM_TOOL/` — **MediaTek ファーム書き込み資材**(別系統):
    `MTK_AllInOne_DA.bin`(MTK Download Agent), `coda.out`, `DaCode`, `TWS_file.zip`,
    `default.ini`, `setting`。→ **設定書き込みとは無関係**。ファーム更新/TWS(イヤホン?)
    用。CyberBoard は **MediaTek SoC** を使用していることが分かる。

> アプリは「Python 製ロジック + PySide2/QtWebEngine の薄い GUI ラッパ」。ユーザーの
> 見立て通り、**核心ロジックは Python**。CLI 化の本質は HID/暗号/フレーミングの移植。

## Python ロジックの構成(zlib ブルートスキャンで判明したモジュール)

アプリ独自モジュール(stdlib / PySide2 / PyInstaller ランタイムを除く):

| モジュール | 役割(推定) |
|---|---|
| `main.py` | エントリポイント |
| `KBSerialOption.py` | **キーボード設定書き込み本体**(シリアル探索・接続・送信シーケンス・ファームDFU)。最重要 |
| `JsonToCmd.py` | 設定 JSON → コマンド列(チャンク化) |
| `TransJsonCmd.py` | 各コマンドの **64バイトフレーム生成**(CRC-8 含む) |
| `CyberBoardJson.py` | 設定 JSON データモデル(`*_from_dict`) |
| `CommonDefine.py` | 定数(CMDType, 製品コード `CB02..CB06`, `CMD_DESCRIBE`) |
| `GlobalInfo.py` | グローバル状態(`com_json`, `com_write_delay=0.005`, `password='135qwr'`) |
| `KBCheckServiceManage.py` | 接続監視サービス(ホットプラグ) |
| `HidDevice.py` | **HID(オーディオ/TWS/EQ 用)** + デバイス検出。⚠ キーボード設定はここを通らない |
| `Comm.py` | **シリアル IAP ファーム更新(MediaTek系)**。CRC-16/X-25。⚠ 設定書き込みとは別 |
| `Central.py` | TWS/オーディオ制御・ファーム更新オーケストレーション |
| `ImageFile.py` | **ファーム hex/bin イメージ parser**(`T_ImageFile`/`T_SubSeg` Address/Data, `HexStringToList` = IAP 用)。🔴訂正(`90` 続15): 旧「画像→LED 変換(推定)」は誤り、**LED と無関係**。→ per-key 座標マップは Python に無く web UI 側 |
| `Music_set1.py` / `Add_audioq` / `ADD_FQ` | オーディオ/EQ 機能(別製品系) |

> **トランスポートの整理**(重要): キーボード設定 = **`KBSerialOption` の
> `self.serial.write()` = USB CDC シリアル**。`HidDevice.T_HID` と `Comm.py` は
> 別製品・別用途。混同しないこと(→ `30-write-protocol.md`)。
> 補助: `helper.py`(ユーティリティ), `webPage.py`(QtWebEngine UI 橋渡し)。

API エンドポイント(アプリ内ハードコード):
`https://diy.angrymiao.com/api/firmware/check`, `…/api/product-collection`,
`…/api/product-collection-map`, `…/welcome/`(+ `diy-test.angrymiao.com` のテスト系)。

## 2 系統の AES に注意

1. **PyInstaller PYZ 暗号化**(`pyimod00_crypto_key.py` + `Cipher` クラス。
   "This class is used only to decrypt Python modules")→ **バイトコード難読化**。
   逆コンパイル時 pyinstxtractor が埋め込み鍵で自動復号。
2. **デバイス通信の AES → 存在しない**(確定 🟢)。`TransJsonCmd` は素のバイト列 +
   CRC-8 のみ。設定書き込みに暗号化は無い。

## 逆コンパイル — 完了 🟢

手順(再現可能):

1. `_re/zscan.py`(自作)で zlib ストリームを抽出 → モジュール名・語彙を把握(初動)。
2. `python3 pyinstxtractor.py <AM_Master>` → CArchive 展開。アプリ独自モジュールは
   **トップレベルに直接 `.pyc`**(PYZ 抽出不要だった)。`.pyc` magic `42 0d 0d 0a` = Python 3.7。
3. **pycdc**(Decompyle++ をソースビルド)で逆コンパイル → `_re/decompiled/*.py`。
   `Comm/HidDevice/JsonToCmd/TransJsonCmd/CommonDefine/GlobalInfo` は完全取得。
4. pycdc が失敗した複雑なファイル(`KBSerialOption`=std::bad_cast,
   `Central`=end of stream)は **`uv venv --python 3.8` + `decompyle3`** で取得 →
   `_re/dc3/*.py`(冒頭にパーサダンプ。**末尾に完全なソース**)。

成果物(durable):

- `_re/decompiled/` — pycdc 出力(クリーン)
- `_re/dc3/` — decompyle3 出力(`KBSerialOption` 等、pycdc 失敗分。末尾に実ソース)
- `_re/AM_Master_extracted/` — 生 `.pyc` 群(再 mine 用)

> 数値定数(VID/PID/baud/CRC/frame レイアウト)・制御フロー・送信順序まで取得済み。
> 残りは**実機キャプチャでの裏取りのみ**(→ `30-write-protocol.md` §8)。

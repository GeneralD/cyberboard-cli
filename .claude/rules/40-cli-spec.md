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

## 独自スキーマ案

### キーマップ `keymap.toml`(例)

```toml
[meta]
product = "R4"
layers = 7

# 物理キー名 → HID キー(レイヤ0)。#MMPPUUUU ではなく人間可読名で書ける
[layer.0]
esc = "Esc"
a = "A"
caps = "LCtrl"          # リマップ例

[layer.1]                # Fn レイヤ
f1 = "BrightnessDown"

[[fn_key]]   input = "P"  out = "Up"
[[swap_key]] input = "A"  out = "B"
[[macro]]    input = "M"  out = ["H","I"]  interval_ms = [0, 100]
```

- 人間可読キー名 ↔ HID コード `#MMPPUUUU` の**変換テーブル**を内蔵(`10` 参照)。
- 物理キー名 ↔ 行列 index(25×8=200)の**R4 レイアウトマップ**が必要(要作成 🔴)。

### LED `led.toml`(例)

```toml
# スロット = page 5/6/7(Custom LED 1/2/3)
[[slot]]
index = 1                # スロット1 (= page 5)
source = "nyan_cat.json" # 既存JSON/merger資産から該当ページを取り込み
lightness = 100
speed_ms = 34

[[slot]]
index = 2
source = "matrix.json"
# あるいは画像/GIF からフレーム生成(ImageFile.py 相当を将来実装)
```

- スロットのソースは「既存 JSON の Custom LED ページ」または将来「画像/GIF/自作フレーム」。
- merger のアニメ合成(連結・差し替え)機能はここに取り込む候補。
  - **参照実装**: `miaomerge`(merger の Tauri/Rust 版)の `merge_configurations.rs`。
    アクション `keep`/`replace`(置換)/`combine`(連結+`frame_num`再計算)。型付きで読みやすい。
    **ただし `frames`(200px)しか合成しない** — per-key(`keyframes`)も混ぜたいなら build 側で
    両方扱う(`90` 2026-06-21 参照)。

## CLI コマンド構成(案)

```text
ambctl devices                 # 接続デバイス列挙(product_id/version/pages/port)
ambctl device info [PORT]      # 1台の詳細(未指定なら自動検出)
ambctl build  -k keymap.toml -l led.toml -o config.json   # 独自→IR(純正JSON)
ambctl verify config.json      # IRスキーマ検証(書き込まない)
ambctl write  config.json [--section keymap|led|all] [--slot 1,2,3] [--dry-run]
ambctl read   -o dump.json     # デバイス→IR 読み戻し(cmd_get_* 利用)
ambctl diff   dump.json config.json   # 書き込み前後の差分確認
```

- **`devices` / `device info` は実装済みの土台あり**🟢: `tools/cb_device.py`(+ 共有コア
  `tools/cb_protocol.py`)。実機 R4 で動作確認済み(`90` 2026-06-22)。
  `list`/`info --json` を持ち、これをそのまま CLI サブコマンドへ昇格できる。
  プロジェクトローカル skill = [`cyberboard-device`](../skills/cyberboard-device/SKILL.md)。
- `write` は段階的に: 接続確立 → (必要なら read で現状退避) → 送信 → **read で検証**。
- `--dry-run` は実送信せずチャンク列を表示。
- 堅牢化(`30` §6): 列挙条件の厳密化(usage/経路)+ 明示リトライ + 各段で読み戻し検証。

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
4. **M3**: 独自スキーマ → IR の `build`(keymap/LED 分離)。
5. **M4**: 部分書き込み(LED スロットだけ)+ 堅牢化(接続安定化)。

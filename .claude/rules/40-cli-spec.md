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
   - 🔴 残: LED `led.toml` ソースからの合成(現状 LED は base から継承=「keymap だけ変更」は成立)。
5. **M4**: 堅牢化(接続安定化)。部分書込は firmware 非対応(続8)のため不要 —
   分離管理は「read→merge→フル書込」で M3 build が吸収する。

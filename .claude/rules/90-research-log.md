# 調査ログ(append-only)

新しい発見は**上に**追記。確定したら該当 rule(`10`〜`40`)へ反映する。

---

## 2026-06-22 (続8) — 🎯 部分書き込みは非対応(JSON_START が全消去)+ read-back settle 遅延

B2(主目的直結): 「LED だけ送れば keymap は残る?」を実機検証。read-back の非対称性
(keymap は `[6,9]` で読めるが LED は読めない)を使い、**LED セクションだけ送って keymap を
省略**したトランザクションの前後で keymap を比較(`experiments/partial-write/`)。

### 確定事実 🟢

- **keymap を省略すると keymap は全 `#FFFFFFFF`= NOR フラッシュ消去状態になった**
  (before 567 mapped → after 1400 全 0xFF)。LED-only 3008 フレーム送信、ACK SUCCESS。
- → **`JSON_START` が設定フラッシュ領域を消去**し、各セクションが自領域を再書込、
  **送らなかったセクションは消去のまま** = **1 トランザクション = 設定全体の置換**。
  **部分書き込みは firmware が非対応**。
- **分離管理の実現方法(確定)**: 必ず **read → merge → フル書込**。
  - LED 変更・keymap 維持: `[6,9]` で keymap 読戻し → フル書込。**今すぐ可能**。
  - keymap 変更・LED 維持: **LED は読めない**ので LED の IR を**ソースに保持** → フル書込。
  - = `40` の「安全側デフォルト」が実機で裏付けられた。分離は build 側の責務。

### 副産物: read-back は settle 遅延が必要 🟢

- 復元のフル書込**直後**に keymap を読むと**全 `#00000000`(ゼロ)**(commit 未完了)。
  833/1400 一致(両方ゼロの位置だけ一致)。**~2 秒待って再読**すると **1400/1400 一致**(3 回連続)。
- → **書込後の read-back 検証には settle 遅延(~2s)が必要**。`cb_read`/`cb_write` に反映予定。
- デバイスは merged 既知正解へ復元済み(keymap 1400/1400 + LED)。

### 残課題

- B3 物理キー↔matrix index(25×8)マップ / per-key 再生上限の実機検証 / LED read 経路の探索。

---

## 2026-06-22 (続7) — ライティング(per-key 灯効)= 公式 UI で 100 フレーム上限(別系統)

ユーザー指摘: 純正 AM Master には display アニメとは別に**「ライティング設定」があり、
1 アニメ 100 フレームまで作れる**(display の 300 とは別の上限)。

我々のモデルでは **ライティング = `keyframes`(各キーのバックライト 90 個)**(`10` 既述)。
display(`frames` 200px)とは別系統で、別の作成上限を持つ。

### 重要な反例(100 は firmware 上限ではない)

- **既知正解 `merged_20250916_161615.json` の page 7 `keyframes` = 123 フレーム**(> 100)。
  これを実機に書込→**ACK SUCCESS**(以前 LED 目視も済)。= **100 は「公式 UI の 1 アニメ
  あたり作成上限」**であって firmware のハード上限**ではない**(display の 300 と同じ性質)。
  merger の `combine` 連結で 100 を超えて 123 まで伸ばせている。
- 実測 keyframes(同設定): page5=42 / page6=42 / page7=123。display: 66/125/53。
- **per-key の真の再生上限は未検証 🔴**: display の教訓「ACK≠再生」より、123 が ACK しても
  全 123 枚再生される保証はない(真値は 100 か 256 か中間か不明)。per-key は 90 キーしか
  無く**数字描画で数えられない**ため、display で使った目視カウント手法が使えない。
- 構造上限は **256**: per-key `frame_index` は `[5,pi]` の `[2]` に **1 バイト**送出。

### スキーマ方針(enforce せず文書化)

- **keyframes を 100 に cap しない**(= 既知正解 123 を弾くため不可)。`rgbFrameSet` 共有の
  **256(構造上限)を維持**し、`pageDatum.keyframes` の description に 100 UI 上限 +
  123 反例 + 再生上限未検証(🔴)を注記。`schemas/cyberboard-config.schema.json` 反映済み。
- まとめ(ライティング/per-key の段モデル、display と非対称):
  公式 UI 作成 = **100/アニメ**(merger combine で超過可)/ 構造 = **256**(1B index)/
  firmware 再生 = **未検証 🔴**。display は UI300・firmware256(確定)。

---

## 2026-06-22 (続6) — ✅ 256 上限を公式オーサリング設定で最終確認 + スキーマに enforcement

続5 の 256 上限を「自作エンコードの癖では?」の疑いごと潰すため、**純正 AM Master の UI で
作成した 300 フレーム設定**(`AM CB Index (1).json`)で追試。元アニメ(0〜78)+ 暗転
(79〜255)の後ろ **256〜299 を赤ベタ `#FF0000` で上書き**して書込(キーマップは merger
既知正解保持、`frame_num=300`、data_frames=3444、ACK SUCCESS)。

- **実機スロット 1 で赤ブロックは一切出なかった**(ユーザー確認「紫の画面は出なかった」)。
  = **公式オーサリング設定でも 256 で頭打ち** → 256 上限は firmware 由来で**完全確定**。
- **3 段モデルを確定**(`experiments/frame-limit-256/README.md` に結論表として記載):
  firmware 再生 = **256/スロット**(真の上限・8bit カーソル)/ 公式 UI 作成 = 300/スロット
  (257〜300 は死にフレーム)/ プロトコル・ACK = 実質無制限(`frame_num` 2B=最大 32767、
  ACK は受理を示すだけ)。
- **スキーマに 256 を enforcement**(ユーザー指示「schema にも配列の上限数を 256 と」):
  `schemas/cyberboard-config.schema.json` の `rgbFrameSet`(display + per-key 両用)を
  `frame_num` `maximum:256` / `frame_data` `maxItems:256` に変更。`lightFrameSet`(spotlight)
  も類推で 256(🔴 未確認注記付き)。**検証済み**: merger 既知正解(256 未満)は PASS のまま、
  300 枚設定は全 3 スロットで `frame_num>256` + `frame_data` 超過の両方を検出して FAIL
  → `cb_verify` が「再生されないフレーム数」を書込前に警告できる。プロトコル上限 32767 は
  `$comment` に温存(続5 の「enforce は tooling 側」方針を撤回し schema 側で enforce)。

---

## 2026-06-22 (続5) — 🎯 フレーム数の真の上限 = 256(2^8)を実機で確定

ユーザーの一次情報(「純正でも 300 超で書けなかった」=ハードウェア説)を実機実験で検証。
**数字描画フレーム**手法で「ACK されたフレームが本当に再生されるか」を目視確定。

### 手法(`$CLAUDE_JOB_DIR/tmp/frame_numbers.py`)

- slot1(page5)の各 display フレームに**自分の index を数字で描画**(40×5 LED に 3×5 フォント)。
  他スロットは最小化。スロットを 0,1,2… と数え上げ、**ループ直前の最大値+1 = 実格納/再生数**。
- 検証: N=30 → **0–29 で正しくループ**(ACK=実格納、数字も判読可=ピクセル並びも正常)。

### 確定事実 🟢

- **N=400 を書くと ACK SUCCESS だが、再生は 0–255 でループ = 256 枚で頭打ち**。
  → **真の per-slot 上限は 256(=2^8)。firmware の再生カーソル/index が 8 ビット**。
  - ACK 経路は 16 ビット(uncertainty の frame_num は 2B、display frame_index も 2B 送出)だが、
    **firmware 内部が uint8** のため 256 で切る。**ACK ≠ 実格納**の決定的実例。
  - **merger の `MAX_FRAMES=300` も AM Master の "~300" も不正確**(真値 256 を捉えていない過大マージン)。
    AM Master の「300 超で書けない」は自前 UI ガードで、我々のツールは迂回送信できるが firmware が 256 で切る。
- ACK ラダー(gradient): N=400/800/1600 すべて ACK=True(rev[2]==1)。**ACK は上限を示さない**
  (1600 でも受理)。**唯一の真実は目視**(数字描画)。
- 大量書込中に**ディスプレイに黄ドット3つ→リブート**の兆候(N=1600 付近)。書込後 `cb_doctor`
  で **HEALTHY**(キーマップ 94F 健在)。リセットからの復帰=実害なし。ただし巨大 N は避ける。

### per-slot 確定 + 公式 UI 上限 300 判明 🟢

- **256 は per-slot**(実機確定): slot1=200(白数字)+ slot2=200(シアン数字)=合計 400 を書込→
  **両スロットとも 0–199 完走**。各スロット独立の 8bit index = **per-slot 256**、3 スロット計 ≥768 使える。
  `tmp/frame_slots.py`。
- **公式 AM Master の「ドット作成画面」上限 = 300**(ユーザー現地確認)。merger の 300 はこれを写した値。
- **完全な図式**: 公式エディタは **300 まで作成可**(UI ハードキャップ)/ firmware は **256 で再生ループ**
  → **257–300 枚目は作れるが永遠に表示されない**(公式エコシステム内在の「作成上限300 vs 再生上限256」
  不一致)。我々のツールは UI を持たず firmware 直叩きなので **各スロット 256 をフル活用可能**。
- 残🔴(軽微): 256 超が「未格納」か「再生カーソルのみ 8bit ラップ」かは LED read 経路が無く区別不可
  (実用上どちらも「使えるのは 256」)。per-key(keyframes)は frame_index 1B 送出=構造上も 256(別途確認)。

### 「我々の符号化バグでは?」を排除(送信バイト実検証)

ユーザー仮説「JSON 側で枚数宣言が抜け/1B 切れしてるのでは」を、生成フレームの実デコードで否定:

- **uncertainty [2,1] は page5/6/7 とも `frame_num=300` を 2B で正しく宣言**(切れなし)。
- **全 300 フレーム送信**、display `frame_index` も 2B 正確: `256→lo=00 hi=01`, `299→lo=2b hi=01`。
- = firmware は「300」宣言 + 300 枚の正データを受領した上で **256 しか再生しない** → **我々の符号化は
  忠実、256 は firmware 内部のバッファ上限**。
- 傍証: 宣言値を uint8 で読むバグなら `300&0xFF=44` でループのはず。実際は **256 ちょうど** =
  剰余切り捨てでなく **256 枚バッファへの飽和格納**。
- プロトコル上、枚数を伝えるフィールドは uncertainty の `frame_num` のみ(他に無い)。公式アプリの
  送信列(`send_r_series_all`)を忠実再現済み = **公式で 300 枚作っても同 firmware が同 256 でループする**
  はず(エディタが警告しないだけ。公式 300 枚の全再生は未検証の思い込み)。

### 純正設定の実査(上限フィールド不在を確証)

ユーザー提供の `~/Downloads/AM CB Index.json`(公式 DL)を全ネストキー走査:

- **`max`/`limit`/`capacity`/`buffer` 系フィールドは皆無**。枚数関連は `page_num` / 各ページ
  `frames.frame_num`・`keyframes.frame_num` / `word_len` / `layer_num` / `*_num` のみ
  = **我々が既に正しく扱う集合と完全一致**。上限はどこにも JSON 宣言されていない=取りこぼし不可能。
- このファイルの page5 は `frame_num=300` だったが、**これはユーザーが上限テスト用に公式 UI で
  300 まで増やした編集物**(工場出荷ではない)。要点は「**公式 UI は 300 まで作成させる**」=
  作成上限 300 と firmware 再生上限 256 の不一致が UI 側で防がれていないこと。
- スキーマ検証 pass(`cb_verify.py`)= 我々のスキーマは公式形式(frame_num=300 含む)もカバー。
- 次検証(ユーザー実施中): 公式 UI で **300 フレーム目に目印**を入れて DL → 我々のツールで書込 →
  目印が表示されない(=256 超は出ない)ことを公式オーサリング由来の設定で再確認。

### 反映

- `10`(フレーム数上限)/ `schemas/cyberboard-config.schema.json`(frame_num $comment)を **256** で更新。

---

## 2026-06-22 (続4) — doctor(疎通診断)+ JSON Schema(IR 形式化)追加

ツール群を 2 つ拡充。どちらも実機/実データで検証済み。

### `tools/cb_doctor.py` — 非破壊の health チェック(AM Master の泣き所対策)

ユーザー談「最初の1週間 AM Master でまともに書けず泣き寝入り」→ **書かずに疎通だけ確かめる**
doctor。`30` §6 で特定した AM Master 不安定要因を**そのままチェック項目化**:

- ✓ `cu.usbmodem*` 列挙(0 件→データ非対応ケーブル/未接続を示唆)
- ✓ `[1,1]` で CyberBoard 同定(ドングルのみ/他デバイスは個別に診断メッセージ)
- ✓ **排他オープン**(失敗=他アプリ=AM Master がポート占有。書込失敗の筆頭要因)
- ✓ フレーム往復 CRC-8(双方向)/ ✓ **bulk read-back [6,9] 94 フレーム全 CRC OK**
  (= 多フレーム転送の健全性 = 書込経路の良好さの強い証拠。ただし書込はしない)
- 実機: **verdict HEALTHY**(LG モニタ `cu.usbmodemABC...` は正しく無視)。read-only のみ
  (`[6,17]` reset 等は一切送らない)。

### `schemas/cyberboard-config.schema.json` — 純正/IR 形式の JSON Schema(draft 2020-12)

ユーザー提案「構造が分かるたびスキーマ化=ドキュメント兼用」。`10`/`CyberBoardJson.py`/実データ
から起こし、**スキーマ検証が実 format の落とし穴を炙り出した**(スキーマ作成の価値そのもの):

- **`"//"` コメントキー**が JSON 内に混在(中国語コメント。`key_layer`/`page_data` 等)→ 許容。
- **`frame_index` が文字列 `"0"`** のページがある(非能動プレースホルダ。miaomerge の
  「数値/文字列混在」と一致)→ `numberish`(int|数字文字列)で受ける。
- **非能動ページの `frame_RGB` プレースホルダが `#0000`**(4hex、正規 #RRGGBB でない)→
  `frameColor`(緩い hex)で受け、`hexColor`(厳密 #RRGGBB)は color ブロック専用に分離。
- `valid` は bool/int/数字文字列を許容(`boolOrInt`)。
- **検証結果**: merger `outputs/*`(1.3.7)+ 旧 `sources/*`(コミュニティ)**全てパス** 🟢。
- 消費者 `tools/cb_verify.py`: config をスキーマ検証(書込前の事前チェック)。jsonschema
  未導入でも basic check に graceful 縮退。不正キーコード/範囲外 lightness を検出確認。

### 次にやること

- 棚卸し済み(できること / 未解明)。未解明の優先 = **B2 部分書込**(LED だけ差替が成立するか)
  → **B5 応答コード** → **B3 物理キー↔matrix index**。実機が繋がっている間に B2 から潰す。
- それらが固まったらサードパーティツールの仕様確定(言語/パッケージング/独自スキーマ TOML/IR/
  部分書込方針)。

---

## 2026-06-22 (続3) — 🎉🎉🎉 read 読み戻し発見(キーマップ完全ラウンドトリップ)+ 書込検証手法

「write できるなら read もできるか?」を実機で検証。**firmware は read コマンドに応答する**
(公式アプリは `cmd_get_*` を未使用=配線なしだが、デバイス側は実装済み)。

### 確定した重大事実(→ `30` §7 反映済み)

- **[6,9] cmd_get_key_msg = キーマップ全体の読み戻し**。応答は **94 フレーム**、
  `06 09 [chunk_idx] [60B] [crc]` で書込([6,7])と同形。連結 → 4B キーコード列。
  - **書込→読戻しで 1400/1400 キー完全一致**(7 レイヤ×200、ミスマッチ 0)。末尾に
    ゼロパディング 10 キー(5640B 返却 vs 5600B 書込=94×60 固定長)。
  - → **キーマップは write→read→diff の自動検証が可能**(目視不要)。`tools/cb_read.py`。
  - レイヤ1 は `#00920xxx`(usage page 0x92 = AM 独自/consumer 系 Fn キー)。
- **[6,15] cmd_get_flash = フラッシュ状態メタのみ**(`06 0f 00 00 05 14 00 00 00 c8...`
  = 0x0514=1300, 0x00c8=200 等)。**フレームデータのフルダンプではない**。
- **[6,10] cmd_get_key_macro = 全ゼロ**(マクロ未定義)。
- **LED フレームの読み戻し経路は未発見**([4,*]/[5,*] の read 変種なし)。
  → **LED 検証は当面 目視のみ**(下記ベーコン方式)。
- 注意: **[6,17] は cmd_reset**。get 系([6,9/10/14/15])の隣なので誤送信厳禁。
  [6,14] get_anykey はキーキャプチャモード懸念で未検証(回避)。

### 書込が「効いた」ことの検証(no-op 曖昧性の排除)

- ユーザー指摘: 現行と同一設定を書いたため「効いたのか無変化か区別不能」。
- 対策として **ベーコン書込**: `merged_…json` の slot1(page5)を**真緑ベタ塗り(静止1フレーム,
  display 200px + per-key 90px とも `#00FF00`)** に置換 → `tools/cb_write.py --execute`
  で書込(2906 フレーム, ACK SUCCESS)。→ **Custom LED スロット1 を緑表示で目視確認**(LED 用)。
- キーマップ用の完全自動検証は、**別キーマップを書いて [6,9] で読み戻す**ことで
  no-op 曖昧性を排除可能(未実施。元設定を保持しておき即復元する想定)。

### 成果物

- `tools/cb_read.py` — `keymap` dump / `--json`(key_layer 断片出力)/ `--compare CFG`
  (config の key_layer と diff)。M2 read の中核。

### 次にやること

- M2: read→IR(JSON)化 + `diff`。キーマップは [6,9] で確立。LED は読み戻し不可のため
  「書込んだ IR を正」として扱う(or 目視)。
- LED 読み戻し経路の探索([4,*]/[5,*] や別カテゴリの read 変種、`Central.py` の HID 経路)。

---

## 2026-06-22 (続2) — 🎉🎉 M1 フル設定書き込み成功(実機 R4 / 3826 フレーム)

merger の既知正解 `outputs/merged_20250916_161615.json` を `tools/cb_write.py` で
**フル書き込み**し、`JSON_END` の ACK(`rev[2]==1`)を取得。M1 の write 経路が
実機で通った。

### やったこと

- `_re/decompiled/JsonToCmd.py`(chunking/順序)+ `KBSerialOption.send_r_series_all` /
  `json_down`(送信ループ・総フレーム数の数え方)を精読。`TransJsonCmd` の全 builder
  バイトレイアウト(uncertainty/page_control/word_page/rgb_frame/key_frame/exchange/
  swap/key_layer_control/key_layer)+ 補助関数(key/rgb/unicode/rgba/int_to_bytes)を確認。
- `tools/cb_write.py` を実装(cb_protocol/cb_device を再利用)。**デフォルト dry-run**、
  `--execute` で実書き込み。送信前後に `[1,1]` product_id プローブ。
- `merged_20250916_161615.json` を書き込み → **ACK SUCCESS**。

### 確定した重大事実(→ `30`/`40` 反映予定)

- **総フレーム数 = START と END を除く全データフレーム数**。`json_down` は `send_start()`
  後に `send_cmd_count = 0` リセット → `send_end(send_cmd_count)` に渡す(37105/37111)。
  END 値は**送信側が実送信数を申告**=自己整合。firmware は受信数と照合(=ドロップ検出。
  count 不一致は `rev[2]!=1` でリトライ、ブリックではない)。
- **R系列送信順(実証)**: START → uncertainty[2,1] → page_control[2,2] →
  word_page[3,1] → rgb_frame[4,pi] → key_frame[5,pi] → exchange[6,1] → swap[6,6] →
  key_layer_control[6,8] → key_layer[6,7] →(ph_key/car_light は try/except)→ END[1,6]。
  **fn/macro/tab は R系列順に無い**(§5 注記が確定)。
- **car_light は本構成では 0 フレーム**: `cmd_send_car_light_info` は空リストで
  `valid_li[0]` IndexError → `send_r_series_all` の try/except で握り潰し。spotlight 無し
  構成では送られない(=実機アプリと同挙動)。
- **デコンパイル由来バグを修復**(忠実移植時の要注意点):
  - `JsonToCmd` line 105 `if key_frames is not None or ...` は**論理反転**(正: `is None`)。
  - `page_control_infos` / `word_page_infos` の**内側ループが欠落**(`control_infos=[]`,
    `word_len=0` で空)。clean な HATSU analog(`get_hatsu_page_control_info`)+ clean builder
    から再構築:page_control は 4 ページ/フレーム(`ceil(page_num/4)`)、word_page は
    28 文字/フレーム(`ceil(word_len/28)`)。
  - `swap_key_infos` の chunking で両分岐が同条件(`== usb_frame_count`)→ 11 件/フレームで再構築。
  - `get_key_layer_infos` line 314 `None.key_layer.layer_num`(self バインド崩れ)。
- **フレームプラン実測**(`merged_20250916_161615.json`, page_num=8):
  uncertainty 1 / page_control 2 / word_page 1(page3 が word_len=28, unicode A-\\) /
  rgb_frame 2684((66+125+53)×11) / key_frame 1035((42+42+123)×5) / exchange 7
  (num=0 だが list 7 件=全 #00000000) / swap 1(4 件) / key_layer 95(control 1 + 5600B÷60=94)
  = **計 3826**。rgb+key=3719 が `90`(2026-06-21)の「3719 USBフレーム規模」と一致。
- **応答**: `JSON_END` rev = `01 06 01 00...`(echo [1,6], `[2]=1` ACK, CRC `0x81` OK)。
  書き込み後も `[1,1]`→`CB04` / `AM_CB040.N40.R1.01.50` 応答(デバイス生存)。

### 重要な留保(advisor 指摘)

- **ACK ≠ 描画の正しさ**。CRC 自己整合 + count 一致 + ACK + 生存 が揃っても、
  系統的なオフセット誤りは「正しい CRC・一致 count・ACK」を出しうる(garbage in, ACK out)。
  **唯一の ground truth は目視**(page 5/6/7 の Custom LED にアニメが出るか)。
  → **M1 完了判定は実機 LED の目視確認待ち**。怪しいのは再構築した page_control の
  フィールド packing と word_page の per-frame word_len(ただし両方ともレビュー済みで一致)。

### 次にやること

- **ユーザーに目視確認依頼**: ディスプレイを Custom LED スロット(1/2/3)へ切替 →
  アニメが merged 設定通りか。OK なら M1 完全クローズ。
- 通れば M2(read 読み戻し + diff)、M3(独自スキーマ→IR build)へ。

---

## 2026-06-22 (続) — 🎉 初の書き込み成功(set_time / ACK 確認)

読み取りに続き、**書き込み経路を実機で実証**。最も安全な `[1,3]` cmd_set_time
(RTC のみ、キーマップ/LED 不変)を `tools/cb_settime.py` で送出。

- 送信 `[1,3]` payload `6a38f8be 00 09`(epoch BE + tz符号0=東 + 9時間=JST)。
- 応答 `01 03 01 00…48`(CRC OK): `[0,1]`=コマンドエコー, **`[2]=01`=ACK 成功**。
- = フレーム構築→送信→**デバイス受理→ACK** まで通った。書き込み系の応答コード
  `rev[2]==1`=成功 を実機確認(`30` §7)。
- バイト構造は decompiled `TransJsonCmd.cmd_set_time_send` 準拠(tz: `[6]`符号 0/1/2,
  `[7]`絶対時)。検出は `cb_device.list_devices()` 流用(コア再利用が機能)。

これで read / write 両系統 + エンコード(`verify_encoding`)+ CRC が**全て実機で確定**。
残るは **M1 本丸 = フル設定書き込み**(JSON_START..frames..JSON_END の多フレーム
トランザクション)。これは初の**設定上書き**なので、既知正解 JSON 選定 + バックアップ方針を
ユーザーと決めてから実施。

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

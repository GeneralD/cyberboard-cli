# 調査ログ(append-only)

新しい発見は**上に**追記。確定したら該当 rule(`10`〜`40`)へ反映する。

---

## 2026-06-23 (続24) — 製品化 #2: 対話的 LED 作成スキル(plugin 側、CLI コアを叩く)

issue #2。`plugins/cyberboard/skills/cyberboard-led/SKILL.md`。AskUserQuestion で slot と
効果を選ばせ、preview を見せて反復、明示確認して実機書込まで。**fork しない**(対話フロー)。
**CLI がコア**の方針通り、スキルは `cyberboard anim/led/write` を**オーケストレーションするだけ**。

### advisor の効いた3指摘(設計の芯)

+ **preview ループは GIF ベース**: `cyberboard led play`(続22)は**非 TTY で 1 フレーム静止**
  → agent の Bash では preview にならない。エージェント側は `anim preview -o preview.gif` →
  `SendUserFile` で見せる。`led play` は**ユーザーが自分の端末で**動かす用、とスキルに明記。
+ **base IR の出所(end-user 文脈)**: repo dev は `outputs/merged_*.json` を base にできたが
  あれは gitignore のローカル専有物。**プラグイン利用者は持たない** → スキルは「AM Master /
  公式 web UI から export した完全 config を base に」と誘導。理由(JSON_START 全消去 + LED
  read-back 不可ゆえ base が現状 LED を保持していないと消える)を明示。`read keymap` は keymap 半分のみ。
+ **自己完結**: プラグインは `~/.claude/plugins/cache/` にコピーされ **repo の tools/ examples/
  rules/ を参照できない** → 効果カタログ(text_scroll/solid/hue_cycle/stripes/gradient_scroll)と
  小さなレシピ例を**スキル内に inline**(`examples/led/` を指さない)。400 行制限内(~275 行)。

### 検証 🟢

+ **レシピ形式の罠を実測で是正**: 当初 inline 例を `{"text_scroll":{…}}`(ネスト)で書いて
  `unknown effect None` で失敗 → 実形式は**フラット + `"effect"` 判別キー**
  (`{"effect":"text_scroll","text":…}` / sequence は各セグメントに `effect`)。3 例とも
  `anim preview` で render 成功(text 80f / sequence 136f / hue 90f)= **inline カタログが
  authorable であることを確認**(利用者の唯一の参照ゆえ正確性が要)。
+ frontmatter は `cyberboard-device` に倣う(name / description / allowed-tools: AskUserQuestion /
  SendUserFile / Read / Write / Bash)。スキルは英語記述 + **日本語対話**を明記。

### 次

+ #6 sprite 縦スクロール + LED デザイン vision ループ(生成→render→vision 批評→改訂)。#1 epic。

## 2026-06-23 (続23) — 製品化 #3: Claude Code プラグイン scaffold(PR #13 merged)

issue #3。CLI を Claude Code プラグインとして配布する scaffold(MCP のみ)。`90` 続21 の
`cyberboard-mcp` を同梱配線。

### 構成

+ `plugins/cyberboard/.claude-plugin/plugin.json` — `mcpServers` で `cyberboard-mcp` を inline 宣言。
  **schemastore の `claude-code-plugin-manifest` スキーマで検証**(`uv run --with jsonschema`)。
  `$schema` 付き。**`version` は省略** → SHA ベース自動更新(#2 でスキル追加時の bump 忘れ回避、advisor 指摘)。
+ `.claude-plugin/marketplace.json` — 単一リポ marketplace。相対 `source: ./plugins/cyberboard`。
  **marketplace 用スキーマは存在しない(URL 404)ため `$schema` 無し**(config-practices の例外)。
+ install: `pip install 'cyberboard-cli[mcp]'`(console script を PATH へ)→ `/plugin marketplace add
  GeneralD/cyberboard-cli` → `/plugin install cyberboard@cyberboard-cli`。skill は `plugins/cyberboard/
  skills/<name>/SKILL.md` 自動検出(マニフェスト追記不要)なので #2 はこの上に乗るだけ。

### レビュー(Copilot 4 件、全採用)

+ README の `sh` フェンスに `/plugin …`(Claude Code コマンド)混在 → シェル(pip)と `text`(/plugin)に分割。
+ 前提条件の文を条件節へ書き換え(pip install 前に有効化すると MCP 起動失敗)。
+ plugin.json / marketplace.json の説明「Bundles」が過大 → 「Wires up …(別途 pip install 要)」へ(advisor の
  「過大評価するな」と同趣旨)。CodeRabbit SUCCESS、新規指摘なし → squash-merge + delete-branch。

### 留保(正直な範囲)

+ schema 検証は**整形式性**の確認で、**実ロード/MCP 起動**の保証ではない。`claude plugin` に非対話 validate は無い
  (details/enable/install/marketplace のみ)。live `/plugin marketplace add` は相対 source が git 経由でしか
  解決されないため **main merge 後でないとテスト不可** → PR 本文に明記して merge。

## 2026-06-23 (続22) — 🎉 製品化 #12: LED アニメをターミナルで再生(`cb_led play`、半角ブロック)

issue #12。LED アニメ(40×5)を GIF ビューア無しで**端末から直接再生**。CLI コア(#5 merged)の上の
純粋表示機能(デバイス I/O 無し)。`experiments/perkey-layout/render_tui.py` の truecolor ANSI を
半角上ブロック化したもの。

### 実装(`tools/cb_led.py` に `play` サブコマンド追加)

+ **半角上ブロック `▀`(U+2580)**で truecolor 描画: **fg=上ピクセル / bg=下ピクセル** → 1 テキスト行=縦 2px。
  5px = **3 テキスト行**(最下行は上半分=5 行目のみ、下半分=端末既定背景 `49m`)。横 40px = **40 文字**。
  = `.config` statusline と同型の塗り分けで 40×5 グリッドをそのまま端末に表現。
+ **入力 2 系統**: GIF(`-i art.gif`、`_gif_frames` 再利用、pillow 要)/ IR config(`-i cfg.json --slot N`、
  ir2gif と同じ frame 抽出、**pillow 不要**=core-only で動く)。`--slot` 有無で分岐。
+ **再生**: TTY ではカーソルを毎フレーム `ESC[3A` で巻き戻しインプレース描画。`ESC[?25l/?25h` で
  カーソル隠し/復元(`Ctrl-C` も finally で必ず復元)。ノブ `--once`/`--loop N`(既定=無限)/`--fps`/
  `--speed-ms`/`--scale`(横複製)/`--resample`。`speed_ms`(IR)or GIF duration でフレーム送り。
+ **縮退**: 非 TTY(パイプ)は 1 フレーム静止 + 警告。COLORTERM≠truecolor は警告のみ(capable 端末を
  誤って潰さない best-effort)。単一フレーム config は静止表示。**256 cap 準拠**(超過は drop 警告)。
+ `cyberboard/cli.py` の `led` help を更新(gif2ir / ir2gif / **play** / recipe)。

### 検証 🟢

+ **pty で TTY 経路を実証**: `ESC[?25l`/`ESC[?25h`/`ESC[3A` 出力 + `--once` で正常終了(exit 0)を確認。
+ GIF/IR 両入力で 3 行 × 40 セル、最下行 `49m`、`▀`=UTF-8 E2 96 80 を確認。`--scale 2`=80 ブロック/行。
+ 256 cap 警告 / エラー系(slot 範囲・scale≥1・frame px 数)/ IR slot が pillow 無し `uv run` で動作。find-debug クリーン。
+ ⚠ `except KeyboardInterrupt: pass` に swallowed-error warning が出るが、Ctrl-C で再生停止する意図的
  idiom(finally で復元)= warning 容認(error でなくコミット非ブロック)。

### 対象外 / 次

+ per-key(`keyframes` 90)は web↔keyframes index マップ未確定(続15)のため display(40×5)のみ対象。
+ 将来 `anim play`(レシピ直再生)への拡張余地。LED デザイン agent(#6)の vision ループは GIF/端末両方で回せる。

---

## 2026-06-23 (続21) — 製品化 #4: MCP サーバ(`cyberboard-mcp`、CLI を subprocess で wrap)

issue #4。CLI の操作を MCP tool として公開。**CLI がコア**の方針通り、各 tool は
`python -m cyberboard.cli …` を subprocess で叩いて結果を返す(= MCP 面が CLI 挙動から乖離しない)。

### SDK の確定(実測で context7 の誤誘導を回避)🟢

+ context7 は最新 main の `mcp.server.mcpserver.MCPServer` を提示したが、**pip 安定版には存在しない**
  (`uv run --with mcp` で実測 → `ModuleNotFoundError`)。リリース版は `from mcp.server.fastmcp import
  FastMCP`(`.tool` decorator + `.run()` あり)。→ **`FastMCP` を採用**。bleeding-edge 名を鵜呑みにせず実測。

### 実装(`cyberboard/mcp_server.py`)

+ `_run(args)` = `subprocess.run([sys.executable,"-m","cyberboard.cli",*args], capture_output=True)` →
  `{ok, exit_code, stdout, stderr}`。`_run_json` は `--json` 系の stdout をパースして構造化。
+ **11 tool**: list_devices / device_info / doctor / verify / build_keymap / render_animation /
  preview_animation / gif_to_ir / ir_to_gif / read_keymap / **write_config**(破壊的=既定 dry-run、
  `execute=True` で実書込)。LED 系は同 env の `[led]` extra が要る(無ければ CLI の clean hint が stderr に出る)。
+ モジュール名は `mcp_server.py`(`mcp.py` だと SDK の `import mcp` を shadow するため回避)。SDK 未導入時は
  import 段で `SystemExit("… pip install 'cyberboard-cli[mcp]'")`。
+ pyproject: extra `mcp = ["mcp>=1.2"]`(+ `all` に追加)、console script `cyberboard-mcp = cyberboard.mcp_server:main`。

### 検証 🟢

+ `uv run --with mcp`: **11 tool 登録**を確認 / `list_devices()` が**実機 R4 を JSON 構造化**で返す
  (`{port, product_id:CB04, …}`)/ `verify(bad)`=ok:False exit:1 / `doctor()`=exit:0 ok:True / `main` callable。
+ find-debug クリーン。README に **MCP server** セクション(install `[mcp]` / `cyberboard-mcp` / client config 例 / tool 一覧)。

### 次

+ #3 plugin(`.claude-plugin/plugin.json` + marketplace、MCP `cyberboard-mcp` 同梱 + user-facing skill)→
  #2 cyberboard-led を plugin skill 化 → #6 sprite + LED design agent。

## 2026-06-23 (続20) — 製品化 #8: 単体配布をクリーン環境で実証 + README に Install/Usage

issue #5(PR #9)で pyproject まで入ったので、issue #8 の残作業は**実証 + ドキュメント**に縮小。受け入れ条件
(install 後どこでも `cyberboard --help` / LED 不要構成では pillow 不要)を**クリーン環境で実機確認**。

### 実証 🟢(`$CLAUDE_JOB_DIR/tmp/pkgtest`、すべてリポ外の throwaway venv)

+ `uv build --wheel` → **core-only venv** に `pip install <whl>`: `cyberboard --help` が任意 dir で動作 /
  `devices` が実機 R4 検出 / pillow 不在 / `anim preview`(有効レシピ)→ **traceback でなく clean hint + rc=1**
  (= #9 の遅延 import 対策が wheel の bundled `_tools` レイアウトでも効く)。
+ **`[led]` venv**: `pip install '<whl>[led]'` → `anim preview` が GIF 生成。**bundled fonts(tom-thumb)が
  wheel 同梱で機能** = force-include `tools`→`cyberboard/_tools` が font 解決込みで正しい。
+ `uvx --from . cyberboard --help` / **`uv tool install '.[led]'` → `cyberboard --version` が /tmp から動作**
  → uninstall でクリーンアップ。= uv tool / uvx / pipx / pip の全経路を確認。

### README

+ 古い framing(「planned CLI」「CLI 未実装」「live capture が唯一の gap」)を是正。**Install**(uvx /
  uv tool / pipx / pip の git+URL、core vs `[led]` extras、clone での `uv run --extra led`)+ **Usage**
  (command 表 + 例)を追加。Roadmap を実状(M0-M3/M5 done、製品化進行中、partial write 非対応の注記)に更新。
+ PyPI 未公開ゆえ install は `git+https://…cyberboard-cli`(default branch=main)。公開は将来。

## 2026-06-23 (続19) — 製品化 #5: CLI コア統一(`cyberboard` 単一エントリ + pyproject)

POC→PR フローの最初の PR(`feat/5-cli-core`)。バラバラの `tools/cb_*.py` を**単一の
`cyberboard <command>` に統一**し、pure Python・**マルチハーネス**(MCP/skill はこのコアを叩く)
の土台を作る。issue #5。

### 設計(`cyberboard/cli.py` = 薄いディスパッチャ)

+ tools/ を `sys.path` に載せ、要求された command の module だけ **lazy import** → `sys.argv`
  を差し替えて `mod.main()` を呼ぶ。各ツールの挙動は不変(移動・改変なし=低マージリスク)。
+ lazy ゆえ **optional 依存の欠落が綺麗なメッセージで出る**(pyserial=device I/O / pillow=LED)。
+ command 表: `devices`/`device`/`doctor`/`build`/`verify`/`led`/`anim`/`read`/`write`/`set-time`。
  `devices`=`cb_device list` のように prepend で吸収。`-h`/`--version` あり。
+ Claude/MCP 固有を**一切持たない**(= マルチハーネスの核。MCP #4・skill #2 はここを呼ぶだけ)。

### パッケージ化(pyproject.toml, hatchling)

+ `[project.scripts] cyberboard = "cyberboard.cli:main"`。deps=**pyserial(core)**、extras=
  `led`(pillow)/`verify`(jsonschema)/`all`。`requires-python>=3.11`(tomllib 使用)。
+ wheel は `cyberboard` パッケージ + **force-include `tools`→`cyberboard/_tools`** で cb_* を同梱。
  ディスパッチャは **repo の `../tools` を優先、無ければ `cyberboard/_tools`** を見る → editable と
  wheel の両方で動く。
+ **レビュー High(`uv run tools/cb_*.py` が pyserial 落ち)を根治**: pyproject 存在で `uv run` が
  project を build し core 依存を入れる。LED 系は `uv run --extra led cyberboard anim …`。

### 検証 🟢

+ `python -m cyberboard.cli` で help/`--version`/unknown(rc=2)、`anim preview`(pillow lazy)、
  `led --help`(prog=`cyberboard led`)、`devices` が**実機 R4 `CB04` を検出**。
+ `uv run --extra led cyberboard …`(entry point)も OK。`uv build --wheel` で cb_* が
  `cyberboard/_tools/` に入ることを確認。

### 次

+ #8 配布整備(uv/pip ドキュメント・PyPI メタ・pipx)→ #4 MCP(コア wrap)→ #3 plugin →
  #2 cyberboard-led を plugin skill として再構築(CLI コア呼び出し)→ #6 sprite + LED design agent。

## 2026-06-23 (続18) — M5 続: 模様回転=marquee を手続き系で実装(hue_cycle / stripes / gradient_scroll)

3原型のうち第2の手続き系(advisor 順序:text → pattern → sprite)。8:1 アスペクトで幾何回転は破綻
するので **marquee(スライド/サイクル)として実装**(advisor 解釈)。cb_anim に 3 エフェクト追加、
全て**循環構造=継ぎ目なし by construction**。

+ **`hue_cycle`**: 色相環サイクル。`spread`(幅に渡る色相回転度)で「全面明滅」↔「虹が幅いっぱいに流れる」。
  cycle_frames で長さ。frame[N]=frame[0](hue%1.0=0)で seamless。
+ **`stripes`**: 色帯スライド。period=`len(colors)×band_width` の modulo タイリング。`slant` で斜め帯。
+ **`gradient_scroll`**: `colors[-1]→colors[0]` で閉じたグラデを横流し。`width` 1 周、`slant` で斜め。
+ ヘルパ追加: `_hsv_hex`(colorsys, hue 周期で seamless)/ `_lerp_hex`(色補間)/ `_colors`(色リスト検証)。

### 検証 🟢(機械 + 目視)

+ **継ぎ目なし機械検証**: wrap(last→first)のピクセル変化量が中央値と一致 + spread=0(完全に均一な動き)。
  hue: N=90 change=200 wrap=200 / stripes: N=15(=3×5) change=40 wrap=40 / gradient: N=40 change=200 wrap=200。
  全フレーム distinct(誤った全同一なし)。
+ **目視(montage)**: hue=幅いっぱいの虹が左へ流れる・鮮やか / stripes=斜め3色帯(slant=1)がスライド /
  gradient=ocean 風グラデ(navy→cyan 閉ループ)が右へ。3つとも 40×5 で意図通り・バンディング無し。
+ 例: `examples/led/pattern-{hue,stripes,gradient}.json`。MAX256・direction guard は text_scroll と共通。

### 次

+ **キャラ縦スクロール(sprite)+ LED デザイン agent**(3原型で唯一 vision ループが価値を出す)。
+ **ユーザー提案: ディスプレイ作成を「スキル」化**(AskUserQuestion で対話的に)→ リポを **claude plugin /
  CLI / MCP 対応**へ。対話性=スキル層(Claude 駆動)、CLI/MCP=非対話の素(render/build/write)で分離。設計中。

---

## 2026-06-23 (続17) — 🎉 M5 続: 宣言的レシピ生成 `cb_anim.py`(text_scroll seamless + sequence 連結)

ユーザーがコミュニティ作品を3原型に整理(**テキスト横スクロール / キャラ縦スクロール / 模様回転**)

+ 欲しい4ノブ(①継ぎ目なしループ ②長さ ③MAX256 ④短いの連結)を提示 → **「開始しよう」**。
advisor レビューで設計を締め、**text-scroll を end-to-end で先に通す**(advisor 順序)。

### advisor の効いた指摘(設計の芯)

+ **3原型は対等でない**: text/pattern = **手続き的**(params だけ)、キャラ縦スクロール =
  **スプライト的**(実際の絵が要る)。→ レシピ schema は 2 系統。**vision ループ(デザイン agent)の
  価値はスプライト系だけ**に出る(text は決定論的で目視改訂の余地が無い)。
+ **コーデック一本化**: cb_anim はフレーム列を生成、cb_led の2変換を共有ヘルパに切出し両者で使う。
+ **出力は IR が正**(書込対象)— palettized 経由で往復させる意味が無いから直接 IR を吐く。
  ⚠ **訂正(続16 の "13200/13200 可逆" は低色数ファイル限定)**: 「40×5 は ≤200 色 < 256 だから
  GIF 可逆」は**単一フレームの理屈で一般には誤り**。GIF はアニメ全体で 1 グローバルパレット(256 色)
  ゆえ**全フレーム横断 >256 色のリッチ素材は色が削られる**(merged_20250916 slot1=66 frames 全 distinct
  で `ir2gif→gif2ir` が 9917/13200=非可逆)。Pillow の P-mode per-frame quantize でもローカルカラー
  テーブルは書かれず改善せず(検証→不採用)。さらに**連続同一フレームは coalesce**(merged_20250914
  =41→10)。**低色数(我々の生成物)は可逆**(cb_anim text=2色で 18000/18000)。→ ir2gif は**ビューア**、
  リッチ素材の可逆フォーマットは IR JSON 自体。
  + **続17b フォロー(silent cap 禁止の徹底)**: ir2gif に劣化警告を追加(`>256 色横断` / `連続同一
    フレーム数`)。実測発火: merged_20250916 slot1=「3416 色 > 256」、merged_20250914 slot2=「28 連続
    重複 coalesce」。cb_anim は `frames_to_gif` 直叩き(ir2gif 非経由)なので**意図的 solid 重複は
    誤検知しない**=警告は劣化ビューア経路にだけ限定。`direction:"right"` も検証(ink 重心が右へ単調
    移動 rightward52/leftward9、gap 巻き戻りのみ左)。残: wrap 89→0 の実機スタッタ確認(ハード待ち)。
+ **フォントは自作禁止** → public-domain の **tom-thumb(Fixed4x6, 5px, MIT)** を vendoring
  (`tools/fonts/`, u8g2 ミラー)。**40×5 で legibility 実描画確認**(`HELLO` 大文字 5px フル、
  小文字+デセンダ `gjpqy` も 5px 内クリップ無し)= 省けない目視ゲートを通過。
+ **256 cap × スクロール周期**: seamless 周期 = `strip幅`。step をノブ化し生成時に警告。
+ **8:1 ゆえ幾何回転は変** → 「模様回転」= marquee(色相サイクル/ストライプ流し)と解釈(次段)。

### `tools/cb_anim.py`(純粋 file→file、Pillow 依存)

+ `render -r recipe.json -b base.json -o config.json [--gif]` / `preview -r recipe.json -o art.gif`。
+ レシピ = 宣言的 JSON。単一エフェクト or `sequence`(連結)。**ホワイトリスト式=生コード非実行**。
  recipe JSON は出力 GIF Comment に同梱。
+ エフェクト v1: `text_scroll`(`text/fg/bg/step/spacing/gap/direction`)+ `solid`(`color/frames`)。
+ **cb_led リファクタ**: `frames_to_page`(display patch・per-key 維持・256 cap=単一真実源)+
  `frames_to_gif`。gif2ir/ir2gif も新ヘルパ経由に置換(挙動不変、anim 産 IR が full schema pass で回帰確認)。

### 実証(全部目視 + 機械検証)🟢

+ **①継ぎ目なしループ**: `gap:0` トーラスタイリング。`AM CYBERBOARD R4` 90 フレーム、wrap
  モンタージュ(frame 89→0)が **1px ずつ連続シフト・段差ゼロ** = seamless 成立を目視確認。
+ **④連結**: `sequence:[緑HELLO(gap40), solid 6f, 赤WORLD(gap40)]` = 136 フレーム。色がセグメント毎に
  切替わり HELLO→WORLD→ループを目視。
+ **③MAX256**: 480 フレーム展開 → 生成時警告 + truncate、IR `frame_num=256`。
+ guard: 不正カラー `#zzz` / 未知エフェクト `wobble` を raise。anim 産 IR は jsonschema full validation pass。
+ ⚠ 軽微: preview GIF は Pillow が連続同一フレームを coalesce(136→127)するが duration が畳まれ
  再生は等価。**IR は全フレーム保持**(=書込対象は正確)。

### 次

+ **キャラ縦スクロール(スプライト)エフェクト + LED デザイン agent**(生成→render→vision 目視→批評→
  改訂)。3原型でここだけ agent の価値。スプライトは AI 生成 or 画像。40×N を 5px 窓で縦送り。
+ 模様回転 = marquee(色相/ストライプ)エフェクト。`led.toml` 合成マニフェスト。TUI エディタ。
+ per-key(keyframes)は依然 web-84↔keyframes-90 index 相関待ち(続15)。

---

## 2026-06-22 (続16) — 🎉 M5: GIF↔IR(display)コーデック `cb_led.py` + per-key 物理配置の web 抽出

LED オーサリングの第一レンガ。**display(40×5)を GIF と相互変換**し、コミュニティ JSON 継ぎ接ぎの
代わりに **5×40 ドット絵 GIF を作る/共有する**主軸を確立(`90` 続15 のアイデア確定 → 実装)。

### `tools/cb_led.py`(純粋 file→file、Pillow 依存)

+ `gif2ir -i art.gif -b base.json --slot N -o config.json`: GIF の各フレームを 40×5 に
  ダウンサンプル(`--resample nearest|box|lanczos`、既定 nearest=ドット絵向き)→ display
  `frames`(200px, `index=y*40+x`)へ。**slot 1/2/3 = page_index 5/6/7**。base は完全 IR 必須
  (JSON_START 全消去)。**per-key `keyframes` は base から維持**(index マップ未解明ゆえ触らない)。
  `speed_ms` は GIF duration 由来(or `--speed-ms`)。GIF に埋まったレシピも表示。
+ `ir2gif -i config.json --slot N -o art.gif [--recipe …]`: IR の display フレームを 40×5×scale
  (既定 ×16=640×80)のアニメ GIF に。目視確認用。`--recipe` で GIF Comment にプロンプト同梱。
+ `recipe art.gif [--set …]`: GIF Comment Extension の R/W(GIF に EXIF は無いので Comment が
  レシピ格納先)。
+ **256 cap** 🟢: firmware 再生上限 256/slot(続5)→ 超過フレームは drop して警告(silent cap 禁止)。

### ラウンドトリップ実証 🟢

+ merged slot1(page5, 66 フレーム)→ `ir2gif` → `gif2ir`(**別 base 上**)→ **display
  13200/13200 px 完全一致**、keyframes(42)維持、recipe 往復一致、出力は `cb_verify` schema pass。
+ 任意サイズ GIF(320×40)→ 40×5 ダウンサンプル OK。300 フレーム GIF → 256 に cap + 警告を確認。
+ = **同じ 40×5 マップが双方向(描画↔サンプル)に使える**(続15 の TUI/PNG 実証 = `render_tui.py` を
  コーデック化したもの)。display は 1:1 マップ既知なので**今すぐ可**。

### per-key は index マップ待ち(open item)🔴

+ `experiments/perkey-layout/r4-perkey-layout.json`: web UI(`diy.angrymiao.com/in-switch-led`、
  Vue `styles[]` の DOM `.led`)から **83 個の in-switch LED 物理座標 {i,x,y,w}** を Playwright 抽出。
  ジオメトリは確実だが、**web-index(84)↔ device keyframes-index(0-89)の対応が未確定**(続15)。
  export 相関パス(既知パターンを焼く/エクスポート順で相関)が要る。
+ `experiments/perkey-layout/render_tui.py`: truecolor ANSI + PNG レンダラ。per-key=物理配置、
  display=40×5 1:1。同マップが双方向に使えることの実証。
+ → **per-key GIF オーサリングは index マップ確定後**。display の GIF コーデックは独立に完成。

### 次

+ LED デザイン agent(prompt→GIF 生成→`ir2gif` で render→vision で目視→批評→改訂ループ)。
+ `led.toml` マニフェスト(slot ごとに GIF/JSON/merger 資産を合成。miaomerge `merge_configurations.rs` 参照)。
+ per-key の web-index↔keyframes-90 相関(open item)。実機 end-to-end(build→cb_led→cb_write→目視)。

---

## 2026-06-22 (続15) — per-key LED を「物理配置 GIF からサンプル」案 + ImageFile.py の正体訂正

ユーザー案: display(40×5)同様に **per-key 灯(`keyframes` 90個)も「キーボード物理配置を模した GIF に描き、
各キーの座標のピクセルをサンプル」**して作れないか(QMK/VIA のレイアウト塗りと同型。per-key RGB authoring の理想)。

### 確認できた事実

+ **能動ページ(5/6/7)の per-key keyframes は 90px**(display は 200px)。工場 config で確認。
+ **前提条件 = per-key index(0-89)→ 物理(x,y)マップが必要**。だが **per-key 90 ≠ keymap 物理キー 81**
  (続10)で、**90 要素の並び順は未デコード🔴**。display は 1:1(`index=row*25+col`)で既知だが per-key は別系統。
+ **`ImageFile.pyc` をデコンパイル(`_re/pycdc`)→ 正体は「ファーム hex/bin イメージ parser」**
  (`T_ImageFile`/`T_SubSeg` Address/Data, `HexStringToList`=IAP)。**rules の「画像→LED 変換(推定)」は誤り**
  (`20` 訂正済み)。= **per-key 座標マップは Python に無い**。抽出済み web 資産(`_re/keycode_*.json`)にも無い。
+ → **per-key 座標マップは web UI(per-key 灯エディタ)にある**。ユーザーの Playwright 案が正しいルート。

### 取得方針(次)

+ **Playwright で <https://diy.angrymiao.com/keyboard/> の per-key/PCB 灯エディタ**を開き、(a) 各キー要素の
  座標 + index を DOM/SVG/Vue data から読む、または (b) **既知パターンを塗って JSON export → keyframes 配列の
  どの index が変わったかで index↔物理を相関**(export 順=配列 index 順なので最も曖昧さが無い)。公開サイト=
  プライバシー問題なし。これで 90 要素の index→(x,y) を確定 → per-key も GIF authoring 可能になる。
+ 代替: 実機で index 毎に 1 灯ずつ点灯→撮影(tedious、device+目視要)。web UI が優位。
+ display(40×5)は 1:1 マップ既知なので **GIF authoring は今すぐ可**(per-key だけがこのマップ待ち)。

---

## 2026-06-22 (続14) — 🎉 M3 build 達成: keymap.toml → IR(`cb_build.py`)+ ラウンドトリップ実証

`build`(独自スキーマ TOML → 焼き込み用 JSON = 完全 IR)の本体を実装。**純粋 file→file**(デバイス I/O 無し)。
①位置(`resolve_position`)+ ②値(`keycode`)が揃ったので残りの「TOML→layer_data override + 機能テーブル
組立」を実装した。

### `tools/cb_build.py`

+ **build**: `-k keymap.toml [-b base] -o config.json`。base IR を deep-copy → toml を差分適用:
  + `[layer.1-7]`(1-indexed→配列 N−1): 位置(別名/座標)→idx、値(可読名/`#…`)→code、該当 idx を上書き。
  + `[[swap_key]]`/`[[exchange_key]]`/`[[macro]]`/`[[fn_key]]`: 提示時は**当該テーブルを全置換**(`*_num`=実数)。
    省略時は base 維持。**swap/exchange は write 送出、macro/fn は R 系列が送らない(§5)→ build が警告**。
  + base 必須(`-b` or `[meta].base`)。`refresh_keymap_from_device` は build では非対応(pure step)。
+ **dump**(逆変換): `--dump config.json [--full]` で IR→keymap.toml。占有位置を別名/座標で出力 + 機能テーブル。
  `--full` は全 200 位置(クリア `.` 含む)を出して base 非依存の厳密ラウンドトリップを可能に。

### ラウンドトリップ実証(無損失の成立条件、`build(dump(C)) == C`)

+ **工場 config を `--full` dump → 別 base(merged)上で build → key_layer 1400/1400 完全一致**
  + swap/macro/fn テーブルも再現。base 非依存で C を復元できた = スキーマ無損失が end-to-end で成立。
+ 現実的な小パッチ(caps→lctrl, esc→電源 passthrough, swap a↔b)でも: override が正しい idx に着弾 /
  未指定位置は base 不変 / **LED(page_data)は base から継承**(=「keymap だけ変更・LED 維持」が build で成立)。
+ 出力 config は schema 検証 pass(`cb_verify`, jsonschema 完全検証も OK)。

### 実データで判明した型の緩さ(忠実保持が必要)

+ TOML 配列テーブルは **1 行 1 キー**(spec 例の詰め書きは無効 → 修正)。
+ macro の `out` と `intvel_ms` は**長さ不一致を許容**(工場 macro idx2: out=2 / intvel=1)→ 等長強制を撤廃。
+ **placeholder エントリ**(全 `#00000000`)は工場 exchange に 7 件(num=0)→ dump で除外、`*_num`=実数で再計算。

### 次

+ LED `led.toml` ソース合成(merger/miaomerge の replace/combine 相当を build に取込)。現状 LED は base 継承。
+ 実機での end-to-end(`build` → `cb_write --execute` → 目視/`[6,9]` 読戻し diff)。

---

## 2026-06-22 (続13) — M3 着手: keymap.toml v1 設計確定 + R4 別名表を工場出荷 layer0 から生成

keymap.toml v1 仕様を確定(`40` §独自スキーマ案、advisor レビュー反映)し、その内蔵テーブル②
**R4 別名表(位置の名前空間 ① = 別名↔座標)**を機械生成した。

### keymap.toml v1 設計(要点、`40` に詳細)

+ **差分パッチモデル**: `JSON_START` が全消去(部分書込 非対応, 続8)ゆえ build は完全 IR を生成。
  toml は **base IR への override のみ**。LED は base 由来(読み戻し不可)、keymap は任意で `[6,9]`。
+ **2 名前空間**: ①位置 = 座標 `r{row}c{col}` + 別名 / ②値 = 可読名 + 生 `#MMPPUUUU` passthrough。
  passthrough を第一級にして**無損失** → `toml→build→IR→write→[6,9]→toml` のラウンドトリップ検証可。
+ **1-indexed** `[layer.1-7]`(配列 index N−1、デフォルト layer1)。

### R4 別名表の生成(🟢 実装・検証済み)

+ ユーザーが**真の工場出荷 JSON**(`~/Downloads/AM CB Index.json`、リポ外ローカル)を提供。
+ **リマップ済み config は別名生成に使えない**ことを実証: merged_20250916 は `idx75`=LCtrl
  (工場は Caps)、`idx125`=Fn2(工場は LCtrl)。**工場出荷 layer0 を正典**にする必要がある。
+ `tools/keymap_alias.py`: `(usage page, usage id) → 可読別名`表(0x07/0x0C/0x92)を工場 layer0 に
  適用 → **81 別名**(物理キー 81 と一致、衝突 0)を `presets/r4-keymap-aliases.json` へ生成。
+ **別名は「機能」でアンカー**(物理位置でない)ので最下段でも正しい: `lctrl→r5c0`(idx125)は
  物理「左から五番目」だが機能で確定、`space→r5c6`, `fn→r5c10`(Fn2), `rctrl→r5c11`, 矢印 r5c12-14。
  → 続12 の「最下段 matrix 列≠物理位置」問題を**別名が吸収**(座標直書きだけが唯一の落とし穴)。
+ `resolve_position(token)`: 座標 `r\d+c\d+` 優先 → 別名表。range チェック + 不正入力で raise。
  自己テスト: 81 別名の round-trip / 座標優先 / 工場 layer0 の occupied 集合と一致 / bad input 全 raise。
+ 生成物(別名表)は**自作のレイアウト導出=コミット可**(README grid と同性質)。工場 config 自体は
  著作物ゆえ非コミット(リポ外)。

### R4 値コーデックの実装(🟢 ②値の名前空間、`tools/keycode.py`)

+ **ハイブリッド設計**(UI ラベル表 `_re/keycode_labels.json` 187 件を精査して判明):
  + 標準キー(0x07/0x0C)は**自作クリーン小文字名**。UI ラベルは標準キーをキーキャップ面 HTML
    (`!<br/>1`, `~<br/>\``)や unicode 矢印で持ち、かつ**14 件の重複**(Layer4-7, S Fn1-7…)= 逆引き不可。
  + ベンダー(0x92)は権威 UI ラベルの**一意サブセット**(Layer1-7/Fn1-7/LED/PCB/BT/2_4G/Win_Mac/
    Battery/Reset/TouchSen)を採用。LFn/RFn・NP・0x90/91/95 は除外 → passthrough。
+ **DRY**: 標準キー名 `STD_NAMES` を `keycode.py` に集約し `keymap_alias.py` が import(①位置別名と
  ②値が同一語彙=「a キー」が「a を出す」)。リファクタ後も別名表 81 件は**生成物 diff ゼロ**で確認。
+ **無損失検証**: 工場 config **全 1400 コード(7 レイヤ)で `code→name→code` 恒等**
  (566 named / 1 passthrough / 残り clear)。MM≠00・未解読は生 `#…` へ落として round-trip。
  名前表は**双方向 bijection**(135 codes、衝突 0)を assert。`.`/空=クリア、`#…`=検証+大文字化。
+ **副産物**: 工場 config の唯一の passthrough = `#00920A01`(Layer2 の Esc 位置=**電源キー** 0x0A01)。
  まさに黒箱の firmware 特別キーで、名前を付けず無損失で通る = passthrough 設計の妥当性が実証された。

### 次

+ `build`(base IR + keymap.toml override → 完全 IR)本体。①位置 resolver(`resolve_position`)+
  ②値 codec(`keycode`)は揃った。残りは TOML パース → layer_data へ override → 完全 IR 出力 +
  swap/exchange/macro/fn_key の組み立て。ラウンドトリップ(`toml→IR→[6,9]→toml`)を成立条件に。

---

## 2026-06-22 (続12) — ⚠ 訂正: 0x92 名は「内部定数」でなく「UI 表示ラベル」が正 + 特別キーは黒箱

続11 で 0x92 名を `app.js` の `r1/r2` 表から取ったが、それは**内部定数テーブル**(レガシー名
`KEY_FN`/`KEY_LEDSWITCH` 等)で **UI 表示名ではなかった**(ユーザー指摘「汎用 Fn なんて UI に無い」)。
権威ソースは別の **UI 表示ラベル表 `"#code":{text,desc}`(187 エントリ)**。`_re/keycode_labels.json`。

### 訂正(権威ラベル)

+ `#00920C0B` は内部名 `KEY_FN` だが **UI 表示 = `Fn2`**。「汎用 Fn」は誤り。
+ **Fn1-7(momentary)** = `0C20`/**`0C0B`**/`0C22`/`0C23`/`0C24`/`0C25`/`0C26`(**Fn2 だけ変則 0C0B**。
  続11 の「0C20-0C26=fnN, 0C21=欠番」は誤り。0C21 は `RFn3`)。**Layer1-7(永続)**=`0C0F-0C15`。
  **LFn/RFn 系**(左右別 Fn): `0C0D`LFnS / `0C0E`RFn / `0C21`RFn3 / `0C1A-0C1F`LFn1,3-7。
+ 機能: ディスプレイ LED(`01xx`: Next/On-Off/Light±/Speed±/Rotation/BT1-3/2.4G)、PCB=per-key 灯
  (`09xx`: Next PCB/Light±/On-Off/Speed±/SAT/Color)+NP ゾーン(`090B-090F`)、Win/Mac/Battery/
  Reset(`0922`/`0910`/`0A02`)、Touch Sen(`1300`)。

### ユーザー知見 + 方針決定: firmware 特別キーは黒箱

+ **電源 OFF 時はキーマップ無効**。起動は **[下段の特定キー(物理 左から五番目、idx125 に対応か)]+[Esc
  (idx0)]** の**ハードワイヤ電源コンボ**。これら「**移動不可キー**」は firmware 内部役割を持つ。
  内部名 `KEY_FN` 等はこの firmware 表現。
+ **ユーザー判断: ここはブラックボックスで差し支えない** → 詳細仕様は解明しない。
  **CLI は 0x92 を解釈せず passthrough**(保存・送信のみ)、`keymap.toml` は独自可読名へ機械マップ。
+ **matrix 訂正**: 続10 の「layer0 デコード=物理レイアウト(押し試験不要)」は**英字段のみ**成立。
  **最下段は matrix 列順≠物理位置**(idx125 が物理「左から五番目」らしい)→ 下段物理対応は要押し試験(未実施)。

---

## 2026-06-22 (続11) — 🎯 AM 独自機能 page 0x92 を公式 web UI から全解読 + レイヤーモデル訂正

ユーザー情報: 公式 UI は **<https://diy.angrymiao.com/keyboard/>**(Vue SPA、QtWebEngine が
リモートロード。app=インポート+書込専用 / web=エクスポート専用 / 編集は両方可 / **書込は app のみ**)。
fn1-7=momentary、layer1-7=永続、**デフォルト layer1**。

### やったこと

+ 公式サイトの JS チャンク 46 本(8.6MB)を取得 → `app.288be2f6.js` に**キーコード↔機能名表
  282 ペア(uniq 141)**を発見。`r1:"name",r2:"#MMPPUUUU"` 形式。生表は `_re/keycode_table.json`
  (gitignore 下)に保存。コミット側には解読した事実のみ記録(方針: 抽出物はローカル限定)。

### 確定事実 🟢

+ **page 構成**: 0x07 標準キー(208) / 0x0C メディア(12) / **0x92 AM 独自(31 uniq)**。
+ **0x92 レイヤー/Fn 機構**(UUUU=0x0Cxx): `0C0B`=KEY_FN(汎用 momentary) / `0C0F-0C15`=
  **layer1-7 永続**(`key_cmd_set_key_layerN`) / `0C20-0C26`=**layer1-7 momentary=fnN**
  (`key_hold_set_key_layerN`、`0C21`=layer2 hold は表に欠番) / `0C0D`=レイヤー左送り。
+ **0x92 LED/接続/system**: `0100`次ページ / `0101`on-off / `0102-0103`明るさ± / `0104-0105`速度± /
  `0106-0108`BT1-3 / `0130`2.4G / `0900-0903`ローカル灯効モード / `0A01`電源 / `0A02`factory_reset。
+ **UUUU は 16bit**: 私の旧 "idx125=0x0b" は誤読、正しくは `#00920C0B`(UUUU=0x0C0B)。デコーダは正。
+ **レイヤーモデル訂正**(続10 の誤り): 「layer0=base / layer1=Fn 専用」は**誤り**。**7 レイヤは対等**、
  配列 index 0-6=公式 layer1-7、デフォルト=layer1(index0)。Fn/layer は任意キーに置ける切替キーコード。

### アーキ整理(ユーザー確認)

+ **キーカスタムは web/app 両方可**(web=エクスポート, app=インポート)、**デバイス書込は app のみ**。
  → 我々の CLI は「app の書込」を内製化する位置づけ。keymap 編集の知識源は web JS(本解読)。

### 次

+ keymap.toml スキーマ設計(独自可読名 ↔ #MMPPUUUU。0x92 は `Fn`/`Layer2`/`MoLayer3`/`BT1`/`Led*` 等へ)。
+ 残🔴: tab_key/press_hold/change_key 書式 / MM 修飾ビット割当。

---

## 2026-06-22 (続10) — 🎯 キーマップ解明: matrix マップ / フォーマット / レイヤ / 設定種別

B3(主目的・keymap 側)。実データ(復元済み既知正解 = デバイス内容)を HID デコードして構造確定。
`experiments/keymap-matrix/`(`decode_keymap.py` + README)。

### 確定事実 🟢

+ **matrix = 25 列 × 8 行 = 200、`index = row*25 + col`**(各行が 25 ごとに始まる:
  使用 index = 0-14 / 25-39 / 50-64 / 75-89 / 100-113 / 125-139)。物理キー **81 個**は
  row 0-5 / col 0-14 に分布、row 6-7 と右端余剰列は未使用。右端列(col14)= Del/Home/End/
  PgUp/PgDn のナビ列(idx 14/39/64/89)。
+ **layer 0 をデコードすると物理レイアウトそのもの** → **押し試験不要で物理キー↔index 確定**。
  グリッド: row0=Esc/F1-F6/メディア/Del/Home、row1=数字段、row2=QWERTY、row3=ASDF段、
  row4=ZXCV段、row5=Fn/Alt/Gui/Space/矢印。
+ **キーコード `#MMPPUUUU`**: PP(usage page)実出現 = `0x07`Keyboard / `0x0C`Consumer
  (メディア) / `0x92`AM ベンダー Fn。MM=修飾 bitmask、`#00000000`=未割当。
+ **7 レイヤ**(公式 UI と一致): layer0=ベース / layer1=Fn(上段が 0x92 AM 機能に化ける) /
  layer2-6=追加(サンプルは未カスタム複製)。
+ **設定できるキー機能の種類**(`CyberBoardJson` クラス): `KeyLayer` / `FnKey` / `SwapKey` /
  `ExchangeKey` / `MACROKey` / `TabKey` / press_hold(`[6,13]`+`[6,11]`)/ change_key(`[6,11]`)。

### 未解明 🔴

+ **AM 独自 Fn(0x92)各コードの意味**(0x100-0x108, 0x130, 0x900-0x903, 0xa01, 0x0b…)。
  Python に無く **QtWebEngine の JS UI 側**で定義 → app の web 資産から要抽出。
+ `tab_key` / press_hold / change_key の正確なフィールド書式 + UI 機能名。
+ MM 修飾 bitmask の具体ビット割当(要実データ/実機確認)。

### 次

+ keymap.toml スキーマ設計(人間可読名 ↔ #MMPPUUUU ↔ 物理位置)。AM Fn 名は web UI 抽出後に拡充。

---

## 2026-06-22 (続9) — 公式の書込ゲート = `pages_num`(中古個体が書けない元凶を特定)

ユーザー談「メルカリ中古は**いきなり書けず**、初期化したら書けた。キーボード状態が公式アプリの
キャッシュと不整合?」を逆コンパイルで検証。**仮説の直感(デバイス状態が書込を阻む)は正しいが、
機構は「キャッシュ内容の同期」ではない**。

### 確定事実 🟢(`_re/dc3/KBSerialOption.py` json_download)

+ 公式が**デバイスから読む唯一の値は `pages_num`**(`cmd_check_pages [2,6]`)。**config の中身は
  読み戻さない**(`get_*` は全デッドコード=続8 で確認済み)。= 「読んでマージ」ではなく
  **ファイル(`global_info.json_path`)を正にしたクライアント側マージ + 全置換書込**。
+ 書込ゲート(原典):

  ```python
  if pages_num == 0:
      if sign(STATUELI)==0:
          if len(f_li)==6: json_sender()
          else: emit(404); "请从官网下载完整版json"   # ← 書込拒否
      else: json_sender()                              # 旧式モード
  elif pages_num == 3: json_sender()                   # 通常 R4(実機実測=3)
  # else 無し → pages_num が 0/3 以外なら json_sender() 不呼出 = 黙って no-op
  ```

+ **中古個体の説明**: `pages_num≠3`(おそらく空で 0)を返す → 404 拒否 or silent no-op =
  **「いきなり書けない」**。**初期化で完全 config 投入 → `pages_num=3` → 書ける**(症状と一致)。
  これは**クライアント側の過保護な前提チェック**で firmware ロックではない(推論🟡: その個体の
  pages_num 未実測。コードと症状は完全一致)。

### 我々のツールへの含意(優位)🟢

+ `cb_write.py` は**この `pages_num` ゲートを持たない** → `JSON_START`→フル config→`JSON_END` を
  無条件送出。**公式が「中古だから」と拒否する個体でも書きにいける**(pages_num=0 個体での実証は未、
  構造上は回避)。`30 §6-7` / `40` 反映済み。
+ device pages_num=3 vs file page_num=8 の食い違い: check_pages は「カスタム/有効ページ数」
  (slots 5/6/7=3?)等の firmware 内部カウントの可能性。空個体で 0 になる仮説と整合。要実測🔴。

---

## 2026-06-22 (続8) — 🎯 部分書き込みは非対応(JSON_START が全消去)+ read-back settle 遅延

B2(主目的直結): 「LED だけ送れば keymap は残る?」を実機検証。read-back の非対称性
(keymap は `[6,9]` で読めるが LED は読めない)を使い、**LED セクションだけ送って keymap を
省略**したトランザクションの前後で keymap を比較(`experiments/partial-write/`)。

### 確定事実 🟢

+ **keymap を省略すると keymap は全 `#FFFFFFFF`= NOR フラッシュ消去状態になった**
  (before 567 mapped → after 1400 全 0xFF)。LED-only 3008 フレーム送信、ACK SUCCESS。
+ → **`JSON_START` が設定フラッシュ領域を消去**し、各セクションが自領域を再書込、
  **送らなかったセクションは消去のまま** = **1 トランザクション = 設定全体の置換**。
  **部分書き込みは firmware が非対応**。
+ **分離管理の実現方法(確定)**: 必ず **read → merge → フル書込**。
  + LED 変更・keymap 維持: `[6,9]` で keymap 読戻し → フル書込。**今すぐ可能**。
  + keymap 変更・LED 維持: **LED は読めない**ので LED の IR を**ソースに保持** → フル書込。
  + = `40` の「安全側デフォルト」が実機で裏付けられた。分離は build 側の責務。

### 副産物: read-back は settle 遅延が必要 🟢

+ 復元のフル書込**直後**に keymap を読むと**全 `#00000000`(ゼロ)**(commit 未完了)。
  833/1400 一致(両方ゼロの位置だけ一致)。**~2 秒待って再読**すると **1400/1400 一致**(3 回連続)。
+ → **書込後の read-back 検証には settle 遅延(~2s)が必要**。`cb_read`/`cb_write` に反映予定。
+ デバイスは merged 既知正解へ復元済み(keymap 1400/1400 + LED)。

### 残課題

+ B3 物理キー↔matrix index(25×8)マップ / per-key 再生上限の実機検証 / LED read 経路の探索。

---

## 2026-06-22 (続7) — ライティング(per-key 灯効)= 公式 UI で 100 フレーム上限(別系統)

ユーザー指摘: 純正 AM Master には display アニメとは別に**「ライティング設定」があり、
1 アニメ 100 フレームまで作れる**(display の 300 とは別の上限)。

我々のモデルでは **ライティング = `keyframes`(各キーのバックライト 90 個)**(`10` 既述)。
display(`frames` 200px)とは別系統で、別の作成上限を持つ。

### 重要な反例(100 は firmware 上限ではない)

+ **既知正解 `merged_20250916_161615.json` の page 7 `keyframes` = 123 フレーム**(> 100)。
  これを実機に書込→**ACK SUCCESS**(以前 LED 目視も済)。= **100 は「公式 UI の 1 アニメ
  あたり作成上限」**であって firmware のハード上限**ではない**(display の 300 と同じ性質)。
  merger の `combine` 連結で 100 を超えて 123 まで伸ばせている。
+ 実測 keyframes(同設定): page5=42 / page6=42 / page7=123。display: 66/125/53。
+ **per-key の真の再生上限は未検証 🔴**: display の教訓「ACK≠再生」より、123 が ACK しても
  全 123 枚再生される保証はない(真値は 100 か 256 か中間か不明)。per-key は 90 キーしか
  無く**数字描画で数えられない**ため、display で使った目視カウント手法が使えない。
+ 構造上限は **256**: per-key `frame_index` は `[5,pi]` の `[2]` に **1 バイト**送出。

### スキーマ方針(enforce せず文書化)

+ **keyframes を 100 に cap しない**(= 既知正解 123 を弾くため不可)。`rgbFrameSet` 共有の
  **256(構造上限)を維持**し、`pageDatum.keyframes` の description に 100 UI 上限 +
  123 反例 + 再生上限未検証(🔴)を注記。`schemas/cyberboard-config.schema.json` 反映済み。
+ まとめ(ライティング/per-key の段モデル、display と非対称):
  公式 UI 作成 = **100/アニメ**(merger combine で超過可)/ 構造 = **256**(1B index)/
  firmware 再生 = **未検証 🔴**。display は UI300・firmware256(確定)。

---

## 2026-06-22 (続6) — ✅ 256 上限を公式オーサリング設定で最終確認 + スキーマに enforcement

続5 の 256 上限を「自作エンコードの癖では?」の疑いごと潰すため、**純正 AM Master の UI で
作成した 300 フレーム設定**(`AM CB Index (1).json`)で追試。元アニメ(0〜78)+ 暗転
(79〜255)の後ろ **256〜299 を赤ベタ `#FF0000` で上書き**して書込(キーマップは merger
既知正解保持、`frame_num=300`、data_frames=3444、ACK SUCCESS)。

+ **実機スロット 1 で赤ブロックは一切出なかった**(ユーザー確認「紫の画面は出なかった」)。
  = **公式オーサリング設定でも 256 で頭打ち** → 256 上限は firmware 由来で**完全確定**。
+ **3 段モデルを確定**(`experiments/frame-limit-256/README.md` に結論表として記載):
  firmware 再生 = **256/スロット**(真の上限・8bit カーソル)/ 公式 UI 作成 = 300/スロット
  (257〜300 は死にフレーム)/ プロトコル・ACK = 実質無制限(`frame_num` 2B=最大 32767、
  ACK は受理を示すだけ)。
+ **スキーマに 256 を enforcement**(ユーザー指示「schema にも配列の上限数を 256 と」):
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

+ slot1(page5)の各 display フレームに**自分の index を数字で描画**(40×5 LED に 3×5 フォント)。
  他スロットは最小化。スロットを 0,1,2… と数え上げ、**ループ直前の最大値+1 = 実格納/再生数**。
+ 検証: N=30 → **0–29 で正しくループ**(ACK=実格納、数字も判読可=ピクセル並びも正常)。

### 確定事実 🟢

+ **N=400 を書くと ACK SUCCESS だが、再生は 0–255 でループ = 256 枚で頭打ち**。
  → **真の per-slot 上限は 256(=2^8)。firmware の再生カーソル/index が 8 ビット**。
  + ACK 経路は 16 ビット(uncertainty の frame_num は 2B、display frame_index も 2B 送出)だが、
    **firmware 内部が uint8** のため 256 で切る。**ACK ≠ 実格納**の決定的実例。
  + **merger の `MAX_FRAMES=300` も AM Master の "~300" も不正確**(真値 256 を捉えていない過大マージン)。
    AM Master の「300 超で書けない」は自前 UI ガードで、我々のツールは迂回送信できるが firmware が 256 で切る。
+ ACK ラダー(gradient): N=400/800/1600 すべて ACK=True(rev[2]==1)。**ACK は上限を示さない**
  (1600 でも受理)。**唯一の真実は目視**(数字描画)。
+ 大量書込中に**ディスプレイに黄ドット3つ→リブート**の兆候(N=1600 付近)。書込後 `cb_doctor`
  で **HEALTHY**(キーマップ 94F 健在)。リセットからの復帰=実害なし。ただし巨大 N は避ける。

### per-slot 確定 + 公式 UI 上限 300 判明 🟢

+ **256 は per-slot**(実機確定): slot1=200(白数字)+ slot2=200(シアン数字)=合計 400 を書込→
  **両スロットとも 0–199 完走**。各スロット独立の 8bit index = **per-slot 256**、3 スロット計 ≥768 使える。
  `tmp/frame_slots.py`。
+ **公式 AM Master の「ドット作成画面」上限 = 300**(ユーザー現地確認)。merger の 300 はこれを写した値。
+ **完全な図式**: 公式エディタは **300 まで作成可**(UI ハードキャップ)/ firmware は **256 で再生ループ**
  → **257–300 枚目は作れるが永遠に表示されない**(公式エコシステム内在の「作成上限300 vs 再生上限256」
  不一致)。我々のツールは UI を持たず firmware 直叩きなので **各スロット 256 をフル活用可能**。
+ 残🔴(軽微): 256 超が「未格納」か「再生カーソルのみ 8bit ラップ」かは LED read 経路が無く区別不可
  (実用上どちらも「使えるのは 256」)。per-key(keyframes)は frame_index 1B 送出=構造上も 256(別途確認)。

### 「我々の符号化バグでは?」を排除(送信バイト実検証)

ユーザー仮説「JSON 側で枚数宣言が抜け/1B 切れしてるのでは」を、生成フレームの実デコードで否定:

+ **uncertainty [2,1] は page5/6/7 とも `frame_num=300` を 2B で正しく宣言**(切れなし)。
+ **全 300 フレーム送信**、display `frame_index` も 2B 正確: `256→lo=00 hi=01`, `299→lo=2b hi=01`。
+ = firmware は「300」宣言 + 300 枚の正データを受領した上で **256 しか再生しない** → **我々の符号化は
  忠実、256 は firmware 内部のバッファ上限**。
+ 傍証: 宣言値を uint8 で読むバグなら `300&0xFF=44` でループのはず。実際は **256 ちょうど** =
  剰余切り捨てでなく **256 枚バッファへの飽和格納**。
+ プロトコル上、枚数を伝えるフィールドは uncertainty の `frame_num` のみ(他に無い)。公式アプリの
  送信列(`send_r_series_all`)を忠実再現済み = **公式で 300 枚作っても同 firmware が同 256 でループする**
  はず(エディタが警告しないだけ。公式 300 枚の全再生は未検証の思い込み)。

### 純正設定の実査(上限フィールド不在を確証)

ユーザー提供の `~/Downloads/AM CB Index.json`(公式 DL)を全ネストキー走査:

+ **`max`/`limit`/`capacity`/`buffer` 系フィールドは皆無**。枚数関連は `page_num` / 各ページ
  `frames.frame_num`・`keyframes.frame_num` / `word_len` / `layer_num` / `*_num` のみ
  = **我々が既に正しく扱う集合と完全一致**。上限はどこにも JSON 宣言されていない=取りこぼし不可能。
+ このファイルの page5 は `frame_num=300` だったが、**これはユーザーが上限テスト用に公式 UI で
  300 まで増やした編集物**(工場出荷ではない)。要点は「**公式 UI は 300 まで作成させる**」=
  作成上限 300 と firmware 再生上限 256 の不一致が UI 側で防がれていないこと。
+ スキーマ検証 pass(`cb_verify.py`)= 我々のスキーマは公式形式(frame_num=300 含む)もカバー。
+ 次検証(ユーザー実施中): 公式 UI で **300 フレーム目に目印**を入れて DL → 我々のツールで書込 →
  目印が表示されない(=256 超は出ない)ことを公式オーサリング由来の設定で再確認。

### 反映

+ `10`(フレーム数上限)/ `schemas/cyberboard-config.schema.json`(frame_num $comment)を **256** で更新。

---

## 2026-06-22 (続4) — doctor(疎通診断)+ JSON Schema(IR 形式化)追加

ツール群を 2 つ拡充。どちらも実機/実データで検証済み。

### `tools/cb_doctor.py` — 非破壊の health チェック(AM Master の泣き所対策)

ユーザー談「最初の1週間 AM Master でまともに書けず泣き寝入り」→ **書かずに疎通だけ確かめる**
doctor。`30` §6 で特定した AM Master 不安定要因を**そのままチェック項目化**:

+ ✓ `cu.usbmodem*` 列挙(0 件→データ非対応ケーブル/未接続を示唆)
+ ✓ `[1,1]` で CyberBoard 同定(ドングルのみ/他デバイスは個別に診断メッセージ)
+ ✓ **排他オープン**(失敗=他アプリ=AM Master がポート占有。書込失敗の筆頭要因)
+ ✓ フレーム往復 CRC-8(双方向)/ ✓ **bulk read-back [6,9] 94 フレーム全 CRC OK**
  (= 多フレーム転送の健全性 = 書込経路の良好さの強い証拠。ただし書込はしない)
+ 実機: **verdict HEALTHY**(LG モニタ `cu.usbmodemABC...` は正しく無視)。read-only のみ
  (`[6,17]` reset 等は一切送らない)。

### `schemas/cyberboard-config.schema.json` — 純正/IR 形式の JSON Schema(draft 2020-12)

ユーザー提案「構造が分かるたびスキーマ化=ドキュメント兼用」。`10`/`CyberBoardJson.py`/実データ
から起こし、**スキーマ検証が実 format の落とし穴を炙り出した**(スキーマ作成の価値そのもの):

+ **`"//"` コメントキー**が JSON 内に混在(中国語コメント。`key_layer`/`page_data` 等)→ 許容。
+ **`frame_index` が文字列 `"0"`** のページがある(非能動プレースホルダ。miaomerge の
  「数値/文字列混在」と一致)→ `numberish`(int|数字文字列)で受ける。
+ **非能動ページの `frame_RGB` プレースホルダが `#0000`**(4hex、正規 #RRGGBB でない)→
  `frameColor`(緩い hex)で受け、`hexColor`(厳密 #RRGGBB)は color ブロック専用に分離。
+ `valid` は bool/int/数字文字列を許容(`boolOrInt`)。
+ **検証結果**: merger `outputs/*`(1.3.7)+ 旧 `sources/*`(コミュニティ)**全てパス** 🟢。
+ 消費者 `tools/cb_verify.py`: config をスキーマ検証(書込前の事前チェック)。jsonschema
  未導入でも basic check に graceful 縮退。不正キーコード/範囲外 lightness を検出確認。

### 次にやること

+ 棚卸し済み(できること / 未解明)。未解明の優先 = **B2 部分書込**(LED だけ差替が成立するか)
  → **B5 応答コード** → **B3 物理キー↔matrix index**。実機が繋がっている間に B2 から潰す。
+ それらが固まったらサードパーティツールの仕様確定(言語/パッケージング/独自スキーマ TOML/IR/
  部分書込方針)。

---

## 2026-06-22 (続3) — 🎉🎉🎉 read 読み戻し発見(キーマップ完全ラウンドトリップ)+ 書込検証手法

「write できるなら read もできるか?」を実機で検証。**firmware は read コマンドに応答する**
(公式アプリは `cmd_get_*` を未使用=配線なしだが、デバイス側は実装済み)。

### 確定した重大事実(→ `30` §7 反映済み)

+ **[6,9] cmd_get_key_msg = キーマップ全体の読み戻し**。応答は **94 フレーム**、
  `06 09 [chunk_idx] [60B] [crc]` で書込([6,7])と同形。連結 → 4B キーコード列。
  + **書込→読戻しで 1400/1400 キー完全一致**(7 レイヤ×200、ミスマッチ 0)。末尾に
    ゼロパディング 10 キー(5640B 返却 vs 5600B 書込=94×60 固定長)。
  + → **キーマップは write→read→diff の自動検証が可能**(目視不要)。`tools/cb_read.py`。
  + レイヤ1 は `#00920xxx`(usage page 0x92 = AM 独自/consumer 系 Fn キー)。
+ **[6,15] cmd_get_flash = フラッシュ状態メタのみ**(`06 0f 00 00 05 14 00 00 00 c8...`
  = 0x0514=1300, 0x00c8=200 等)。**フレームデータのフルダンプではない**。
+ **[6,10] cmd_get_key_macro = 全ゼロ**(マクロ未定義)。
+ **LED フレームの読み戻し経路は未発見**([4,*]/[5,*] の read 変種なし)。
  → **LED 検証は当面 目視のみ**(下記ベーコン方式)。
+ 注意: **[6,17] は cmd_reset**。get 系([6,9/10/14/15])の隣なので誤送信厳禁。
  [6,14] get_anykey はキーキャプチャモード懸念で未検証(回避)。

### 書込が「効いた」ことの検証(no-op 曖昧性の排除)

+ ユーザー指摘: 現行と同一設定を書いたため「効いたのか無変化か区別不能」。
+ 対策として **ベーコン書込**: `merged_…json` の slot1(page5)を**真緑ベタ塗り(静止1フレーム,
  display 200px + per-key 90px とも `#00FF00`)** に置換 → `tools/cb_write.py --execute`
  で書込(2906 フレーム, ACK SUCCESS)。→ **Custom LED スロット1 を緑表示で目視確認**(LED 用)。
+ キーマップ用の完全自動検証は、**別キーマップを書いて [6,9] で読み戻す**ことで
  no-op 曖昧性を排除可能(未実施。元設定を保持しておき即復元する想定)。

### 成果物

+ `tools/cb_read.py` — `keymap` dump / `--json`(key_layer 断片出力)/ `--compare CFG`
  (config の key_layer と diff)。M2 read の中核。

### 次にやること

+ M2: read→IR(JSON)化 + `diff`。キーマップは [6,9] で確立。LED は読み戻し不可のため
  「書込んだ IR を正」として扱う(or 目視)。
+ LED 読み戻し経路の探索([4,*]/[5,*] や別カテゴリの read 変種、`Central.py` の HID 経路)。

---

## 2026-06-22 (続2) — 🎉🎉 M1 フル設定書き込み成功(実機 R4 / 3826 フレーム)

merger の既知正解 `outputs/merged_20250916_161615.json` を `tools/cb_write.py` で
**フル書き込み**し、`JSON_END` の ACK(`rev[2]==1`)を取得。M1 の write 経路が
実機で通った。

### やったこと

+ `_re/decompiled/JsonToCmd.py`(chunking/順序)+ `KBSerialOption.send_r_series_all` /
  `json_down`(送信ループ・総フレーム数の数え方)を精読。`TransJsonCmd` の全 builder
  バイトレイアウト(uncertainty/page_control/word_page/rgb_frame/key_frame/exchange/
  swap/key_layer_control/key_layer)+ 補助関数(key/rgb/unicode/rgba/int_to_bytes)を確認。
+ `tools/cb_write.py` を実装(cb_protocol/cb_device を再利用)。**デフォルト dry-run**、
  `--execute` で実書き込み。送信前後に `[1,1]` product_id プローブ。
+ `merged_20250916_161615.json` を書き込み → **ACK SUCCESS**。

### 確定した重大事実(→ `30`/`40` 反映予定)

+ **総フレーム数 = START と END を除く全データフレーム数**。`json_down` は `send_start()`
  後に `send_cmd_count = 0` リセット → `send_end(send_cmd_count)` に渡す(37105/37111)。
  END 値は**送信側が実送信数を申告**=自己整合。firmware は受信数と照合(=ドロップ検出。
  count 不一致は `rev[2]!=1` でリトライ、ブリックではない)。
+ **R系列送信順(実証)**: START → uncertainty[2,1] → page_control[2,2] →
  word_page[3,1] → rgb_frame[4,pi] → key_frame[5,pi] → exchange[6,1] → swap[6,6] →
  key_layer_control[6,8] → key_layer[6,7] →(ph_key/car_light は try/except)→ END[1,6]。
  **fn/macro/tab は R系列順に無い**(§5 注記が確定)。
+ **car_light は本構成では 0 フレーム**: `cmd_send_car_light_info` は空リストで
  `valid_li[0]` IndexError → `send_r_series_all` の try/except で握り潰し。spotlight 無し
  構成では送られない(=実機アプリと同挙動)。
+ **デコンパイル由来バグを修復**(忠実移植時の要注意点):
  + `JsonToCmd` line 105 `if key_frames is not None or ...` は**論理反転**(正: `is None`)。
  + `page_control_infos` / `word_page_infos` の**内側ループが欠落**(`control_infos=[]`,
    `word_len=0` で空)。clean な HATSU analog(`get_hatsu_page_control_info`)+ clean builder
    から再構築:page_control は 4 ページ/フレーム(`ceil(page_num/4)`)、word_page は
    28 文字/フレーム(`ceil(word_len/28)`)。
  + `swap_key_infos` の chunking で両分岐が同条件(`== usb_frame_count`)→ 11 件/フレームで再構築。
  + `get_key_layer_infos` line 314 `None.key_layer.layer_num`(self バインド崩れ)。
+ **フレームプラン実測**(`merged_20250916_161615.json`, page_num=8):
  uncertainty 1 / page_control 2 / word_page 1(page3 が word_len=28, unicode A-\\) /
  rgb_frame 2684((66+125+53)×11) / key_frame 1035((42+42+123)×5) / exchange 7
  (num=0 だが list 7 件=全 #00000000) / swap 1(4 件) / key_layer 95(control 1 + 5600B÷60=94)
  = **計 3826**。rgb+key=3719 が `90`(2026-06-21)の「3719 USBフレーム規模」と一致。
+ **応答**: `JSON_END` rev = `01 06 01 00...`(echo [1,6], `[2]=1` ACK, CRC `0x81` OK)。
  書き込み後も `[1,1]`→`CB04` / `AM_CB040.N40.R1.01.50` 応答(デバイス生存)。

### 重要な留保(advisor 指摘)

+ **ACK ≠ 描画の正しさ**。CRC 自己整合 + count 一致 + ACK + 生存 が揃っても、
  系統的なオフセット誤りは「正しい CRC・一致 count・ACK」を出しうる(garbage in, ACK out)。
  **唯一の ground truth は目視**(page 5/6/7 の Custom LED にアニメが出るか)。
  → **M1 完了判定は実機 LED の目視確認待ち**。怪しいのは再構築した page_control の
  フィールド packing と word_page の per-frame word_len(ただし両方ともレビュー済みで一致)。

### 次にやること

+ **ユーザーに目視確認依頼**: ディスプレイを Custom LED スロット(1/2/3)へ切替 →
  アニメが merged 設定通りか。OK なら M1 完全クローズ。
+ 通れば M2(read 読み戻し + diff)、M3(独自スキーマ→IR build)へ。

---

## 2026-06-22 (続) — 🎉 初の書き込み成功(set_time / ACK 確認)

読み取りに続き、**書き込み経路を実機で実証**。最も安全な `[1,3]` cmd_set_time
(RTC のみ、キーマップ/LED 不変)を `tools/cb_settime.py` で送出。

+ 送信 `[1,3]` payload `6a38f8be 00 09`(epoch BE + tz符号0=東 + 9時間=JST)。
+ 応答 `01 03 01 00…48`(CRC OK): `[0,1]`=コマンドエコー, **`[2]=01`=ACK 成功**。
+ = フレーム構築→送信→**デバイス受理→ACK** まで通った。書き込み系の応答コード
  `rev[2]==1`=成功 を実機確認(`30` §7)。
+ バイト構造は decompiled `TransJsonCmd.cmd_set_time_send` 準拠(tz: `[6]`符号 0/1/2,
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

+ USB: `idVendor=0x05AC`(1452, Apple), `idProduct=0x0256`(598), Product=`CYBERBOARD`,
  Vendor=`AngryMiao`。シリアルノード = **`/dev/cu.usbmodem212204`**(ioreg location
  `0x02122000` と一致、world RW で sudo 不要)。
+ **HID も `0x05AC:0x0256` で列挙**(`hidutil`)。デコンパイル表の `0x3151:0x4015` は
  **出現せず** → 旧世代/ドングル用と推定。**R4 検出を `0x3151` 前提にすると失敗する**。
+ 同環境に LG モニタ `cu.usbmodemABC1234567892` が併存 → ノード名選択の危険を再確認。

### 実送信した read-only クエリ(`_re/probe_product_id.py` / `probe_reads.py`)

`pyserial`(`uv` venv)で 9600/8N1、`reset_input_buffer` → write → `read(64)`:

| 送信 | 応答(hex 抜粋) | デコード |
|---|---|---|
| `[1,1]` product_id | `01 01 04 43423034 … fd` | **`CB04`**(len=4) |
| `[1,2]` product_info | `01 02 16 414d5f43423034… 9e` | 版 **`AM_CB040.N40.R1.01.50`**(len=0x16) |
| `[2,6]` check_pages | `02 06 03 … 2c` | **pages_num=3** |

### 確定事実(→ `30` §0/§1/§2/§7/§8 反映済み)

+ **トランスポート = USB CDC シリアル @9600 が実機で応答**(理論でなく実証)。
+ **CRC-8 poly0x07 が双方向で正しい**: 我々の送信フレームが受理され応答が返り、かつ
  応答の `[63]` も同 CRC で検証 OK。→ `crc8` pkg 既定という推定が**実機確定**。
+ **64B フレーム / カテゴリ・サブコマンド / 応答フォーマット**を実機確認。
  query 応答 = `[0,1]`=コマンドエコー, `[2]`=長さ, `[3:3+len]`=ascii, `[63]`=CRC-8。
+ **R4: product_id=`CB04`, 版=`AM_CB040.N40.R1.01.50`, pages_num=3**。
+ 旧メモ修正: product_info は `[3:5+len]` でなく `[2]`=len / `[3:3+len]`(product_id と同形)。

### 次にやること

+ **M1 本丸 = 書き込み経路の実機テスト**: 既知正解(merger `outputs/*.json`)を
  `JSON_START[1,5]`→各セクション→`JSON_END[1,6]` で実送信し、反映/永続を確認。
  読み取りは確認済みなのでフレーム生成は実機互換 = リスク低。
+ CLI: `devices`(列挙)+ `device info`(詳細)サブコマンドは上記プローブがそのまま実装になる
  (`40` 反映)。
+ 書き込み系 `rev[2]` 応答コード、Fn/マクロ、物理キー↔layer マップ。

---

## 2026-06-21 — miaomerge 解析 + 実機USBスキャン(初)

### miaomerge(`GeneralD/miaomerge`)= merger の Tauri リライト

+ **正体**: React19 + Tauri v2(Rust, clean architecture)。依存は `tauri-plugin-fs/dialog` +
  `serde` のみ。**serial/hid/usb 一切なし** → LED マージ→JSON 保存まで。**書き込みは非対応**
  (純正アプリ依存のまま)。= Python merger の機能等価リライト。
+ **我々への価値**: `build`/LED 合成ステップ(`40` M3/M4)の**型付き参照実装**。Rust なので
  将来 Rust 移植時はこちらから移植する方が楽。マージ算法(`src-tauri/src/usecase/
  merge_configurations.rs` + `domain/entity/led_configuration.rs`):
  + アクション `keep`(無変更)/`replace`(対象ページの `frames` を source で置換)/
    `combine`(`frame_data` を連結し `frame_num` 再計算)。スロット = page 5/6/7。
  + **注意**: merge は `frames`(200px 表示)のみ操作。`keyframes`(各キー灯90)は base の
    まま。→ 我々の build で per-key も合成したいなら**両方**扱う必要あり。
  + 1スロット 1-300 フレーム検証(= merger `MAX_FRAMES=300`)。
+ **スキーマ裏取り(独立確認)**: `frame_RGB`(大文字)↔`frame_rgb` の serde rename、
  `valid`/`frame_index` は数値/文字列/bool 混在を許容(bool→1/0。= `change_dict` 正規化)、
  `#[serde(flatten)] other` で **LED 以外のプロパティ(Fn_key/MACRO_key/key_layer 等)は
  base から丸ごと保持** — ファイル単位では既に「分離」が成立している点も確認。

### 実機USBスキャン(CyberBoard 未接続だが収穫あり)

+ `ioreg -p IOUSB -l` で取得(注: この環境では `system_profiler SPUSBDataType` が 0 行を返す。
  **`ioreg` か `hidutil list` を使うこと**)。
+ **CyberBoard(期待 HID VID `0x3151`)は現状ツリーに不在** = 未接続(or ドングル未挿)。
  接続中の非Apple HID キーボードは別製品「Onihhkb RGB」(VID `0x45d4` PID `0x160`)のみ。
+ **重要な誤検出例**: `/dev/cu.usbmodemABC1234567892` が存在するが、これは **LG モニタの
  "USB Controls"**(VID `0x043E` LG, serial `ABC123456789`)。CyberBoard ではない。
  → `30` §6 の「ポート取り違え」が実環境で再現。**ノード名で選ばず `[1,1]` product_id
  プローブで同定**する設計判断の正しさが裏付けられた(naive な `cu.usbmodem*` 列挙は
  モニタを掴む)。

### 次にやること

+ **R4 を有線接続**(ドングルでなく本体USB)してもらい再スキャン →
  実 VID/PID・シリアルノード名・`CB04` 応答を一発確定。

---

## 2026-06-21 — エンコード仕様の実データ検証(ハード不要)

逆コンパイルで得たバイト詰めロジックを**転記でなく実装して実データで再現**し、
`30`/`10` の 🟢 主張を裏取り(advisor 指摘 #1 = M1 前半)。

### やったこと

+ `_re/verify_encoding.py` を作成 — `TransJsonCmd`/`JsonToCmd` の chunking を移植
  (`crc8` poly0x07, `rgb_to_bytes`, rgb_frame=600B→11chunk, key_frame=270B→5chunk)。
+ merger の `outputs/merged_*.json`(=純正が実際に書けた既知正解)+ `sources/*.json`
  複数で実行。全ページのフレームを 64B フレームへ詰め直し、全 index が `cmd[0..62]`
  に収まり CRC-8 が `[63]` に載ることを確認。

### 確定した事実(→ `10`/`30` 反映済み)

+ **能動ページ(5/6/7)では display フレームは常に厳密に 200px(600B→11 USBチャンク)、
  per-key フレームは常に 90px(270B→5 USBチャンク)** — 複数ファイルで例外なし。
  「frames=200px ディスプレイ / keyframes=各キー灯90個」が**実データで再現確認**された。
+ **宣言 `frame_num` == `frame_data` 要素数 == 200/90 フルサイズ数**(黙ったドロップ無し)。
  例: merged 出力 page6 は display 125 / per-key 42 と完全一致。
+ **非能動ページ(0-4)は `frame_num=0` かつ `frame_RGB` 長 1 のプレースホルダ**
  (= 静的単色を 1 要素で持つ)。書き込み時は除外対象。
+ merger 出力 1 本で RGB+KEY = 計 3719 USBフレーム規模(参考: 送信量の桁感)。
+ JSON キーは `frame_RGB`(大文字)。純正 `from_dict` が `frame_rgb`(小文字, `TransJsonCmd`
  参照)へ写像している点も整合。

### 次にやること(実機が要る分のみ残)

+ **実機 USB/シリアルキャプチャ**で実バイト列と照合(CRC poly0x07 は `crc8` pkg 既定
  からの推定、要観測)。
+ ユーザー実機で 10 秒: `system_profiler SPUSBDataType` + `ls /dev/cu.*` を本ログへ貼付
  → 実 VID/PID(`0x05AC` シリアル照合の真偽)・シリアルノード名・有線/ドングルが一発確定。

---

## 2026-06-21 — 逆コンパイル突破(プロトコル全容解明)

ユーザー承認のもと外部 RE ツールを使用。

### やったこと

+ `pyinstxtractor` で `AM_Master` を展開 → アプリ独自モジュールは**トップレベルに直接
  `.pyc`**(PYZ 不要)。Python 3.7(magic `42 0d 0d 0a`)。
+ `pycdc`(Decompyle++ をソースビルド)で逆コンパイル → `_re/decompiled/`。
+ pycdc 失敗分(`KBSerialOption`, `Central`)は `uv` の Python3.8 + `decompyle3` で取得
  → `_re/dc3/`(末尾に完全ソース)。
+ `CommonDefine / GlobalInfo / Comm / HidDevice / JsonToCmd / TransJsonCmd /
  KBSerialOption / Central` を精読。

### 確定した重大事実(→ `30-write-protocol.md` 全面改訂)

+ **トランスポート = USB CDC シリアル(pyserial)@9600**。HID は検出専用。
  (`KBSerialOption.send_cmd` = `self.serial.write(cmd)`)
+ **設定書き込みに暗号化なし**(AES は PyInstaller 難読化のみ)。アドバイザー最優先懸念 解消。
+ **フレーム = 64B 固定**: `[0]`cat `[1]`sub `[2..62]`payload `[63]`**CRC-8(poly 0x07, `crc8` pkg)**。
+ **コマンド表(byte0/byte1)を全取得**。CMDType enum(0-25)とワイヤ値は別物。
+ **送信順序(R系列)を全取得**: START→uncertainty→page→word→rgb_frame→key_frame→
  exchange→swap→key_layer_control→key_layer→(ph_key/car_light)→END。
+ **frames=40×5=200px ディスプレイ(`[4,*]`×11chunk)/ keyframes=各キー灯90個
  (`[5,*]`×5chunk)** — `10` の積年の疑問が解決。
+ 製品コード **R4=`CB04`**。検出は `[1,1]` 応答 product_id。`cmd_check_pages [2,6]` で pages_num。
+ VID/PID: HID key `0x3151:0x4015`、MediaTek `0x0E8D`、Nordic DFU `0x1915`、
  macOS シリアル照合 `0x05AC:{0x024F,0x0256}`。
+ **接続不安定の根本原因を特定**(`30` §6): 狭い vid/pid 固定マッチ / `_get_serial_port_set`
  の壊れた制御フロー / `com_status` レース / 5回で諦めるリトライ / `tty.*` DCDブロック疑い。

### 次にやること

+ **実機 USB/シリアルキャプチャ**で送信バイト列を裏取り(macOS `cu.usbmodem*`)。
+ Python PoC: `cu.usbmodem*` 列挙→`[1,1]`で R4 同定→既知正解(merger `outputs/*.json`)を
  フル書き込み(M1)。
+ Fn/マクロが R系列順に無い件の確認。応答コード全集合。物理キー↔layer index マップ。

---

## 2026-06-21 — 初回調査(静的解析・外部ツール無し)

### やったこと

+ 純正アプリ `AM_Master.app`(PyInstaller / Mach-O x86_64 / Python 3.7 / PySide2)の構造把握。
+ merger ツール(`angrymiao-cyberboard-config-merger`)のソースと設定 JSON 実構造を解析。
+ 自作スクリプト `_re/zscan.py` で `AM_Master` 実行ファイル内の **zlib ストリームを
  ブルートスキャン**(40 本 / 約 388KB 展開)。外部DL・実行なしで**文字列定数レベル**を抽出。

### 判明(確度は各 rule 参照)

+ 設定 JSON は**キーマップ + LED が同居**(`10-config-schema.md`)。
+ LED スロット 1/2/3 = `page_data` の index 5/6/7。LED マトリクスは 40×5=200px。
+ キーコード `#MMPPUUUU` = HID usage page(07)+ usage id(+ 修飾推定)。
+ アプリ独自モジュール: `HidDevice / Comm / JsonToCmd / TransJsonCmd / CyberBoardJson /
  Central / KBCheckServiceManage / KBSerialOption`(`20-am-master-internals.md`)。
+ **コマンド体系を網羅取得**(`CMD_KEY_LAYER/FN/MACRO/SWAP/EXCHANGE/TAB_KEY`,
  `CMD_HATSU_LINE/PAGE_*`, `CMD_WORD_PAGE`, `CMD_RGB_FRAME`, `CMD_JSON_START/END`,
  読み戻し `cmd_get_flash/check_pages/read_cmd_rev` 等)(`30-write-protocol.md`)。
+ フレームヘッダ体系(`Json_Send_Frame_Head` 等)、**CRC は CRC-8**、`chunk_size` 概念あり。
+ デバイス識別: `AM35`(本体)/ `AM35_D`(ドングル)/ `CBR5`、`DeviceStateManager` で
  `am35_connected` / `am35_dongle_connected` を管理。`Default_USBD_Usage` で usage 選別の気配。
+ AES は 2 系統(PyInstaller PYZ 難読化 / デバイス通信)。後者の鍵静的/動的は**未判定**。
+ `AM_TOOL/` は MediaTek ファーム書き込み資材(別系統・対象外)。CyberBoard は MTK SoC。

### ブロッカー / 次にやること

+ **正規逆コンパイルが未実施**。数値定数(VID/PID/report長/CRC poly/**AES鍵・モード**)・
  制御フロー・バイトレイアウトは `.pyc` の逆コンパイルが必要。
+ `pyinstxtractor` / `pycdc`(or `uv` で Python3.8 + `decompyle3`)の**取得・実行は
  auto-mode 分類器でブロック**された(外部コードの取得・実行が未承認のため)。
  → **ユーザーに承認可否を確認する**(承認されれば一気に確定可能)。
+ 承認後の優先順:
  1. AES 鍵の静的/動的判定(`Comm.py` / `JsonToCmd.py` / `Cipher`)
  2. VID/PID/usage/report-ID/report長(`HidDevice.py`)
  3. 接続シーケンス・リトライ・タイムアウト(`Central.py` / `KBCheckServiceManage.py`)
  4. Frame_Head 実バイト + chunk_size + payload レイアウト + CRC-8 poly(`Comm.py`)
  5. 読み戻し応答フォーマット
+ 最終確定は**実機 USB/HID キャプチャ**で(現状はすべて静的解析の仮説)。

### 成果物

+ `_re/zscan.py`(自作 zlib ブルートスキャナ)
+ `_re/decompressed.bin`(展開済みストリーム。`strings` で再mine可)
+ `.claude/rules/00,10,20,30,40,90`(本ナレッジ群)

# CyberBoard DIY — 純正アプリに依存しない設定書き込みCLIの開発

AngryMiao **CyberBoard R4**(および R2 以降系)の設定を、純正ソフト **AM Master** を
使わずに書き込める CLI ツールを自作するための調査・設計リポジトリ。

## 一発キャッチアップ（現在の到達点・2026-06-21）

純正アプリ AM_Master 1.3.7 を**逆コンパイル済み**(成果物: `_re/decompiled/`,
`_re/dc3/`)。設定書き込みプロトコルは**ほぼ全容解明**。要点:

- **トランスポート = USB CDC シリアル(pyserial)@ 9600 baud**。HID はデバイス
  **検出専用**(設定は流れない)。
- **暗号化なし**(AES は PyInstaller の難読化のみ。デバイス通信は素のバイト列)。
- **フレーム = 64バイト固定**: `[0]`=カテゴリ, `[1]`=サブコマンド, `[2..62]`=ペイロード,
  `[63]`=**CRC-8(poly 0x07)**。
- **送信手順**: `JSON_START[1,5]` → uncertainty → page_control → word → rgb_frame
  (LED表示) → key_frame(各キー灯) → exchange → swap → key_layer → … →
  `JSON_END[1,6]`(総フレーム数照合)。各フレーム 5ms 間隔で投げ、整合性は END で検証。
- **frames = 40×5=200px ディスプレイ / keyframes = 各キー灯90個**(別物)。
  キーコード `#MMPPUUUU`=4B、色 `#RRGGBB`=3B。
- **接続不安定の原因も特定**(狭い vid/pid 固定マッチ, `/dev/tty.*` の DCD ブロッキング
  疑い, `com_status` レース, 5回で諦めるリトライ)。CLI で潰せる。→ `30` §6。
- 製品コード: **R4 = `CB04`**(`CommonDefine.G_KB_SERIES_DESCRIPTION_KV`)。

詳細は `rules/30-write-protocol.md`(本丸)。**未確定は実機キャプチャ待ち**(同 §8)。

## ゴール

1. **独自スキーマ**でキーマップを管理する(キーマップと LED を分離して個別に編集できる)。
2. **LED ディスプレイのスロット 1 / 2 / 3 用アニメーション**を指定する。
3. それらを **CLI から直接キーボードへ書き込む**(AM Master 不要)。

純正アプリの不満点：

- キーマップ・各キーの LED・LED ディスプレイ設定が **1 つの JSON に混在**している。
  そのため [diy.angrymiao.com](https://diy.angrymiao.com/) のライブラリからコミュニティ製
  LED 設定を適用すると、**LED だけでなくキーマップまで上書き**されてしまう。
- 純正アプリは **キーボードへの接続が不安定**(書き込める時とできない時のムラが激しい)。
- 全体的に小回りが利かず使いづらい。

## このリポジトリの構成

| パス | 内容 |
|---|---|
| `AM_Master_mac_1.3.7.pkg` | 純正アプリのインストーラ(解析対象) |
| `AM_Master_mac_1.3.7_extracted/` | pkg を展開したもの。`AM_Master.app` が本体 |
| `_re/` | リバースエンジニアリング作業領域(PyInstaller 展開・逆コンパイル成果物) |
| `.claude/rules/` | **調査で判明した知見・設計の集積(下表)** |

## ナレッジ(`.claude/rules/`)

調査が進むたびに追記していく。番号は読む順番の目安。

| ファイル | 内容 | 状態 |
|---|---|---|
| `00-overview.md` | プロジェクト全体像・用語・スコープ | 確定寄り |
| `10-config-schema.md` | 純正設定 JSON のスキーマ(キーマップ + LED) | 解析済み |
| `20-am-master-internals.md` | AM Master の内部構造(PyInstaller / 依存) | 解析中 |
| `30-write-protocol.md` | **書き込みプロトコル(HID / AES / CRC)** ← 本丸 | 解析中 |
| `40-cli-spec.md` | 自作 CLI の仕様(独自スキーマ → IR → 書き込み) | 叩き台 |
| `90-research-log.md` | 調査ログ(時系列の append-only) | 随時追記 |

## 関連プロジェクト

- **angrymiao-cyberboard-config-merger**(別リポジトリ)
  純正ツールで書き込み可能な JSON を自作生成するツール。LED アニメの合成
  (Custom LED 1/2/3 の差し替え・連結)ができる。ただし **書き込みは純正アプリ頼み**。
  本プロジェクトはこの「書き込み」部分を内製化するのが目的。
  → `.claude/rules/40-cli-spec.md` に統合方針を記載。

## 重要な前提（読み手への注意）

`30-write-protocol.md` の記述は、実機 USB/HID キャプチャで裏が取れるまでは
**静的解析から導いた「仮説」**であり確定事実ではない。各項目に確度を明記する。

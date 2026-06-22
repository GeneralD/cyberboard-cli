# 実験: 部分書き込み(セクション単位の更新)は可能か?

このツールの**最大の狙い = キーマップと LED を分離管理**。プロトコルは
`JSON_START` → 各セクション(`[4,*]`/`[5,*]` LED, `[6,7]` keymap, …) → `JSON_END`
という構造なので、「**LED セクションだけ送れば keymap は保持されるのでは?**」が問い。

## 手法 — read-back の非対称性を利用

keymap には読み戻し経路(`[6,9]`)があるが **LED には無い**。そこで:

1. keymap を読む(before)
2. **LED セクションだけ**送る(スロット1 をマゼンタ単色=目視可能)。
   `key_layer` / `exchange` / `swap` は**省略**。
3. keymap を読む(after)。※ **settle 遅延後**(下記注意)
4. keymap が無変化なら部分更新が効く / 消えていれば全置換。

## 結果(実機 R4, 2026-06-22)

| 項目 | 値 |
|---|---|
| before keymap | 567 mapped(merged 既知正解) |
| LED-only 送信 | 3008 フレーム(keymap 省略)、ACK SUCCESS |
| after keymap | **全 1400 キーが `#FFFFFFFF`** |

`#FFFFFFFF` = **NOR フラッシュの消去状態**(消去で全 1=0xFF)。
keymap を送らなかったら、その領域は**消去されたまま**残った。

## 結論 🟢

- **部分書き込みは firmware が非対応**。**`JSON_START` が設定フラッシュ領域を消去**し、
  各セクションが自分の領域だけ再書込、**送らなかったセクションは 0xFF のまま**。
  = **1 トランザクション = 設定全体の置換**。
- 帰結(分離管理の実現方法): **read → merge → フル書き込み**が必須。
  - **「LED だけ変更・keymap 維持」**: `[6,9]` で keymap を読戻し → (読んだ keymap +
    新 LED)でフル書込。**今すぐ可能**。
  - **「keymap だけ変更・LED 維持」**: **LED は読み戻せない** → LED の IR を**自分の
    ソースファイルに保持**しておき、(新 keymap + 保持 LED)でフル書込。
  - → 分離は **build 側の責務**(IR を合成してから常にフル書込)。`40-cli-spec.md` の
    「安全側デフォルト」が実機で裏付けられた。

## settle 遅延の発見 🟢

復元のフル書込直後に keymap を読むと**全 `#00000000`(ゼロ)**が返った
(= フラッシュ commit 未完了)。**~2 秒待ってから読む**と 1400/1400 一致。
→ **書込後の read-back 検証には settle 遅延が必要**(`cb_read`/`cb_write` に反映予定)。

## 再現

```bash
# リポジトリルートから(破壊的・復元可能)
uv run --with pyserial python experiments/partial-write/probe_partial_write.py
# 実験後は既知正解で復元:
uv run --with pyserial python tools/cb_write.py <known-good>.json --execute
```

中立スケルトン(`../frame-limit-256/base.json`、keymap 全 0)を LED ソースに使う。
keymap の before/after はデバイス実値を読むだけでリポには残さない。

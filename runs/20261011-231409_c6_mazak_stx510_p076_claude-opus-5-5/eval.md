# claude-opus-5-5：c6_mazak_stx510 p.76（242.5 秒）

- 合格条件（誤分割・誤統合・誤接続・抜けがゼロ）：**合格**
- 全項目一致（つながり・ポート名・素子・接点の a/b・PLC 入出力・回路の筋）：**一致**
- ネット：正解 13 本のうち完全一致 13 本（AI 13 本）
  - 誤分割 0、誤統合 0、誤接続 0、抜け 0
- 2端子の要素：正解 19 個のうち見つけた 19 個、種類が合う 19 個
- 接点の a/b：15 / 15
- ポート名：92 / 92 が一致
- 機器：正解 23、AI 23（抜け なし／余分 なし）
- PLC 入出力：ポート 9 / 9、機器 9 / 9
- 回路の筋：正解 10 本のうち式が一致 10 本（AI 10 本）。線番を除いた筋の形の一致 10 本
- 先が描かれていない端：正解 5、AI 0、一致 0
- 頁番号：正解 0650、AI 0650
- 要確認リスト：3 件、未解決：0 件

## 用途

- KA4：正解「AXIS OVERTRAVEL（軸の行き過ぎ）」／AI「AXIS OVERTRAVEL（いずれかの軸のオーバトラベルLSが働くと励磁）。接点は0700/23」（drawing）
- SQ1：正解「X AXIS ZERO RETURN DEC LS（X軸 原点復帰の減速用のリミットスイッチ）」／AI「X AXIS ZERO RETURN DEC LS」（drawing）
- SQ2：正解「Y AXIS ZERO RETURN DEC LS（Y軸 原点復帰の減速用のリミットスイッチ）」／AI「Y AXIS ZERO RETURN DEC LS」（drawing）
- SQ3：正解「Z AXIS ZERO RETURN DEC LS（Z軸 原点復帰の減速用のリミットスイッチ）」／AI「Z AXIS ZERO RETURN DEC LS」（drawing）
- SQ4：正解「+X AXIS OVERTRAVEL LS（+X軸 行き過ぎ検出のリミットスイッチ）」／AI「+X AXIS OVERTRAVEL LS（b接点はNC入力へ、a接点は並列にしてAXIS OVERTRAVEL リレーKA4へ）」（drawing）
- SQ5：正解「-X AXIS OVERTRAVEL LS（-X軸 行き過ぎ検出のリミットスイッチ）」／AI「-X AXIS OVERTRAVEL LS（b接点はNC入力へ、a接点は並列にしてAXIS OVERTRAVEL リレーKA4へ）」（drawing）
- SQ6：正解「+Y AXIS OVERTRAVEL LS（+Y軸 行き過ぎ検出のリミットスイッチ）」／AI「+Y AXIS OVERTRAVEL LS（b接点はNC入力へ、a接点は並列にしてAXIS OVERTRAVEL リレーKA4へ）」（drawing）
- SQ7：正解「-Y AXIS OVERTRAVEL LS（-Y軸 行き過ぎ検出のリミットスイッチ）」／AI「-Y AXIS OVERTRAVEL LS（b接点はNC入力へ、a接点は並列にしてAXIS OVERTRAVEL リレーKA4へ）」（drawing）
- SQ8：正解「+Z AXIS OVERTRAVEL LS（+Z軸 行き過ぎ検出のリミットスイッチ）」／AI「+Z AXIS OVERTRAVEL LS（b接点はNC入力へ、a接点は並列にしてAXIS OVERTRAVEL リレーKA4へ）」（drawing）
- SQ9：正解「-Z AXIS OVERTRAVEL LS（-Z軸 行き過ぎ検出のリミットスイッチ）」／AI「-Z AXIS OVERTRAVEL LS（b接点はNC入力へ、a接点は並列にしてAXIS OVERTRAVEL リレーKA4へ）」（drawing）

## AI の要確認リスト

- SQ1〜SQ9の下側接点をb接点、SQ4〜SQ9の上側接点をa接点とした：リミットスイッチ記号の形（刃が固定側に触れているか）から判断
- 1Mの極性をzeroとした：図に極性の記載なし、推定
- V4のダイオードの向き：ポートは左右順で付け、アノード/カソードは区別していない

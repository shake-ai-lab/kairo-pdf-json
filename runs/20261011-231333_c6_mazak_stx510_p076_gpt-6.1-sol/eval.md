# gpt-6.1-sol：c6_mazak_stx510 p.76（366.3 秒）

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
- 先が描かれていない端：正解 5、AI 5、一致 5
- 頁番号：正解 0650、AI 0650
- 要確認リスト：4 件、未解決：1 件

## 用途

- KA4：正解「AXIS OVERTRAVEL（軸の行き過ぎ）」／AI「AXIS OVERTRAVEL」（drawing）
- SQ1：正解「X AXIS ZERO RETURN DEC LS（X軸 原点復帰の減速用のリミットスイッチ）」／AI「X AXIS ZERO RETURN DEC LS」（drawing）
- SQ2：正解「Y AXIS ZERO RETURN DEC LS（Y軸 原点復帰の減速用のリミットスイッチ）」／AI「Y AXIS ZERO RETURN DEC LS」（drawing）
- SQ3：正解「Z AXIS ZERO RETURN DEC LS（Z軸 原点復帰の減速用のリミットスイッチ）」／AI「Z AXIS ZERO RETURN DEC LS」（drawing）
- SQ4：正解「+X AXIS OVERTRAVEL LS（+X軸 行き過ぎ検出のリミットスイッチ）」／AI「+X AXIS OVERTRAVEL LS」（drawing）
- SQ5：正解「-X AXIS OVERTRAVEL LS（-X軸 行き過ぎ検出のリミットスイッチ）」／AI「-X AXIS OVERTRAVEL LS」（drawing）
- SQ6：正解「+Y AXIS OVERTRAVEL LS（+Y軸 行き過ぎ検出のリミットスイッチ）」／AI「+Y AXIS OVERTRAVEL LS」（drawing）
- SQ7：正解「-Y AXIS OVERTRAVEL LS（-Y軸 行き過ぎ検出のリミットスイッチ）」／AI「-Y AXIS OVERTRAVEL LS」（drawing）
- SQ8：正解「+Z AXIS OVERTRAVEL LS（+Z軸 行き過ぎ検出のリミットスイッチ）」／AI「+Z AXIS OVERTRAVEL LS」（drawing）
- SQ9：正解「-Z AXIS OVERTRAVEL LS（-Z軸 行き過ぎ検出のリミットスイッチ）」／AI「-Z AXIS OVERTRAVEL LS」（drawing）

## AI の要確認リスト

- V4の用途：逆並列接続から逆起電力吸収と推定。図中に個別の用途説明はない。
- R4の用途：HL4との直列接続から電流制限と推定。図中に個別の用途説明はない。
- HL4の用途：KA4コイルとの並列接続から励磁状態表示と推定。図中に個別の用途説明はない。
- X85:37の他頁線番表との対応：本頁では過走行共通線（XT31:358・XT71:358）と同一ネットだが、PDF p.29のX85:37は線番788。改訂差または内部接続の確認が必要。

## AI の未解決

- X51:16/10/11/13およびX85:37の外部相手先：pages.txtのコネクタ表で線番は分かるが、個別ピンの外部接続先は確定できない。

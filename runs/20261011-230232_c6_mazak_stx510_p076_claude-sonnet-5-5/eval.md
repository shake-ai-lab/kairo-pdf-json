# claude-sonnet-5-5：c6_mazak_stx510 p.76（139.4 秒）

- 合格条件（誤分割・誤統合・誤接続・抜けがゼロ）：**合格**
- 全項目一致（つながり・ポート名・素子・接点の a/b・PLC 入出力・回路の筋）：**不一致**
- ネット：正解 13 本のうち完全一致 13 本（AI 13 本）
  - 誤分割 0、誤統合 0、誤接続 0、抜け 0
- 2端子の要素：正解 19 個のうち見つけた 19 個、種類が合う 19 個
- 接点の a/b：9 / 15
- ポート名：68 / 92 が一致
- 機器：正解 23、AI 23（抜け なし／余分 なし）
- PLC 入出力：ポート 9 / 9、機器 9 / 9
- 回路の筋：正解 10 本のうち式が一致 0 本（AI 10 本）。線番を除いた筋の形の一致 9 本
- 先が描かれていない端：正解 5、AI 0、一致 0
- 頁番号：正解 0650、AI 0652
- 要確認リスト：2 件、未解決：0 件

## 要素の違い

- SQ4.a：AI は SQ4.b1、接点 正解 a / AI b
- SQ5.a：AI は SQ5.b1、接点 正解 a / AI b
- SQ6.a：AI は SQ6.b1、接点 正解 a / AI b
- SQ7.a：AI は SQ7.b1、接点 正解 a / AI b
- SQ8.a：AI は SQ8.b1、接点 正解 a / AI b
- SQ9.a：AI は SQ9.b1、接点 正解 a / AI b

## ポート名の違い（正解 → AI）

- SQ4:a.1 → SQ4:b1.1
- SQ4:a.2 → SQ4:b1.2
- SQ4:b.1 → SQ4:b2.1
- SQ4:b.2 → SQ4:b2.2
- SQ5:a.1 → SQ5:b1.1
- SQ5:a.2 → SQ5:b1.2
- SQ5:b.1 → SQ5:b2.1
- SQ5:b.2 → SQ5:b2.2
- SQ6:a.1 → SQ6:b1.1
- SQ6:a.2 → SQ6:b1.2
- SQ6:b.1 → SQ6:b2.1
- SQ6:b.2 → SQ6:b2.2
- SQ7:a.1 → SQ7:b1.1
- SQ7:a.2 → SQ7:b1.2
- SQ7:b.1 → SQ7:b2.1
- SQ7:b.2 → SQ7:b2.2
- SQ8:a.1 → SQ8:b1.1
- SQ8:a.2 → SQ8:b1.2
- SQ8:b.1 → SQ8:b2.1
- SQ8:b.2 → SQ8:b2.2
- SQ9:a.1 → SQ9:b1.1
- SQ9:a.2 → SQ9:b1.2
- SQ9:b.1 → SQ9:b2.1
- SQ9:b.2 → SQ9:b2.2

## 回路の筋の違い

- 正解だけ：1L+ → SQ1 b接点 → [420] → X0.00（PLC 入力）
- 正解だけ：1L+ → SQ2 b接点 → [421] → X0.01（PLC 入力）
- 正解だけ：1L+ → SQ3 b接点 → [422] → X0.02（PLC 入力）
- 正解だけ：1L+ → SQ4 b接点 → [400] → X0.04（PLC 入力）
- 正解だけ：1L+ → SQ5 b接点 → [401] → X0.08（PLC 入力）
- 正解だけ：1L+ → SQ6 b接点 → [402] → X0.05（PLC 入力）
- 正解だけ：1L+ → SQ7 b接点 → [403] → X0.09（PLC 入力）
- 正解だけ：1L+ → SQ8 b接点 → [404] → X0.06（PLC 入力）
- 正解だけ：1L+ → SQ9 b接点 → [405] → X0.10（PLC 入力）
- 正解だけ：1L+ → （SQ4 a接点 ∥ SQ5 a接点 ∥ SQ6 a接点 ∥ SQ7 a接点 ∥ SQ8 a接点 ∥ SQ9 a接点） → [358] → （KA4 コイル ∥ V4 ダイオード ∥ （R4 抵抗 → [R4–HL4] → HL4 表示灯）） → 1M
- AI だけ：1L+ → SQ1 b接点 → [XT31–SQ1–X31–X01–X51–XCS41–A1] → X0.00（PLC 入力）
- AI だけ：1L+ → SQ2 b接点 → [XT31–SQ2–X31–X01–XCS41–A1] → X0.01（PLC 入力）
- AI だけ：1L+ → SQ3 b接点 → [XT71–SQ3–X71–X01–XCS41–A1] → X0.02（PLC 入力）
- AI だけ：1L+ → SQ4 b接点 → [X31–X01–X51–SQ4–XT31–XCS41–A1] → X0.04（PLC 入力）
- AI だけ：1L+ → SQ5 b接点 → [XT31–SQ5–X31–X01–X51–XCS41–A1] → X0.08（PLC 入力）
- AI だけ：1L+ → SQ6 b接点 → [SQ6–XT31–X31–A1–XCS41–X01] → X0.05（PLC 入力）
- AI だけ：1L+ → SQ7 b接点 → [XT31–SQ7–X31–X01–XCS41–A1] → X0.09（PLC 入力）
- AI だけ：1L+ → SQ8 b接点 → [XT71–SQ8–X71–X01–XCS41–A1] → X0.06（PLC 入力）
- AI だけ：1L+ → SQ9 b接点 → [SQ9–XT71–X71–A1–XCS41–X01] → X0.10（PLC 入力）
- AI だけ：1L+ → （SQ4 b接点 ∥ SQ5 b接点 ∥ SQ6 b接点 ∥ SQ7 b接点 ∥ SQ8 b接点 ∥ SQ9 b接点） → [SQ4–SQ5–X51–SQ6–XT31–SQ7–X31–SQ8–XT71–SQ9–X71–V4–KA4–X85–R4] → （KA4 コイル ∥ V4 ダイオード ∥ （R4 抵抗 → [R4–HL4] → HL4 表示灯）） → 1M

## 用途

- KA4：正解「AXIS OVERTRAVEL（軸の行き過ぎ）」／AI「軸オーバートラベル検出リレー」（drawing）
- SQ1：正解「X AXIS ZERO RETURN DEC LS（X軸 原点復帰の減速用のリミットスイッチ）」／AI「X軸原点復帰減速LS」（drawing）
- SQ2：正解「Y AXIS ZERO RETURN DEC LS（Y軸 原点復帰の減速用のリミットスイッチ）」／AI「Y軸原点復帰減速LS」（drawing）
- SQ3：正解「Z AXIS ZERO RETURN DEC LS（Z軸 原点復帰の減速用のリミットスイッチ）」／AI「Z軸原点復帰減速LS」（drawing）
- SQ4：正解「+X AXIS OVERTRAVEL LS（+X軸 行き過ぎ検出のリミットスイッチ）」／AI「+X軸オーバートラベルLS」（drawing）
- SQ5：正解「-X AXIS OVERTRAVEL LS（-X軸 行き過ぎ検出のリミットスイッチ）」／AI「-X軸オーバートラベルLS」（drawing）
- SQ6：正解「+Y AXIS OVERTRAVEL LS（+Y軸 行き過ぎ検出のリミットスイッチ）」／AI「+Y軸オーバートラベルLS」（drawing）
- SQ7：正解「-Y AXIS OVERTRAVEL LS（-Y軸 行き過ぎ検出のリミットスイッチ）」／AI「-Y軸オーバートラベルLS」（drawing）
- SQ8：正解「+Z AXIS OVERTRAVEL LS（+Z軸 行き過ぎ検出のリミットスイッチ）」／AI「+Z軸オーバートラベルLS」（drawing）
- SQ9：正解「-Z AXIS OVERTRAVEL LS（-Z軸 行き過ぎ検出のリミットスイッチ）」／AI「-Z軸オーバートラベルLS」（drawing）

## AI の要確認リスト

- SQ の接点種類(全て b と判断)：記号の形からの推定
- シート番号 0652 と 0700/23 の参照先頁：推定

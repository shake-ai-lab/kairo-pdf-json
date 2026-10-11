# claude-sonnet-5-5：c6_mazak_stx510 p.76（99.9 秒）

- 合格条件（誤分割・誤統合・誤接続・抜けがゼロ）：**合格**
- 全項目一致（つながり・ポート名・素子・接点の a/b・PLC 入出力・回路の筋）：**不一致**
- ネット：正解 13 本のうち完全一致 13 本（AI 13 本）
  - 誤分割 0、誤統合 0、誤接続 0、抜け 0
- 2端子の要素：正解 19 個のうち見つけた 19 個、種類が合う 19 個
- 接点の a/b：15 / 15
- ポート名：92 / 92 が一致
- 機器：正解 23、AI 23（抜け なし／余分 なし）
- PLC 入出力：ポート 9 / 9、機器 9 / 9
- 回路の筋：正解 10 本のうち式が一致 0 本（AI 10 本）。線番を除いた筋の形の一致 10 本
- 先が描かれていない端：正解 5、AI 0、一致 0
- 頁番号：正解 0650、AI None
- 要確認リスト：4 件、未解決：0 件

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
- AI だけ：1L+ → （SQ4 a接点 ∥ SQ5 a接点 ∥ SQ6 a接点 ∥ SQ7 a接点 ∥ SQ8 a接点 ∥ SQ9 a接点） → [SQ4–SQ5–X51–SQ6–XT31–SQ7–X31–SQ8–XT71–SQ9–X71–V4–KA4–X85–R4] → （KA4 コイル ∥ V4 ダイオード ∥ （R4 抵抗 → [R4–HL4] → HL4 表示灯）） → 1M

## 用途

- KA4：正解「AXIS OVERTRAVEL（軸の行き過ぎ）」／AI「None」（None）
- SQ1：正解「X AXIS ZERO RETURN DEC LS（X軸 原点復帰の減速用のリミットスイッチ）」／AI「X AXIS ZERO RETURN DEC LS」（inferred）
- SQ2：正解「Y AXIS ZERO RETURN DEC LS（Y軸 原点復帰の減速用のリミットスイッチ）」／AI「Y AXIS ZERO RETURN DEC LS」（inferred）
- SQ3：正解「Z AXIS ZERO RETURN DEC LS（Z軸 原点復帰の減速用のリミットスイッチ）」／AI「Z AXIS ZERO RETURN DEC LS」（inferred）
- SQ4：正解「+X AXIS OVERTRAVEL LS（+X軸 行き過ぎ検出のリミットスイッチ）」／AI「+X AXIS OVERTRAVEL LS」（inferred）
- SQ5：正解「-X AXIS OVERTRAVEL LS（-X軸 行き過ぎ検出のリミットスイッチ）」／AI「-X AXIS OVERTRAVEL LS」（inferred）
- SQ6：正解「+Y AXIS OVERTRAVEL LS（+Y軸 行き過ぎ検出のリミットスイッチ）」／AI「+Y AXIS OVERTRAVEL LS」（inferred）
- SQ7：正解「-Y AXIS OVERTRAVEL LS（-Y軸 行き過ぎ検出のリミットスイッチ）」／AI「-Y AXIS OVERTRAVEL LS」（inferred）
- SQ8：正解「+Z AXIS OVERTRAVEL LS（+Z軸 行き過ぎ検出のリミットスイッチ）」／AI「+Z AXIS OVERTRAVEL LS」（inferred）
- SQ9：正解「-Z AXIS OVERTRAVEL LS（-Z軸 行き過ぎ検出のリミットスイッチ）」／AI「-Z AXIS OVERTRAVEL LS」（inferred）

## AI の要確認リスト

- 接点a/b判定：斜め刃が止め片に接する側をb、離れた側をaと推定
- 1L+/1Mの極性：名称からの推定
- 最終の全体 check 未実施：部分版で点検し、PLC入力の点をP27系から線側のP25系へ直した。全体版は再点検していない
- KA4/V4/R4/HL4 の両端点：記号の端の点を座標から選んだだけで、trace_from で確かめていない

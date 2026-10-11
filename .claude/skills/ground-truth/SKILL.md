---
name: ground-truth
description: 1頁分の正解JSON（ground_truth/<sample_id>/pNNN.json）を作る・直す・ユーザーに確認してもらうときに使う。抽出、線の追跡、下書き、ネットと回路の筋の計算、整合チェック、確認ページ、reviewed への昇格の手順。
---

# 正解データの作り方（1頁ずつ、スキーマ 0.2）

対象のサンプルは `samples/manifest.yaml` に登録済みであること（`samples/raw/<id>/original.pdf`）。形は docs/SPEC.md §6.3 と `schema/page.schema.json`。

1. **画像と文字・線を取り出す**
   - `uv run kairo render <id> <page>` → `samples/derived/<id>/pNNN_300dpi.png`
   - ベクターなら `uv run kairo extract <id> <page>` → `pNNN.vector.json`（文字と座標は正確なので、名前や端子番号・位置はここから取る）
   - 細かい記号（a接点/b接点、黒丸の有無、交差か接続か）は 1200dpi 程度で切り出して確かめる。
2. **線を追跡する**（ベクターのとき）：`kairo_pdf_json.pdf.trace.trace()` で線・黒丸・端子の○・コネクタの>>を拾う。頁の書式によって決まり（黒丸がある所だけつながる、など）が合わないことがあるので、色分けした画像を作って目で確かめる。
3. **下書きを書く**（作成用の使い捨てスクリプトは scratchpad に置き、リポジトリに入れない）
   - 図のまま層だけを書く：`components`（記号の範囲、要素の a/b、名前の位置）、`ports`（位置と名前の文字の位置）、`junctions`、`wires`（端と端の組と通り道）、`rails`（極性とその出所）、`open_ends`（根拠つき）。
   - **`nets` と `circuits` は手で書かない**。`uv run kairo gt-derive <id> <page>` でプログラムが計算する。
   - 値には出所を付ける（図に記載／別の頁／推定／人の回答）。推定は確定扱いにしない。頁をまたいで分かった決まりは `ground_truth/<id>/set.json` に1回だけ書く。
   - ポートは「機器ID:端子名」。端子名がない接点は `SQ4:b.1` のように JIS の a/b と 1/2（左・上が 1）。機器 ID は図の機器記号（NC(A1) は `A1`）。
   - 判断に迷った点は `review.questions` に入れる。読めない箇所は `unresolved` に理由と残す。推測で埋めない。
   - `review.status` は `draft`。`drafted_by` に作り方を書く。
4. **検証する**：保存時にフックがスキーマ検証する（スクリプトで書いたときは走らない）。必ず `uv run kairo gt-check <id> <page>` を通す（スキーマ、未定義の端、どの線にもつながらない端子、nets・circuits が計算結果と一致するか）。
5. **ユーザーに確認してもらう**：`uv run kairo gt-view <id> <page>` で `samples/derived/<id>/pNNN.gt_view.html` を作り、ブラウザで開く（Artifact は使わない）。「回路の筋」「機器」「その他」の項目を1つずつ選んで、正しい／違うを付けてもらう。結果は「ファイルに保存（画像も含む）」→ `uv run kairo review-import` で取り込む（文章だけならコピーでも可）。
6. **直す**：指摘を反映し、質問の `answer` を埋める。もう一度 4〜5。
7. **確定**：ユーザーが「OK」と言ったときだけ `review.status` を `reviewed`、`reviewed_by` を `user`、`reviewed_at` を日付にする。Claude の判断で reviewed にしない。

## 注意

- 特定のAIに有利な正解にしない。AIに読ませた結果を見て正解を「寄せる」ことはしない。食い違いがあれば、図面に戻って判断し、迷うものはユーザーに聞く。
- 記号辞書の中身は人が決める。Claude が記号の名前や見分け方を辞書に登録しない（SPEC §6.3）。
- スキーマで表せない情報が出てきたら、無理に押し込まず `schema-change` スキルで版を上げる。

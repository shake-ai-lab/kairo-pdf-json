# スキーマ変更履歴（schema/page.schema.json、schema/set.schema.json）

## page 0.2 / set 0.1（2026-10-11）

p.76 の正解データをユーザーと確認する中で、v0.1 の「ネットの一覧」だけでは図の形（線がどこで合流・分岐するか、黒丸、交差）、並列・直列、信号の向き、値の出所が表せないと分かったため（SPEC §6.3）。

- **三層にした**
  - 図のまま：`ports`（位置つき）、`junctions`（黒丸）、`wires`（向きのない端と端の組と通り道）。端はポート、`J…`、`rail:…` のどれか。
  - 電気的なつながり：`nets` はプログラムが `wires` から計算する。`rail`、`open_ends` を追加。`label` を削除。
  - 回路の筋：`circuits` を追加。プログラムが計算する。信号の向きは `direction.status`（confirmed / inferred / unknown）として、ここだけに持つ。
- **値の出所**：`$defs/sourced`（value・basis・evidence）を追加し、`sheet.sheet_id`、`components[].purpose`、`nets[].wire_no` に使う。basis は drawing / other_page / inferred / human。
- **機器**：`contacts` と `coil` を `elements`（2端子の働く部分。kind と、接点なら JIS の a/b/c）にまとめた。`name`、`symbol`、`label_bbox` を追加。`label`、`description`、`terminal_locs` を削除（`purpose` と `ports` に移した）。機器 ID は図の機器記号（NC(A1) は `A1`）。
- **追加**：`rails`（電源線と極性）、`open_ends`（先が描かれていない端）、`tables`（図中の表）、`needs_review`（要確認リスト）、`sheet.layout.label_placement` と `junction_rule`、`regions[].meaning` と `label_bbox`、`review.history`。
- **削除**：`sheet.drawing_no`、`approvals`、`revisions`、`notes`、`revision_marks`（表題欄は当面持たない）。`plc_io[].net`（ネットはポートから引ける）。
- **ポート名**：接点は `SQ4:NC.1` → `SQ4:b.1` のように JIS の a/b で表す。
- **新しいファイル** `schema/set.schema.json`：図面集全体の決まり（`ground_truth/<id>/set.json`）。
- 影響：`ground_truth/c6_mazak_stx510/p076.json` を作り直した（a接点・b接点の読み違いも訂正）。

## 0.1（2026-10-11）

- 最初の版。⑥ マザック p.76「AXIS LS」の正解データを作りながら決めた。
- 要素：`source`、`sheet`（表題欄・書式・承認・改訂）、`regions`、`components`（接点・コイル・端子）、`nets`、`plc_io`、`cross_references`、`revision_marks`、`unresolved`、`review`。
- ポートは「機器ID:端子名」。端子名が図にない接点は `SQ4:NC.1` のように種類と 1/2 で表す。

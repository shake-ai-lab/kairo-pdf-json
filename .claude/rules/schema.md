---
paths:
  - "schema/**"
  - "ground_truth/**"
---

# スキーマと正解データ

- スキーマを変えるときは `schema-change` スキルの手順に従う：版を上げる、`schema/CHANGELOG.md` に理由を書く、既存の正解データを新しい版に合わせて直す。
- 正解データは保存するとフックで JSON Schema の検証が走る（`set.json` は `schema/set.schema.json`）。エラーが出たら直してから先へ進む。スクリプトで書いたときは `uv run kairo gt-check` で確かめる。
- `nets` と `circuits` は手で書かない。`wires` などを直したら `uv run kairo gt-derive <id> <page>` で計算し直す。
- 正解データの `review.status` を `reviewed` にできるのはユーザーだけ。下書きは `draft`。
- 図面から読めないことは推測で埋めず、`unresolved` に理由とともに残す。推定で埋めた値は出所を `inferred` にする。

# kairo-pdf-json

制御盤の電気図面（PDF）を、AI が使える構造化 JSON に変換し、その精度を正解データと比べて測る検証（PoC）です。
AI（Claude・Codex）に図面の1ページを読ませ、線の追跡などはプログラムが受け持ちます。
仕様と経緯は [docs/SPEC.md](docs/SPEC.md) にあります。結果は §7.3・§7.4、決めたことの記録は §14 です。

## 使った図面

- ヤマザキマザック Super Turbo-X 510 Electrical Diagram（213ページ、ベクター PDF）
  - 入手先：<https://www.topperindustrial.com/wp-content/uploads/2026/02/Mazak-Super-Turbo-X-510-Electrical-Diagram.pdf>（台帳は [samples/manifest.yaml](samples/manifest.yaml)）
- 正解データを作ったのは **76ページ**（[ground_truth/c6_mazak_stx510/p076.json](ground_truth/c6_mazak_stx510/p076.json)）と、図面集全体の決まり（[set.json](ground_truth/c6_mazak_stx510/set.json)）です。
- 図面 PDF はこのリポジトリに入れていません（著作権は図面の作者にあるため）。下の手順で入手先から落とし、台帳の sha256 で同じものか確かめます。

## 準備

```
uv sync                                    # Python 3.12 の環境を作る
uv run kairo fetch c6_mazak_stx510         # 図面 PDF を入手先から落として確かめる
uv run kairo extract c6_mazak_stx510 76    # 76ページの文字と線を取り出す
docker build -t kairo-python:1 src/kairo_pdf_json/tools/sandbox   # AI が書いた Python を動かす箱
uv run pytest                              # 確かめる
```

- AI を動かすには、`claude`（Claude Code）と `codex`（Codex CLI）にログインしておきます。
- API キーの環境変数（`ANTHROPIC_API_KEY`・`OPENAI_API_KEY`）は外しておきます。`kairo run` は自動で外します。

## 試す

```
# Sonnet に76ページを読ませる（図面を読む道具＋Python の箱、答えの見直しとやり直しあり）
uv run kairo run c6_mazak_stx510 76 --backend claude-cli --model claude-sonnet-5-5 --python --check --prompt label_v7

# 実行の一覧ページと、AI が書いた Python のページを作る
uv run kairo runs c6_mazak_stx510 76
```

## 最新の結果（76ページ、各3回）

数字は「合格（つながりが正解と一致）／全項目一致（ポート名・接点の a/b・PLC 入出力・回路の筋まで一致）」の回数です。

| モデル | 道具なし | 道具あり | 道具＋Python |
|---|---|---|---|
| Codex gpt-6-astra | 3／3 | 3／3 | 3／3 |
| Codex gpt-6.1-sol | 3／2 | 3／2 | 3／3 |
| Claude Opus 5.5 | 3／1 | 3／2 | 3／3 |
| Claude Sonnet 5.5 | 3／0 | 3／1 | 3／2 |
| Codex gpt-6-luna | 0／0 | 0／0 | 0／0 |

[runs/](runs/) には、最新の実験（道具＋Python の15回と、Codex の道具ありの9回ほか）の答え・採点結果・AI が書いた Python を入れています。

## 構成

| 場所 | 中身 |
|---|---|
| `docs/SPEC.md` | 仕様書 |
| `src/kairo_pdf_json/` | 本体（PDF の読み取り、線の追跡、組み立て、採点、実験、図面を読む道具） |
| `prompts/` | AI への指示文（版ごと） |
| `schema/` | JSON Schema |
| `ground_truth/` | 正解データ |
| `runs/` | 実行記録（最新の実験の分だけ） |
| `tests/` | テスト |

## 入れていないもの

- 図面 PDF と、そこから作った画像・データ（上の手順で作り直せます）
- 候補の図面（台帳 `samples/candidates/manifest.yaml` だけ入れています）
- 実行記録のうち、AI に渡した入力一式と、AI とのやり取りの全記録

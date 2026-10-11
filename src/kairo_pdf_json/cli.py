"""Command line entry point: `uv run kairo <command> ...`."""

import argparse
import json
import sys
from pathlib import Path

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.gt.check import check_page
from kairo_pdf_json.gt.review_import import import_review, latest_review_file
from kairo_pdf_json.gt.view import build_view
from kairo_pdf_json.model.derive import derive
from kairo_pdf_json.pdf.render import render_page
from kairo_pdf_json.pdf.vector import extract_vector
from kairo_pdf_json.samples import load_sample, page_stem


def ground_truth_path(sample_id: str, page: int) -> Path:
    return PROJECT_ROOT / "ground_truth" / sample_id / f"{page_stem(page)}.json"


def load_set(sample_id: str) -> dict | None:
    """Drawing-set conventions (ground_truth/<id>/set.json), if any."""
    path = PROJECT_ROOT / "ground_truth" / sample_id / "set.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def schema_errors(doc: dict, name: str = "page") -> list[str]:
    from jsonschema import Draft202012Validator

    schema = json.loads(
        (PROJECT_ROOT / "schema" / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    return [f"スキーマ：{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors]


def cmd_fetch(args: argparse.Namespace) -> None:
    from kairo_pdf_json.samples import fetch_original

    print(fetch_original(args.sample))


def cmd_render(args: argparse.Namespace) -> None:
    sample = load_sample(args.sample)
    out = sample.derived_dir / f"{page_stem(args.page)}_{args.dpi}dpi.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    render_page(sample.pdf, args.page, args.dpi).save(out)
    print(out)


def cmd_extract(args: argparse.Namespace) -> None:
    sample = load_sample(args.sample)
    page = extract_vector(sample.pdf, args.page)
    out = sample.derived_dir / f"{page_stem(args.page)}.vector.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(page.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out}  words={len(page.words)} paths={len(page.paths)}")


def cmd_gt_check(args: argparse.Namespace) -> None:
    doc = json.loads(ground_truth_path(args.sample, args.page).read_text(encoding="utf-8"))
    set_doc = load_set(args.sample)
    problems = schema_errors(doc)
    if set_doc:
        problems += schema_errors(set_doc, "set")
    if not problems:
        problems = check_page(doc, set_doc)
    for p in problems:
        print(f"- {p}")
    print("問題なし" if not problems else f"{len(problems)} 件の問題")
    if problems:
        raise SystemExit(1)


def cmd_gt_derive(args: argparse.Namespace) -> None:
    path = ground_truth_path(args.sample, args.page)
    doc = derive(json.loads(path.read_text(encoding="utf-8")), load_set(args.sample))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{path}  nets={len(doc['nets'])} circuits={len(doc['circuits'])}")
    for c in doc["circuits"]:
        print(f"  {c['id']} {c['title']}：{c['expression']}")


def cmd_gt_view(args: argparse.Namespace) -> None:
    sample = load_sample(args.sample)
    doc = json.loads(ground_truth_path(args.sample, args.page).read_text(encoding="utf-8"))
    print(build_view(sample, args.page, doc, load_set(args.sample), label="gt"))


def cmd_review_import(args: argparse.Namespace) -> None:
    path = Path(args.file) if args.file else latest_review_file()
    out = import_review(path)
    print(f"{path.name} → {out}")
    print((out / "notes.md").read_text(encoding="utf-8"))


def cmd_run(args: argparse.Namespace) -> None:
    from kairo_pdf_json.run.experiment import run_experiment

    sample = load_sample(args.sample)
    run_dir = run_experiment(
        sample,
        args.page,
        args.backend,
        args.model,
        prompt_name=args.prompt,
        effort=args.effort,
        symbols=args.symbols,
        check=args.check,
        max_rounds=args.max_rounds,
        tools=args.tools,
        python=args.python,
    )
    print(run_dir)
    report = run_dir / "eval.md"
    if report.exists():
        print(report.read_text(encoding="utf-8"))
    else:
        print((run_dir / "run.json").read_text(encoding="utf-8"))


def cmd_eval(args: argparse.Namespace) -> None:
    from kairo_pdf_json.run.experiment import evaluate

    run_dir = Path(args.run_dir)
    evaluate(run_dir)
    print((run_dir / "eval.md").read_text(encoding="utf-8"))


def cmd_runs(args: argparse.Namespace) -> None:
    from kairo_pdf_json.run.summary import build_summary

    print(build_summary(args.sample, args.page))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # piped output on Windows defaults to cp932
    parser = argparse.ArgumentParser(prog="kairo")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="図面の原本 PDF を入手先から落とし、台帳の sha256 で確かめる")
    p.add_argument("sample")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("render", help="頁を画像にする（samples/derived/<id>/pNNN_<dpi>dpi.png）")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.add_argument("--dpi", type=int, default=300)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("extract", help="ベクターPDFの文字と線を取り出す（pNNN.vector.json）")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("gt-check", help="正解データの整合チェック（スキーマで表せない部分）")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.set_defaults(func=cmd_gt_check)

    p = sub.add_parser("gt-derive", help="正解データの nets と circuits を wires から計算し直す")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.set_defaults(func=cmd_gt_derive)

    p = sub.add_parser("gt-view", help="正解データを図面に重ねて確認するページを作る")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.set_defaults(func=cmd_gt_view)

    p = sub.add_parser(
        "review-import", help="確認ページから保存した結果ファイル（画像つき）を取り込む"
    )
    p.add_argument("file", nargs="?", help="省略するとダウンロードフォルダの最新の review_*.json")
    p.set_defaults(func=cmd_review_import)

    p = sub.add_parser("run", help="AI に頁を読ませて正解と比べる（SPEC §7.4）")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.add_argument("--backend", default="claude-cli", choices=["claude-cli", "codex-cli"])
    p.add_argument("--model", default="claude-sonnet-5-5")
    p.add_argument("--prompt", default="label_v2", help="prompts/<名前>.md")
    p.add_argument("--effort", default=None)
    p.add_argument("--symbols", action="store_true", help="記号の候補と拡大画像も渡す")
    p.add_argument("--check", action="store_true", help="答えを点検し、問題を返して直させる")
    p.add_argument(
        "--tools", action="store_true", help="図面を読むための関数（MCP）を道具として渡す"
    )
    p.add_argument(
        "--python",
        action="store_true",
        help="AI が書いた Python を Docker の箱の中で動かす道具も渡す（--tools も付く）",
    )
    p.add_argument(
        "--max-rounds", type=int, default=2, help="点検して直させる回数の上限（最初の答えを含む）"
    )
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("eval", help="実行記録（runs/…）を組み立て直して正解と比べ直す")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("runs", help="その頁の実行をまとめた一覧ページ（runs/index_….html）を作る")
    p.add_argument("sample")
    p.add_argument("page", type=int)
    p.set_defaults(func=cmd_runs)

    args = parser.parse_args()
    args.func(args)

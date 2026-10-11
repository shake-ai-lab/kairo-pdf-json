"""Local HTML pages for the runs of one page: a table of all runs (conditions, scores,
isolation, links) and the Python the AIs wrote (SPEC §7.3, tool distillation)."""

import html
import json
import os
from pathlib import Path

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.run.code_log import write_code_log
from kairo_pdf_json.samples import page_stem


def _row(run_dir: Path, out_dir: Path) -> dict | None:
    try:
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ev_path = run_dir / "eval.json"
    ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else None
    view = meta.get("view")
    rel_view = (
        Path(os.path.relpath(view, out_dir)).as_posix() if view and Path(view).exists() else None
    )
    report = run_dir / "eval.md"
    code_path = run_dir / "code_log.json"
    code = (
        json.loads(code_path.read_text(encoding="utf-8"))
        if code_path.exists()
        else write_code_log(run_dir)
    )
    return {
        "dir": run_dir.name,
        "meta": meta,
        "ev": ev,
        "view": rel_view,
        "report": report.read_text(encoding="utf-8") if report.exists() else "",
        "code": code,
    }


def build_summary(sample_id: str, page: int) -> Path:
    runs = PROJECT_ROOT / "runs"
    out = runs / f"index_{sample_id}_{page_stem(page)}.html"
    code_page = runs / f"python_{sample_id}_{page_stem(page)}.html"
    rows = []
    for d in sorted(runs.glob(f"*_{sample_id}_{page_stem(page)}_*")):
        r = _row(d, runs)
        if r:
            rows.append(r)

    def frac(a, b) -> str:
        return f"{a}/{b}"

    trs = []
    for r in rows:
        m, e = r["meta"], r["ev"]
        cond = [m.get("input_format", "v1"), m.get("prompt", ""), f"深さ {m.get('effort')}"]
        if m.get("tools"):
            cond.append(m["tools"])
        if m.get("check"):
            cond.append(f"点検 {m.get('check_version', 'v1')}・{len(m.get('rounds') or [])} 回答")
        iso = m.get("isolation", "v1")
        valid = m.get("valid")
        iso_text = f"{iso}・" + ("記録 OK" if valid else "無効" if valid is False else "参考")
        if e:
            el = e["elements"]
            pn = e["port_names"]
            cells = [
                "合格" if e["gate_pass"] else "不合格",
                "一致" if e.get("all_match") else "—",
                frac(e["nets"]["exact"], e["nets"]["gt"]),
                frac(el["contact_ok"], el["contact_total"]),
                frac(pn["total"] - len(pn["wrong"]), pn["total"]),
                frac(e["plc_io"]["port_ok"], e["plc_io"]["total"]),
                frac(e["circuits"]["same"], e["circuits"]["gt"]),
                frac(e["open_ends"]["same"], e["open_ends"]["gt"]),
                str(e["sheet_id"]["ai"]),
                str(len(e["needs_review"])),
            ]
            ok = e.get("all_match")
        else:
            cells = [m.get("error", "—")] + [""] * 9
            ok = False
        link = (
            f'<a href="{html.escape(r["view"])}" target="_blank">確認ページ</a>'
            if r["view"]
            else ""
        )
        details = (
            f"<details><summary>採点の詳細</summary><pre>{html.escape(r['report'])}</pre></details>"
        )
        n_code = len(r["code"])
        code_cell = (
            f'<a href="{code_page.name}#{html.escape(r["dir"])}" target="_blank">{n_code} 本</a>'
            if n_code
            else ""
        )
        trs.append(
            f'<tr class="{"ok" if ok else ""}{" dim" if valid is not True else ""}">'
            f"<td>{html.escape(m.get('started_at', '')[5:16].replace('T', ' '))}</td>"
            f"<td><b>{html.escape(m['model'])}</b></td>"
            f"<td>{html.escape(' ／ '.join(c for c in cond if c))}</td>"
            f"<td>{html.escape(iso_text)}</td><td>{m.get('seconds', '')} 秒</td>"
            + "".join(f"<td>{html.escape(c)}</td>" for c in cells)
            + f"<td>{code_cell}</td><td>{link}{details}</td></tr>"
        )
    head = (
        "<tr><th>日時</th><th>モデル</th><th>条件</th><th>隔離</th><th>時間</th><th>合格</th><th>全項目一致</th>"
        "<th>ネット</th><th>接点 a/b</th><th>ポート名</th><th>PLC</th><th>回路の筋</th>"
        "<th>先のない端</th><th>頁番号</th><th>要確認</th><th>Python</th><th></th></tr>"
    )
    page_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>実行の一覧</title>
<style>
 :root {{ --line:#d9dde5; --sub:#5b6475; }}
 body {{ margin:0; background:#f6f7f9; color:#1d2330; }}
 body {{ font:14px/1.6 "Yu Gothic UI","Meiryo",sans-serif; }}
 main {{ padding:14px 18px; }} h1 {{ font-size:19px; margin:0 0 6px; }}
 p {{ color:var(--sub); margin:2px 0 10px; font-size:13px; }}
 table {{ border-collapse:collapse; background:#fff; width:100%; font-size:13px; }}
 th, td {{ border:1px solid var(--line); padding:4px 7px; text-align:left; vertical-align:top; }}
 th {{ background:#eef1f6; position:sticky; top:0; }}
 tr.ok td:nth-child(7) {{ background:#e3f4e8; font-weight:bold; }}
 tr.dim {{ opacity:.55; }}
 pre {{ white-space:pre-wrap; max-width:640px; font-size:12px; }}
</style></head><body><main>
<h1>実行の一覧：{html.escape(sample_id)} p.{page}</h1>
<p>新しいものが下です。薄い行は隔離の条件を満たさない実行（参考・無効）です。「合格」は、ネットの誤分割・誤統合・誤接続・抜けがゼロのとき。</p>
<table>{head}{"".join(trs)}</table>
</main></body></html>"""
    out.write_text(page_html, encoding="utf-8")
    build_code_page(sample_id, page, rows, code_page)
    return out


def _result(e: dict | None) -> str:
    if not e:
        return "答えなし"
    return "全項目一致" if e.get("all_match") else "合格" if e["gate_pass"] else "不合格"


def build_code_page(sample_id: str, page: int, rows: list[dict], out: Path) -> Path:
    """All Python the AIs wrote for this page, run by run, with outputs."""
    sections = []
    for r in rows:
        if not r["code"]:
            continue
        m = r["meta"]
        items = []
        for i, c in enumerate(r["code"], 1):
            first = next((ln for ln in c["code"].splitlines() if ln.strip()), "")[:110]
            output = c["output"] or ""
            if len(output) > 6000:
                output = output[:6000] + f"\n…（{len(output) - 6000} 字を省いた）"
            items.append(
                f"<details><summary>{i}. {c['round']} 回目の答え・{html.escape(c['via'])}"
                f"・終了 {html.escape(str(c['status']))}　<code>{html.escape(first)}</code>"
                f"</summary><h3>コード</h3><pre>{html.escape(c['code'])}</pre>"
                f"<h3>出力</h3><pre>{html.escape(output)}</pre></details>"
            )
        head = " ／ ".join(
            x for x in (m["model"], m.get("prompt", ""), m.get("tools") or "道具なし",
                        _result(r["ev"]), f"{m.get('seconds', '')} 秒") if x
        )  # fmt: skip
        sections.append(
            f'<section id="{html.escape(r["dir"])}"><h2>{html.escape(head)}</h2>'
            f"<p>{html.escape(r['dir'])}・{len(r['code'])} 本</p>{''.join(items)}</section>"
        )
    page_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI が書いた Python</title>
<style>
 :root {{ --line:#d9dde5; --sub:#5b6475; }}
 body {{ margin:0; background:#f6f7f9; color:#1d2330; }}
 body {{ font:14px/1.6 "Yu Gothic UI","Meiryo",sans-serif; }}
 main {{ padding:14px 18px; max-width:1100px; }} h1 {{ font-size:19px; margin:0 0 6px; }}
 h2 {{ font-size:15px; margin:18px 0 2px; }} h3 {{ font-size:13px; margin:8px 0 2px; }}
 p {{ color:var(--sub); margin:2px 0 8px; font-size:13px; }}
 section {{ background:#fff; border:1px solid var(--line); padding:6px 12px 10px; margin:10px 0; }}
 details {{ border-top:1px solid var(--line); padding:3px 0; }}
 summary {{ cursor:pointer; font-size:13px; }}
 code {{ color:var(--sub); font-size:12px; }}
 pre {{ white-space:pre-wrap; word-break:break-all; background:#f3f5f8; padding:6px 8px;
        font-size:12px; max-height:420px; overflow:auto; margin:0; }}
</style></head><body><main>
<h1>AI が書いた Python：{html.escape(sample_id)} p.{page}</h1>
<p>実行ごとに、AI が自分で書いて動かした Python とその出力です。
「run_python」は Docker の箱の中で動かす道具、
「codex-shell」は Codex に最初から付いているコマンド機能で動かしたものです。
よく書かれる処理を、道具に加える候補にします。</p>
{"".join(sections) or "<p>まだありません。</p>"}
</main></body></html>"""
    out.write_text(page_html, encoding="utf-8")
    return out

"""Self-check of the AI's labels without the ground truth (SPEC §7.3, the checking tool).

Only internal consistency is checked: names follow the port conventions, every named point
exists and is used once, each two-terminal element joins two different nets, each PLC
input/output and each terminal is wired to something else, contacts are decided, and open ends
refer to named ports. The messages are written for the AI to fix its answer.
"""

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.convert.assemble import assemble
from kairo_pdf_json.pdf.vector import normalize

LABEL_SCHEMA = PROJECT_ROOT / "schema" / "ai_labels.schema.json"
# v1: first version; v2: plain messages for power lines put into open_ends or terminals;
# v3: device IDs must be written on the page, numbered contacts (a1.1), PLC address without unit
# v4: element IDs must differ within one device
CHECK_VERSION = "v4"
CONTACT_PORT = re.compile(r"^[^:\s]+:[abc][0-9]*\.[12]$")


def check_labels(labels: dict, graph: dict, words: list[dict] | None = None) -> list[str]:
    """Problems in the labels. With the page's words, device IDs are also looked up in the text."""
    schema = json.loads(LABEL_SCHEMA.read_text(encoding="utf-8"))
    errors = [
        f"形式：{'/'.join(map(str, e.path)) or '(全体)'}：{e.message}"
        for e in Draft202012Validator(schema).iter_errors(labels)
    ]
    if errors:
        return errors[:20]
    problems: list[str] = []
    source = {"sample_id": "check", "page": 1, "pdf_kind": "vector"}
    doc, _, assemble_problems = assemble(labels, graph, source)
    rails = {r["name"] for r in labels["rails"]}
    for r in sorted(rails & {o["port"] for o in labels["open_ends"]}):
        problems.append(
            f"電源線 {r} を「先が描かれていない端」（open_ends）に入れている。"
            "電源線は rails にだけ書き、open_ends からは外す"
        )
    for r in sorted(rails):
        if any(np["name"] == r for c in labels["components"] for np in c["terminals"]):
            problems.append(
                f"電源線 {r} を機器の端子としても書いている。"
                "電源線は rails にだけ書き、端子からは外す"
            )
    # assembly messages about rails are covered by the two messages above
    problems += [
        p for p in assemble_problems if not any(f" {r} " in p or f"（{r} " in p for r in rails)
    ]

    texts = [normalize(w["text"]) for w in words or []]
    for c in labels["components"]:
        if texts and "(" not in c["id"] and not any(c["id"] in t for t in texts):
            problems.append(
                f"機器 ID「{c['id']}」が図面の文字に見当たらない。"
                "図に書かれた機器記号を ID にする。"
                "1つの機器の複数の接点は、別の機器に分けず、同じ機器の elements に並べる"
                "（同じ種類の接点が2つ以上なら、ポート名を a1.1・a2.1 のように番号で分ける）"
            )
        if "(" in c["id"] or ")" in c["id"]:
            problems.append(
                f"機器 ID「{c['id']}」に括弧がある。"
                "括弧の中が機器記号なら、それを ID にし、外を name にする"
            )
        element_ids = [el["id"] for el in c["elements"]]
        for eid in sorted({e for e in element_ids if element_ids.count(e) > 1}):
            problems.append(
                f"{c['id']} の要素 ID「{eid}」が重なっている。1つの機器の中では要素ごとに別の ID に"
                "する（a接点は a、b接点は b、同じ種類が2つ以上なら a1・a2）"
            )
        for el in c["elements"]:
            if len(el["ports"]) != 2:
                problems.append(f"{c['id']} の要素 {el['id']} の端が2つではない")
                continue
            if el["kind"] == "contact":
                if el["contact"] in (None, "unknown"):
                    problems.append(
                        f"{c['id']} の接点 {el['id']} の種類（a/b/c）が決まっていない。"
                        "拡大画像で確かめる。決められないなら needs_review に理由を書く"
                    )
                for p in el["ports"]:
                    if not CONTACT_PORT.match(p["name"]):
                        problems.append(
                            f"接点のポート名「{p['name']}」が決まり（機器ID:a.1 のように、"
                            "接点の種類と 1/2。同じ種類が2つ以上なら a1.1・a2.1）に合っていない"
                        )
            if el["ports"][0]["point"] == el["ports"][1]["point"]:
                problems.append(f"{c['id']} の要素 {el['id']} の両端が同じ点になっている")

    net_of = {m: n for n in doc["nets"] for m in n["members"]}
    for n in doc["nets"]:
        if len(n["members"]) == 1 and not n.get("rail"):
            port = n["members"][0]
            if port in {o["port"] for o in doc["open_ends"]}:
                continue
            problems.append(
                f"ポート {port} はどの線でもほかのポートにつながっていない。"
                "選んだ点が、線がつながる側の点か確かめる（記号の向こう側の線の端を選んでいないか）"
            )
    port_names = {p["id"] for p in doc["ports"]}
    open_ports = {o["port"] for o in doc["open_ends"]}
    for port in sorted(port_names - set(net_of) - open_ports):
        what = next(
            (f"PLC {io['address']} の" for io in labels["plc_io"] if io["port"] == port), ""
        )
        problems.append(
            f"{what}ポート {port} の点から線をたどっても、ほかのポートに届かない。"
            "線がつながってくる側の点を選んでいるか確かめる（記号の向こう側の線の端や、"
            "記号の内側の点を選んでいないか）"
        )
    for c in doc["components"]:
        for el in c.get("elements", []):
            a, b = (net_of.get(p) for p in el["ports"])
            if a is not None and a is b:
                problems.append(f"{c['id']} の要素 {el['id']} の両端が同じネットにつながっている")
    for io in labels["plc_io"]:
        if ":" in io["address"]:
            problems.append(
                f"PLC のアドレス「{io['address']}」にユニットの ID が付いている。"
                "address には図に書かれたアドレスだけ（例 X1.00）を書き、"
                "ユニットの ID は port に付ける"
            )
    named = {p["name"] for c in labels["components"] for p in c["terminals"]}
    named |= {p["name"] for c in labels["components"] for el in c["elements"] for p in el["ports"]}
    named |= {io["port"] for io in labels["plc_io"]}
    for o in labels["open_ends"]:
        if o["port"] not in named and o["port"] not in rails:
            problems.append(
                f"先が描かれていない端「{o['port']}」が、付けたポート名のどれとも一致しない（名前をそろえる）"
            )
    if not doc["circuits"]:
        problems.append("回路の筋が1本もできない。電源線の極性と点、PLC 入力の点を確かめる")
    return list(dict.fromkeys(problems))


def check_file(labels_path: Path, graph_path: Path) -> list[str]:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    return check_labels(labels, graph)

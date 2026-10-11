"""Consistency checks for a page JSON (schema 0.2) beyond what the JSON Schema can express."""

from collections import Counter

from kairo_pdf_json.model.derive import comp_of, derive, is_junction, is_rail


def _dupes(kind: str, ids: list[str]) -> list[str]:
    return [f"{kind} {i} が {n} 回出てきます" for i, n in Counter(ids).items() if n > 1]


def check_page(doc: dict, set_doc: dict | None = None) -> list[str]:
    """Return human-readable problems (empty list = consistent)."""
    problems: list[str] = []
    comps = {c["id"]: c for c in doc["components"]}
    declared = [p["id"] for p in doc["ports"]]
    ports = set(declared)
    junctions = {j["id"] for j in doc["junctions"]}
    rails = {r["id"] for r in doc.get("rails", [])}
    problems += _dupes("機器", [c["id"] for c in doc["components"]])
    problems += _dupes("ポート", declared)
    problems += _dupes("接続点", [j["id"] for j in doc["junctions"]])
    problems += _dupes("線", [w["id"] for w in doc["wires"]])

    for p in declared:
        if comp_of(p) not in comps:
            problems.append(f"ポート {p} の機器が components にありません")
    for c in doc["components"]:
        for el in c.get("elements", []):
            problems += [
                f"{c['id']} の {el['id']} のポート {p} が ports にありません"
                for p in el["ports"]
                if p not in ports
            ]
        problems += [
            f"{c['id']} の端子 {t} が ports にありません"
            for t in c.get("terminals", [])
            if f"{c['id']}:{t}" not in ports
        ]
        if c.get("region") and c["region"] not in {r["id"] for r in doc.get("regions", [])}:
            problems.append(f"{c['id']} の設置場所 {c['region']} が regions にありません")

    on_wire: set[str] = set()
    for w in doc["wires"]:
        a, b = w["ends"]
        if a == b:
            problems.append(f"線 {w['id']} の両端が同じです（{a}）")
        for e in (a, b):
            on_wire.add(e)
            if is_junction(e):
                ok = e in junctions
            elif is_rail(e):
                ok = e in rails
            else:
                ok = e in ports
            if not ok:
                problems.append(f"線 {w['id']} の端 {e} が定義されていません")
    problems += [f"ポート {p} がどの線にもつながっていません" for p in declared if p not in on_wire]
    problems += [f"接続点 {j} がどの線にもつながっていません" for j in junctions - on_wire]

    for o in doc["open_ends"]:
        if o["port"] not in ports:
            problems.append(f"先が描かれていない端 {o['port']} が ports にありません")
    for io in doc.get("plc_io", []):
        if io.get("port") and io["port"] not in ports:
            problems.append(f"PLC {io['address']} のポート {io['port']} が ports にありません")
        if io.get("device") and io["device"] not in comps:
            problems.append(f"PLC {io['address']} の機器 {io['device']} が components にありません")

    if not problems:
        derived = derive(doc, set_doc)
        for key in ("nets", "circuits"):
            if derived[key] != doc[key]:
                problems.append(
                    f"{key} が wires から計算した結果と違います（kairo gt-derive で更新）"
                )
    return problems

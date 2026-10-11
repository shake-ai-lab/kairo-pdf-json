"""Compare a page JSON (e.g. assembled from AI labels) with the ground truth (SPEC §8).

Both are laid on the same traced graph (pdf.trace.key_graph). A point the AI names is treated as
the ground-truth point it is wired to without passing another named point (e.g. the tip of a
symbol's stub line is the same conductor as the terminal it hangs from). Nets are compared as
sets of such points, so the connection structure is scored independently of how ports were
named; elements are matched by component and by the pair of nets they join; names are scored
separately.
"""

import math
import re
from collections import Counter, defaultdict, deque


def _nearest(points: list[dict]):
    def find(pos, tol: float = 1.5) -> str | None:
        if not pos:
            return None
        best = min(points, key=lambda p: math.dist((p["x"], p["y"]), pos))
        return best["id"] if math.dist((best["x"], best["y"]), pos) <= tol else None

    return find


def _named_points(doc: dict, find) -> dict[str, str]:
    """end name (port, rail, junction) -> point id"""
    out = {}
    for p in doc["ports"]:
        if (pt := find(p.get("pos"))) is not None:
            out[p["id"]] = pt
    for r in doc.get("rails", []):
        if (pt := find(r.get("pos"))) is not None:
            out[r["id"]] = pt
    for j in doc.get("junctions", []):
        if (pt := find(j.get("pos"))) is not None:
            out[j["id"]] = pt
    return out


def _canonical(graph: dict, named: set[str]):
    """Map any point to the named point it hangs from (nearest along runs, not crossing names)."""
    adj: dict[str, list[str]] = defaultdict(list)
    for r in graph["runs"]:
        adj[r["a"]].append(r["b"])
        adj[r["b"]].append(r["a"])
    best: dict[str, tuple[int, str]] = {}
    for p in named:
        q, seen = deque([(p, 0)]), {p}
        while q:
            cur, d = q.popleft()
            for nb in adj[cur]:
                if nb in seen or nb in named:
                    continue
                seen.add(nb)
                if nb not in best or d + 1 < best[nb][0]:
                    best[nb] = (d + 1, p)
                q.append((nb, d + 1))

    def canon(pt: str | None) -> str | None:
        if pt is None:
            return None
        if pt in named:
            return pt
        return best[pt][1] if pt in best else None

    return canon


def _net_index(doc: dict, named_pts: dict[str, str]) -> dict[str, int]:
    """point -> index of the net it belongs to (ports, rails and junctions)."""
    of_end: dict[str, int] = {}
    for i, n in enumerate(doc["nets"]):
        for m in n["members"]:
            of_end[m] = i
        if n.get("rail"):
            of_end[n["rail"]] = i
    changed = True
    while changed:  # junctions take the net of what they join
        changed = False
        for w in doc["wires"]:
            a, b = w["ends"]
            for x, y in ((a, b), (b, a)):
                if x not in of_end and y in of_end:
                    of_end[x] = of_end[y]
                    changed = True
    return {pt: of_end[e] for e, pt in named_pts.items() if e in of_end}


def _is_junction(end: str) -> bool:
    return end.startswith("J") and ":" not in end


def compare(ai: dict, gt: dict, graph: dict) -> dict:
    """Nets are compared by which net each ground-truth port ended up in: found by its name
    first, or by its position when the AI named it differently. A port placed at another point
    of the same net (e.g. the junction dot next to a coil terminal) is electrically the same and
    is reported separately as a position difference."""
    find = _nearest(graph["points"])
    g_named = _named_points(gt, find)  # GT end -> point
    canon = _canonical(graph, set(g_named.values()))
    g_net = _net_index(gt, g_named)  # GT point -> GT net index
    g_port_pt = {e: pt for e, pt in g_named.items() if not _is_junction(e)}  # ports and rails
    g_net_of = {g: g_net[pt] for g, pt in g_port_pt.items() if pt in g_net}

    a_pt = {e: canon(pt) for e, pt in _named_points(ai, find).items()}
    a_net_of_end: dict[str, int] = {}
    for i, n in enumerate(ai["nets"]):
        for m in n["members"]:
            a_net_of_end[m] = i
        if n.get("rail"):
            a_net_of_end[n["rail"]] = i
    by_point: dict[str, list[str]] = defaultdict(list)
    for e, pt in a_pt.items():
        if pt and e in a_net_of_end:
            by_point[pt].append(e)

    # each GT port: the AI net it is in (by name, else by position)
    a_net_of_gt: dict[str, int] = {}
    for g, pt in g_port_pt.items():
        if g in a_net_of_end:
            a_net_of_gt[g] = a_net_of_end[g]
        elif by_point.get(pt):
            a_net_of_gt[g] = a_net_of_end[by_point[pt][0]]
    g_groups: dict[int, set[str]] = defaultdict(set)
    for g, n in g_net_of.items():
        g_groups[n].add(g)
    a_groups: dict[int, set[str]] = defaultdict(set)
    for g, n in a_net_of_gt.items():
        if g in g_net_of:
            a_groups[n].add(g)
    split, merge, misconnected = [], [], []
    gnet_of_anet: dict[int, int] = {}
    for s in g_groups.values():
        if len({a_net_of_gt[g] for g in s if g in a_net_of_gt}) > 1:
            split.append(sorted(s))
    for an, s in a_groups.items():
        parts = Counter(g_net_of[g] for g in s)
        if len(parts) > 1:
            merge.append(sorted(s))
        top = parts.most_common(1)[0][0]
        gnet_of_anet[an] = top
        misconnected += [g for g in s if g_net_of[g] != top]
    missing = sorted(g for g in g_net_of if g not in a_net_of_gt)
    exact = sum(1 for s in g_groups.values() if any(s == t for t in a_groups.values()))
    a_unmapped = sorted(e for e, pt in a_pt.items() if pt is None and ":" in e)

    # names, and where the named port sits
    named_rows, name_wrong, position_off = [], [], []
    for g, pt in g_port_pt.items():
        if ":" not in g or g.startswith("rail:"):
            continue
        named_rows.append(g)
        if g not in a_pt:
            name_wrong.append((g, sorted(by_point.get(pt, []))))
        elif a_pt[g] != pt:
            same_net = gnet_of_anet.get(a_net_of_end.get(g, -1)) == g_net_of.get(g)
            if same_net:
                position_off.append(g)
            else:
                name_wrong.append((g, sorted(by_point.get(pt, []))))

    # elements: same component and the same pair of nets
    def gt_elements() -> list[dict]:
        return [
            {"ref": f"{c['id']}.{el['id']}", "comp": c["id"], **el,
             "nets": [g_net_of.get(p) for p in el["ports"]]}
            for c in gt["components"] for el in c.get("elements", [])
        ]  # fmt: skip

    def ai_elements() -> list[dict]:  # key: element IDs may repeat within a component
        return [
            {"ref": f"{c['id']}.{el['id']}", "key": (c["id"], i), "comp": c["id"], **el,
             "nets": [gnet_of_anet.get(a_net_of_end.get(p, -1)) for p in el["ports"]]}
            for c in ai["components"] for i, el in enumerate(c.get("elements", []))
        ]  # fmt: skip

    ge, ae = gt_elements(), ai_elements()
    rows = []
    used: set[tuple] = set()
    for g in ge:
        key = Counter(g["nets"])
        a = next(
            (
                x
                for x in ae
                if x["comp"] == g["comp"]
                and x["key"] not in used
                and None not in x["nets"]
                and Counter(x["nets"]) == key
            ),
            None,
        )
        if a:
            used.add(a["key"])
        rows.append(
            {
                "gt": g["ref"],
                "ai": a["ref"] if a else None,
                "kind_ok": bool(a) and a["kind"] == g["kind"],
                "contact_gt": g.get("contact"),
                "contact_ai": a.get("contact") if a else None,
            }
        )
    contact_rows = [r for r in rows if r["contact_gt"]]
    g_comps = {c["id"] for c in gt["components"]}
    a_comps = {c["id"] for c in ai["components"]}

    a_io = {io["address"]: io for io in ai.get("plc_io", [])}
    io_rows = []
    for io in gt.get("plc_io", []):
        a = a_io.get(io["address"])
        port_ok = False
        if a:
            an = a_net_of_end.get(a["port"])
            port_ok = an is not None and gnet_of_anet.get(an) == g_net_of.get(io["port"])
        io_rows.append(
            {
                "address": io["address"],
                "port_ok": port_ok,
                "device_ok": bool(a) and a.get("device") == io.get("device"),
            }
        )

    g_expr = [c["expression"] for c in gt["circuits"]]
    a_expr = [c["expression"] for c in ai["circuits"]]
    g_shape = [re.sub(r"\[[^\]]*\]", "[]", e) for e in g_expr]
    a_shape = [re.sub(r"\[[^\]]*\]", "[]", e) for e in a_expr]
    g_open = {g_named[o["port"]] for o in gt["open_ends"] if o["port"] in g_named}
    a_open = {a_pt.get(o["port"]) for o in ai["open_ends"]} - {None}

    def purpose_of(doc):
        return {c["id"]: (c.get("purpose") or {}) for c in doc["components"]}

    gpur, apur = purpose_of(gt), purpose_of(ai)
    purposes = [
        {
            "id": cid,
            "gt": gpur[cid].get("value"),
            "ai": apur.get(cid, {}).get("value"),
            "ai_basis": apur.get(cid, {}).get("basis"),
        }
        for cid in sorted(gpur)
        if gpur[cid]
    ]
    gate = not (split or merge or misconnected or missing)
    all_match = (
        gate
        and not name_wrong
        and all(r["ai"] and r["kind_ok"] for r in rows)
        and all(r["contact_ai"] == r["contact_gt"] for r in contact_rows)
        and all(r["port_ok"] and r["device_ok"] for r in io_rows)
        and all(e in a_expr for e in g_expr)
    )
    return {
        "gate_pass": gate,
        "all_match": all_match,
        "nets": {
            "gt": len(g_groups),
            "ai": len(ai["nets"]),
            "exact": exact,
            "split": split,
            "merge": merge,
            "misconnected": sorted(set(misconnected)),
            "missing_points": missing,
            "unmapped_ai_ports": a_unmapped,
        },
        "port_names": {"total": len(named_rows), "wrong": name_wrong, "position_off": position_off},
        "elements": {
            "gt": len(ge),
            "found": sum(1 for r in rows if r["ai"]),
            "kind_ok": sum(1 for r in rows if r["kind_ok"]),
            "contact_total": len(contact_rows),
            "contact_ok": sum(1 for r in contact_rows if r["contact_ai"] == r["contact_gt"]),
            "rows": rows,
            "extra": [x["ref"] for x in ae if x["key"] not in used],
        },
        "components": {
            "gt": len(g_comps),
            "ai": len(a_comps),
            "missing": sorted(g_comps - a_comps),
            "extra": sorted(a_comps - g_comps),
        },
        "plc_io": {
            "total": len(io_rows),
            "port_ok": sum(r["port_ok"] for r in io_rows),
            "device_ok": sum(r["device_ok"] for r in io_rows),
        },
        "circuits": {
            "gt": len(g_expr),
            "ai": len(a_expr),
            "same": sum(1 for e in g_expr if e in a_expr),
            # the same path when the wire numbers in brackets are left out
            "same_shape": sum(1 for e in g_shape if e in a_shape),
            "gt_only": [e for e in g_expr if e not in a_expr],
            "ai_only": [e for e in a_expr if e not in g_expr],
        },
        "open_ends": {"gt": len(g_open), "ai": len(a_open), "same": len(g_open & a_open)},
        "sheet_id": {
            "gt": (gt["sheet"].get("sheet_id") or {}).get("value"),
            "ai": (ai["sheet"].get("sheet_id") or {}).get("value"),
        },
        "purposes": purposes,
        "needs_review": ai.get("needs_review", []),
        "unresolved": ai.get("unresolved", []),
    }


def report_md(r: dict, title: str) -> str:
    """Japanese summary for people."""
    n, e, c = r["nets"], r["elements"], r["components"]
    io, cc, oe, pn = r["plc_io"], r["circuits"], r["open_ends"], r["port_names"]
    verdict = "合格" if r["gate_pass"] else "不合格"
    names_ok = pn["total"] - len(pn["wrong"])
    errors = (
        f"誤分割 {len(n['split'])}、誤統合 {len(n['merge'])}、誤接続 {len(n['misconnected'])}、"
        f"抜け {len(n['missing_points'])}"
    )
    lines = [
        f"# {title}",
        "",
        f"- 合格条件（誤分割・誤統合・誤接続・抜けがゼロ）：**{verdict}**",
        f"- 全項目一致（つながり・ポート名・素子・接点の a/b・PLC 入出力・回路の筋）："
        f"**{'一致' if r.get('all_match') else '不一致'}**",
        f"- ネット：正解 {n['gt']} 本のうち完全一致 {n['exact']} 本（AI {n['ai']} 本）",
        f"  - {errors}",
        f"- 2端子の要素：正解 {e['gt']} 個のうち見つけた {e['found']} 個、"
        f"種類が合う {e['kind_ok']} 個",
        f"- 接点の a/b：{e['contact_ok']} / {e['contact_total']}",
        f"- ポート名：{names_ok} / {pn['total']} が一致"
        + (
            f"（うち {len(pn.get('position_off', []))} 個は同じネットの別の点）"
            if pn.get("position_off")
            else ""
        ),
        f"- 機器：正解 {c['gt']}、AI {c['ai']}"
        f"（抜け {', '.join(c['missing']) or 'なし'}／余分 {', '.join(c['extra']) or 'なし'}）",
        f"- PLC 入出力：ポート {io['port_ok']} / {io['total']}、"
        f"機器 {io['device_ok']} / {io['total']}",
        f"- 回路の筋：正解 {cc['gt']} 本のうち式が一致 {cc['same']} 本（AI {cc['ai']} 本）。"
        f"線番を除いた筋の形の一致 {cc.get('same_shape', '—')} 本",
        f"- 先が描かれていない端：正解 {oe['gt']}、AI {oe['ai']}、一致 {oe['same']}",
        f"- 頁番号：正解 {r['sheet_id']['gt']}、AI {r['sheet_id']['ai']}",
        f"- 要確認リスト：{len(r['needs_review'])} 件、未解決：{len(r['unresolved'])} 件",
        "",
    ]
    if n["split"] or n["merge"] or n["misconnected"] or n["missing_points"]:
        lines += ["## つながりの誤り", ""]
        lines += [f"- 誤分割：{', '.join(s)}" for s in n["split"]]
        lines += [f"- 誤統合：{', '.join(s)}" for s in n["merge"]]
        if n["misconnected"]:
            lines.append(f"- 誤接続：{', '.join(n['misconnected'])}")
        if n["missing_points"]:
            lines.append(f"- 抜け：{', '.join(n['missing_points'])}")
        lines.append("")
    bad = [
        x
        for x in e["rows"]
        if not x["ai"] or not x["kind_ok"] or x["contact_ai"] != x["contact_gt"]
    ]
    if bad:
        lines += ["## 要素の違い", ""]
        for x in bad:
            contact = (
                f"、接点 正解 {x['contact_gt']} / AI {x['contact_ai']}" if x["contact_gt"] else ""
            )
            lines.append(f"- {x['gt']}：AI は {x['ai'] or '（見つけていない）'}{contact}")
        lines.append("")
    if pn["wrong"]:
        lines += ["## ポート名の違い（正解 → AI）", ""]
        lines += [f"- {g} → {', '.join(a) or '（名前なし）'}" for g, a in pn["wrong"]]
        lines.append("")
    if cc["gt_only"] or cc["ai_only"]:
        lines += ["## 回路の筋の違い", ""]
        lines += [f"- 正解だけ：{x}" for x in cc["gt_only"]]
        lines += [f"- AI だけ：{x}" for x in cc["ai_only"]]
        lines.append("")
    if r["purposes"]:
        lines += ["## 用途", ""]
        lines += [
            f"- {p['id']}：正解「{p['gt']}」／AI「{p['ai']}」（{p['ai_basis']}）"
            for p in r["purposes"]
        ]
        lines.append("")
    if r["needs_review"]:
        lines += ["## AI の要確認リスト", ""]
        lines += [f"- {x['what']}：{x['reason']}" for x in r["needs_review"]]
        lines.append("")
    if r["unresolved"]:
        lines += ["## AI の未解決", ""]
        lines += [f"- {x['what']}：{x['reason']}" for x in r["unresolved"]]
        lines.append("")
    return "\n".join(lines)

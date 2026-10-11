"""Compute the derived layers of a page JSON (schema 0.2) from the drawn layer.

- nets: groups of ports joined by `wires` (through junctions and pass-through terminals)
- circuits: paths from a supply rail to a PLC input or to the return rail, reduced to series and
  parallel parts, with the signal direction and its status (SPEC §6.3)

The same code is used for ground truth and for AI output, so circuits are never hand-written.
"""

import re
from collections import defaultdict

SHORT = {
    "coil": "コイル",
    "resistor": "抵抗",
    "diode": "ダイオード",
    "lamp": "表示灯",
    "other": "部品",
}
CONTACT = {"a": "a接点", "b": "b接点", "c": "c接点", "unknown": "接点"}
BASIS_JA = {"drawing": "図に記載", "other_page": "別の頁", "inferred": "推定", "human": "人の回答"}
PASS_THROUGH = {"terminal_block", "connector"}


def is_junction(end: str) -> bool:
    return re.fullmatch(r"J[0-9]+", end) is not None


def is_rail(end: str) -> bool:
    return end.startswith("rail:")


def comp_of(port: str) -> str:
    return port.split(":", 1)[0]


def term_of(port: str) -> str:
    return port.split(":", 1)[1]


class _DSU:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def conventions_of(set_doc: dict | None) -> dict[str, dict]:
    return {c["id"]: c for c in (set_doc or {}).get("conventions", [])}


# ---------------------------------------------------------------- nets


def derive_nets(doc: dict, set_doc: dict | None = None) -> list[dict]:
    comps = {c["id"]: c for c in doc["components"]}
    rails = {r["id"]: r for r in doc.get("rails", [])}
    open_ports = {o["port"] for o in doc.get("open_ends", [])}
    conv = conventions_of(set_doc).get("terminal_no_is_wire_no")
    dsu = _DSU()
    order: list[str] = []
    for w in doc["wires"]:
        a, b = w["ends"]
        for e in (a, b):
            if e not in dsu.parent:
                order.append(e)
        dsu.union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for e in order:
        groups[dsu.find(e)].append(e)
    nets: list[dict] = []
    used: set[str] = set()
    for ends in groups.values():
        ports = [e for e in ends if not is_junction(e) and not is_rail(e)]
        rail = next((e for e in ends if is_rail(e)), None)
        if not ports:
            continue
        wire_no = None
        if conv:
            nums = {
                term_of(p)
                for p in ports
                if comps.get(comp_of(p), {}).get("kind") == "terminal_block"
            }
            if len(nums) == 1:
                wire_no = {
                    "value": nums.pop(),
                    "basis": conv["basis"],
                    "evidence": [conv["rule"], *conv.get("evidence", [])],
                }
        if wire_no:
            nid = f"n_{wire_no['value']}"
        elif rail:
            nid = f"n_{rails[rail]['name'] if rail in rails else rail[5:]}"
        else:
            nid = "n_" + "_".join(dict.fromkeys(comp_of(p) for p in ports))
        base, k = nid, 2
        while nid in used:
            nid, k = f"{base}_{k}", k + 1
        used.add(nid)
        nets.append(
            {
                "id": nid,
                "rail": rail,
                "wire_no": wire_no,
                "kind": "power" if rail else "signal",
                "members": ports,
                "open_ends": [p for p in ports if p in open_ports],
            }
        )
    return nets


# ---------------------------------------------------------------- circuits


def _elements(doc: dict) -> list[tuple[str, dict, dict]]:
    out = []
    for c in doc["components"]:
        for el in c.get("elements", []):
            out.append((f"{c['id']}.{el['id']}", c, el))
    return out


def element_label(comp: dict, el: dict) -> str:
    short = CONTACT[el.get("contact", "unknown")] if el["kind"] == "contact" else SHORT[el["kind"]]
    return f"{comp['id']} {short}"


def _paths_edges(adj: dict, s: str, t: str, banned: set[str], limit: int = 200_000) -> set[int]:
    """Edges that lie on some simple path from s to t (small graphs: plain DFS)."""
    found: set[int] = set()
    steps = 0
    stack: list[tuple[str, list[int], set[str]]] = [(s, [], {s})]
    while stack:
        node, path, seen = stack.pop()
        steps += 1
        if steps > limit:
            break
        if node == t:
            found.update(path)
            continue
        for e, nxt in adj[node]:
            if nxt in seen or nxt in banned:
                continue
            stack.append((nxt, [*path, e], seen | {nxt}))
    return found


def _rev(x: tuple) -> tuple:
    if x[0] == "ser":
        return ("ser", [_rev(i) for i in reversed(x[1])])
    if x[0] == "par":
        return ("par", [_rev(i) for i in x[1]])
    return x


def _reduce(edges: list[dict], s: str, t: str) -> tuple | None:
    """Series-parallel reduction between s and t. Each edge: {u, v, x} with x oriented u→v."""
    edges = [dict(e) for e in edges]
    changed = True
    while changed and len(edges) > 1:
        changed = False
        groups: dict[frozenset, list[int]] = defaultdict(list)
        for i, e in enumerate(edges):
            groups[frozenset((e["u"], e["v"]))].append(i)
        for idx in groups.values():
            if len(idx) > 1:
                first = edges[idx[0]]
                parts = []
                for i in idx:
                    e = edges[i]
                    x = e["x"] if e["u"] == first["u"] else _rev(e["x"])
                    parts += x[1] if x[0] == "par" else [x]
                merged = {"u": first["u"], "v": first["v"], "x": ("par", parts)}
                edges = [e for i, e in enumerate(edges) if i not in idx] + [merged]
                changed = True
                break
        if changed:
            continue
        deg: dict[str, list[int]] = defaultdict(list)
        for i, e in enumerate(edges):
            deg[e["u"]].append(i)
            deg[e["v"]].append(i)
        for w, idx in deg.items():
            if w in (s, t) or len(idx) != 2:
                continue
            e1, e2 = edges[idx[0]], edges[idx[1]]
            x1 = e1["x"] if e1["v"] == w else _rev(e1["x"])
            u = e1["u"] if e1["v"] == w else e1["v"]
            x2 = e2["x"] if e2["u"] == w else _rev(e2["x"])
            v = e2["v"] if e2["u"] == w else e2["u"]
            merged = {"u": u, "v": v, "x": ("ser", [x1, ("net", w), x2])}
            edges = [e for i, e in enumerate(edges) if i not in idx] + [merged]
            changed = True
            break
    if len(edges) == 1 and {edges[0]["u"], edges[0]["v"]} == {s, t}:
        e = edges[0]
        return e["x"] if e["u"] == s else _rev(e["x"])
    return None


def _flat(x: tuple) -> list[tuple]:
    """Top-level series items."""
    if x[0] != "ser":
        return [x]
    out = []
    for i in x[1]:
        out += _flat(i)
    return out


def _compress(ids: list[str]) -> str:
    """SQ4, SQ5, SQ6 → SQ4〜SQ6."""
    parts = []
    run: list[tuple[str, int]] = []
    for cid in ids:
        m = re.fullmatch(r"(.*?)(\d+)", cid)
        if m and run and run[-1][0] == m.group(1) and run[-1][1] + 1 == int(m.group(2)):
            run.append((m.group(1), int(m.group(2))))
            continue
        if run:
            parts.append(run)
        run = [(m.group(1), int(m.group(2)))] if m else [(cid, -1)]
    if run:
        parts.append(run)
    out = []
    for r in parts:
        if r[0][1] < 0:
            out.append(r[0][0])
        elif len(r) >= 3:
            out.append(f"{r[0][0]}{r[0][1]}〜{r[-1][0]}{r[-1][1]}")
        else:
            out += [f"{p}{n}" for p, n in r]
    return "・".join(out)


class _Page:
    def __init__(self, doc: dict, nets: list[dict]) -> None:
        self.doc = doc
        self.comps = {c["id"]: c for c in doc["components"]}
        self.rails = {r["id"]: r for r in doc.get("rails", [])}
        self.nets = {n["id"]: n for n in nets}
        self.net_of = {p: n["id"] for n in nets for p in n["members"]}
        self.rail_net = {n["rail"]: n["id"] for n in nets if n["rail"]}
        self.els = {ref: (c, el) for ref, c, el in _elements(doc)}
        self.io = {p["port"]: p for p in doc.get("plc_io", []) if p.get("port")}
        regions = {r["id"]: r for r in doc.get("regions", [])}
        self.region_name = {
            k: (self.comps[k].get("name") if k in self.comps else None) or r["label"]
            for k, r in regions.items()
        }
        self.wire_adj: dict[str, list[str]] = defaultdict(list)
        for w in doc["wires"]:
            a, b = w["ends"]
            self.wire_adj[a].append(b)
            self.wire_adj[b].append(a)

    def net_label(self, nid: str) -> str:
        n = self.nets[nid]
        if n["wire_no"]:
            return n["wire_no"]["value"]
        if n["rail"]:
            return self.rails.get(n["rail"], {}).get("name", n["rail"][5:])
        return "–".join(dict.fromkeys(comp_of(p) for p in n["members"]))

    def render(self, x: tuple) -> str:
        if x[0] == "el":
            return element_label(*self.els[x[1]])
        if x[0] == "net":
            return f"[{self.net_label(x[1])}]"
        if x[0] == "ser":
            return " → ".join(self.render(i) for i in x[1])
        parts = [f"（{self.render(i)}）" if i[0] == "ser" else self.render(i) for i in x[1]]
        return "（" + " ∥ ".join(parts) + "）"

    def refs(self, x: tuple) -> list[str]:
        if x[0] == "el":
            return [x[1]]
        if x[0] == "net":
            return []
        return [r for i in x[1] for r in self.refs(i)]

    def port_text(self, p: str) -> str:
        if is_junction(p):
            return "黒丸"
        if is_rail(p):
            return self.rails.get(p, {}).get("name", p[5:])
        c = self.comps.get(comp_of(p), {})
        kind = c.get("kind")
        if kind == "terminal_block":
            return f"端子台 {c['id']} の {term_of(p)} 番"
        if kind == "connector":
            where = self.region_name.get(c.get("region") or "", "")
            return f"コネクタ {c['id']} の {term_of(p)} 番" + (f"（{where}）" if where else "")
        if p in self.io:
            return f"PLC 入力 {self.io[p]['address']}"
        return p

    def route(self, nid: str, entries: list[str], exits: list[str]) -> dict:
        n = self.nets[nid]
        through = [
            p
            for p in n["members"]
            if self.comps.get(comp_of(p), {}).get("kind") in PASS_THROUGH
            and p not in n["open_ends"]
        ]
        r = {"net": nid, "entries": entries, "exits": exits, "through": through}
        if len(entries) == 1 and len(exits) == 1:
            path = self._bfs(entries[0], exits[0])
            if path:
                r["path"] = path
                on = set(path)
                r["branches"] = [
                    {"at": node, "to": self._leaves(node, on)}
                    for node in path
                    if any(nb not in on for nb in self.wire_adj[node])
                ]
        return r

    def _bfs(self, s: str, t: str) -> list[str] | None:
        prev = {s: None}
        q = [s]
        while q:
            cur = q.pop(0)
            if cur == t:
                out = []
                while cur is not None:
                    out.append(cur)
                    cur = prev[cur]
                return out[::-1]
            for nb in self.wire_adj[cur]:
                if nb not in prev:
                    prev[nb] = cur
                    q.append(nb)
        return None

    def _leaves(self, start: str, on: set[str]) -> list[str]:
        out, stack, seen = [], [nb for nb in self.wire_adj[start] if nb not in on], set(on)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if not is_junction(cur):
                out.append(cur)
            stack += [nb for nb in self.wire_adj[cur] if nb not in seen and is_junction(cur)]
        return out

    def route_text(self, r: dict) -> str:
        label = f"[{self.net_label(r['net'])}]"
        if "path" in r:
            text = " → ".join(self.port_text(p) for p in r["path"][1:-1])
            for b in r.get("branches", []):
                opens = [p for p in b["to"] if p in self.nets[r["net"]]["open_ends"]]
                if opens:
                    where = "黒丸" if is_junction(b["at"]) else self.port_text(b["at"])
                    text += (
                        f"（{where}から {', '.join(self.port_text(p) for p in opens)} へ分岐。"
                        "この頁では先が描かれていない）"
                    )
            return f"{label} {text}" if text else label
        parts = [
            f"入る：{'、'.join(self.port_text_el(p) for p in r['entries'])}",
            f"通る：{'、'.join(self.port_text(p) for p in r['through'])}" if r["through"] else "",
            f"出る：{'、'.join(self.port_text_el(p) for p in r['exits'])}",
        ]
        opens = self.nets[r["net"]]["open_ends"]
        if opens:
            parts.append(
                f"この頁では先が描かれていない：{'、'.join(self.port_text(p) for p in opens)}"
            )
        return f"{label} " + " ／ ".join(p for p in parts if p)

    def port_text_el(self, p: str) -> str:
        for c, el in self.els.values():
            if p in el["ports"]:
                return element_label(c, el)
        return self.port_text(p)


def derive_circuits(doc: dict, nets: list[dict]) -> list[dict]:
    pg = _Page(doc, nets)
    adj: dict[str, list[tuple[int, str]]] = defaultdict(list)
    graph: list[dict] = []
    for ref, (_c, el) in pg.els.items():
        a, b = (pg.net_of.get(p) for p in el["ports"])
        if a is None or b is None or a == b:
            continue
        i = len(graph)
        graph.append({"u": a, "v": b, "x": ("el", ref)})
        adj[a].append((i, b))
        adj[b].append((i, a))
    plus = [(rid, nid) for rid, nid in pg.rail_net.items() if pg.rails[rid]["polarity"] == "plus"]
    zero = {nid for rid, nid in pg.rail_net.items() if pg.rails[rid]["polarity"] == "zero"}
    receivers = [
        (p["port"], pg.net_of[p["port"]])
        for p in doc.get("plc_io", [])
        if p["direction"] == "input" and p.get("port") in pg.net_of
    ]
    circuits: list[dict] = []
    for rail_id, s in plus:
        rail = pg.rails[rail_id]
        pol = rail.get("polarity_basis") or {"basis": "inferred"}
        known = pol["basis"] != "inferred"
        for port, t in receivers:
            es = _paths_edges(adj, s, t, banned=zero)
            if es:
                circuits.append(
                    _circuit(pg, [graph[i] for i in sorted(es)], s, t, rail, known, receiver=port)
                )
        for z in zero:
            es = _paths_edges(adj, s, z, banned={t for _, t in receivers})
            # one circuit per group of inner nets that hang together
            inner = defaultdict(set)
            dsu = _DSU()
            for i in es:
                u, v = graph[i]["u"], graph[i]["v"]
                if u not in (s, z) and v not in (s, z):
                    dsu.union(u, v)
            for i in es:
                u, v = graph[i]["u"], graph[i]["v"]
                key = next((n for n in (u, v) if n not in (s, z)), f"direct{i}")
                inner[dsu.find(key) if not key.startswith("direct") else key].add(i)
            for group in inner.values():
                circuits.append(
                    _circuit(
                        pg, [graph[i] for i in sorted(group)], s, z, rail, known, receiver=None
                    )
                )
    for k, c in enumerate(circuits, 1):
        c["id"] = f"c{k}"
    return circuits


def _circuit(
    pg: _Page, edges: list[dict], s: str, t: str, rail: dict, known: bool, receiver: str | None
) -> dict:
    x = _reduce(edges, s, t)
    nets_in = sorted({e["u"] for e in edges} | {e["v"] for e in edges}, key=list(pg.nets).index)
    refs = [e["x"][1] for e in edges]
    end_rail = pg.nets[t]["rail"]
    to = receiver or end_rail or t
    io = pg.io.get(receiver) if receiver else None
    first = [e["x"][1] for e in edges if s in (e["u"], e["v"])]
    last = [e["x"][1] for e in edges if t in (e["u"], e["v"])]
    if receiver:
        title = f"{_compress([r.split('.')[0] for r in dict.fromkeys(first)])} → {io['address']}"
    else:
        title = (
            f"{_compress(list(dict.fromkeys(r.split('.')[0] for r in first)))} → "
            f"{_compress(list(dict.fromkeys(r.split('.')[0] for r in last)))}"
        )
    start = pg.rails.get(rail["id"], rail)["name"]
    finish = f"{io['address']}（PLC 入力）" if io else pg.net_label(t)
    if x is None:
        expression = f"{start} → （直列・並列に分けられない：{'、'.join(refs)}） → {finish}"
        steps = [expression]
        routes: list[dict] = []
    else:
        mid = f" → [{pg.net_label(t)}]" if receiver else ""
        expression = f"{start} → {pg.render(x)}{mid} → {finish}"
        steps, routes = _steps(pg, x, s, t, rail, io)
    opens = [p for nid in nets_in for p in pg.nets[nid]["open_ends"]]
    target_role = "PLC 入力（受け手）" if io else f"{finish}（0V 側）"
    pol = BASIS_JA[(rail.get("polarity_basis") or {}).get("basis", "inferred")]
    basis = f"{start} は＋側（{pol}）、{target_role}"
    if opens:
        basis += f"。ただし {'、'.join(opens)} の側から信号が来るかは不明"
    return {
        "id": "",
        "title": title,
        "kind": "to_receiver" if receiver else "to_return",
        "from": rail["id"],
        "to": to,
        "expression": expression,
        "elements": refs,
        "nets": nets_in,
        "routes": routes,
        "steps": steps,
        "open_ends": opens,
        "direction": {"status": "confirmed" if known else "inferred", "basis": basis},
    }


def _steps(pg: _Page, x: tuple, s: str, t: str, rail: dict, io: dict | None):
    items = _flat(x)
    steps = [f"{rail['name']}（電源の＋側）" if rail["polarity"] == "plus" else rail["name"]]
    routes = []
    seq = [("net", s), *items, ("net", t)]
    for k, it in enumerate(seq):
        if it[0] == "net":
            if it[1] in (s, t) and pg.nets[it[1]]["rail"]:
                continue
            before = pg.refs(seq[k - 1]) if k > 0 else []
            after = pg.refs(seq[k + 1]) if k + 1 < len(seq) else []
            members = pg.nets[it[1]]["members"]
            entries = [p for r in before for p in pg.els[r][1]["ports"] if p in members]
            exits = [p for r in after for p in pg.els[r][1]["ports"] if p in members]
            if it[1] == t and io:
                exits = [io["port"]]
            r = pg.route(it[1], entries, exits)
            routes.append(r)
            steps.append(pg.route_text(r))
        elif it[0] == "el":
            steps.append(pg.render(it).replace(" ", " の ", 1))
        elif it[0] == "par":
            subs = it[1]
            if all(s_[0] == "el" for s_ in subs):
                labels = [element_label(*pg.els[s_[1]]) for s_ in subs]
                kinds = {lab.split(" ", 1)[1] for lab in labels}
                if len(kinds) == 1:
                    comps = _compress([lab.split(" ", 1)[0] for lab in labels])
                    steps.append(f"{comps} の {kinds.pop()}（{len(subs)}つが並列）")
                    continue
            steps.append(" ／ ".join(pg.render(s_) for s_ in subs) + f"（{len(subs)}つが並列）")
        else:
            steps.append(pg.render(it))
    if io:
        steps.append(f"PLC 入力 {io['address']}「{io.get('comment') or ''}」")
    elif pg.nets[t]["rail"]:
        steps.append(f"{pg.net_label(t)}（0V 側）")
    return steps, routes


def derive(doc: dict, set_doc: dict | None = None) -> dict:
    """Return a copy of doc with `nets` and `circuits` recomputed."""
    out = dict(doc)
    out["nets"] = derive_nets(doc, set_doc)
    out["circuits"] = derive_circuits(doc, out["nets"])
    return out

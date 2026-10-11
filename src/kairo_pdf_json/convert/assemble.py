"""Turn the AI's labels (schema/ai_labels.schema.json) into a page JSON (schema 0.2).

The AI names points of the traced graph (pdf.trace.key_graph); this module walks the wire runs
between named points to build `wires`, then computes nets and circuits (model.derive). Points
the AI left unnamed still conduct: an unnamed terminal circle or connector pin becomes the port
`?:P…`, an unnamed branch becomes a junction, and an unnamed wire end is a dead end.
"""

from collections import defaultdict

from kairo_pdf_json.model.derive import derive


def _bbox(b) -> list[float] | None:
    return [round(float(x), 2) for x in b] if b and len(b) == 4 else None


def assemble(labels: dict, graph: dict, source: dict) -> tuple[dict, dict, list[str]]:
    """Return (page JSON, drawing-set conventions, problems found while assembling)."""
    problems: list[str] = []
    points = {p["id"]: p for p in graph["points"]}
    runs_at: dict[str, list[dict]] = defaultdict(list)
    for r in graph["runs"]:
        runs_at[r["a"]].append(r)
        if r["b"] != r["a"]:
            runs_at[r["b"]].append(r)

    name_of: dict[str, str] = {}

    def assign(point: str, name: str) -> None:
        if point not in points:
            problems.append(f"{name} の点 {point} が線の追跡結果にありません")
        elif point in name_of and name_of[point] != name:
            problems.append(f"点 {point} に2つの名前があります（{name_of[point]} と {name}）")
        else:
            name_of[point] = name

    for c in labels["components"]:
        for el in c["elements"]:
            for np in el["ports"]:
                assign(np["point"], np["name"])
        for np in c["terminals"]:
            assign(np["point"], np["name"])
    rails = []
    for r in labels["rails"]:
        rid = f"rail:{r['name']}"
        assign(r["point"], rid)
        p = points.get(r["point"])
        rails.append(
            {
                "id": rid,
                "name": r["name"],
                "polarity": r["polarity"],
                "polarity_basis": r["polarity_basis"],
                **({"pos": [p["x"], p["y"]]} if p else {}),
            }
        )
    for io in labels["plc_io"]:
        assign(io["point"], io["port"])
    seen_names: dict[str, str] = {}
    for pt, nm in name_of.items():
        if nm in seen_names:
            problems.append(f"名前 {nm} が2つの点に付いています（{seen_names[nm]} と {pt}）")
        seen_names[nm] = pt

    # unnamed points that still conduct
    dots = sorted(
        (p for p in graph["points"] if p["kind"] == "junction_dot"), key=lambda p: (p["y"], p["x"])
    )
    k = 0
    for p in dots:
        if p["id"] not in name_of:
            k += 1
            name_of[p["id"]] = f"J{k}"
    for p in graph["points"]:
        if p["id"] in name_of:
            continue
        if p["kind"] in ("terminal_circle", "connector_pin"):
            name_of[p["id"]] = f"?:{p['id']}"
            problems.append(f"端子 {p['id']}（{p['kind']}）に名前がありません")
        elif p["kind"] == "branch":
            k += 1
            name_of[p["id"]] = f"J{k}"

    # walk runs between named points; unnamed ends are dead ends
    used: set[str] = set()
    wires = []
    for start in sorted(name_of, key=lambda q: (points[q]["y"], points[q]["x"])):
        for r0 in runs_at[start]:
            if r0["id"] in used:
                continue
            path, cur, r = [], start, r0
            ok = True
            while True:
                used.add(r["id"])
                seg = r["path"] if r["a"] == cur else r["path"][::-1]
                path += seg if not path else seg[1:]
                nxt = r["b"] if r["a"] == cur else r["a"]
                if nxt in name_of:
                    break
                rest = [x for x in runs_at[nxt] if x["id"] != r["id"]]
                if len(rest) != 1:
                    ok = False
                    break
                cur, r = nxt, rest[0]
            if ok and nxt != start:
                wires.append({"ends": [name_of[start], name_of[nxt]], "path": path})
    for i, w in enumerate(wires, 1):
        w["id"] = f"W{i}"
    wires = [{"id": w["id"], "ends": w["ends"], "path": w["path"]} for w in wires]

    junctions = [
        {"id": nm, "pos": [points[pt]["x"], points[pt]["y"]]}
        for pt, nm in name_of.items()
        if nm.startswith("J") and ":" not in nm
    ]
    port_pos = {
        nm: [points[pt]["x"], points[pt]["y"]]
        for pt, nm in name_of.items()
        if ":" in nm and not nm.startswith("rail:")
    }

    comps: dict[str, dict] = {}
    for c in labels["components"]:
        comp = {
            "id": c["id"],
            "name": c["name"],
            "kind": c["kind"],
            "symbol": c["symbol"],
            "region": c["region"],
            "purpose": c["purpose"],
        }
        els = []
        for el in c["elements"]:
            e = {"id": el["id"], "kind": el["kind"], "symbol": el["symbol"]}
            if el["kind"] == "contact":
                e["contact"] = el["contact"] or "unknown"
            e["ports"] = [np["name"] for np in el["ports"]][:2]
            if len(e["ports"]) != 2:
                problems.append(f"{c['id']} の {el['id']} の端が2つではありません")
                continue
            if _bbox(el["bbox"]):
                e["loc"] = {"bbox": _bbox(el["bbox"])}
            els.append(e)
        if els:
            comp["elements"] = els
        terms = [np["name"].split(":", 1)[1] for np in c["terminals"] if ":" in np["name"]]
        if terms:
            comp["terminals"] = terms
        boxes = [e["loc"]["bbox"] for e in els if "loc" in e]
        if boxes:
            comp["loc"] = {
                "bbox": [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
            }
        comps[c["id"]] = comp
    # every port needs a component; terminals the AI named but did not list are added
    for nm in port_pos:
        cid, term = nm.split(":", 1)
        if cid not in comps:
            comps[cid] = {"id": cid, "kind": "unknown" if cid == "?" else "unit", "terminals": []}
        c = comps[cid]
        in_el = any(nm in e["ports"] for e in c.get("elements", []))
        if not in_el and term not in c.setdefault("terminals", []):
            c["terminals"].append(term)
    for c in comps.values():
        if c.get("terminals") == []:
            del c["terminals"]
    regions = [
        {"id": r["id"], "label": r["label"], "kind": r["kind"], "meaning": r["meaning"]}
        for r in labels["regions"]
    ]
    region_ids = {r["id"] for r in regions}
    for c in comps.values():
        if c.get("region") and c["region"] not in region_ids:
            regions.append(
                {"id": c["region"], "label": c["region"], "kind": "other", "meaning": None}
            )
            region_ids.add(c["region"])

    sheet = {"title": labels["sheet"]["title"], "sheet_id": labels["sheet"]["sheet_id"]}
    sheet["layout"] = labels["sheet"]["layout"]
    doc = {
        "schema_version": "0.2",
        "source": source,
        "sheet": sheet,
        "regions": regions,
        "rails": rails,
        "components": list(comps.values()),
        "ports": [{"id": nm, "pos": pos} for nm, pos in port_pos.items()],
        "junctions": junctions,
        "wires": wires,
        "open_ends": [],
        "nets": [],
        "circuits": [],
        "plc_io": [
            {
                "address": io["address"],
                "direction": io["direction"],
                "unit": io["port"].split(":", 1)[0],
                "port": io["port"],
                "device": io["device"],
                "comment": io["comment"],
            }
            for io in labels["plc_io"]
        ],
        "cross_references": [
            {
                "text": x["text"],
                "kind": x["kind"],
                "component": x["component"],
                "target": {
                    "sheet": x["target_sheet"],
                    "line": x["target_line"],
                    "page": x["target_page"],
                },
            }
            for x in labels["cross_references"]
        ],
        "tables": [
            {"id": f"T{i}", "title": t["title"], "rows": t["rows"], "note": t["note"]}
            for i, t in enumerate(labels["tables"], 1)
        ],
        "unresolved": labels["unresolved"],
        "needs_review": [
            {"what": n["what"], "reason": n["reason"], "ref": n["ref"]}
            for n in labels["needs_review"]
        ],
    }
    for o in labels["open_ends"]:
        port = o["port"]
        if port not in port_pos and port.count(":") >= 2 and port.split(":", 1)[1] in port_pos:
            # e.g. "A11:X51:16" for the port the AI itself named "X51:16"
            problems.append(
                f"先が描かれていない端 {port} を {port.split(':', 1)[1]} と読み替えました"
            )
            port = port.split(":", 1)[1]
        if port in port_pos:
            doc["open_ends"].append({"port": port, "note": o["note"], "evidence": o["evidence"]})
        else:
            problems.append(f"先が描かれていない端 {port} が点に付いていません")
    set_doc = {"conventions": labels["conventions"]}
    return derive(doc, set_doc), set_doc, problems

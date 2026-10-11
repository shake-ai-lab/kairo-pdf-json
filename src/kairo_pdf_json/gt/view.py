"""Build the local review page for a page JSON (schema 0.2).

Everything shown comes from the page JSON: wires and junctions (drawn as they are in the JSON),
ports, components, circuits. For vector pages the symbols and the label text are taken from the
vector data inside the boxes the JSON gives, so the page looks like the drawing. Green tags show
the reading (a/b contact, coil …) so the reviewer can tell it apart from the drawing itself.
"""

import html
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

import pypdfium2 as pdfium

from kairo_pdf_json.model.derive import CONTACT, SHORT, comp_of, is_junction, is_rail
from kairo_pdf_json.pdf.render import render_page
from kairo_pdf_json.samples import Sample, page_stem

TEMPLATE = Path(__file__).with_name("view_template.html")
KIND_JA = {
    "limit_switch": "リミットスイッチ",
    "terminal_block": "端子台",
    "connector": "コネクタ",
    "unit": "ユニット",
    "plc_unit": "ユニット（PLC 入力）",
    "relay": "リレー",
    "diode": "ダイオード",
    "resistor": "抵抗",
    "indicator_lamp": "表示灯",
}
BASIS_JA = {"drawing": "図に記載", "other_page": "別の頁", "inferred": "推定", "human": "人の回答"}
PLUS, ZERO = "#e07000", "#1f6fd1"
PALETTE = ["#d62828", "#8e44ad", "#0f8a7e", "#b5651d", "#c2185b"]
Box = tuple[float, float, float, float]


def page_size_pt(pdf_path: Path, page: int) -> tuple[float, float]:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return doc[page - 1].get_size()  # rotation applied, pt
    finally:
        doc.close()


def _inside(pts, box: Box, m: float = 0.4) -> bool:
    return all(box[0] - m <= p[0] <= box[2] + m and box[1] - m <= p[1] <= box[3] + m for p in pts)


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _poly(pts) -> str:
    return "M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in pts)


def _circle(pos, r: float, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<circle{c} cx="{pos[0]:.2f}" cy="{pos[1]:.2f}" r="{r}"/>'


def _rect(x: float, y: float, w: float, h: float, cls: str = "", rx: float = 1.5) -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<rect{c} x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{rx}"/>'


def _sourced(v: dict) -> str:
    """'value' with its source: 別の頁：p.12…／p.188…"""
    ev = "／".join(v.get("evidence", []))
    return (
        f"{BASIS_JA.get(v.get('basis', ''), '')}：{ev}"
        if ev
        else BASIS_JA.get(v.get("basis", ""), "")
    )


class _Drawing:
    def __init__(self, doc: dict, vector: dict | None) -> None:
        self.doc = doc
        self.vector = vector
        self.words = (vector or {}).get("words", [])
        self.ports = {p["id"]: p for p in doc["ports"]}
        self.comps = {c["id"]: c for c in doc["components"]}
        self.rails = {r["id"]: r for r in doc.get("rails", [])}
        self.junctions = {j["id"]: j for j in doc["junctions"]}
        self.net_of: dict[str, str] = {}
        for n in doc["nets"]:
            for p in n["members"]:
                self.net_of[p] = n["id"]
            if n.get("rail"):
                self.net_of[n["rail"]] = n["id"]
        # junctions belong to the net of the wires they join
        changed = True
        while changed:
            changed = False
            for w in doc["wires"]:
                a, b = w["ends"]
                for x, y in ((a, b), (b, a)):
                    if x not in self.net_of and y in self.net_of:
                        self.net_of[x] = self.net_of[y]
                        changed = True
        self.wires_of_net: dict[str, list[dict]] = defaultdict(list)
        for w in doc["wires"]:
            self.wires_of_net[self.net_of.get(w["ends"][0], "?")].append(w)
        self.elements = {
            f"{c['id']}.{el['id']}": (c, el)
            for c in doc["components"]
            for el in c.get("elements", [])
        }
        self.io = {p["port"]: p for p in doc.get("plc_io", []) if p.get("port")}
        self.open_ports = {o["port"] for o in doc["open_ends"]}

    # ---- geometry helpers
    def paths_in(self, box: Box, m: float = 0.4) -> list[list[tuple[float, float]]]:
        if not self.vector:
            return [
                [
                    (box[0], box[1]),
                    (box[2], box[1]),
                    (box[2], box[3]),
                    (box[0], box[3]),
                    (box[0], box[1]),
                ]
            ]
        return [
            [(q[0], q[1]) for q in p["pts"]]
            for p in self.vector["paths"]
            if _inside(p["pts"], box, m)
        ]

    def words_in(self, box: Box) -> list[dict]:
        out = []
        for w in self.words:
            x0, y0, x1, y1 = w["bbox"]
            if _inside([((x0 + x1) / 2, (y0 + y1) / 2)], box, 0.2):
                out.append(w)
        return out

    def port_box(self, pid: str) -> Box | None:
        p = self.ports.get(pid)
        if not p or "pos" not in p:
            return None
        x, y = p["pos"]
        kind = self.comps.get(comp_of(pid), {}).get("kind")
        if kind == "connector":
            return (x - 6.2, y - 4.3, x + 6.2, y + 4.3)
        if pid in self.io:
            return (x - 7.0, y - 7.4, x + 21.5, y + 7.4)
        return None

    # ---- pieces
    def prune(self, wires: list[dict], keep: set[str]) -> list[dict]:
        wires = list(wires)
        while True:
            deg: dict[str, int] = defaultdict(int)
            for w in wires:
                for e in w["ends"]:
                    deg[e] += 1
            drop = [w for w in wires if any(deg[e] == 1 and e not in keep for e in w["ends"])]
            if not drop:
                return wires
            wires = [w for w in wires if w not in drop]

    def net_svg(self, wires: list[dict], color: str, nid: str = "") -> str:
        d = " ".join(_poly(w["path"]) for w in wires if w.get("path"))
        ends = {e for w in wires for e in w["ends"]}
        dots = "".join(
            _circle(self.junctions[j]["pos"], 1.1)
            for j in ends
            if is_junction(j) and j in self.junctions
        )
        attr = f' data-net="{html.escape(nid)}"' if nid else ""
        return f'<g class="net"{attr} style="--c:{color}"><path d="{d}"/>{dots}</g>'

    def symbols_svg(self, boxes: list[Box], ports: list[str], cls: str = "sym") -> str:
        paths = [p for b in boxes for p in self.paths_in(b)]
        for pid in ports:
            b = self.port_box(pid)
            if b:
                paths += self.paths_in(b, 0.2)
        d = " ".join(_poly(p) for p in paths)
        circles = "".join(
            _circle(self.ports[p]["pos"], 1.95)
            for p in ports
            if self.comps.get(comp_of(p), {}).get("kind") == "terminal_block" and p in self.ports
        )
        return f'<g class="{cls}"><path d="{d}"/>{circles}</g>'

    def labels_svg(self, boxes: list[Box]) -> tuple[str, list[Box]]:
        seen, out, used = set(), [], []
        for b in boxes:
            for w in self.words_in(b):
                key = tuple(w["bbox"])
                if key in seen:
                    continue
                seen.add(key)
                x0, y0, x1, y1 = w["bbox"]
                used.append((x0, y0, x1, y1))
                out.append(
                    f'<text class="lbl" x="{x0:.2f}" y="{y1 - 1.2:.2f}" '
                    f'font-size="{w["size"]:.1f}">{html.escape(w["text"])}</text>'
                )
        return "".join(out), used

    def place_tags(self, tags: list[tuple[str, Box]], obstacles: list[Box]) -> str:
        placed: list[Box] = []
        out = []
        page_words = [tuple(w["bbox"]) for w in self.words]
        for text, b in tags:
            w, h = len(text) * 4.6 + 3, 6.2
            ax, ay = b[2] + 1.5, b[1] - h - 0.4  # preferred: above right
            best = None
            for r in range(0, 34):
                for dx in range(-r, r + 1):
                    for dy in (-r, r) if abs(dx) != r else range(-r, r + 1):
                        x, y = ax + dx * 1.5, ay + dy * 1.5
                        cand = (x, y, x + w, y + h)
                        if any(_overlap(cand, o) for o in obstacles + page_words + placed):
                            continue
                        dist = math.hypot(x - ax, y - ay)
                        if best is None or dist < best[0]:
                            best = (dist, cand)
                if best:
                    break
            if not best:
                continue
            c = best[1]
            placed.append(c)
            out.append(
                f'<g class="tag">{_rect(c[0], c[1], w, h)}'
                f'<text x="{c[0] + 1.5:.1f}" y="{c[1] + 4.6:.1f}">{text}</text></g>'
            )
        return "".join(out)

    def open_svg(self, pid: str) -> str:
        p = self.ports.get(pid)
        if not p or "pos" not in p:
            return ""
        x, y = p["pos"]
        x -= 3.2
        return (
            f'<g class="open"><path d="M{x:.2f},{y:.2f}H{x - 12:.2f}"/>'
            f'<circle cx="{x - 15.5:.2f}" cy="{y:.2f}" r="3.3"/>'
            f'<text x="{x - 15.5:.2f}" y="{y + 1.7:.2f}">?</text></g>'
        )


def _union(boxes: list) -> list[float] | None:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _seg_boxes(wires: list[dict]) -> list[Box]:
    out = []
    for w in wires:
        for a, b in zip(w["path"], w["path"][1:], strict=False):
            out.append(
                (
                    min(a[0], b[0]) - 0.4,
                    min(a[1], b[1]) - 0.4,
                    max(a[0], b[0]) + 0.4,
                    max(a[1], b[1]) + 0.4,
                )
            )
    return out


def _el_box(el: dict) -> Box | None:
    b = (el.get("loc") or {}).get("bbox")
    return tuple(b) if b and len(b) == 4 else None


def _element_short(el: dict) -> str:
    return CONTACT[el.get("contact", "unknown")] if el["kind"] == "contact" else SHORT[el["kind"]]


def _circuit_item(dr: _Drawing, c: dict) -> dict:
    keep_by_net: dict[str, set[str]] = defaultdict(set)
    for ref in c["elements"]:
        for p in dr.elements[ref][1]["ports"]:
            keep_by_net[dr.net_of.get(p, "?")].add(p)
    keep_by_net[dr.net_of.get(c["from"], "?")].add(c["from"])
    keep_by_net[dr.net_of.get(c["to"], "?")].add(c["to"])
    for p in c.get("open_ends", []):
        keep_by_net[dr.net_of.get(p, "?")].add(p)
    parts, legend, all_wires, ports = [], [], [], set()
    k = 0
    for nid in c["nets"]:
        wires = dr.prune(dr.wires_of_net[nid], keep_by_net[nid])
        net = next(n for n in dr.doc["nets"] if n["id"] == nid)
        rail = dr.rails.get(net.get("rail") or "")
        if rail:
            color = PLUS if rail["polarity"] == "plus" else ZERO
            name = f"{rail['name']}（{'電源の＋側' if rail['polarity'] == 'plus' else '0V 側'}）"
        else:
            color, k = PALETTE[k % len(PALETTE)], k + 1
            between = " と ".join(dict.fromkeys(comp_of(p) for p in net["members"]))
            name = f"{net['wire_no']['value']}（線番）" if net.get("wire_no") else f"{between} の間"
        legend.append([name, color])
        parts.append(dr.net_svg(wires, color))
        all_wires += wires
        ports |= {e for w in wires for e in w["ends"] if not is_junction(e) and not is_rail(e)}
    el_boxes = [b for r in c["elements"] if (b := _el_box(dr.elements[r][1]))]
    pass_ports = sorted(
        p for p in ports if p not in {q for r in c["elements"] for q in dr.elements[r][1]["ports"]}
    )
    parts.append(dr.symbols_svg(el_boxes, pass_ports))
    label_boxes = []
    comps_in = {r.split(".")[0] for r in c["elements"]}
    for cid in comps_in:
        if dr.comps[cid].get("label_bbox"):
            label_boxes.append(tuple(dr.comps[cid]["label_bbox"]))
    for p in ports:
        label_boxes += [tuple(b) for b in dr.ports.get(p, {}).get("label_bboxes", [])]
    for rid in (c["from"], c["to"]):
        if rid in dr.rails and dr.rails[rid].get("label_bbox"):
            label_boxes.append(tuple(dr.rails[rid]["label_bbox"]))
    if c["to"] in dr.io:
        y = dr.ports[c["to"]]["pos"][1]
        label_boxes.append((420.0, y - 9.0, 600.0, y + 1.0))  # the input's name on the right
    for x in dr.doc.get("cross_references", []):
        if x.get("component") in comps_in and x.get("loc", {}).get("bbox"):
            b = x["loc"]["bbox"]
            label_boxes += [tuple(b), (b[0] - 2, b[1] - 22, b[0] + 75, b[1] - 8)]
    labels, used = dr.labels_svg(label_boxes)
    parts.append(labels)
    for p in c.get("open_ends", []):
        parts.append(dr.open_svg(p))
    tags = [(_element_short(dr.elements[r][1]), _el_box(dr.elements[r][1])) for r in c["elements"]]
    if c["to"] in dr.io:
        tags.append(("PLC入力", dr.port_box(c["to"])))
    markers = []
    for p in c.get("open_ends", []):
        if "pos" in dr.ports.get(p, {}):
            x, y = dr.ports[p]["pos"]
            markers.append((x - 22.5, y - 3.4, x - 3.0, y + 3.4))
            tags.append(("先は不明", (x - 22.5, y - 3.4, x - 15.5, y + 3.4)))
    obstacles = (
        markers
        + _seg_boxes(all_wires)
        + el_boxes
        + used
        + [dr.port_box(p) for p in pass_ports if dr.port_box(p)]
    )
    parts.append(dr.place_tags([t for t in tags if t[1]], obstacles))
    xs = [pt[0] for w in all_wires for pt in w["path"]]
    ys = [pt[1] for w in all_wires for pt in w["path"]]
    meta = [f"式：{c['expression']}"]
    st = {"confirmed": "確定", "inferred": "推定", "unknown": "不明"}[c["direction"]["status"]]
    meta.append(f"信号の向き：{st}（{c['direction'].get('basis', '')}）")
    sub = "回路の筋"
    for ref in c["elements"]:
        comp = dr.comps[ref.split(".")[0]]
        switch = comp["kind"] == "limit_switch"
        if comp.get("purpose") and (not switch or c["kind"] == "to_receiver"):
            pu = comp["purpose"]
            meta.append(f"{comp['id']} の用途：{pu['value']}（{_sourced(pu)}）")
            if sub == "回路の筋":
                m = re.search(r"（(.+)）$", pu["value"])
                sub = m.group(1) if m else pu["value"]
    for nid in c["nets"]:
        net = next(n for n in dr.doc["nets"] if n["id"] == nid)
        if net.get("wire_no"):
            wn = net["wire_no"]
            meta.append(f"線番 {wn['value']}（{_sourced(wn)}）")
    return {
        "key": f"circuit:{c['id']}",
        "nets": c["nets"],
        "title": c["title"],
        "sub": sub,
        "steps": c.get("steps", []),
        "meta": list(dict.fromkeys(meta)),
        "legend": legend,
        "svg": "".join(parts),
        "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
    }


def _component_item(dr: _Drawing, c: dict) -> dict:
    boxes = [b for el in c.get("elements", []) if (b := _el_box(el))]
    ports = [p["id"] for p in dr.doc["ports"] if comp_of(p["id"]) == c["id"]]
    label_boxes = [tuple(c["label_bbox"])] if c.get("label_bbox") else []
    for p in ports:
        label_boxes += [tuple(b) for b in dr.ports[p].get("label_bboxes", [])]
    labels, _ = dr.labels_svg(label_boxes)
    marks = "".join(_circle(dr.ports[p]["pos"], 2.2, "mark") for p in ports if "pos" in dr.ports[p])
    bb = c.get("loc", {}).get("bbox")
    frame = (
        _rect(bb[0] - 3, bb[1] - 3, bb[2] - bb[0] + 6, bb[3] - bb[1] + 6, "frame", 2) if bb else ""
    )
    svg = (
        frame
        + dr.symbols_svg(boxes, [p for p in ports if dr.port_box(p)], "sym hl")
        + labels
        + marks
    )
    rows = [f"種類：{KIND_JA.get(c['kind'], c['kind'])}"]
    if c.get("name"):
        rows.append(f"名前：{c['name']}")
    if c.get("symbol"):
        rows.append(f"記号：{c['symbol']}")
    if c.get("region"):
        r = next((r for r in dr.doc.get("regions", []) if r["id"] == c["region"]), {})
        rows.append(f"設置場所：{r.get('label', c['region'])}（{r.get('meaning') or ''}）")
    for el in c.get("elements", []):
        line = (el.get("loc") or {}).get("line")
        where = f"（{line} 行目）" if line else ""
        rows.append(f"{_element_short(el)}：{' と '.join(el['ports'])}{where}")
    if c.get("terminals"):
        rows.append(f"端子：{', '.join(c['terminals'])}")
    if c.get("purpose"):
        pu = c["purpose"]
        rows.append(f"用途：{pu['value']}")
        rows.append(f"用途の出所：{BASIS_JA[pu['basis']]}（{'／'.join(pu.get('evidence', []))}）")
    xs = (
        [b[0] for b in boxes]
        + [b[2] for b in boxes]
        + [dr.ports[p]["pos"][0] for p in ports if "pos" in dr.ports[p]]
    )
    ys = (
        [b[1] for b in boxes]
        + [b[3] for b in boxes]
        + [dr.ports[p]["pos"][1] for p in ports if "pos" in dr.ports[p]]
    )
    return {
        "key": f"comp:{c['id']}",
        "title": c["id"] + (f"（{c['name']}）" if c.get("name") else ""),
        "sub": KIND_JA.get(c["kind"], c["kind"]),
        "steps": [],
        "meta": rows,
        "legend": [],
        "svg": svg,
        "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
    }


def _other_items(dr: _Drawing, doc: dict, set_doc: dict | None) -> list[dict]:
    items = []
    sh = doc["sheet"]
    rows = [f"頁名：{sh['title']}"]
    if sh.get("sheet_id"):
        s = sh["sheet_id"]
        rows.append(f"頁番号：{s['value']}（{_sourced(s)}）")
    lay = sh.get("layout", {})
    if lay:
        where = f"行 {lay.get('lines', '')}、列 {lay.get('columns', '')}"
        rows.append(
            f"書式：{lay.get('orientation', '')}・{lay.get('location_system', '')}（{where}）"
        )
        if lay.get("label_placement"):
            rows.append(f"名前の置き方：{lay['label_placement']}")
        if lay.get("junction_rule"):
            rows.append(f"接続の描き方：{lay['junction_rule']}")
    items.append({"key": "other:sheet", "title": "頁名・頁番号・書式", "sub": "頁", "meta": rows})
    rails = doc.get("rails", [])
    if rails:
        meta = []
        for r in rails:
            pb = r.get("polarity_basis") or {}
            meta.append(f"{r['name']}：{pb.get('value', r['polarity'])}（{_sourced(pb)}）")
        pts = [r["pos"] for r in rails if r.get("pos")]
        items.append(
            {
                "key": "other:rails",
                "title": "電源線と極性",
                "sub": "電源線",
                "meta": meta,
                "svg": "".join(_circle(pt, 4.0, "mark") for pt in pts),
                "bbox": _union([[*pt, *pt] for pt in pts]),
            }
        )
    for t in doc.get("tables", []):
        table = (
            "<table class='cells'>"
            + "".join(
                "<tr>" + "".join(f"<td>{html.escape(x)}</td>" for x in row) + "</tr>"
                for row in t["rows"]
            )
            + "</table>"
        )
        items.append(
            {
                "key": f"other:table:{t['id']}",
                "title": t.get("title") or "図中の表",
                "sub": "表",
                "meta": [t.get("note") or ""],
                "html": table,
                "bbox": t.get("bbox"),
            }
        )
    opens = [o for o in doc["open_ends"] if "pos" in dr.ports.get(o["port"], {})]
    if doc["open_ends"]:
        meta = [
            f"{o['port']}：{'／'.join([o['note'], *o.get('evidence', [])])}"
            for o in doc["open_ends"]
        ]
        pts = [dr.ports[o["port"]]["pos"] for o in opens]
        items.append(
            {
                "key": "other:open_ends",
                "title": f"先が描かれていない端（{len(doc['open_ends'])} か所）",
                "sub": "先が描かれていない端",
                "meta": meta,
                "svg": "".join(dr.open_svg(o["port"]) for o in opens),
                "bbox": _union([[*pt, *pt] for pt in pts]),
            }
        )
    for x in doc.get("cross_references", []):
        tg = x.get("target") or {}
        items.append(
            {
                "key": f"other:xref:{x['text']}",
                "title": f"他頁参照「{x['text']}」",
                "sub": "参照",
                "meta": [
                    f"{x.get('component') or ''} の接点の位置：頁番号 {tg.get('sheet')} の "
                    f"{tg.get('line')} 行目（PDF の p.{tg.get('page')}）"
                ],
                "bbox": x.get("loc", {}).get("bbox"),
            }
        )
    if set_doc:
        meta = [
            f"{cv['rule']}（{BASIS_JA[cv['basis']]}：{'／'.join(cv.get('evidence', []))}）"
            for cv in set_doc.get("conventions", [])
        ]
        meta += [
            f"機器記号 {dc['code']}＝{dc['meaning']}（{'／'.join(dc.get('evidence', []))}）"
            for dc in set_doc.get("device_codes", [])
        ]
        items.append(
            {"key": "other:set", "title": "図面集全体の決まり", "sub": "set.json", "meta": meta}
        )
    for it in items:
        it.setdefault("steps", [])
        it.setdefault("legend", [])
        it.setdefault("bbox", None)
        b = it["bbox"]
        frame = _rect(b[0] - 4, b[1] - 4, b[2] - b[0] + 8, b[3] - b[1] + 8, "frame", 2) if b else ""
        it.setdefault("svg", frame)
    return items


def build_view(
    sample: Sample,
    page: int,
    doc: dict,
    set_doc: dict | None = None,
    *,
    label: str = "gt",
    dpi: int = 300,
) -> Path:
    """Write samples/derived/<id>/pNNN.<label>_view.html next to the rendered image."""
    out_dir = sample.derived_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    image = out_dir / f"{page_stem(page)}_{dpi}dpi.png"
    if not image.exists():
        render_page(sample.pdf, page, dpi).save(image)
    vec_path = out_dir / f"{page_stem(page)}.vector.json"
    vector = json.loads(vec_path.read_text(encoding="utf-8")) if vec_path.exists() else None
    width, height = page_size_pt(sample.pdf, page)
    dr = _Drawing(doc, vector)
    data = {
        "circuits": [_circuit_item(dr, c) for c in doc["circuits"]],
        "comps": [_component_item(dr, c) for c in doc["components"]],
        "others": _other_items(dr, doc, set_doc),
    }
    context = "".join(dr.net_svg(ws, "#9aa3b2", nid) for nid, ws in dr.wires_of_net.items())
    content = _union(
        [[*pt, *pt] for w in doc["wires"] for pt in w.get("path", [])]
        + [r.get("bbox") or r.get("label_bbox") for r in doc.get("regions", [])]
        + [r.get("label_bbox") for r in doc.get("regions", [])]
        + [t.get("bbox") for t in doc.get("tables", [])]
        + [x.get("loc", {}).get("bbox") for x in doc.get("cross_references", [])]
    ) or [0, 0, width, height]
    m = 18
    x0, y0 = max(0.0, content[0] - m), max(0.0, content[1] - m)
    x1, y1 = min(width, content[2] + m), min(height, content[3] + m)
    viewbox = f"{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}"
    pdf_rel = Path(os.path.relpath(sample.pdf, out_dir)).as_posix()
    html_text = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__TITLE__", f"{sample.id} p.{page}「{doc['sheet']['title']}」の確認")
        .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
        .replace("__CONTEXT__", context)
        .replace("__VIEWBOX__", viewbox)
        .replace("__PAGE_W__", f"{width:.2f}")
        .replace("__PAGE_H__", f"{height:.2f}")
        .replace("__IMAGE__", image.name)
        .replace("__STORAGE_KEY__", f"kairo-{label}-{sample.id}-{page_stem(page)}-v02")
        .replace("__SAMPLE__", sample.id)
        .replace("__PAGE_NO__", str(page))
        .replace("__SHEET_TITLE__", html.escape(doc["sheet"]["title"]))
        .replace("__PDF__", pdf_rel)
    )
    out = out_dir / f"{page_stem(page)}.{label}_view.html"
    out.write_text(html_text, encoding="utf-8")
    return out

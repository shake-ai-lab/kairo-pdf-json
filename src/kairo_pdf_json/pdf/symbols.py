"""Symbol candidates from vector data: places where something other than a wire is drawn.

The tracer (pdf.trace) keeps straight horizontal/vertical lines as wires. Everything else that is
drawn near the wiring (diagonal strokes, small closed shapes, short stubs hanging off a wire) is
grouped by proximity; each group is one candidate. The program does not decide what a candidate
means. It only says "something is drawn here", gives the points of the traced graph that touch
it, and a high-resolution crop, so the AI (or a person) can classify it (SPEC §7.3).
"""

import math
from pathlib import Path

import pypdfium2 as pdfium

from kairo_pdf_json.pdf.trace import TracedPage, bbox_of

Point = tuple[float, float]


class _DSU:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


def _seg_dist(a: Point, b: Point, c: Point, d: Point) -> float:
    """Distance between segments a-b and c-d (approximate: end points to the other segment)."""

    def pt_seg(p: Point, s: Point, t: Point) -> float:
        dx, dy = t[0] - s[0], t[1] - s[1]
        length2 = dx * dx + dy * dy
        u = (
            0.0
            if length2 == 0
            else max(0, min(1, ((p[0] - s[0]) * dx + (p[1] - s[1]) * dy) / length2))
        )
        return math.dist(p, (s[0] + u * dx, s[1] + u * dy))

    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def candidates(vpage: dict, tp: TracedPage, graph: dict, gap: float = 1.2) -> list[dict]:
    """Group non-wire drawing into candidates with their bbox and the graph points they touch."""
    # pieces of drawing that are not plain wires
    pieces: list[tuple[Point, Point]] = []
    known = {i for d in tp.dots for i in d.paths} | {c.path for c in tp.circles}
    known |= {i for pin in tp.pins for i in pin.paths}
    for i, p in enumerate(vpage["paths"]):
        if i in known:
            continue
        pts = [(float(q[0]), float(q[1])) for q in p["pts"]]
        for a, b in zip(pts, pts[1:], strict=False):
            horizontal_or_vertical = abs(a[0] - b[0]) < 0.05 or abs(a[1] - b[1]) < 0.05
            if not horizontal_or_vertical or math.dist(a, b) < 6.0:
                pieces.append((a, b))
    # short traced edges: parts of symbols drawn with straight lines (stops, boxes)
    for e in tp.edges:
        if math.dist(e.a, e.b) < 6.0:
            pieces.append((e.a, e.b))
    # small closed shapes made of straight lines that touch no wire (coil, resistor, input box)
    seen: set[int] = set()
    for start in tp.nodes:
        if start.id in seen or not start.edges:
            continue
        comp, stack = set(), [start.id]
        while stack:
            n = stack.pop()
            if n in comp:
                continue
            comp.add(n)
            for e in tp.nodes[n].edges:
                stack += [tp.edges[e].na, tp.edges[e].nb]
        seen |= comp
        nodes = [tp.nodes[n] for n in comp]
        closed = all(len(n.edges) == 2 for n in nodes)
        box = bbox_of([n.pos for n in nodes])
        if closed and max(box[2] - box[0], box[3] - box[1]) <= 25:
            edges = {e for n in nodes for e in n.edges}
            pieces += [(tp.edges[e].a, tp.edges[e].b) for e in edges]
    dsu = _DSU(len(pieces))
    boxes = [bbox_of([a, b]) for a, b in pieces]
    order = sorted(range(len(pieces)), key=lambda k: boxes[k][0])
    for n, i in enumerate(order):
        for j in order[n + 1 :]:
            if boxes[j][0] > boxes[i][2] + gap:
                break
            if boxes[j][1] > boxes[i][3] + gap or boxes[i][1] > boxes[j][3] + gap:
                continue
            if _seg_dist(*pieces[i], *pieces[j]) <= gap:
                dsu.union(i, j)
    groups: dict[int, list[int]] = {}
    for k in range(len(pieces)):
        groups.setdefault(dsu.find(k), []).append(k)
    out = []
    for members in groups.values():
        pts = [p for k in members for p in pieces[k]]
        box = bbox_of(pts)
        w, h = box[2] - box[0], box[3] - box[1]
        if max(w, h) < 1.0 or max(w, h) > 40:  # specks and frames
            continue
        touch = [
            p["id"]
            for p in graph["points"]
            if box[0] - 1.0 <= p["x"] <= box[2] + 1.0 and box[1] - 1.0 <= p["y"] <= box[3] + 1.0
        ]
        out.append({"bbox": [round(x, 2) for x in box], "pieces": len(members), "points": touch})
    out.sort(key=lambda c: (round(c["bbox"][1] / 4), c["bbox"][0]))
    for k, c in enumerate(out, 1):
        c["id"] = f"S{k}"
    return [{"id": c["id"], **{k: v for k, v in c.items() if k != "id"}} for c in out]


def render_crops(pdf: Path, page: int, cands: list[dict], out_dir: Path, dpi: int = 1200) -> None:
    """Save a high-resolution crop of each candidate (with a margin) as <id>.png."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf))
    try:
        pg = doc[page - 1]
        width, height = pg.get_size()
        for c in cands:
            x0, y0, x1, y1 = c["bbox"]
            m = 6.0
            crop = (
                max(0, x0 - m),
                max(0, height - (y1 + m)),
                max(0, width - (x1 + m)),
                max(0, y0 - m),
            )
            img = pg.render(scale=dpi / 72, crop=crop).to_pil()
            img.save(out_dir / f"{c['id']}.png")
            c["image"] = f"symbols/{c['id']}.png"
            box = (max(0, x0 - m), max(0, y0 - m), min(width, x1 + m), min(height, y1 + m))
            c["image_box"] = [round(v, 2) for v in box]
    finally:
        doc.close()

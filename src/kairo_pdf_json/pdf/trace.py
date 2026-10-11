"""Trace wires on a vector page into a graph of nodes and straight edges.

The rules follow how the drawing is drawn (SPEC §7.2, found on Mazak p.76); they belong to the
page format and may need to change for other drawings:

- wires are straight horizontal or vertical segments; diagonal segments are parts of symbols
- a T or a crossing connects only where a junction dot is drawn
- a terminal circle and a connector pin (">>": one curve chevron plus one two-line chevron)
  pass the wire through; each becomes a single node
- a wire drawn straight through a diode-like symbol (triangle with a bar at its apex) is cut at
  the symbol

Input is the dict written by `kairo extract` (`pNNN.vector.json`). Coordinates are pt, top-left.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import pairwise

Point = tuple[float, float]
Box = tuple[float, float, float, float]

TOL = 0.35


def bbox_of(pts: list[Point]) -> Box:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _axis(a: Point, b: Point) -> str | None:
    if abs(a[1] - b[1]) < 0.05:
        return "h"
    if abs(a[0] - b[0]) < 0.05:
        return "v"
    return None


def _on_segment(p: Point, a: Point, b: Point, tol: float = TOL, interior: bool = False) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.dist(p, a) <= tol
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    lo, hi = (0.02, 0.98) if interior else (-0.01, 1.01)
    if t < lo or t > hi:
        return False
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)) <= tol


def _clip(a: Point, b: Point, box: Box) -> tuple[float, float] | None:
    """Liang-Barsky: the part of segment a-b inside box, as parameters (t0, t1)."""
    x0, y0, x1, y1 = box
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
    return (t0, t1) if t0 < t1 else None


class _DSU:
    def __init__(self) -> None:
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


@dataclass
class Dot:
    center: Point
    r: float
    paths: list[int]


@dataclass
class Circle:
    center: Point
    r: float
    path: int


@dataclass
class Pin:
    """A connector pin drawn as ">>" or "<<". `tip` touches the inner wire, `outer` the outer."""

    tip: Point
    outer: Point
    center: Point
    paths: list[int]


@dataclass
class Edge:
    a: Point
    b: Point
    path: int
    na: int = -1  # node ids, filled by trace()
    nb: int = -1


@dataclass
class Node:
    id: int
    pos: Point
    dot: int | None = None
    circle: int | None = None
    pin: int | None = None
    edges: list[int] = field(default_factory=list)


@dataclass
class TracedPage:
    dots: list[Dot]
    circles: list[Circle]
    pins: list[Pin]
    cut_boxes: list[Box]  # diode-like symbols that cut the wire through them
    edges: list[Edge]
    nodes: list[Node]
    symbol_points: list[Point] = field(default_factory=list)  # ends of symbol lines

    def nodes_in(self, box: Box, margin: float = 0.6) -> list[Node]:
        x0, y0, x1, y1 = box
        return [
            n
            for n in self.nodes
            if x0 - margin <= n.pos[0] <= x1 + margin and y0 - margin <= n.pos[1] <= y1 + margin
        ]

    def nearest_node(self, pt: Point) -> Node:
        return min(self.nodes, key=lambda n: math.dist(n.pos, pt))


def _classify(paths: list[dict]):
    dots: list[Dot] = []
    circles: list[Circle] = []
    curve_chevrons: list[dict] = []
    segs: list[tuple[Point, Point, int]] = []
    for i, p in enumerate(paths):
        pts = [(float(q[0]), float(q[1])) for q in p["pts"]]
        x0, y0, x1, y1 = bbox_of(pts)
        w, h = x1 - x0, y1 - y0
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        if p["kind"] == "curve" and max(w, h) <= 3.2 and abs(w - h) < 0.7:
            for d in dots:
                if math.dist(d.center, c) < 1.2:
                    d.paths.append(i)
                    d.r = max(d.r, max(w, h) / 2)
                    break
            else:
                dots.append(Dot(c, max(w, h) / 2, [i]))
        elif p["kind"] == "curve" and 3.5 <= w <= 4.2 and 3.5 <= h <= 4.2:
            circles.append(Circle(c, max(w, h) / 2, i))
        elif p["kind"] == "curve" and len(pts) <= 4 and 3.5 <= w <= 4.2 and 7.3 <= h <= 8.0:
            mx = sum(q[0] for q in pts) / len(pts)
            tip = max(pts, key=lambda q: abs(q[0] - mx))
            arm = min(pts, key=lambda q: abs(q[0] - mx))
            curve_chevrons.append(
                {"path": i, "tip": tip, "side": 1 if arm[0] > tip[0] else -1, "c": c}
            )
        else:
            for a, b in pairwise(pts):
                if math.dist(a, b) > 0.05:
                    segs.append((a, b, i))
    return dots, circles, curve_chevrons, segs


def _diode_boxes(paths: list[dict], segs: list[tuple[Point, Point, int]]) -> list[Box]:
    """Triangles (a closed curve or three short lines) with a bar through the apex."""
    tris: list[list[Point]] = []
    for p in paths:
        pts = [(float(q[0]), float(q[1])) for q in p["pts"]]
        if p["kind"] == "curve" and len(pts) == 4 and math.dist(pts[0], pts[-1]) < 0.1:
            tris.append(pts[:3])
    short = [s for s in segs if math.dist(s[0], s[1]) < 12]
    for i, s1 in enumerate(short):
        for s2 in short[i + 1 :]:
            shared = [p for p in s1[:2] for q in s2[:2] if math.dist(p, q) < TOL]
            if len(shared) != 1:
                continue
            o1 = s1[1] if math.dist(s1[0], shared[0]) < TOL else s1[0]
            o2 = s2[1] if math.dist(s2[0], shared[0]) < TOL else s2[0]
            for s3 in short:
                if s3 is s1 or s3 is s2:
                    continue
                a, b = s3[:2]
                if (math.dist(a, o1) < TOL and math.dist(b, o2) < TOL) or (
                    math.dist(a, o2) < TOL and math.dist(b, o1) < TOL
                ):
                    tris.append([shared[0], o1, o2])
    boxes: list[Box] = []
    for tri in tris:
        for k in range(3):
            apex = tri[k]
            base = (tri[(k + 1) % 3], tri[(k + 2) % 3])
            ax = _axis(*base)
            if ax is None:
                continue
            base_len = math.dist(*base)
            for a, b, _ in segs:
                if _axis(a, b) != ax or not _on_segment(apex, a, b, interior=True):
                    continue
                if 0.6 * base_len <= math.dist(a, b) <= 1.6 * base_len:
                    box = bbox_of(tri + [a, b])
                    if all(math.dist(box[:2], o[:2]) > 0.5 for o in boxes):
                        boxes.append(box)
    return boxes


def trace(vpage: dict) -> TracedPage:
    paths = vpage["paths"]
    dots, circles, curve_chevrons, segs = _classify(paths)
    cut_boxes = _diode_boxes(paths, segs)

    # cut wires at diode-like symbols; keep only axis-aligned pieces as wires
    wires: list[tuple[Point, Point, int]] = []
    symbol_segs: list[tuple[Point, Point, int]] = []
    for a, b, i in segs:
        pieces = [(a, b)]
        swallowed = False
        for box in cut_boxes:
            nxt = []
            for pa, pb in pieces:
                t = _clip(pa, pb, box)
                if t is None:
                    nxt.append((pa, pb))
                    continue
                t0, t1 = t
                qa = (pa[0] + (pb[0] - pa[0]) * t0, pa[1] + (pb[1] - pa[1]) * t0)
                qb = (pa[0] + (pb[0] - pa[0]) * t1, pa[1] + (pb[1] - pa[1]) * t1)
                if t0 > 1e-6:
                    nxt.append((pa, qa))
                if t1 < 1 - 1e-6:
                    nxt.append((qb, pb))
                if t0 <= 1e-6 and t1 >= 1 - 1e-6:
                    swallowed = True
            pieces = nxt
        if swallowed and not pieces:
            symbol_segs.append((a, b, i))
            continue
        for pa, pb in pieces:
            if math.dist(pa, pb) >= 0.05:
                (wires if _axis(pa, pb) else symbol_segs).append((pa, pb, i))

    # connector pins: the curve chevron plus the two-line chevron on its arm side
    pins: list[Pin] = []
    for ch in curve_chevrons:
        tx, ty = ch["tip"]
        outer = None
        for a, b, _ in symbol_segs:
            for p in (a, b):
                if abs(p[1] - ty) < 0.3 and 3.5 <= (p[0] - tx) * ch["side"] <= 7.5:
                    outer = p
        if outer is None:
            continue
        arms = [
            i for a, b, i in symbol_segs if math.dist(a, outer) < TOL or math.dist(b, outer) < TOL
        ]
        pins.append(Pin(ch["tip"], outer, ch["c"], [ch["path"], *arms]))

    # split wires where a junction dot sits on them
    edges: list[Edge] = []
    for a, b, i in wires:
        cuts = [a, b] + [
            d.center for d in dots if _on_segment(d.center, a, b, tol=max(d.r, 0.5), interior=True)
        ]
        cuts.sort(key=lambda p: math.dist(a, p))
        for p, q in pairwise(cuts):
            if math.dist(p, q) > 0.05:
                edges.append(Edge(p, q, i))

    # nodes: shared end points, dots, circles and pins
    dsu = _DSU()
    ends = [(e, end) for e in range(len(edges)) for end in ("a", "b")]

    def pt(e: int, end: str) -> Point:
        return getattr(edges[e], end)

    grid: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    for e, end in ends:
        p = pt(e, end)
        grid[(round(p[0]), round(p[1]))].append((e, end))
    for e, end in ends:
        dsu.find(("end", e, end))
        p = pt(e, end)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for e2, end2 in grid.get((round(p[0]) + dx, round(p[1]) + dy), []):
                    if (e2, end2) != (e, end) and math.dist(p, pt(e2, end2)) <= TOL:
                        dsu.union(("end", e, end), ("end", e2, end2))
    for j, d in enumerate(dots):
        dsu.find(("dot", j))
        for e, end in ends:
            if math.dist(pt(e, end), d.center) <= d.r + 0.6:
                dsu.union(("dot", j), ("end", e, end))
    for t, c in enumerate(circles):
        dsu.find(("circle", t))
        for e, end in ends:
            if abs(math.dist(pt(e, end), c.center) - c.r) <= 0.5:
                dsu.union(("circle", t), ("end", e, end))
    for n, pin in enumerate(pins):
        dsu.find(("pin", n))
        for e, end in ends:
            p = pt(e, end)
            if math.dist(p, pin.tip) <= TOL or math.dist(p, pin.outer) <= TOL:
                dsu.union(("pin", n), ("end", e, end))

    node_ids: dict = {}
    nodes: list[Node] = []
    members: dict = defaultdict(list)
    for key in list(dsu.parent):
        members[dsu.find(key)].append(key)
    for root, keys in members.items():
        node = Node(len(nodes), (0.0, 0.0))
        pts = []
        for k in keys:
            if k[0] == "dot":
                node.dot = k[1]
            elif k[0] == "circle":
                node.circle = k[1]
            elif k[0] == "pin":
                node.pin = k[1]
            else:
                pts.append(pt(k[1], k[2]))
        if node.dot is not None:
            node.pos = dots[node.dot].center
        elif node.circle is not None:
            node.pos = circles[node.circle].center
        elif node.pin is not None:
            node.pos = pins[node.pin].center
        elif pts:
            node.pos = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        node_ids[root] = node.id
        nodes.append(node)
    for e, edge in enumerate(edges):
        edge.na = node_ids[dsu.find(("end", e, "a"))]
        edge.nb = node_ids[dsu.find(("end", e, "b"))]
        nodes[edge.na].edges.append(e)
        if edge.nb != edge.na:
            nodes[edge.nb].edges.append(e)
    sym_pts = [p for a, b, _ in symbol_segs for p in (a, b)]
    return TracedPage(dots, circles, pins, cut_boxes, edges, nodes, sym_pts)


def key_graph(tp: TracedPage) -> dict:
    """Points worth naming and the wire runs between them (handed to the AI, SPEC §7.4).

    Key points are junction dots, terminal circles, connector pins, wire ends, unmarked
    branches, bends, and points where a symbol line starts (a contact's terminal can sit in
    the middle of a straight line). A run goes from one key point to the next. Closed loops
    without key points (frames, boxes) are left out.
    """
    grid: dict[tuple[int, int], list[Point]] = defaultdict(list)
    for p in tp.symbol_points:
        grid[(round(p[0]), round(p[1]))].append(p)

    def touches_symbol(pos: Point) -> bool:
        gx, gy = round(pos[0]), round(pos[1])
        return any(
            math.dist(pos, q) <= TOL
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for q in grid.get((gx + dx, gy + dy), [])
        )

    def bends(n: Node) -> bool:
        a, b = (tp.edges[e] for e in n.edges)
        return _axis(a.a, a.b) != _axis(b.a, b.b)

    def kind(n: Node) -> str | None:
        if not n.edges:
            return None
        if n.dot is not None:
            return "junction_dot"
        if n.circle is not None:
            return "terminal_circle"
        if n.pin is not None:
            return "connector_pin"
        if len(n.edges) == 1:
            return "end"
        if len(n.edges) > 2:
            return "branch"
        if bends(n):
            return "bend"
        if touches_symbol(n.pos):
            return "symbol_touch"
        return None

    keys = sorted((n for n in tp.nodes if kind(n)), key=lambda n: (round(n.pos[1], 1), n.pos[0]))
    name = {n.id: f"P{k}" for k, n in enumerate(keys, 1)}
    points = [
        {"id": name[n.id], "kind": kind(n), "x": round(n.pos[0], 2), "y": round(n.pos[1], 2)}
        for n in keys
    ]
    used: set[int] = set()
    runs = []
    for n in keys:
        for e0 in n.edges:
            if e0 in used:
                continue
            path, cur, e = [n.pos], n.id, e0
            while True:
                used.add(e)
                edge = tp.edges[e]
                nxt = edge.nb if edge.na == cur else edge.na
                path.append(tp.nodes[nxt].pos)
                if nxt in name:
                    break
                rest = [x for x in tp.nodes[nxt].edges if x != e]
                cur, e = nxt, rest[0]
            pts = [path[0]]
            for a, b in pairwise(path[1:]):
                p = pts[-1]
                straight = (abs(p[0] - a[0]) < 0.05 and abs(a[0] - b[0]) < 0.05) or (
                    abs(p[1] - a[1]) < 0.05 and abs(a[1] - b[1]) < 0.05
                )
                if not straight:
                    pts.append(a)
            pts.append(path[-1])
            runs.append(
                {
                    "id": f"R{len(runs) + 1}",
                    "a": name[n.id],
                    "b": name[nxt],
                    "path": [[round(x, 2), round(y, 2)] for x, y in pts],
                }
            )
    return {"points": points, "runs": runs}

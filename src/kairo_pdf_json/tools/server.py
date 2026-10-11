"""MCP server: functions for reading one drawing page, given to the AI as tools (SPEC §7.3).

Started by `kairo run --tools` for one run. It reads only the run's work folder (graph.json,
symbols.json, pages.txt), the page's vector data and the sample PDF, which the run passes in
environment variables. Every function returns measured facts; none decides what a symbol means.
Coordinates are pt with the origin at the page's top-left.
"""

import io
import json
import math
import os
import re
import subprocess
import time
import uuid
from collections import Counter, defaultdict, deque
from functools import cache
from pathlib import Path

import pypdfium2 as pdfium
from mcp.server.mcpserver import Image, MCPServer

from kairo_pdf_json.convert.assemble import assemble
from kairo_pdf_json.convert.check_labels import check_labels

WORK = Path(os.environ.get("KAIRO_WORK", "."))
PDF = Path(os.environ.get("KAIRO_PDF", ""))
PAGE = int(os.environ.get("KAIRO_PAGE", "1"))
VECTOR = Path(os.environ.get("KAIRO_VECTOR", ""))
MAX_PX = 2000

server = MCPServer(
    "pdf",
    instructions="電気図面の1頁を読むための道具。座標は頁の左上が原点、単位は pt。"
    "どの道具も測った事実だけを返し、記号の意味は決めない。",
)


@cache
def _vector() -> dict:
    return json.loads(VECTOR.read_text(encoding="utf-8"))


@cache
def _graph() -> dict:
    return json.loads((WORK / "graph.json").read_text(encoding="utf-8"))


@cache
def _words() -> list[dict]:
    return [
        {"id": f"W{i}", "text": w["text"], "bbox": [round(x, 2) for x in w["bbox"]],
         "font": w["font"].split("+")[-1], "size": round(w["size"], 1)}
        for i, w in enumerate(_vector()["words"], 1)
    ]  # fmt: skip


@cache
def _symbols() -> list[dict]:
    path = WORK / "symbols.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _json(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _render(
    page: int, box: tuple[float, float, float, float] | None, dpi: int
) -> tuple[bytes, int]:
    doc = pdfium.PdfDocument(str(PDF))
    try:
        if not 1 <= page <= len(doc):
            raise ValueError(f"頁は 1〜{len(doc)}")
        pg = doc[page - 1]
        width, height = pg.get_size()
        x0, y0, x1, y1 = box or (0, 0, width, height)
        x0, y0 = max(0.0, x0), max(0.0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("範囲が空です")
        dpi = int(min(dpi, MAX_PX * 72 / max(x1 - x0, y1 - y0)))
        crop = (x0, height - y1, width - x1, y0)
        img = pg.render(scale=dpi / 72, crop=crop).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), dpi
    finally:
        doc.close()


_crop_count = 0


@server.tool()
def crop(x0: float, y0: float, x1: float, y1: float, dpi: int = 600) -> list:
    """この頁の好きな範囲を拡大した画像を返す（pt。画像の長辺は2000ピクセルまで）。"""
    global _crop_count
    data, used = _render(PAGE, (x0, y0, x1, y1), dpi)
    _crop_count += 1
    (WORK / "crops").mkdir(exist_ok=True)
    name = f"crops/crop_{_crop_count}.png"
    (WORK / name).write_bytes(data)
    return [
        f"範囲 [{x0}, {y0}, {x1}, {y1}] を {used}dpi で（同じ画像を {name} に保存）",
        Image(data=data, format="png"),
    ]


@server.tool()
def page_image(
    page: int, x0: float = 0, y0: float = 0, x1: float = 0, y1: float = 0, dpi: int = 100
) -> list:
    """図面集の別の頁の画像を返す。範囲を省くと頁全体（部品配置図などを見るのに使う）。"""
    box = (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None
    data, used = _render(page, box, dpi)
    return [
        f"PDF {page} 頁" + (f"の範囲 {list(box)}" if box else "の全体") + f"（{used}dpi）",
        Image(data=data, format="png"),
    ]


@server.tool()
def find_text(pattern: str, regex: bool = False) -> str:
    """この頁の文字を探す。位置・フォント・大きさつきで返す（最大100件）。"""
    rx = re.compile(pattern) if regex else None
    hits = [w for w in _words() if (rx.search(w["text"]) if rx else pattern in w["text"])]
    return _json(hits[:100])


@server.tool()
def words_in(x0: float, y0: float, x1: float, y1: float) -> str:
    """範囲の中にある文字（中心が範囲に入るもの）を返す。"""
    out = [
        w for w in _words()
        if x0 <= _cx(w) <= x1 and y0 <= _cy(w) <= y1
    ]  # fmt: skip
    return _json(out[:200])


def _segments() -> list[tuple[tuple[float, float], tuple[float, float], float, str]]:
    segs = []
    for p in _vector()["paths"]:
        pts = [(float(q[0]), float(q[1])) for q in p["pts"]]
        for a, b in zip(pts, pts[1:], strict=False):
            segs.append((a, b, float(p["width"]), p["kind"]))
    return segs


def _cx(w: dict) -> float:
    return (w["bbox"][0] + w["bbox"][2]) / 2


def _cy(w: dict) -> float:
    return (w["bbox"][1] + w["bbox"][3]) / 2


def _seg(a, b) -> dict:
    return {
        "from": [round(a[0], 2), round(a[1], 2)],
        "to": [round(b[0], 2), round(b[1], 2)],
        "orientation": _orient(a, b),
        "length": round(math.dist(a, b), 2),
    }


def _orient(a, b) -> str:
    if abs(a[1] - b[1]) < 0.05:
        return "横"
    if abs(a[0] - b[0]) < 0.05:
        return "縦"
    return f"斜め {round(math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0])) % 180)}度"


@server.tool()
def lines_in(x0: float, y0: float, x1: float, y1: float) -> str:
    """範囲に入る線（両端のどちらかが範囲内）を、向き・長さ・太さつきで返す（最大200本）。"""
    out = []
    for a, b, w, kind in _segments():
        if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in (a, b)):
            out.append({**_seg(a, b), "width": w, "from_curve": kind == "curve"})
    return _json(out[:200])


@server.tool()
def line_stats() -> str:
    """頁の線の太さの分布（太さごとの本数・合計の長さ・縦横の割合）を返す。"""
    acc: dict[float, dict] = defaultdict(lambda: {"count": 0, "length": 0.0, "straight": 0})
    for a, b, w, _ in _segments():
        s = acc[round(w, 2)]
        s["count"] += 1
        s["length"] += math.dist(a, b)
        s["straight"] += _orient(a, b) in ("横", "縦")
    rows = [
        {"width": w, "count": s["count"], "total_length": round(s["length"], 1),
         "share_horizontal_or_vertical": round(s["straight"] / s["count"], 2)}
        for w, s in sorted(acc.items(), key=lambda kv: -kv[1]["length"])
    ]  # fmt: skip
    fonts = Counter((w["font"], w["size"]) for w in _words())
    return _json(
        {
            "lines": rows,
            "fonts": [{"font": f, "size": s, "count": n} for (f, s), n in fonts.most_common(10)],
        }
    )


def _labels_near(p: dict) -> list[str]:
    x, y = p["x"], p["y"]
    near = [
        w
        for w in _words()
        if abs((w["bbox"][0] + w["bbox"][2]) / 2 - x) < 14
        and -18 < (w["bbox"][1] + w["bbox"][3]) / 2 - y < 2
    ]
    return [w["text"] for w in near][:4]


@server.tool()
def trace_from(point: str) -> str:
    """graph.json の点から線をたどり、届く点（黒丸・端子の○・コネクタ・線の端など）を返す。
    記号（接点など）の所では線が切れているので、そこで止まる。端子とコネクタには近くの文字を添える。"""
    g = _graph()
    pts = {p["id"]: p for p in g["points"]}
    if point not in pts:
        return _json({"error": f"点 {point} はありません"})
    adj: dict[str, list[str]] = defaultdict(list)
    for r in g["runs"]:
        adj[r["a"]].append(r["b"])
        adj[r["b"]].append(r["a"])
    seen, q = {point: 0}, deque([point])
    while q:
        cur = q.popleft()
        for nb in adj[cur]:
            if nb not in seen:
                seen[nb] = seen[cur] + 1
                q.append(nb)
    out = []
    for pid, steps in sorted(seen.items(), key=lambda kv: kv[1]):
        p = pts[pid]
        if p["kind"] in ("bend",):
            continue
        item = {"id": pid, "kind": p["kind"], "x": p["x"], "y": p["y"], "runs_away": steps}
        if p["kind"] in ("terminal_circle", "connector_pin"):
            item["labels_near"] = _labels_near(p)
        out.append(item)
    return _json({"from": point, "reached": out[:200], "count": len(out)})


@server.tool()
def symbol_features(symbol: str) -> str:
    """symbols.json の候補（S…）について、描かれている線を測った値を返す：
    線ごとの向き・長さ、斜めの線が縦線と交わるか（越えているか）、閉じた三角・四角の数、
    範囲のどの辺で配線の点に触れているか。"""
    cand = next((c for c in _symbols() if c["id"] == symbol), None)
    if cand is None:
        return _json({"error": f"候補 {symbol} はありません（symbols.json を確かめる）"})
    x0, y0, x1, y1 = cand["bbox"]
    m = 0.6
    segs = [
        s
        for s in _segments()
        if all(x0 - m <= p[0] <= x1 + m and y0 - m <= p[1] <= y1 + m for p in s[:2])
    ]
    lines = [_seg(a, b) for a, b, _, _ in segs]
    diag = [(a, b) for a, b, _, _ in segs if _orient(a, b).startswith("斜め")]
    vert = [(a, b) for a, b, _, _ in segs if _orient(a, b) == "縦"]
    crossings = []
    for a, b in diag:
        for c, d in vert:
            vx = c[0]
            if min(a[0], b[0]) < vx < max(a[0], b[0]):
                t = (vx - a[0]) / (b[0] - a[0])
                y = a[1] + t * (b[1] - a[1])
                if min(c[1], d[1]) - 0.2 <= y <= max(c[1], d[1]) + 0.2:
                    beyond = round(max(a[0], b[0]) - vx, 2)
                    crossings.append(
                        {"at": [round(vx, 2), round(y, 2)], "diagonal_goes_past_by": beyond}
                    )
    ends = Counter()
    for a, b, _, _ in segs:
        for p in (a, b):
            ends[(round(p[0], 1), round(p[1], 1))] += 1
    pts = {p["id"]: p for p in _graph()["points"]}
    touch = []
    for pid in cand.get("points", []):
        p = pts.get(pid)
        if not p:
            continue
        side = min(
            (
                ("左", abs(p["x"] - x0)),
                ("右", abs(p["x"] - x1)),
                ("上", abs(p["y"] - y0)),
                ("下", abs(p["y"] - y1)),
            ),
            key=lambda s: s[1],
        )[0]
        touch.append({"id": pid, "kind": p["kind"], "x": p["x"], "y": p["y"], "side": side})
    triangles = sum(1 for s in _closed_shapes(segs) if s == 3)
    rects = sum(1 for s in _closed_shapes(segs) if s == 4)
    return _json({
        "symbol": symbol, "bbox": cand["bbox"], "size": [round(x1 - x0, 2), round(y1 - y0, 2)],
        "lines": lines, "diagonal_count": len(diag), "diagonal_crosses_vertical": crossings,
        "closed_triangles": triangles, "closed_rectangles": rects, "touching_points": touch,
    })  # fmt: skip


def _closed_shapes(segs) -> list[int]:
    """Corners of each small closed shape among the segments. Lines are split where another line
    ends on them (T-shaped corners), corners are counted where the direction changes."""

    def key(p):
        return (round(p[0] / 0.2) * 0.2, round(p[1] / 0.2) * 0.2)

    ends = [p for a, b, _, _ in segs for p in (a, b)]
    adj: dict[tuple, set] = defaultdict(set)
    for a, b, _, _ in segs:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        if length2 == 0:
            continue
        cuts = [a, b]
        for p in ends:
            t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
            if 0.02 < t < 0.98 and math.dist(p, (a[0] + t * dx, a[1] + t * dy)) < 0.25:
                cuts.append(p)
        cuts.sort(key=lambda q: math.dist(a, q))
        for u, v in zip(cuts, cuts[1:], strict=False):
            if key(u) != key(v):
                adj[key(u)].add(key(v))
                adj[key(v)].add(key(u))
    cycles: set[tuple] = set()
    for u in adj:
        for v in adj[u]:  # shortest way back from v to u without the edge u-v closes a cycle
            prev, q = {v: None}, deque([v])
            while q and u not in prev:
                cur = q.popleft()
                for nb in adj[cur]:
                    if nb not in prev and not (cur == v and nb == u):
                        prev[nb] = cur
                        q.append(nb)
            if u in prev:
                path, cur = [], u
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                if 3 <= len(path) <= 12:
                    cycles.add(tuple(sorted(path)))
    sizes = []
    for cyc in cycles:
        pts = list(cyc)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        ring = sorted(pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        corners = 0
        for i, p in enumerate(ring):
            a, b = ring[i - 1], ring[(i + 1) % len(ring)]
            cross = (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])
            if abs(cross) > 0.05:
                corners += 1
        sizes.append(corners)
    return sizes


@server.tool()
def where(x: float, y: float) -> str:
    """座標が図面の何行目・何列か（左端の行番号と上端の列記号から、いちばん近いもの）を返す。"""
    rows = [w for w in _words() if re.fullmatch(r"\d{2}", w["text"]) and w["bbox"][0] < 80]
    cols = [w for w in _words() if re.fullmatch(r"[A-Z]", w["text"]) and w["bbox"][1] < 70]
    row = min(rows, key=lambda w: abs((w["bbox"][1] + w["bbox"][3]) / 2 - y), default=None)
    col = min(cols, key=lambda w: abs((w["bbox"][0] + w["bbox"][2]) / 2 - x), default=None)
    return _json({"line": row["text"] if row else None, "column": col["text"] if col else None})


@server.tool()
def check(labels: dict) -> str:
    """答え（指定の JSON Schema の形）を点検する。正解データは使わず、答えの中の食い違いと
    決まりへの合い方だけを見る。問題の一覧を返す（空なら問題なし）。"""
    return _json({"problems": check_labels(labels, _graph(), _words())})


@server.tool()
def preview(labels: dict) -> str:
    """答えからつながり（ネット）と回路の筋を組み立てて返す。答える前の確認に使う。"""
    try:
        doc, _, problems = assemble(
            labels, _graph(), {"sample_id": "preview", "page": PAGE, "pdf_kind": "vector"}
        )
    except Exception as e:  # noqa: BLE001
        return _json({"error": f"組み立てられません：{e}"})
    return _json({
        "nets": [{"id": n["id"], "members": n["members"], "rail": n["rail"]} for n in doc["nets"]],
        "circuits": [c["expression"] for c in doc["circuits"]],
        "problems": problems,
    })  # fmt: skip


@server.tool()
def search_pages(pattern: str, regex: bool = False, max_hits: int = 40) -> str:
    """図面集の全頁の文字から探す。頁番号と前後の文字を返す。"""
    text = (WORK / "pages.txt").read_text(encoding="utf-8")
    hits = []
    parts = re.split(r"(?m)^=== p\.(\d+) ===$", text)
    rx = re.compile(pattern if regex else re.escape(pattern))
    for i in range(1, len(parts), 2):
        page, body = int(parts[i]), parts[i + 1]
        flat = re.sub(r"\s+", " ", body)
        for m in rx.finditer(flat):
            hits.append({"page": page, "context": flat[max(0, m.start() - 60) : m.end() + 60]})
            if len(hits) >= max_hits:
                return _json(hits)
    return _json(hits)


SANDBOX_IMAGE = "kairo-python:1"
PY_SECONDS = 60
PY_MAX_CHARS = 20000


def run_python(code: str) -> str:
    """Python 3.12 のコードを箱の中で動かし、標準出力と標準エラーを返す。
    箱の中では、作業フォルダが /work（読み取り専用。graph.json・words.json・symbols.json・
    pages.txt・画像など）、この頁の線と文字の全データが /data/vector.json（読み取り専用）。
    使えるのは標準ライブラリと numpy・Pillow。ネットにはつながらず、書き込めるのは /tmp だけ
    （呼ぶたびに消える）。1回60秒まで、出力は2万字まで。結果は print で出す。"""
    name = f"kairo-py-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm", "-i", "--name", name, "--network", "none",
        "--read-only", "--tmpfs", "/tmp:size=64m", "--memory", "1g", "--cpus", "1",
        "--pids-limit", "64", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--mount", f"type=bind,source={WORK.resolve()},target=/work,readonly",
        "--mount", f"type=bind,source={VECTOR.resolve()},target=/data/vector.json,readonly",
        "-w", "/work", "-e", "PYTHONIOENCODING=utf-8", "-e", "HOME=/tmp",
        SANDBOX_IMAGE, "timeout", str(PY_SECONDS), "python", "-",
    ]  # fmt: skip
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, input=code, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=PY_SECONDS + 60,
        )  # fmt: skip
        status, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        status, out, err = None, "", "時間切れで止めた"
    if status == 124:
        err += f"\n{PY_SECONDS} 秒を超えたので止めた"
    text = f"[終了コード {status}、{time.time() - t0:.1f} 秒]\n{out}"
    if err.strip():
        text += f"\n--- 標準エラー ---\n{err}"
    if len(text) > PY_MAX_CHARS:
        text = text[:PY_MAX_CHARS] + f"\n…（{len(text) - PY_MAX_CHARS} 字を省いた）"
    return text


if os.environ.get("KAIRO_PYTHON"):  # only for `kairo run --python`
    server.tool()(run_python)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()

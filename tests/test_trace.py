import json

import pytest

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.pdf.trace import trace

VECTOR = PROJECT_ROOT / "samples/derived/c6_mazak_stx510/p076.vector.json"


@pytest.mark.skipif(not VECTOR.exists(), reason="local sample not extracted (kairo extract)")
def test_mazak_p76_symbols_are_found():
    t = trace(json.loads(VECTOR.read_text(encoding="utf-8")))
    assert len(t.dots) == 29  # junction dots, including the tiny ones at KA4's terminals
    assert len([c for c in t.circles if c.r < 2.2]) == 15  # 11 terminal circles + 4 in the logo
    assert len(t.pins) == 34  # every ">>" / "<<" pin on the page
    assert len(t.cut_boxes) == 2  # V4 and HL4: the wire runs through the symbol


def test_crossing_without_dot_does_not_connect():
    page = {
        "paths": [
            {"kind": "line", "pts": [[0, 10], [20, 10]], "width": 0.2},
            {"kind": "line", "pts": [[10, 0], [10, 20]], "width": 0.2},
        ]
    }
    t = trace(page)
    assert len({e.na for e in t.edges} | {e.nb for e in t.edges}) == 4


def test_dot_joins_a_tee():
    dot = [[10 + 1.4 * x, 10 + 1.4 * y] for x, y in ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 0))]
    page = {
        "paths": [
            {"kind": "line", "pts": [[0, 10], [20, 10]], "width": 0.2},
            {"kind": "line", "pts": [[10, 10], [10, 20]], "width": 0.2},
            {"kind": "curve", "pts": dot, "width": 0.2},
        ]
    }
    t = trace(page)
    dot_node = next(n for n in t.nodes if n.dot is not None)
    assert len(dot_node.edges) == 3

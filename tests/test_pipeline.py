"""Assemble + compare round trip: labels made from the ground truth must score perfectly."""

import json
import math

import pytest

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.convert.assemble import assemble
from kairo_pdf_json.eval.compare import compare
from kairo_pdf_json.pdf.trace import key_graph, trace

VECTOR = PROJECT_ROOT / "samples/derived/c6_mazak_stx510/p076.vector.json"
GT = PROJECT_ROOT / "ground_truth/c6_mazak_stx510"


def labels_from_page(doc: dict, set_doc: dict, graph: dict) -> dict:
    def point(pos) -> str:
        return min(graph["points"], key=lambda p: math.dist((p["x"], p["y"]), pos))["id"]

    pos = {p["id"]: p["pos"] for p in doc["ports"]}
    comps = []
    for c in doc["components"]:
        comps.append(
            {
                "id": c["id"],
                "name": c.get("name"),
                "kind": c["kind"],
                "symbol": c.get("symbol"),
                "region": c.get("region"),
                "purpose": c.get("purpose"),
                "elements": [
                    {
                        "id": el["id"],
                        "kind": el["kind"],
                        "contact": el.get("contact"),
                        "symbol": el.get("symbol"),
                        "ports": [{"name": p, "point": point(pos[p])} for p in el["ports"]],
                        "bbox": el.get("loc", {}).get("bbox", []),
                    }
                    for el in c.get("elements", [])
                ],
                "terminals": [
                    {"name": f"{c['id']}:{t}", "point": point(pos[f"{c['id']}:{t}"])}
                    for t in c.get("terminals", [])
                ],
            }
        )
    return {
        "sheet": doc["sheet"],
        "regions": [
            {
                "id": r["id"],
                "label": r["label"],
                "kind": r["kind"],
                "meaning": r.get("meaning") or "",
            }
            for r in doc.get("regions", [])
        ],
        "rails": [
            {
                "name": r["name"],
                "polarity": r["polarity"],
                "polarity_basis": r["polarity_basis"],
                "point": point(r["pos"]),
            }
            for r in doc["rails"]
        ],
        "components": comps,
        "plc_io": [
            {
                **{k: io.get(k) for k in ("address", "direction", "port", "device", "comment")},
                "point": point(pos[io["port"]]),
            }
            for io in doc["plc_io"]
        ],
        "open_ends": [
            {"port": o["port"], "note": o["note"], "evidence": o.get("evidence", [])}
            for o in doc["open_ends"]
        ],
        "conventions": set_doc["conventions"],
        "cross_references": [],
        "tables": [
            {"title": t.get("title"), "rows": t["rows"], "note": t.get("note")}
            for t in doc.get("tables", [])
        ],
        "unresolved": [],
        "needs_review": [],
    }


@pytest.mark.skipif(not VECTOR.exists(), reason="local sample not extracted (kairo extract)")
def test_labels_from_ground_truth_score_perfectly():
    gt = json.loads((GT / "p076.json").read_text(encoding="utf-8"))
    set_doc = json.loads((GT / "set.json").read_text(encoding="utf-8"))
    graph = key_graph(trace(json.loads(VECTOR.read_text(encoding="utf-8"))))
    labels = labels_from_page(gt, set_doc, graph)
    doc, _, problems = assemble(labels, graph, gt["source"])
    assert problems == []
    r = compare(doc, gt, graph)
    assert r["gate_pass"]
    assert r["all_match"]
    assert r["elements"]["extra"] == []
    assert r["nets"]["exact"] == r["nets"]["gt"]
    assert r["port_names"]["wrong"] == []
    assert r["elements"]["contact_ok"] == r["elements"]["contact_total"]
    assert r["circuits"]["same"] == r["circuits"]["gt"]
    assert r["open_ends"]["same"] == r["open_ends"]["gt"]


@pytest.mark.skipif(not VECTOR.exists(), reason="local sample not extracted (kairo extract)")
def test_self_check_passes_correct_labels_and_flags_a_cut_off_plc_input():
    from kairo_pdf_json.convert.check_labels import check_labels

    gt = json.loads((GT / "p076.json").read_text(encoding="utf-8"))
    set_doc = json.loads((GT / "set.json").read_text(encoding="utf-8"))
    graph = key_graph(trace(json.loads(VECTOR.read_text(encoding="utf-8"))))
    labels = labels_from_page(gt, set_doc, graph)
    words = json.loads(VECTOR.read_text(encoding="utf-8"))["words"]
    assert check_labels(labels, graph, words) == []
    # point X0.00 at an unnamed wire end that leads nowhere (beyond the input box)
    named = {np["point"] for c in labels["components"] for np in c["terminals"]}
    named |= {p["point"] for c in labels["components"] for el in c["elements"] for p in el["ports"]}
    named |= {io["point"] for io in labels["plc_io"]}
    kind = {p["id"]: p["kind"] for p in graph["points"]}
    stray = next(  # a short line whose both ends are loose (e.g. the line under an input name)
        r["a"]
        for r in graph["runs"]
        if kind[r["a"]] == kind[r["b"]] == "end" and not {r["a"], r["b"]} & named
    )
    labels["plc_io"][0]["point"] = stray
    for c in labels["components"]:
        for np in c["terminals"]:
            if np["name"] == labels["plc_io"][0]["port"]:
                np["point"] = stray
    problems = check_labels(labels, graph)
    assert any("ほかのポートに届かない" in p for p in problems)


@pytest.mark.skipif(not VECTOR.exists(), reason="local sample not extracted (kairo extract)")
def test_self_check_flags_a_device_split_in_two_and_a_unit_in_the_address():
    from kairo_pdf_json.convert.check_labels import check_labels

    gt = json.loads((GT / "p076.json").read_text(encoding="utf-8"))
    set_doc = json.loads((GT / "set.json").read_text(encoding="utf-8"))
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    graph = key_graph(trace(vector))
    labels = labels_from_page(gt, set_doc, graph)
    two = next(c for c in labels["components"] if len(c["elements"]) == 2)
    second = two["elements"].pop()
    labels["components"].append({**two, "id": two["id"] + "_2", "elements": [second]})
    labels["plc_io"][0]["address"] = labels["plc_io"][0]["port"]
    problems = check_labels(labels, graph, vector["words"])
    assert any(f"「{two['id']}_2」が図面の文字に見当たらない" in p for p in problems)
    assert any("ユニットの ID が付いている" in p for p in problems)


@pytest.mark.skipif(not VECTOR.exists(), reason="local sample not extracted (kairo extract)")
def test_self_check_flags_the_same_element_id_twice_in_one_device():
    from kairo_pdf_json.convert.check_labels import check_labels

    gt = json.loads((GT / "p076.json").read_text(encoding="utf-8"))
    set_doc = json.loads((GT / "set.json").read_text(encoding="utf-8"))
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    graph = key_graph(trace(vector))
    labels = labels_from_page(gt, set_doc, graph)
    two = next(c for c in labels["components"] if len(c["elements"]) == 2)
    for el in two["elements"]:
        el["id"] = two["id"]
    problems = check_labels(labels, graph, vector["words"])
    assert any(f"{two['id']} の要素 ID「{two['id']}」が重なっている" in p for p in problems)

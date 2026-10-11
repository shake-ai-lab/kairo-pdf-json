import base64
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.gt.check import check_page
from kairo_pdf_json.gt.review_import import import_review
from kairo_pdf_json.model.derive import derive

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
SCHEMA = json.loads((PROJECT_ROOT / "schema" / "page.schema.json").read_text(encoding="utf-8"))


def minimal_page(**overrides) -> dict:
    """1L+ → SQ1 (b contact) → XT1:1 → PLC input A1:X0."""
    doc = {
        "schema_version": "0.2",
        "source": {"sample_id": "x", "page": 1, "pdf_kind": "vector"},
        "sheet": {"title": "T"},
        "rails": [{"id": "rail:P", "name": "P", "polarity": "plus"}],
        "components": [
            {
                "id": "SQ1",
                "kind": "limit_switch",
                "elements": [
                    {"id": "b", "kind": "contact", "contact": "b", "ports": ["SQ1:b.1", "SQ1:b.2"]}
                ],
            },
            {"id": "XT1", "kind": "terminal_block", "terminals": ["1"]},
            {"id": "A1", "kind": "plc_unit", "terminals": ["X0"]},
        ],
        "ports": [{"id": p} for p in ("SQ1:b.1", "SQ1:b.2", "XT1:1", "A1:X0")],
        "junctions": [],
        "wires": [
            {"id": "W1", "ends": ["rail:P", "SQ1:b.1"]},
            {"id": "W2", "ends": ["SQ1:b.2", "XT1:1"]},
            {"id": "W3", "ends": ["XT1:1", "A1:X0"]},
        ],
        "open_ends": [],
        "nets": [],
        "circuits": [],
        "plc_io": [{"address": "X0", "direction": "input", "port": "A1:X0", "device": "SQ1"}],
        "cross_references": [],
        "unresolved": [],
    }
    doc.update(overrides)
    return derive(doc)


def test_minimal_page_is_valid_and_consistent():
    doc = minimal_page()
    assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []
    assert check_page(doc) == []


def test_undefined_wire_end_and_unconnected_port_are_reported():
    doc = minimal_page()
    doc["wires"].append({"id": "W4", "ends": ["XT1:1", "KA9:1"]})
    doc["ports"].append({"id": "XT1:2"})
    problems = check_page(doc)
    assert any("KA9:1" in p and "定義されていません" in p for p in problems)
    assert any("XT1:2" in p for p in problems)


def test_hand_edited_nets_are_reported():
    doc = minimal_page()
    doc["nets"][0]["members"].append("XT1:1")
    assert any("nets" in p and "計算した結果と違います" in p for p in check_page(doc))


def test_committed_ground_truth_is_valid_and_consistent():
    for path in (PROJECT_ROOT / "ground_truth").glob("*/p*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        set_path = path.parent / "set.json"
        set_doc = json.loads(set_path.read_text(encoding="utf-8")) if set_path.exists() else None
        assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == [], path
        assert check_page(doc, set_doc) == [], path


def test_review_import_writes_notes_and_images(tmp_path: Path):
    review = {
        "kind": "kairo-review",
        "sample_id": "c6_mazak_stx510",
        "page": 76,
        "title": "AXIS LS",
        "saved_at": "2026-10-11T12:34:56.000Z",
        "items": {
            "net:n_358": {
                "verdict": "ng",
                "note": "並列ではない",
                "images": [
                    {
                        "id": "a",
                        "name": "s.png",
                        "type": "image/png",
                        "data": base64.b64encode(PNG).decode(),
                    }
                ],
            },
            "q:Q1": {"verdict": "ok", "note": "", "images": []},
        },
    }
    src = tmp_path / "review_c6_mazak_stx510_p076.json"
    src.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    out = import_review(src, out_root=tmp_path / "out")
    notes = (out / "notes.md").read_text(encoding="utf-8")
    assert "[net:n_358] 違う：並列ではない" in notes
    assert "[q:Q1] OK" in notes
    assert (out / "net_n_358_1.png").read_bytes() == PNG

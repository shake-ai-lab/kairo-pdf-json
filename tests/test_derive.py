from kairo_pdf_json.model.derive import derive


def lamp_page() -> dict:
    """Two a contacts in parallel from P to net 10, then a coil and a resistor+lamp to M.

    Net 10 also leaves the page at connector X9:1 (an open end).
    """
    contact = [
        {
            "id": sq,
            "kind": "limit_switch",
            "elements": [
                {"id": "a", "kind": "contact", "contact": "a", "ports": [f"{sq}:a.1", f"{sq}:a.2"]}
            ],
        }
        for sq in ("SQ1", "SQ2")
    ]
    two = [
        ("KA1", "coil", ["KA1:1", "KA1:2"]),
        ("R1", "resistor", ["R1:1", "R1:2"]),
        ("HL1", "lamp", ["HL1:1", "HL1:2"]),
    ]
    parts = [
        {"id": cid, "kind": kind, "elements": [{"id": "body", "kind": kind, "ports": ports}]}
        for cid, kind, ports in two
    ]
    return {
        "schema_version": "0.2",
        "source": {"sample_id": "x", "page": 1, "pdf_kind": "vector"},
        "sheet": {"title": "T"},
        "rails": [
            {
                "id": "rail:P",
                "name": "P",
                "polarity": "plus",
                "polarity_basis": {"value": "+", "basis": "human"},
            },
            {"id": "rail:M", "name": "M", "polarity": "zero"},
        ],
        "components": [
            *contact,
            *parts,
            {"id": "XT1", "kind": "terminal_block", "terminals": ["10"]},
            {"id": "X9", "kind": "connector", "terminals": ["1"]},
        ],
        "ports": [],
        "junctions": [{"id": "J1", "pos": [0, 0]}, {"id": "J2", "pos": [0, 0]}],
        "wires": [
            {"id": "W1", "ends": ["rail:P", "SQ1:a.1"]},
            {"id": "W2", "ends": ["rail:P", "SQ2:a.1"]},
            {"id": "W3", "ends": ["SQ1:a.2", "XT1:10"]},
            {"id": "W4", "ends": ["SQ2:a.2", "XT1:10"]},
            {"id": "W5", "ends": ["XT1:10", "J1"]},
            {"id": "W6", "ends": ["J1", "KA1:1"]},
            {"id": "W7", "ends": ["J1", "R1:1"]},
            {"id": "W8", "ends": ["J1", "X9:1"]},
            {"id": "W9", "ends": ["R1:2", "HL1:1"]},
            {"id": "W10", "ends": ["KA1:2", "J2"]},
            {"id": "W11", "ends": ["HL1:2", "J2"]},
            {"id": "W12", "ends": ["J2", "rail:M"]},
        ],
        "open_ends": [{"port": "X9:1", "note": "この頁では先が描かれていない"}],
        "nets": [],
        "circuits": [],
        "plc_io": [],
        "cross_references": [],
        "unresolved": [],
    }


SET = {
    "conventions": [
        {"id": "terminal_no_is_wire_no", "rule": "端子番号＝線番", "basis": "other_page"}
    ]
}


def test_nets_follow_wires_and_take_wire_numbers_from_terminals():
    doc = derive(lamp_page(), SET)
    nets = {n["id"]: n for n in doc["nets"]}
    assert set(nets) == {"n_P", "n_10", "n_R1_HL1", "n_M"}
    assert nets["n_10"]["wire_no"]["value"] == "10"
    assert nets["n_10"]["open_ends"] == ["X9:1"]
    assert set(nets["n_10"]["members"]) == {"SQ1:a.2", "SQ2:a.2", "XT1:10", "KA1:1", "R1:1", "X9:1"}


def test_circuit_is_reduced_to_series_and_parallel_with_direction_status():
    doc = derive(lamp_page(), SET)
    [c] = doc["circuits"]
    assert c["expression"] == (
        "P → （SQ1 a接点 ∥ SQ2 a接点） → [10] → "
        "（KA1 コイル ∥ （R1 抵抗 → [R1–HL1] → HL1 表示灯）） → M"
    )
    assert c["direction"]["status"] == "confirmed"
    assert "X9:1" in c["direction"]["basis"] and "不明" in c["direction"]["basis"]
    assert c["steps"][1] == "SQ1・SQ2 の a接点（2つが並列）"


def test_inferred_polarity_gives_inferred_direction():
    page = lamp_page()
    page["rails"][0]["polarity_basis"] = {"value": "+", "basis": "inferred"}
    assert derive(page, SET)["circuits"][0]["direction"]["status"] == "inferred"

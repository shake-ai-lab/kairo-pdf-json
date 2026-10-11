"""The drawing tools (MCP server functions) on the local Mazak p.76 inputs."""

import importlib
import json
import subprocess

import pytest

from kairo_pdf_json import PROJECT_ROOT

DERIVED = PROJECT_ROOT / "samples/derived/c6_mazak_stx510"
WORK = DERIVED / "ai_input_p076"


@pytest.fixture
def tools(monkeypatch):
    if not (WORK / "symbols.json").exists():
        pytest.skip("local inputs not prepared")
    monkeypatch.setenv("KAIRO_WORK", str(WORK))
    monkeypatch.setenv("KAIRO_PDF", str(PROJECT_ROOT / "samples/raw/c6_mazak_stx510/original.pdf"))
    monkeypatch.setenv("KAIRO_PAGE", "76")
    monkeypatch.setenv("KAIRO_VECTOR", str(DERIVED / "p076.vector.json"))
    from kairo_pdf_json.tools import server

    return importlib.reload(server)


def test_where_gives_line_and_column(tools):
    assert json.loads(tools.where(110, 244)) == {"line": "09", "column": "B"}


def test_symbol_features_tell_the_stop_line_apart(tools):
    feats = {c["id"]: json.loads(tools.symbol_features(c["id"])) for c in tools._symbols()[:10]}
    crossing = [s for s, f in feats.items() if f["diagonal_crosses_vertical"]]
    plain = [
        s for s, f in feats.items() if f["diagonal_count"] and not f["diagonal_crosses_vertical"]
    ]
    assert crossing and plain  # b contacts (blade past the stop) and a contacts (blade free)


def _has_sandbox() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", "kairo-python:1"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


@pytest.mark.skipif(not _has_sandbox(), reason="Docker or the kairo-python:1 box is not ready")
def test_run_python_reads_the_inputs_but_cannot_write_or_reach_out(tools):
    code = """
import json, os, socket
print(len(json.load(open('/work/graph.json'))['points']) > 0)
print('words' in json.load(open('/data/vector.json')))
for target in ('/work/x.txt', '/x.txt'):
    try:
        open(target, 'w').write('x')
        print('wrote', target)
    except OSError:
        print('no write')
try:
    socket.create_connection(('1.1.1.1', 80), timeout=3)
    print('net')
except OSError:
    print('no net')
print(sorted(os.listdir('/work'))[:3])
"""
    out = tools.run_python(code)
    assert out.startswith("[終了コード 0、")
    lines = out.splitlines()
    assert lines[1:6] == ["True", "True", "no write", "no write", "no net"]
    assert "Users" not in out  # nothing of the host folders is visible


def test_trace_from_a_loose_end_reaches_nothing_else(tools):
    graph = tools._graph()
    kind = {p["id"]: p["kind"] for p in graph["points"]}
    loose = next(r["a"] for r in graph["runs"] if kind[r["a"]] == kind[r["b"]] == "end")
    assert json.loads(tools.trace_from(loose))["count"] <= 2

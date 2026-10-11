"""Python written by the AI is taken out of the transcript with its output and round."""

import json

from kairo_pdf_json.run.code_log import extract


def test_code_log_takes_python_from_both_clis(tmp_path):
    lines = [
        {"round": 1},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__pdf__run_python",
             "input": {"code": "print(1)"}},
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "a"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": [{"type": "text",
                          "text": json.dumps({"result": "[終了コード 0、1.2 秒]\n1\n"})}]},
        ]}},
        {"round": 2},
        {"type": "item.completed", "item": {
            "type": "command_execution", "command": "powershell -Command \"python -c 'print(2)'\"",
            "aggregated_output": "2\n", "exit_code": 0}},
        {"type": "item.completed", "item": {
            "type": "command_execution", "command": "Get-Content graph.json",
            "aggregated_output": "{}", "exit_code": 0}},
        {"type": "item.completed", "item": {
            "type": "mcp_tool_call", "server": "pdf", "tool": "run_python",
            "arguments": {"code": "print(3)"}, "status": "completed",
            "result": {"content": [{"type": "text", "text": "[終了コード 1、0.9 秒]\nboom"}]}}},
    ]  # fmt: skip
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    got = extract(path)
    assert [(e["round"], e["via"], e["status"]) for e in got] == [
        (1, "run_python", "0"),
        (2, "codex-shell", 0),
        (2, "run_python", "1"),
    ]
    assert got[0]["code"] == "print(1)" and got[0]["output"].endswith("1\n")
    assert got[2]["output"].endswith("boom")

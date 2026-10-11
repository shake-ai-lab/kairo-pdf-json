"""The Python an AI wrote during a run, taken from its transcript (SPEC §7.3, tool distillation).

Two sources: the run_python tool (both CLIs) and, in older Codex runs, shell commands that start
Python. Each entry keeps the code, its output and which answer round it belongs to.
"""

import json
import re
from pathlib import Path

PY_COMMAND = re.compile(r"\bpython[0-9.]*(\.exe)?\b", re.I)
EXIT_HEADER = re.compile(r"^\[終了コード (\S+)、")


def _text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _text(content.get("content")) if "content" in content else json.dumps(content)
    if isinstance(content, list):
        return "\n".join(_text(c.get("text")) if isinstance(c, dict) else str(c) for c in content)
    return str(content)


def _unwrap(output: str) -> str:
    """The MCP server may wrap a returned string as {"result": "..."}."""
    if output.startswith('{"result"'):
        try:
            return json.loads(output)["result"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return output


def _status(output: str, fallback):
    m = EXIT_HEADER.match(output)
    return m.group(1) if m else fallback


def extract(transcript: Path) -> list[dict]:
    """Every piece of Python in the transcript, in order, with its output."""
    entries: list[dict] = []
    pending: dict[str, dict] = {}  # Claude tool_use id -> entry waiting for its result
    rnd = 1
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if set(e) == {"round"}:
            rnd = e["round"]
            continue
        item = e.get("item") or {}
        if e.get("type") == "item.completed":
            kind = item.get("type")
            if kind == "command_execution" and PY_COMMAND.search(item.get("command", "")):
                entries.append({
                    "round": rnd, "via": "codex-shell", "code": item["command"],
                    "output": item.get("aggregated_output") or "", "status": item.get("exit_code"),
                })  # fmt: skip
            elif kind == "mcp_tool_call" and item.get("tool") == "run_python":
                args = item.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args)
                out = _unwrap(_text(item.get("result")) or _text(item.get("error")))
                entries.append({
                    "round": rnd, "via": "run_python", "code": args.get("code", ""),
                    "output": out, "status": _status(out, item.get("status")),
                })  # fmt: skip
            continue
        content = (e.get("message") or {}).get("content")
        for part in content if isinstance(content, list) else []:
            if part.get("type") == "tool_use" and str(part.get("name")).endswith("run_python"):
                entry = {
                    "round": rnd, "via": "run_python", "code": part["input"].get("code", ""),
                    "output": "", "status": None,
                }  # fmt: skip
                pending[part["id"]] = entry
                entries.append(entry)
            elif part.get("type") == "tool_result" and part.get("tool_use_id") in pending:
                entry = pending.pop(part["tool_use_id"])
                entry["output"] = _unwrap(_text(part.get("content")))
                entry["status"] = _status(entry["output"], "error" if part.get("is_error") else "")
    return entries


def write_code_log(run_dir: Path) -> list[dict]:
    """Write runs/…/code_log.json from the run's transcript and return the entries."""
    transcript = run_dir / "transcript.jsonl"
    entries = extract(transcript) if transcript.exists() else []
    (run_dir / "code_log.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    return entries

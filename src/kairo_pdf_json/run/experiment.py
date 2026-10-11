"""Run the labelling experiment (SPEC §7.4): give an AI the extracted page, assemble, compare.

Each run is saved under runs/<time>_<sample>_pNNN_<model>/ with the inputs, the prompt, the raw
CLI output, the labels, the assembled page JSON, the evaluation and the timing. The CLI runs in
a temporary folder outside the project so that this project's CLAUDE.md, hooks and memory do not
leak into the experiment.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pypdfium2 as pdfium
from jsonschema import Draft202012Validator

from kairo_pdf_json import PROJECT_ROOT
from kairo_pdf_json.convert.assemble import assemble
from kairo_pdf_json.convert.check_labels import CHECK_VERSION, check_labels
from kairo_pdf_json.eval.compare import compare, report_md
from kairo_pdf_json.gt.view import build_view
from kairo_pdf_json.pdf.render import render_page
from kairo_pdf_json.pdf.symbols import candidates as symbol_candidates
from kairo_pdf_json.pdf.symbols import render_crops
from kairo_pdf_json.pdf.trace import key_graph, trace
from kairo_pdf_json.run.code_log import write_code_log
from kairo_pdf_json.samples import Sample, page_stem

LABEL_SCHEMA = PROJECT_ROOT / "schema" / "ai_labels.schema.json"
TOOLS = "Read,Grep,Glob"
# v1: graph.json and words.json on one line (the reader cut them off); v2: one item per line;
# v3: both CLIs get the 7 images with the first message
INPUT_FORMAT = "v3"
CODEX_EFFORT = "medium"  # used when no effort is given (the Codex catalog defaults differ by model)


def _write_lines(path: Path, data: dict | list) -> None:
    """JSON with one item per line: the AI's file reader cuts very long lines."""

    nl = "\n"

    def items(xs: list) -> str:
        return ("," + nl).join("  " + json.dumps(x, ensure_ascii=False) for x in xs)

    if isinstance(data, list):
        text = "[" + nl + items(data) + nl + "]" + nl
    else:
        parts = [f'"{k}": [{nl}{items(v)}{nl}]' for k, v in data.items()]
        text = "{" + nl + ("," + nl).join(parts) + nl + "}" + nl
    json.loads(text)  # still valid JSON
    path.write_text(text, encoding="utf-8")


def prepare_inputs(sample: Sample, page: int, out: Path, symbols: bool = False) -> dict:
    """Write the files the AI gets (page image, tiles, words, traced graph, all pages' text)."""
    out.mkdir(parents=True, exist_ok=True)
    derived = sample.derived_dir
    image = derived / f"{page_stem(page)}_300dpi.png"
    if not image.exists():
        render_page(sample.pdf, page, 300).save(image)
    shutil.copy(image, out / "page.png")
    vector = json.loads((derived / f"{page_stem(page)}.vector.json").read_text(encoding="utf-8"))
    width, height = vector["width"], vector["height"]

    from PIL import Image

    img = Image.open(image)
    k = img.width / width
    tiles = []
    cols, rows, pad = 2, 3, 20.0  # pt of overlap
    for r in range(rows):
        for c in range(cols):
            x0, x1 = max(0, c * width / cols - pad), min(width, (c + 1) * width / cols + pad)
            y0, y1 = max(0, r * height / rows - pad), min(height, (r + 1) * height / rows + pad)
            name = f"tile_r{r + 1}c{c + 1}.png"
            img.crop((round(x0 * k), round(y0 * k), round(x1 * k), round(y1 * k))).save(out / name)
            tiles.append(
                {
                    "file": name,
                    "x0": round(x0, 1),
                    "y0": round(y0, 1),
                    "x1": round(x1, 1),
                    "y1": round(y1, 1),
                }
            )
    (out / "tiles.json").write_text(
        json.dumps(tiles, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    words = [
        {"id": f"W{i}", "text": w["text"], "bbox": [round(x, 2) for x in w["bbox"]]}
        for i, w in enumerate(vector["words"], 1)
    ]
    _write_lines(out / "words.json", words)
    traced = trace(vector)
    graph = key_graph(traced)
    _write_lines(out / "graph.json", graph)
    if symbols:  # symbol candidates with 1200dpi crops (SPEC §7.3)
        cands = symbol_candidates(vector, traced, graph)
        render_crops(sample.pdf, page, cands, out / "symbols")
        _write_lines(out / "symbols.json", cands)
    doc = pdfium.PdfDocument(str(sample.pdf))
    try:
        with (out / "pages.txt").open("w", encoding="utf-8") as f:
            for i in range(len(doc)):
                f.write(f"=== p.{i + 1} ===\n{doc[i].get_textpage().get_text_range()}\n")
    finally:
        doc.close()
    return {"graph": graph, "words": words, "width": width, "height": height}


def render_prompt(path: Path, sample: Sample, page: int, width: float, height: float) -> str:
    return (
        path.read_text(encoding="utf-8")
        .replace("{{SAMPLE_TITLE}}", sample.title)
        .replace("{{PAGE}}", str(page))
        .replace("{{PAGE_W}}", f"{width:.0f}")
        .replace("{{PAGE_H}}", f"{height:.0f}")
    )


WORK_ROOT = Path(tempfile.gettempdir()) / "kairo-runs"
# v1: no read limits and no record of what the AI read; v2: denied folders + audited tool calls
ISOLATION = "v2"


def _rule_path(p: Path) -> str:
    """Claude permission-rule form of an absolute folder: //c/Users/name/folder/**"""
    p = p.resolve()
    drive, rest = p.drive.rstrip(":").lower(), p.as_posix().split(":", 1)[1]
    return f"//{drive}{rest}/**"


def denied_dirs() -> list[Path]:
    """Folders the AI must not read: other projects (and this one), session logs, downloads …"""
    home = Path.home()
    dirs = [
        PROJECT_ROOT.parent,
        home / ".claude",
        home / ".codex",
        home / "Downloads",
        home / "Documents",
        home / "Desktop",
        home / "OneDrive",
        Path(tempfile.gettempdir()) / "claude",
    ]
    return [d for d in dirs if d.exists()]


def _outside(path_text: str, work: Path) -> bool:
    p = Path(path_text).expanduser()
    if not p.is_absolute():
        p = work / p
    try:
        p.resolve().relative_to(work.resolve())
        return False
    except ValueError:
        return True


def claude_exe() -> str:
    """The real claude.exe: the npm .cmd shim goes through cmd.exe, which breaks long arguments."""
    found = shutil.which("claude")
    if not found:
        raise SystemExit("claude CLI が見つかりません")
    shim = Path(found)
    if shim.suffix.lower() == ".cmd":
        exe = shim.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.exists():
            return str(exe)
    return found


def codex_exe() -> str:
    found = shutil.which("codex")
    if found and not found.lower().endswith((".cmd", ".ps1")):
        return found
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    exes = sorted(base.glob("*/codex.exe"), key=lambda q: q.stat().st_mtime)
    if exes:
        return str(exes[-1])
    raise SystemExit("codex CLI が見つかりません")


def compact_schema() -> str:
    schema = json.loads(LABEL_SCHEMA.read_text(encoding="utf-8"))
    # the CLIs do not load the draft 2020-12 meta-schema
    for key in ("$schema", "$id"):
        schema.pop(key, None)
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def image_names(work: Path) -> list[str]:
    return ["page.png", *sorted(q.name for q in work.glob("tile_*.png"))]


def _clean_env(*keys: str) -> dict[str, str]:
    for k in keys:
        if os.environ.get(k):
            print(f"注意：{k} が設定されています。この実行では外して動かします（API 課金を防ぐ）")
    return {k: v for k, v in os.environ.items() if k not in keys}


def tool_env(work: Path, sample: Sample, page: int, python: bool = False) -> dict[str, str]:
    """Environment for the drawing-tools MCP server (tools/server.py) of one run."""
    env = {
        "KAIRO_WORK": str(work),
        "KAIRO_PDF": str(sample.pdf),
        "KAIRO_PAGE": str(page),
        "KAIRO_VECTOR": str(sample.derived_dir / f"{page_stem(page)}.vector.json"),
        "PYTHONIOENCODING": "utf-8",
    }
    if python:
        env["KAIRO_PYTHON"] = "1"
    return env


def sandbox_image_id() -> str:
    """ID of the box run_python uses; stops the run when it has not been built."""
    from kairo_pdf_json.tools.server import SANDBOX_IMAGE

    proc = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE, "--format", "{{.Id}}"],
        capture_output=True, text=True,
    )  # fmt: skip
    if proc.returncode != 0:
        raise SystemExit(
            f"Python の箱 {SANDBOX_IMAGE} がありません。Docker を起動して "
            f"docker build -t {SANDBOX_IMAGE} src/kairo_pdf_json/tools/sandbox で作ってください"
        )
    return proc.stdout.strip()


def _toml_str(text: str) -> str:
    return "'" + text.replace("'", "") + "'"  # TOML literal string: backslashes stay as they are


def run_claude(
    model: str, work: Path, prompt: str, effort: str | None, tools: dict | None = None
) -> dict:
    deny = [f"{t}({_rule_path(d)})" for d in denied_dirs() for t in ("Read", "Grep", "Glob")]
    cmd = [
        claude_exe(), "-p", "--model", model,
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
        "--json-schema", compact_schema(),
        "--tools", TOOLS, "--allowedTools", TOOLS + (",mcp__pdf" if tools else ""),
        "--disallowedTools", *deny,
        "--setting-sources", "local", "--no-session-persistence",
    ]  # fmt: skip
    if tools:
        config = {"mcpServers": {"pdf": {
            "type": "stdio", "command": sys.executable,
            "args": ["-m", "kairo_pdf_json.tools.server"], "env": tools,
        }}}  # fmt: skip
        config_file = work.parent / f"{work.name}.mcp.json"
        config_file.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        cmd += ["--mcp-config", str(config_file), "--strict-mcp-config"]
    if effort:
        cmd += ["--effort", effort]
    # the same 7 images Codex gets with -i, attached to the first message
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode((work / name).read_bytes()).decode(),
            },
        }
        for name in image_names(work)
    ]
    content.append({"type": "text", "text": prompt})
    message = {"type": "user", "message": {"role": "user", "content": content}}
    proc = subprocess.run(
        cmd, input=json.dumps(message) + "\n", capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=work, env=_clean_env("ANTHROPIC_API_KEY"), timeout=3600,
    )  # fmt: skip
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    calls, outside = [], []
    for e in events:
        if e.get("type") != "assistant":
            continue
        for part in e.get("message", {}).get("content", []):
            if part.get("type") != "tool_use":
                continue
            inp = part.get("input", {})
            calls.append({"tool": part.get("name"), "input": inp})
            for key in ("file_path", "path"):
                if inp.get(key) and _outside(inp[key], work):
                    outside.append(f"{part.get('name')} {inp[key]}")
            pattern = inp.get("pattern", "")
            if (
                part.get("name") == "Glob"
                and Path(pattern).is_absolute()
                and _outside(pattern, work)
            ):
                outside.append(f"Glob {pattern}")
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr[-4000:],
        "events": events,
        "labels": result.get("structured_output"),
        "num_turns": result.get("num_turns"),
        "usage": result.get("usage"),
        "cost_usd_list_price": result.get("total_cost_usd"),
        "tool_calls": calls,
        "outside_access": outside,
        "denials": result.get("permission_denials", []),
        "denied_dirs": [str(d) for d in denied_dirs()],
    }


# a drive letter counts only at the start of a word (so "stack:\n" in code is not "k:\")
ABS_PATH = re.compile(
    r"((?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'<>|;]*"
    r"|\\\\[A-Za-z0-9.-]+\\[^\s\"']+|(?<![A-Za-z0-9_])~[\\/][^\s\"']*)"
)
SHELL_PREFIX = re.compile(
    r'^\s*"?[A-Za-z]:\\[^"]*?(powershell|pwsh|cmd)(\.exe)?"?\s+(-NoProfile\s+)?(-Command|/c)\s+',
    re.I,
)


def codex_outside(command: str, work: Path) -> list[str]:
    """Paths outside the work folder that a shell command touches (the shell itself excluded)."""
    script = SHELL_PREFIX.sub("", command.replace("\\\\", "\\"))
    found = [f"command {m}" for m in ABS_PATH.findall(script) if _outside(m, work)]
    if re.search(r"\.\.[\\/]", script):
        found.append(f"command（..\\ を含む）{script[:200]}")
    return found


def audit_codex(calls: list[dict], workdir: str) -> list[str]:
    work = Path(workdir)
    out: list[str] = []
    for c in calls:
        if c["tool"] == "command":
            out += codex_outside(c["input"], work)
        elif c["tool"].startswith("mcp:pdf."):
            continue  # our own drawing tools read only the run folder and the sample PDF
        elif c["tool"] in ("file_change", "web_search", "mcp_tool_call", "image_generation") or c[
            "tool"
        ].startswith("mcp:"):
            out.append(c["tool"])
        else:  # e.g. viewing an image: check every path it mentions
            text = json.dumps(c["input"], ensure_ascii=False)
            out += [f"{c['tool']} {m}" for m in ABS_PATH.findall(text) if _outside(m, work)]
    return out


def run_codex(
    model: str, work: Path, prompt: str, effort: str | None, tools: dict | None = None
) -> dict:
    schema_file = work.parent / f"{work.name}.schema.json"
    out_file = work.parent / f"{work.name}.last.json"
    schema_file.write_text(compact_schema(), encoding="utf-8")
    cmd = [
        codex_exe(), "exec", prompt, "--json", "-m", model,
        "--output-schema", str(schema_file), "-o", str(out_file),
        "-s", "read-only", "-C", str(work), "--skip-git-repo-check", "--ephemeral",
        "--ignore-user-config", "--ignore-rules", "-c", "project_doc_max_bytes=0",
        # the Windows sandbox (commands are all rejected without it); no apps, plugins or web
        "-c", 'windows.sandbox="unelevated"', "-c", 'web_search="disabled"',
        "--disable", "apps", "--disable", "plugins", "--disable", "remote_plugin",
        "--disable", "skill_search", "--disable", "goals", "--disable", "image_generation",
    ]  # fmt: skip
    if tools:
        env = ", ".join(f"{k} = {_toml_str(v)}" for k, v in tools.items())
        cmd += [
            "-c", f"mcp_servers.pdf.command={_toml_str(sys.executable)}",
            "-c", 'mcp_servers.pdf.args=["-m", "kairo_pdf_json.tools.server"]',
            "-c", f"mcp_servers.pdf.env={{{env}}}",
            "-c", "mcp_servers.pdf.startup_timeout_sec=60",
            "-c", "mcp_servers.pdf.tool_timeout_sec=180",
            # exec never asks, so without this every call fails with "requires approval"
            "-c", 'mcp_servers.pdf.default_tools_approval_mode="approve"',
        ]  # fmt: skip
        if tools.get("KAIRO_PYTHON"):  # Python only in the box (run_python), not in Codex's shell
            cmd += ["--disable", "shell_tool", "--disable", "unified_exec"]
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    for img in image_names(work):
        cmd += ["-i", str(work / img)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=work, env=_clean_env("OPENAI_API_KEY"), timeout=3600, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    calls, outside, usage, turns = [], [], {}, 0
    for e in events:
        if e.get("type") == "turn.completed":
            turns += 1
            for k, v in (e.get("usage") or {}).items():
                if isinstance(v, int):
                    usage[k] = usage.get(k, 0) + v
        item = e.get("item") or {}
        if e.get("type") != "item.completed":
            continue
        kind = item.get("type")
        if kind == "command_execution":
            command = item.get("command", "")
            calls.append({"tool": "command", "input": command})
        elif kind == "mcp_tool_call":
            name = f"mcp:{item.get('server')}.{item.get('tool')}"
            calls.append({"tool": name, "input": item.get("arguments")})
        elif kind not in ("agent_message", "reasoning", "todo_list", "error"):
            calls.append({"tool": kind, "input": item})
    outside = audit_codex(calls, str(work))
    labels = None
    if out_file.exists():
        try:
            labels = json.loads(out_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            labels = None
    for f in (schema_file, out_file):
        f.unlink(missing_ok=True)
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr[-4000:],
        "events": events,
        "labels": labels,
        "num_turns": turns,
        "usage": usage,
        "cost_usd_list_price": None,
        "tool_calls": calls,
        "outside_access": outside,
        "denials": [],
        "denied_dirs": [],
    }


FEEDBACK_FILE = PROJECT_ROOT / "prompts" / "feedback_v1.md"  # sent back with the problems


def run_experiment(
    sample: Sample, page: int, backend: str, model: str, *, prompt_name: str = "label_v2",
    effort: str | None = None, symbols: bool = False, check: bool = False, max_rounds: int = 2,
    tools: bool = False, python: bool = False,
) -> Path:  # fmt: skip
    """Run one model on one page. With check=True, the self-check (convert.check_labels) runs
    after each answer and its problems are sent back for another answer, up to max_rounds."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = PROJECT_ROOT / "runs" / f"{stamp}_{sample.id}_{page_stem(page)}_{model}"
    inputs = run_dir / "input"
    tools = tools or python  # run_python is one of the drawing tools
    symbols = symbols or tools  # symbol_features needs symbols.json
    image_id = sandbox_image_id() if python else None
    info = prepare_inputs(sample, page, inputs, symbols=symbols)
    graph = info["graph"]
    prompt_path = PROJECT_ROOT / "prompts" / f"{prompt_name}.md"
    prompt = render_prompt(prompt_path, sample, page, info["width"], info["height"])
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    work = WORK_ROOT / run_dir.name
    shutil.copytree(inputs, work)
    if backend == "codex-cli" and not effort:
        effort = CODEX_EFFORT
    if backend not in ("claude-cli", "codex-cli"):
        raise SystemExit(f"バックエンド {backend} はありません")
    started = time.time()
    labels, rounds, all_calls, outside, denials = None, [], [], [], []
    usage_total: dict = {}
    res: dict = {}
    current_prompt = prompt
    for n in range(1, (max_rounds if check else 1) + 1):
        t0 = time.time()
        runner = run_claude if backend == "claude-cli" else run_codex
        env = tool_env(work, sample, page, python) if tools else None
        res = runner(model, work, current_prompt, effort, env)
        with (run_dir / "transcript.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"round": n}) + "\n")
            for e in res.pop("events"):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        all_calls += [{"round": n, **c} for c in res.pop("tool_calls")]
        outside += res["outside_access"]
        denials += res.get("denials") or []
        for k, v in (res.get("usage") or {}).items():
            if isinstance(v, int | float):
                usage_total[k] = usage_total.get(k, 0) + v
        new = res.pop("labels")
        info_round = {
            "round": n,
            "seconds": round(time.time() - t0, 1),
            "got_answer": new is not None,
        }
        if new is not None:
            labels = new
            (run_dir / f"labels_round{n}.json").write_text(
                json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        if check and labels is not None:
            problems = check_labels(labels, graph, info["words"])
            info_round["problems"] = problems
            if problems and n < max_rounds:
                (work / "previous_labels.json").write_text(
                    json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                listed = "\n".join(f"- {p}" for p in problems)
                feedback = FEEDBACK_FILE.read_text(encoding="utf-8")
                current_prompt = prompt + "\n\n" + feedback.format(round=n, problems=listed)
                rounds.append(info_round)
                continue
        rounds.append(info_round)
        break
    elapsed = time.time() - started
    (run_dir / "tool_calls.json").write_text(
        json.dumps(all_calls, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_code_log(run_dir)
    meta = {
        "sample": sample.id,
        "page": page,
        "backend": backend,
        "model": model,
        "effort": effort or "cli-default（high）",
        "prompt": prompt_name,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "label_schema": json.loads(LABEL_SCHEMA.read_text(encoding="utf-8"))["$id"],
        "input_format": INPUT_FORMAT + ("+symbols" if symbols else ""),
        "check": check,
        "tools": ("pdf-tools v1" + (" + run_python" if python else "")) if tools else None,
        "sandbox_image": image_id,
        "check_version": CHECK_VERSION if check else None,
        "isolation": ISOLATION,
        "started_at": datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "seconds": round(elapsed, 1),
        "rounds": rounds,
        "returncode": res.get("returncode"),
        "stderr": res.get("stderr"),
        "num_turns": res.get("num_turns"),
        "usage": usage_total,
        "cost_usd_list_price": res.get("cost_usd_list_price"),
        "outside_access": outside,
        "denials": denials,
        "denied_dirs": res.get("denied_dirs"),
        "tool_call_count": len(all_calls),
        "valid": not outside,
    }
    if labels is None:
        meta["error"] = "構造化出力がありません"
        (run_dir / "run.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return run_dir
    (run_dir / "labels.json").write_text(
        json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    schema = json.loads(LABEL_SCHEMA.read_text(encoding="utf-8"))
    meta["label_schema_errors"] = [
        e.message for e in Draft202012Validator(schema).iter_errors(labels)
    ][:20]
    (run_dir / "run.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    evaluate(run_dir)
    shutil.rmtree(work, ignore_errors=True)
    return run_dir


def evaluate(run_dir: Path) -> dict:
    """Assemble the labels of a run, compare with the ground truth, write reports and a view."""
    from kairo_pdf_json.samples import load_sample

    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    calls_path = run_dir / "tool_calls.json"
    if (
        meta.get("backend") == "codex-cli"
        and calls_path.exists()
        and not meta.get("isolation_note")
    ):
        # re-check with the current audit rules (they may have been refined since the run)
        calls = json.loads(calls_path.read_text(encoding="utf-8"))
        meta["outside_access"] = audit_codex(calls, str(WORK_ROOT / run_dir.name))
        meta["valid"] = not meta["outside_access"]
    sample = load_sample(meta["sample"])
    page = meta["page"]
    labels = json.loads((run_dir / "labels.json").read_text(encoding="utf-8"))
    graph = json.loads((run_dir / "input" / "graph.json").read_text(encoding="utf-8"))
    source = {"sample_id": sample.id, "page": page, "pdf_kind": sample.kind}
    doc, set_doc, problems = assemble(labels, graph, source)
    (run_dir / "page.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    page_schema = json.loads(
        (PROJECT_ROOT / "schema" / "page.schema.json").read_text(encoding="utf-8")
    )
    schema_errors = [e.message for e in Draft202012Validator(page_schema).iter_errors(doc)][:20]
    gt_path = PROJECT_ROOT / "ground_truth" / sample.id / f"{page_stem(page)}.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    result = compare(doc, gt, graph)
    result["assemble_problems"] = problems
    result["page_schema_errors"] = schema_errors
    (run_dir / "eval.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    title = f"{meta['model']}：{sample.id} p.{page}（{meta['seconds']} 秒）"
    md = report_md(result, title)
    if problems:
        md += "\n## 組み立てのときの問題\n\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    (run_dir / "eval.md").write_text(md, encoding="utf-8")
    view = build_view(sample, page, doc, set_doc, label=f"run-{run_dir.name}")
    meta["view"] = str(view)
    (run_dir / "run.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return result

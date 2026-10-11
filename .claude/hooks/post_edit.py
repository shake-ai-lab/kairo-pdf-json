"""PostToolUse checks for files edited inside this project.

- *.py: ruff format, then ruff check --fix; remaining problems are reported back (exit 2).
- ground_truth/**/*.json: validated against schema/page.schema.json, or schema/set.schema.json
  for set.json (exit 2 on errors).
Run inside the project environment (`uv run`) so ruff and jsonschema are available.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE_SCHEMA = ROOT / "schema" / "page.schema.json"
SET_SCHEMA = ROOT / "schema" / "set.schema.json"
SKIP_DIRS = {".venv", ".ruff_cache", ".pytest_cache", "__pycache__"}


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def check_python(path: Path) -> None:
    run([sys.executable, "-m", "ruff", "format", str(path)])
    # F401 (unused import) is ignored here: imports are often added before the code that uses them
    result = run(
        [sys.executable, "-m", "ruff", "check", "--fix", "--extend-ignore", "F401", str(path)]
    )
    if result.returncode != 0:
        fail(f"ruff check で問題が見つかりました（{path.name}）:\n{result.stdout}{result.stderr}")


def check_ground_truth(path: Path) -> None:
    schema_path = SET_SCHEMA if path.name == "set.json" else PAGE_SCHEMA
    if not schema_path.exists():
        return
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"正解JSONを読めません（{path.name}）: {exc}")
    errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        lines = [f"- {'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors[:20]]
        fail(f"正解JSONがスキーマに合いません（{path.name}）:\n" + "\n".join(lines))


def main() -> None:
    sys.stderr.reconfigure(encoding="utf-8")
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    raw = (data.get("tool_input") or {}).get("file_path", "")
    if not raw:
        return
    path = Path(raw).resolve()
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return  # outside the project (e.g. scratch files)
    if not path.exists() or SKIP_DIRS.intersection(rel.parts):
        return
    if path.suffix == ".py":
        check_python(path)
    elif path.suffix == ".json" and rel.parts[0] == "ground_truth":
        check_ground_truth(path)


if __name__ == "__main__":
    main()

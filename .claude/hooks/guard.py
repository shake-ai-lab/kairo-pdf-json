"""PreToolUse guard.

Blocks (exit code 2, reason on stderr):
- writing or deleting sample originals under samples/raw/
- `git add` of docs/reference/ or forced adds that bypass .gitignore
- publishing confidential or non-redistributable files with the Artifact tool
Uses only the standard library so it runs on any Python.
"""

import json
import re
import sys

NO_PUBLISH = ("docs/reference", "samples/", "docs/vector-pdf", "ground_truth/", "runs/")


def norm(text: str) -> str:
    return text.replace("\\", "/")


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    sys.stderr.reconfigure(encoding="utf-8")
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = norm(tool_input.get("file_path", ""))
        if "/samples/raw/" in path or path.startswith("samples/raw/"):
            deny(
                "samples/raw/ の原本は変更できません（.claude/rules/samples.md）。"
                "派生物は samples/derived/ に置いてください。"
            )

    elif tool == "Bash":
        command = norm(tool_input.get("command", ""))
        if re.search(r"\bgit\s+add\b", command):
            if "docs/reference" in command:
                deny("docs/reference/ は社外秘のため git に登録できません。")
            if re.search(r"\s(-f|--force)\b", command):
                deny(
                    "git add -f は使えません。.gitignore で除外しているファイル"
                    "（社外秘・再配布できないサンプル）を登録しないためです。"
                )
        if re.search(r"\b(rm|mv|del)\b[^;&|]*samples/raw", command):
            deny("samples/raw/ の原本は削除・移動できません（.claude/rules/samples.md）。")

    elif tool == "Artifact":
        if any(key in tool_input for key in ("file_path", "file_paths", "files")):
            blob = norm(json.dumps(tool_input, ensure_ascii=False))
            hit = next((frag for frag in NO_PUBLISH if frag in blob), None)
            if hit:
                deny(
                    f"{hit} を含むファイルは公開できません"
                    "（社外秘・再配布できない図面を含むため）。"
                    "ローカルの HTML で見せてください。"
                )

    sys.exit(0)


if __name__ == "__main__":
    main()

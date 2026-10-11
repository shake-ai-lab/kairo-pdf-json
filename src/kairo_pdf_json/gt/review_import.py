"""Import a review file saved from the review page (verdicts, notes and pasted images)."""

import base64
import json
import mimetypes
import re
from pathlib import Path

from kairo_pdf_json.samples import load_sample, page_stem

DOWNLOADS = Path.home() / "Downloads"


def latest_review_file(folder: Path = DOWNLOADS) -> Path:
    files = sorted(folder.glob("review_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"{folder} に review_*.json がありません")
    return files[-1]


def _safe(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._+-]", "_", text)


def import_review(path: Path, out_root: Path | None = None) -> Path:
    """Write notes.md and the images to <out_root>/pNNN_<time>/.

    out_root defaults to samples/derived/<id>/review.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind") != "kairo-review":
        raise ValueError(f"{path.name} は確認ページから保存したファイルではありません")
    if out_root is None:
        out_root = load_sample(data["sample_id"]).derived_dir / "review"
    stamp = re.sub(r"[^0-9T]", "", data["saved_at"])[:15]
    out = out_root / f"{page_stem(int(data['page']))}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# {data['sample_id']} p.{data['page']}「{data['title']}」確認結果（{data['saved_at']}）",
        "",
    ]
    for key, item in sorted(data["items"].items()):
        verdict = {"ok": "OK", "ng": "違う"}.get(item.get("verdict") or "", "—")
        note = f"：{item['note']}" if item.get("note") else ""
        lines.append(f"- [{key}] {verdict}{note}")
        for i, image in enumerate(item.get("images", []), 1):
            ext = mimetypes.guess_extension(image.get("type") or "") or ".png"
            name = f"{_safe(key)}_{i}{ext}"
            (out / name).write_bytes(base64.b64decode(image["data"]))
            lines.append(f"  - 画像: {name}")
    (out / "notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out

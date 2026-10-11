"""Sample registry: samples/manifest.yaml and the paths derived from it."""

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from kairo_pdf_json import PROJECT_ROOT

SAMPLES_DIR = PROJECT_ROOT / "samples"
MANIFEST = SAMPLES_DIR / "manifest.yaml"


@dataclass(frozen=True)
class Sample:
    id: str
    title: str
    kind: str
    pages: int

    @property
    def pdf(self) -> Path:
        return SAMPLES_DIR / "raw" / self.id / "original.pdf"

    @property
    def derived_dir(self) -> Path:
        return SAMPLES_DIR / "derived" / self.id


def _entry(sample_id: str) -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    for entry in data["samples"]:
        if entry["id"] == sample_id:
            return entry
    raise KeyError(f"samples/manifest.yaml に {sample_id} がありません")


def load_sample(sample_id: str) -> Sample:
    entry = _entry(sample_id)
    return Sample(entry["id"], entry["title"], entry["kind"], int(entry["pages"]))


def fetch_original(sample_id: str) -> Path:
    """Download the original PDF from the manifest's source_url and check its sha256.
    The PDFs are not in the public repository (they are not ours to redistribute)."""
    entry = _entry(sample_id)
    out = SAMPLES_DIR / "raw" / sample_id / "original.pdf"
    if out.exists():
        if hashlib.sha256(out.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{out} の中身が台帳の sha256 と違います。原本は書き換えません")
        return out
    request = urllib.request.Request(
        entry["source_url"], headers={"User-Agent": "Mozilla/5.0 (kairo-pdf-json)"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(
            f"落とした PDF が台帳の sha256 と違います（{digest}）。"
            "入手先の版が変わった可能性があります"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def page_stem(page: int) -> str:
    return f"p{page:03d}"

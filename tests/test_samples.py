"""The original PDF is fetched from the manifest's source and checked against its sha256."""

import hashlib

import pytest

from kairo_pdf_json import samples


def _setup(tmp_path, monkeypatch, content: bytes, digest: str) -> None:
    src = tmp_path / "source.pdf"
    src.write_bytes(content)
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "samples:\n"
        "  - id: s1\n    title: t\n    kind: vector\n    pages: 1\n"
        f"    source_url: {src.as_uri()}\n    sha256: {digest}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(samples, "SAMPLES_DIR", tmp_path)
    monkeypatch.setattr(samples, "MANIFEST", manifest)


def test_fetch_saves_the_pdf_when_its_hash_matches(tmp_path, monkeypatch):
    content = b"%PDF-1.4 sample"
    _setup(tmp_path, monkeypatch, content, hashlib.sha256(content).hexdigest())
    out = samples.fetch_original("s1")
    assert out == tmp_path / "raw" / "s1" / "original.pdf"
    assert out.read_bytes() == content
    assert samples.fetch_original("s1") == out  # already there: kept as it is


def test_fetch_refuses_a_pdf_whose_hash_differs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, b"%PDF-1.4 other", "0" * 64)
    with pytest.raises(SystemExit):
        samples.fetch_original("s1")
    assert not (tmp_path / "raw" / "s1" / "original.pdf").exists()

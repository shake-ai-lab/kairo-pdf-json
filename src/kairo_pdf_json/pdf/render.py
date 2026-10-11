"""Render PDF pages to images with pypdfium2 (page rotation is applied)."""

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


def render_page(pdf_path: Path, page: int, dpi: int = 300) -> Image.Image:
    """Render a 1-based page number at the given resolution."""
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        bitmap = doc[page - 1].render(scale=dpi / 72)
        return bitmap.to_pil().convert("RGB")
    finally:
        doc.close()

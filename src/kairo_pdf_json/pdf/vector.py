"""Extract words and line geometry from vector PDF pages with pdfminer.six.

Coordinates are converted to the page's top-left origin in pt, after applying /Rotate,
so they line up with images rendered by `render.render_page`.
"""

import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import (
    LAParams,
    LTChar,
    LTComponent,
    LTContainer,
    LTCurve,
    LTLine,
    LTPage,
    LTRect,
    LTTextLine,
)
from pdfminer.pdfpage import PDFPage

Point = tuple[float, float]


@dataclass
class Word:
    text: str
    norm: str
    bbox: list[float]  # x0, y0, x1, y1 (top-left origin, pt)
    size: float
    font: str


@dataclass
class Stroke:
    kind: str  # line | rect | curve
    pts: list[list[float]]
    width: float


@dataclass
class VectorPage:
    page: int
    width: float
    height: float
    rotation: int
    words: list[Word] = field(default_factory=list)
    paths: list[Stroke] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def normalize(text: str) -> str:
    """Full-width alphanumerics to half-width, collapse spaces."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


class _Transform:
    def __init__(self, ltpage: LTPage, rotation: int) -> None:
        self.w, self.h = ltpage.width, ltpage.height
        self.rot = rotation % 360

    @property
    def size(self) -> tuple[float, float]:
        return (self.h, self.w) if self.rot in (90, 270) else (self.w, self.h)

    def point(self, x: float, y: float) -> Point:
        # PDF user space (bottom-left origin) -> displayed page (top-left origin)
        if self.rot == 0:
            return x, self.h - y
        if self.rot == 90:
            return y, x
        if self.rot == 180:
            return self.w - x, y
        return self.h - y, self.w - x  # 270

    def bbox(self, x0: float, y0: float, x1: float, y1: float) -> list[float]:
        (ax, ay), (bx, by) = self.point(x0, y0), self.point(x1, y1)
        return [
            round(min(ax, bx), 2),
            round(min(ay, by), 2),
            round(max(ax, bx), 2),
            round(max(ay, by), 2),
        ]


def _iter(container: LTContainer):
    for obj in container:
        yield obj
        if isinstance(obj, LTContainer) and not isinstance(obj, LTTextLine):
            yield from _iter(obj)


def _words_from_line(line: LTTextLine, tf: _Transform) -> list[Word]:
    words: list[Word] = []
    chars: list[LTChar] = []

    def flush() -> None:
        if not chars:
            return
        text = "".join(c.get_text() for c in chars)
        x0 = min(c.x0 for c in chars)
        y0 = min(c.y0 for c in chars)
        x1 = max(c.x1 for c in chars)
        y1 = max(c.y1 for c in chars)
        words.append(
            Word(
                text,
                normalize(text),
                tf.bbox(x0, y0, x1, y1),
                round(chars[0].size, 2),
                chars[0].fontname,
            )
        )
        chars.clear()

    for obj in line:
        if isinstance(obj, LTChar) and obj.get_text().strip():
            chars.append(obj)
        else:  # LTAnno (inferred space) or a blank char ends the word
            flush()
    flush()
    return words


def _path(obj: LTComponent, kind: str, tf: _Transform) -> Stroke:
    pts = [list(map(lambda v: round(v, 2), tf.point(x, y))) for x, y in obj.pts]  # type: ignore[attr-defined]
    return Stroke(kind, pts, round(float(getattr(obj, "linewidth", 0) or 0), 2))


def extract_vector(pdf_path: Path, page: int) -> VectorPage:
    """Extract words and paths from a 1-based page number."""
    with open(pdf_path, "rb") as fh:
        pdfpage = next(p for i, p in enumerate(PDFPage.get_pages(fh)) if i == page - 1)
        rotation = int(pdfpage.rotate or 0)
    # all_texts: also group characters drawn inside Form XObjects into text lines
    laparams = LAParams(all_texts=True)
    ltpage = next(extract_pages(str(pdf_path), page_numbers=[page - 1], laparams=laparams))
    tf = _Transform(ltpage, rotation)
    width, height = tf.size
    result = VectorPage(page, round(width, 2), round(height, 2), rotation)
    for obj in _iter(ltpage):
        if isinstance(obj, LTTextLine):
            result.words.extend(_words_from_line(obj, tf))
        elif isinstance(obj, LTLine):
            result.paths.append(_path(obj, "line", tf))
        elif isinstance(obj, LTRect):
            result.paths.append(_path(obj, "rect", tf))
        elif isinstance(obj, LTCurve):
            result.paths.append(_path(obj, "curve", tf))
    return result

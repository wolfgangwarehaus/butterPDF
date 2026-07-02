"""Where raster images sit on each page — so dark mode can leave them natural.

The document-background recolor (page_view.recolor) inverts a page's grayscale
content for dark modes. A colour heuristic keeps colourful pixels natural, but a
photo's *neutral* regions (a grey studio backdrop, shadows) still invert and look
patchy. The robust fix is to protect the actual image placements, read from the
PDF itself.

This walks each page's content stream, tracking the CTM (``cm`` / ``q`` / ``Q``),
and records the bounding box of every image XObject drawn with ``Do``. Boxes are
returned in **points, top-left origin** (matching the rendered page), so a caller
scales them to pixels. Per-page + lazy + cached; any parse failure yields no boxes
(the recolor simply falls back to the colour heuristic — never a crash).

Limitation: images nested inside Form XObjects aren't followed yet (rare for
photos); those regions fall back to the heuristic.
"""

from __future__ import annotations


def _mat_mul(m1: tuple, m2: tuple) -> tuple:
    """PDF matrix concat: apply m1 then m2 (row-vector convention)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _apply(m: tuple, x: float, y: float) -> tuple:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


class ImageBoxes:
    """Lazy per-page image-placement boxes for one PDF file."""

    def __init__(self, path: str):
        self._path = path
        self._reader = None
        self._cache: dict[int, list[tuple[float, float, float, float]]] = {}

    def _reader_or_none(self):
        if self._reader is None:
            try:
                from pypdf import PdfReader

                self._reader = PdfReader(self._path)
            except Exception:
                self._reader = False  # sentinel: tried, unavailable
        return self._reader or None

    def boxes_pt(self, page_index: int) -> list[tuple[float, float, float, float]]:
        """Image boxes on ``page_index`` in points, top-left origin
        ``(left, top, right, bottom)``. Empty on any failure."""
        if page_index in self._cache:
            return self._cache[page_index]
        boxes = self._compute(page_index)
        self._cache[page_index] = boxes
        return boxes

    def _compute(self, page_index: int) -> list[tuple[float, float, float, float]]:
        reader = self._reader_or_none()
        if reader is None:
            return []
        try:
            from pypdf.generic import ContentStream

            page = reader.pages[page_index]
            mediabox = page.mediabox
            llx = float(mediabox.left)
            ury = float(mediabox.top)
            xobjects = page.get("/Resources", {}).get("/XObject", {})
            content = page.get_contents()
            if content is None:
                return []
            ops = ContentStream(content, reader).operations

            boxes: list[tuple[float, float, float, float]] = []
            ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            stack: list[tuple] = []
            for operands, op in ops:
                if op == b"q":
                    stack.append(ctm)
                elif op == b"Q":
                    ctm = stack.pop() if stack else ctm
                elif op == b"cm":
                    ctm = _mat_mul(tuple(float(v) for v in operands), ctm)
                elif op == b"Do" and operands:
                    xo = xobjects.get(operands[0])
                    obj = xo.get_object() if xo is not None else None
                    if obj is not None and obj.get("/Subtype") == "/Image":
                        pts = [_apply(ctm, x, y) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        # user space (bottom-left origin) → points from top-left
                        boxes.append(
                            (
                                min(xs) - llx,
                                ury - max(ys),
                                max(xs) - llx,
                                ury - min(ys),
                            )
                        )
            return boxes
        except Exception:
            return []

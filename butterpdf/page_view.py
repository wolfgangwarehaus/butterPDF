"""RenderedPdfView — butterPDF's own continuous-scroll PDF view.

Qt's ``QPdfView`` renders fast but hides where each page sits in the viewport, so
it can't anchor editable widgets at exact PDF coordinates. butterPDF's whole point
is fill + sign, which need that. So we render pages ourselves — ``QPdfDocument.render``
into a pixmap per page, laid out in a scroll area — giving pixel-exact page geometry
that overlay widgets (form fields, signature stamps) can be positioned against.

Each page is a :class:`PageWidget`; a field rect in PDF points maps to page pixels
via :meth:`PageWidget.pt_to_px` (PDF's bottom-left origin flipped to Qt's top-left).
Overlay widgets are added as children of the page widget, so they scroll and scale
with it for free.

The view keeps the frosted look: transparent background (the window frost shows
through the gutters), an 8px left gutter mirroring the right scrollbar lane, 10px
inter-page spacing, and the slim auto-fade accent scrollbars.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

# Default page paper. QPdfDocument.render draws only page *content* (transparent
# elsewhere), so without this the window frost shows through the page — which looks
# striking (a mode: Transparent) but isn't the paper a PDF reader should default to.
_PAPER = QColor(Qt.GlobalColor.white)

# points → device-independent pixels at zoom 1.0 (100%). PDF points are 1/72", a
# logical pixel is 1/96", so 100% is 96/72 px per point — matches QPdfView's 1.0.
_PX_PER_PT = 96.0 / 72.0
_GUTTER = 8      # left frosted gutter, mirrors the right scrollbar lane

# Above this chroma (0..1 channel spread) a pixel is treated as fully colourful and
# its lightness is left untouched; the weight ramps SMOOTHLY to 1 at neutral, so
# there's no hard threshold to jag anti-aliased edges.
_SAT_TAPER = 0.30


def recolor(
    image: QImage,
    *,
    invert: bool,
    floor: int,
    ceil: int,
    protect_boxes: list | None = None,
) -> QImage:
    """Re-level a rendered page for a document-background mode, keeping colours and
    images natural. Works in *lightness*: a pixel's lightness L is (optionally)
    inverted then mapped into ``[floor, ceil]`` (so under invert white paper → dark,
    black text → light), while hue + saturation are preserved. How much of that
    lightness change applies is weighted SMOOTHLY by how neutral the pixel is —
    saturated colours (tabs, logos) keep their exact lightness, neutral text/paper
    fully invert, and anti-aliased edges ramp between the two (no jagged threshold).
    Anything inside ``protect_boxes`` (image placements in this image's pixel space)
    is left exactly as rendered, so photos stay natural whole."""
    img = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    src = np.frombuffer(memoryview(img.constBits()), np.uint8, count=bpl * h)
    px = src.reshape(h, bpl)[:, : w * 4].reshape(h, w, 4)
    rgb = px[..., :3].astype(np.float32) / 255.0

    mx = rgb.max(2)
    mn = rgb.min(2)
    lum = (mx + mn) / 2.0
    chroma = mx - mn
    # Smooth neutral weight: 1 for neutral pixels, tapering (smoothstep) to 0 as
    # chroma passes _SAT_TAPER — no hard edge, so anti-aliasing stays clean.
    t = np.clip(1.0 - chroma / _SAT_TAPER, 0.0, 1.0)
    neutral_w = t * t * (3.0 - 2.0 * t)
    # A colour that met white paper leaves LIGHT anti-aliased edge pixels; against
    # the inverted (dark) paper those read as a light fringe. So a saturated pixel
    # is only fully preserved when it's mid-lightness (a real fill body) — light
    # ones still darken toward the paper. (Dark modes only; no fringe without invert.)
    light_push = np.clip((lum - 0.6) / 0.4, 0.0, 1.0) if invert else 0.0
    weight = 1.0 - (1.0 - neutral_w) * (1.0 - light_push)

    inv = (1.0 - lum) if invert else lum
    target = (floor / 255.0) + inv * ((ceil - floor) / 255.0)
    new_lum = lum + (target - lum) * weight

    # Reconstruct RGB at the new lightness, keeping hue + saturation: scale each
    # channel's deviation from L by the HSL chroma-span ratio for the new L.
    old_span = 1.0 - np.abs(2.0 * lum - 1.0)
    new_span = 1.0 - np.abs(2.0 * new_lum - 1.0)
    ratio = np.divide(new_span, old_span, out=np.zeros_like(old_span), where=old_span > 1e-4)
    out = new_lum[..., None] + (rgb - lum[..., None]) * ratio[..., None]
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)

    for x0, y0, x1, y1 in protect_boxes or ():
        xa, ya = max(0, int(x0)), max(0, int(y0))
        xb, yb = min(w, int(round(x1))), min(h, int(round(y1)))
        if xb > xa and yb > ya:
            out[ya:yb, xa:xb] = px[ya:yb, xa:xb, :3]  # image region → exact render

    result = np.dstack([out, px[..., 3]])  # keep alpha
    return QImage(result.tobytes(), w, h, QImage.Format.Format_RGBA8888).copy()
_PAGE_SPACING = 10
_ZOOM_MIN = 0.1
_ZOOM_MAX = 8.0


class PageWidget(QWidget):
    """One rendered page. Sized to the page at the current scale; renders its
    pixmap lazily (on first paint per scale) and caches it. Overlay widgets are
    children positioned via :meth:`pt_to_px`."""

    def __init__(self, doc: QPdfDocument, index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._doc = doc
        self._index = index
        self._scale = _PX_PER_PT  # px per point
        self._pixmap: QPixmap | None = None
        self._pt_size = doc.pagePointSize(index)  # QSizeF, PDF points
        self._paper: QColor | None = _PAPER
        self._recolor: tuple[bool, int, int] | None = None  # (invert, floor, ceil)
        self._boxes_provider = None  # callable(index) -> [image boxes in points]
        self._fields: list[tuple] = []  # (widget, rect_pt) overlays anchored to the page
        # Opaque only when the paper fully covers the widget (an opaque fill) — a
        # translucent/None paper must let the frost show through.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._apply_size()

    # ── field overlays ──────────────────────────────────────────────────────
    def add_field(self, widget: QWidget, rect_pt: tuple) -> None:
        """Anchor an editable ``widget`` over a PDF rect (points, bottom-left
        origin). It becomes a child, so it scrolls + re-places with the page."""
        widget.setParent(self)
        self._fields.append((widget, rect_pt))
        self._place_field(widget, rect_pt)
        widget.show()

    def _place_field(self, widget: QWidget, rect_pt: tuple) -> None:
        x0, y0, x1, y1 = rect_pt
        left, top = self.pt_to_px(x0, y1)      # y1 = the rect's upper edge
        right, bottom = self.pt_to_px(x1, y0)
        widget.setGeometry(
            round(left), round(top),
            max(1, round(right - left)), max(1, round(bottom - top)),
        )

    def set_display(self, paper: QColor | None, recolor_args: tuple | None) -> None:
        """Set the paper behind the content + how to recolor the page.
        ``recolor_args`` is ``(invert, floor, ceil)`` for :func:`recolor`, or
        ``None`` for a straight (identity) render. Re-renders only when the recolor
        actually changes."""
        if recolor_args != self._recolor:
            self._recolor = recolor_args
            self._pixmap = None  # re-render with the new recolor
        self._paper = paper
        opaque = paper is not None and paper.alpha() == 255
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, opaque)
        self.update()

    # ── geometry ──────────────────────────────────────────────────────────
    @property
    def index(self) -> int:
        return self._index

    def set_scale(self, px_per_pt: float) -> None:
        if px_per_pt == self._scale:
            return
        self._scale = px_per_pt
        self._pixmap = None  # re-render at the new scale on next paint
        self._apply_size()

    def _apply_size(self) -> None:
        w = max(1, round(self._pt_size.width() * self._scale))
        h = max(1, round(self._pt_size.height() * self._scale))
        self.setFixedSize(w, h)
        for widget, rect_pt in getattr(self, "_fields", ()):  # re-place on zoom
            self._place_field(widget, rect_pt)

    def pt_to_px(self, x_pt: float, y_pt: float) -> tuple[float, float]:
        """Map a PDF point (origin bottom-left) to a page pixel (origin top-left)
        at the current scale — for positioning overlay widgets."""
        return x_pt * self._scale, (self._pt_size.height() - y_pt) * self._scale

    # ── render ────────────────────────────────────────────────────────────
    def _render(self) -> None:
        dpr = self.devicePixelRatioF()
        w = max(1, round(self.width() * dpr))
        h = max(1, round(self.height() * dpr))
        img = self._doc.render(self._index, QSize(w, h))
        if self._recolor is not None:
            invert, floor, ceil = self._recolor
            boxes = None
            if self._boxes_provider is not None:
                s = self._scale * dpr  # points → this image's pixels
                boxes = [
                    (x0 * s, y0 * s, x1 * s, y1 * s)
                    for (x0, y0, x1, y1) in self._boxes_provider(self._index)
                ]
            img = recolor(img, invert=invert, floor=floor, ceil=ceil, protect_boxes=boxes)
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self._pixmap = pm

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._pixmap is None:
            self._render()
        painter = QPainter(self)
        if self._paper is not None:
            painter.fillRect(self.rect(), self._paper)  # paper behind the content
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()


class RenderedPdfView(QScrollArea):
    """Continuous vertical scroll of rendered pages. Mirrors the slice of
    ``QPdfView`` the viewer used (fit-width / zoom / page nav) but exposes page
    geometry for overlays."""

    current_page_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._doc: QPdfDocument | None = None
        self._pages: list[PageWidget] = []
        self._zoom = 1.0
        self._fit = True
        self._current = 0
        self._paper: QColor | None = _PAPER
        self._recolor: tuple | None = None
        self._boxes_provider = None

        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        self._canvas = QWidget()
        self._vbox = QVBoxLayout(self._canvas)
        self._vbox.setContentsMargins(_GUTTER, 0, _GUTTER, 0)
        self._vbox.setSpacing(_PAGE_SPACING)
        self._vbox.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(self._canvas)

        self._frost()
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    # ── public API (the slice PdfViewer uses) ─────────────────────────────
    def set_document(self, doc: QPdfDocument) -> None:
        self._doc = doc
        self._rebuild()

    def set_image_boxes(self, provider) -> None:
        """Set a ``callable(page_index) -> [(x0,y0,x1,y1) in points]`` giving image
        placements so dark modes leave photos natural. Takes effect on next render."""
        self._boxes_provider = provider
        for page in self._pages:
            page._boxes_provider = provider
            page._pixmap = None
            page.update()

    def rebuild(self) -> None:
        """Rebuild pages from the current document (call after it turns Ready)."""
        self._rebuild()

    def page_count(self) -> int:
        return self._doc.pageCount() if self._doc else 0

    def current_page(self) -> int:
        return self._current

    def page_widget(self, index: int) -> PageWidget | None:
        return self._pages[index] if 0 <= index < len(self._pages) else None

    def jump_to_page(self, index: int) -> None:
        index = max(0, min(len(self._pages) - 1, index))
        if not self._pages:
            return
        y = self._pages[index].pos().y()
        self.verticalScrollBar().setValue(max(0, y - _PAGE_SPACING))

    def set_display(self, paper: QColor | None, recolor_args: tuple | None) -> None:
        """Set the paper + recolor for every page (the viewer resolves these from
        the app theme + the 'Document background' setting). ``recolor_args`` is
        ``(invert, floor, ceil)`` or ``None`` for a straight render."""
        self._paper = paper
        self._recolor = recolor_args
        for page in self._pages:
            page.set_display(paper, recolor_args)

    def is_fit(self) -> bool:
        return self._fit

    def zoom_factor(self) -> float:
        return self._zoom

    def set_fit_width(self) -> None:
        self._fit = True
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._relayout()

    def zoom_by(self, factor: float) -> None:
        base = self._fit_zoom() if self._fit else self._zoom
        self._fit = False
        self._zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, base * factor))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._relayout()

    # ── internals ─────────────────────────────────────────────────────────
    def _rebuild(self) -> None:
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._pages = []
        self._current = 0
        if not self._doc or self._doc.pageCount() <= 0:
            return
        for i in range(self._doc.pageCount()):
            page = PageWidget(self._doc, i, self._canvas)
            page._boxes_provider = self._boxes_provider
            page.set_display(self._paper, self._recolor)
            self._vbox.addWidget(page, 0, Qt.AlignmentFlag.AlignHCenter)
            self._pages.append(page)
        self._relayout()

    def _fit_zoom(self) -> float:
        """The zoom that fits the widest page to the viewport width (minus gutters)."""
        if not self._pages:
            return 1.0
        avail = self.viewport().width() - 2 * _GUTTER
        widest_pt = max(p._pt_size.width() for p in self._pages)
        if widest_pt <= 0:
            return 1.0
        return max(_ZOOM_MIN, min(_ZOOM_MAX, avail / (widest_pt * _PX_PER_PT)))

    def _relayout(self) -> None:
        if not self._pages:
            return
        zoom = self._fit_zoom() if self._fit else self._zoom
        for page in self._pages:
            page.set_scale(zoom * _PX_PER_PT)
        self._canvas.adjustSize()

    def _on_scroll(self, _value: int) -> None:
        if not self._pages:
            return
        mid = self.verticalScrollBar().value() + self.viewport().height() // 2
        cur = 0
        for i, page in enumerate(self._pages):
            if page.pos().y() <= mid:
                cur = i
            else:
                break
        if cur != self._current:
            self._current = cur
            self.current_page_changed.emit(cur)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self._fit:
            self._relayout()

    def _frost(self) -> None:
        """Transparent view + viewport + canvas so the window frost shows through
        the gutters and inter-page gaps — uniform frosted glass, a dough hallmark."""
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }")
        self.viewport().setAutoFillBackground(False)
        self._canvas.setAutoFillBackground(False)
        self._canvas.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

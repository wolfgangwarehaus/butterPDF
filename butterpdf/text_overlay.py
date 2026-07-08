"""TextStampOverlay — an in-place text box you type into, right on the page.

Born focused and empty at the click point ("Insert text here…"): type, click
away, and it reads as text sitting on the page. Click-away also makes the body
draggable (grab anywhere); double-click re-enters editing; ✕ deletes; an empty
box quietly removes itself when it loses focus. It speaks the same overlay
protocol as :class:`~butterpdf.sign_overlay.SignatureOverlay` (``reposition()``
on zoom, ``rect_pt`` + ``image`` at save), so the save step composites typed
text exactly like a signature — which is what makes NON-interactive
(scan-style) forms fillable.

Geometry: the box keeps a fixed form-line height in PDF points and grows with
the text; the font tracks the page zoom so the type is WYSIWYG-ish against the
composited render (same family as :func:`butterpdf.signature.render_typed`).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QColor, QFontDatabase, QImage, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

_HEIGHT_PT = 14.0  # one form line, PDF points
_PAD = 3  # px rim: frame + drag grip
_CHIP = 16  # ✕ delete chip, px
_MIN_W = 60  # px floor so an empty box is clickable


def _stamp_font_family() -> str:
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


class TextStampOverlay(QWidget):
    """The in-place text box. ``(x_pt, y_pt)`` is the click point — it becomes
    the box's bottom-left anchor, in page points."""

    def __init__(self, page, x_pt: float, y_pt: float, text: str = "") -> None:
        super().__init__(page)
        self._page = page
        self._x0_pt = x_pt
        self._y0_pt = y_pt
        self._drag = None
        self._dragged = False
        self._edit = QLineEdit(text, self)
        self._edit.setFrame(False)
        f = self._edit.font()
        f.setFamily(_stamp_font_family())
        self._edit.setFont(f)
        self._edit.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.85);color:#111;"
            "border:none;padding:0 2px;}"
        )
        self._edit.textChanged.connect(self.reposition)
        self._edit.returnPressed.connect(self._edit.clearFocus)
        self._edit.installEventFilter(self)
        self.setMouseTracking(True)

    # ── the overlay protocol (matches SignatureOverlay) ─────────────────────
    @property
    def rect_pt(self) -> tuple:
        """The composite rect: anchored at the box, sized to the RENDER's
        aspect at the fixed line height — so the baked text isn't stretched
        to the editing box's chrome (rim + chip)."""
        img = self.image
        aspect = img.width() / img.height() if not img.isNull() and img.height() else 1.0
        w_pt = _HEIGHT_PT * aspect
        return (self._x0_pt, self._y0_pt, self._x0_pt + w_pt, self._y0_pt + _HEIGHT_PT)

    @property
    def image(self) -> QImage:
        """The text rendered for compositing — null when there's nothing to
        bake (the save step skips null images)."""
        text = self._edit.text().strip()
        if not text:
            return QImage()
        from PySide6.QtGui import QColor as _C

        from butterpdf.signature import render_typed

        return render_typed(text, font_family=_stamp_font_family(), color=_C(17, 17, 17))

    def reposition(self) -> None:
        """Pixel geometry from the point anchor at the page's current scale;
        the font and width track the zoom and the text."""
        left, top = self._page.pt_to_px(self._x0_pt, self._y0_pt + _HEIGHT_PT)
        _, bottom = self._page.pt_to_px(self._x0_pt, self._y0_pt)
        line_px = max(8, round(bottom - top))
        f = self._edit.font()
        f.setPixelSize(max(6, round(line_px * 0.72)))
        self._edit.setFont(f)
        fm = self._edit.fontMetrics()
        text_w = fm.horizontalAdvance(self._edit.text() or " ") + 10
        w = max(_MIN_W, text_w) + 2 * _PAD + _CHIP + 2
        self.setGeometry(round(left), round(top) - _PAD, w, line_px + 2 * _PAD)
        self._edit.setGeometry(_PAD, _PAD, w - 2 * _PAD - _CHIP - 2, line_px)

    # ── editing lifecycle ────────────────────────────────────────────────────
    def start_editing(self) -> None:
        self._edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._edit.setFocus()

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 (Qt override)
        if obj is self._edit and ev.type() == QEvent.Type.FocusOut:
            if not self._edit.text().strip():
                self._remove()  # an abandoned empty box cleans itself up
                return False
            # parked: the body becomes a drag target until double-clicked
            self._edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.update()
        return False

    def _remove(self) -> None:
        self._page.remove_overlay(self)
        self.setParent(None)
        self.deleteLater()

    # ── paint (frame + delete chip, mirroring SignatureOverlay) ─────────────
    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        chip = self._close_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(chip)
        p.setPen(QPen(QColor(255, 255, 255), 1.4))
        p.drawLine(chip.left() + 4, chip.top() + 4, chip.right() - 4, chip.bottom() - 4)
        p.drawLine(chip.right() - 4, chip.top() + 4, chip.left() + 4, chip.bottom() - 4)
        p.end()

    def _close_rect(self) -> QRect:
        return QRect(self.width() - _CHIP - 1, (self.height() - _CHIP) // 2, _CHIP, _CHIP)

    # ── drag / re-edit (body clicks land here while the edit is parked):
    # a CLICK (press+release, no movement) re-enters editing; a DRAG moves ─────
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._close_rect().contains(e.position().toPoint()):
            self._remove()
            return
        self._drag = e.globalPosition().toPoint() - self.pos()
        self._dragged = False

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag is None:
            return
        target = e.globalPosition().toPoint() - self._drag
        if not self._dragged and (target - self.pos()).manhattanLength() < 4:
            return  # jitter within the click threshold — still a click
        self._dragged = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        target.setX(max(0, min(self._page.width() - self.width(), target.x())))
        target.setY(max(0, min(self._page.height() - self.height(), target.y())))
        self.move(target)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._drag is not None and self._dragged:
            # re-anchor: pixel top-left back to the point anchor
            x_pt, top_pt = self._page.px_to_pt(self.x(), self.y() + _PAD)
            self._x0_pt, self._y0_pt = x_pt, top_pt - _HEIGHT_PT
        elif self._drag is not None:
            self.start_editing()  # a plain click: back into the text
        self._drag = None
        self._dragged = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

"""SignatureOverlay — a placed signature the user can drag, resize, and delete.

A child of the page it sits on; it keeps its position/size in **PDF points**
(``rect_pt``) so it re-places correctly when the page zooms and the save step can
composite it at the right spot. Drag the body to move, drag the bottom-right
handle to resize (aspect-locked), click the ✕ to remove.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

_HANDLE = 14  # bottom-right resize grip, px
_MIN = 24


class SignatureOverlay(QWidget):
    """A movable/resizable signature image on a page."""

    def __init__(self, page, image: QImage, rect_pt: tuple) -> None:
        super().__init__(page)
        self._page = page
        self._image = image
        self._pixmap = QPixmap.fromImage(image)
        self._aspect = image.height() / image.width() if image.width() else 1.0
        self._rect_pt = rect_pt  # (x0,y0,x1,y1) points, bottom-left origin
        self._drag: QPoint | None = None
        self._resizing = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    @property
    def rect_pt(self) -> tuple:
        return self._rect_pt

    @property
    def image(self) -> QImage:
        return self._image

    # ── geometry ──────────────────────────────────────────────────────────
    def reposition(self) -> None:
        """Set pixel geometry from the point-rect at the page's current scale."""
        x0, y0, x1, y1 = self._rect_pt
        left, top = self._page.pt_to_px(x0, y1)   # y1 = upper edge
        right, bottom = self._page.pt_to_px(x1, y0)
        self.setGeometry(round(left), round(top),
                         max(_MIN, round(right - left)), max(_MIN, round(bottom - top)))

    def _sync_rect_pt(self) -> None:
        """Recompute the point-rect from current pixel geometry (after a move/resize)."""
        g = self.geometry()
        x0, y1 = self._page.px_to_pt(g.left(), g.top())
        x1, y0 = self._page.px_to_pt(g.right(), g.bottom())
        self._rect_pt = (x0, y0, x1, y1)

    # ── paint ─────────────────────────────────────────────────────────────
    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self.rect(), self._pixmap)
        # selection frame + resize handle + delete affordance
        p.setPen(QPen(QColor(0, 0, 0, 60), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        from butterpdf import ui_helpers

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ui_helpers.ACCENT))
        p.drawRect(self._handle_rect())
        # ✕ delete chip, top-right
        chip = self._close_rect()
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(chip)
        p.setPen(QPen(QColor(255, 255, 255), 1.4))
        p.drawLine(chip.left() + 4, chip.top() + 4, chip.right() - 4, chip.bottom() - 4)
        p.drawLine(chip.right() - 4, chip.top() + 4, chip.left() + 4, chip.bottom() - 4)
        p.end()

    def _handle_rect(self) -> QRect:
        return QRect(self.width() - _HANDLE, self.height() - _HANDLE, _HANDLE, _HANDLE)

    def _close_rect(self) -> QRect:
        return QRect(self.width() - 18, 2, 16, 16)

    # ── interaction ───────────────────────────────────────────────────────
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        if self._close_rect().contains(pos):
            self._page.remove_overlay(self)
            self.setParent(None)
            self.deleteLater()
            return
        if self._handle_rect().contains(pos):
            self._resizing = True
        else:
            self._drag = e.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        pos = e.position().toPoint()
        if self._resizing:
            new_w = max(_MIN, pos.x())
            self.resize(new_w, max(_MIN, round(new_w * self._aspect)))  # aspect-locked
            self.update()
            return
        if self._drag is not None:
            target = e.globalPosition().toPoint() - self._drag
            # keep it inside the page
            target.setX(max(0, min(self._page.width() - self.width(), target.x())))
            target.setY(max(0, min(self._page.height() - self.height(), target.y())))
            self.move(target)
            return
        # hover cursor feedback
        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor if self._handle_rect().contains(pos)
            else Qt.CursorShape.OpenHandCursor
        )

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._resizing or self._drag is not None:
            self._sync_rect_pt()
        self._resizing = False
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

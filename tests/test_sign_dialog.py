"""InkCanvas — the signature draw surface. The ink-quality contract from the
walkthrough refinement: float samples, one smoothed path per stroke, a
DPR-sized backing image, and a bare tap still leaves a dot."""

from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from butterpdf.sign_dialog import InkCanvas, _smooth_stroke_path


def _ev(t, x, y):
    return QMouseEvent(
        t, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


@pytest.fixture
def canvas(qapp):
    c = InkCanvas()
    c.resize(520, 180)
    c.show()
    yield c
    c.deleteLater()


def test_smooth_path_is_curved_not_polygonal():
    """≥3 samples produce quadratic segments (curveTo elements), not a chain
    of straight lines — the 'skippy' fix."""
    pts = [QPointF(x, 50 + 20 * math.sin(x / 30)) for x in range(0, 200, 20)]
    path = _smooth_stroke_path(pts)
    kinds = {path.elementAt(i).type for i in range(path.elementCount())}
    from PySide6.QtGui import QPainterPath

    assert QPainterPath.ElementType.CurveToElement in kinds


def test_two_points_degrade_to_a_line():
    path = _smooth_stroke_path([QPointF(0, 0), QPointF(10, 10)])
    assert path.elementCount() == 2  # move + line


def test_stroke_bakes_and_trims(canvas):
    canvas.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, 30, 90))
    for i in range(40):
        canvas.mouseMoveEvent(_ev(QEvent.Type.MouseMove, 30 + i * 8, 90 + 25 * math.sin(i / 5)))
    canvas.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, 342, 90))
    img = canvas.image()
    assert img is not None and not img.isNull()
    assert img.width() > 100  # trimmed to the ink, not the whole canvas


def test_tap_leaves_a_dot(canvas):
    """An i-dot / t-cross is a press+release with no move — it must still ink."""
    canvas.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, 100, 100))
    canvas.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, 100, 100))
    assert canvas.image() is not None


def test_backing_image_carries_the_device_pixel_ratio(canvas):
    assert canvas._img.devicePixelRatio() == pytest.approx(canvas.devicePixelRatioF())
    assert canvas._img.width() == round(520 * canvas.devicePixelRatioF())


def test_empty_canvas_yields_no_image(canvas):
    assert canvas.image() is None

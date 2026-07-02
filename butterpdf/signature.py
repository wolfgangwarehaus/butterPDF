"""Signatures — create, store, and reuse.

butterPDF's headline: sign a document in seconds. A signature is a transparent
PNG (ink on nothing) made three ways — **drawn** on an ink canvas, **typed** in a
script face, or **imported** from an image — and saved so the next document is a
two-click sign. This module owns the model (create + persist + list); placing one
on a page and baking it into the saved PDF live in the viewer / save engine.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QRect, QStandardPaths, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen


def _as_array(image: QImage):
    """(ARGB32 QImage, H×W×4 uint8 view in B,G,R,A order). The view aliases the
    image buffer — keep the returned QImage alive while you use the array."""
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(memoryview(img.constBits()), np.uint8, count=bpl * h)
    arr = buf.reshape(h, bpl)[:, : w * 4].reshape(h, w, 4)
    return img, arr


def signatures_dir() -> Path:
    """Where saved signatures live — the app data dir's ``signatures/`` folder."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    d = Path(base or Path.home() / ".local" / "share") / "signatures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_signatures() -> list[Path]:
    """Saved signature PNGs, most-recent first."""
    files = sorted(signatures_dir().glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def save_signature(image: QImage, *, slug: str, timestamp: int) -> Path:
    """Persist ``image`` as a reusable signature. ``slug`` names it; ``timestamp``
    (caller-supplied — this module can't call the clock) disambiguates."""
    trimmed = trim(image)
    path = signatures_dir() / f"{slug}-{timestamp}.png"
    trimmed.save(str(path), "PNG")
    return path


def trim(image: QImage, *, pad: int = 6) -> QImage:
    """Crop transparent margins so a placed signature is tight to the ink (with a
    little padding). Returns the original if it's fully transparent/empty."""
    img, arr = _as_array(image)
    w, h = img.width(), img.height()
    ys, xs = np.where(arr[..., 3] > 8)  # index 3 = alpha (B,G,R,A)
    if xs.size == 0:
        return image
    rect = QRect(int(xs.min()), int(ys.min()),
                 int(xs.max() - xs.min()) + 1, int(ys.max() - ys.min()) + 1)
    rect = rect.adjusted(-pad, -pad, pad, pad).intersected(QRect(0, 0, w, h))
    return img.copy(rect)


def render_typed(text: str, *, font_family: str, color: QColor | None = None) -> QImage:
    """Render ``text`` in ``font_family`` (a script face reads as a signature) to a
    transparent image, sized to the glyphs."""
    from PySide6.QtGui import QFont, QFontMetrics

    color = color or QColor(20, 24, 40)
    font = QFont(font_family)
    font.setPixelSize(96)
    metrics = QFontMetrics(font)
    rect = metrics.boundingRect(text)
    w = max(1, rect.width() + 40)
    h = max(1, rect.height() + 40)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(font)
    p.setPen(QPen(color))
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return trim(img)


def to_rgb_alpha(image: QImage) -> tuple[bytes, bytes, int, int]:
    """Split a signature into ``(rgb_bytes, alpha_bytes, width, height)`` for a
    PDF image XObject + soft-mask (so the transparent background composites onto
    the page instead of a white box)."""
    img = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(memoryview(img.constBits()), np.uint8, count=bpl * h)
    arr = buf.reshape(h, bpl)[:, : w * 4].reshape(h, w, 4)  # R,G,B,A
    rgb = np.ascontiguousarray(arr[..., :3]).tobytes()
    alpha = np.ascontiguousarray(arr[..., 3]).tobytes()
    return rgb, alpha, w, h


def load_image(path: str) -> QImage | None:
    """Load an imported signature image (whitening handled by the caller if the
    scan has a white background). Returns None if it can't be read."""
    img = QImage()
    if img.load(path):
        return img.convertToFormat(QImage.Format.Format_ARGB32)
    return None


def whiten_to_transparent(image: QImage, *, threshold: int = 235) -> QImage:
    """Make near-white pixels transparent — turns a scanned-on-paper signature
    into ink-on-nothing so it composites cleanly onto a page."""
    img, arr = _as_array(image)
    out = arr.copy()  # arr aliases the source buffer; write to a copy
    b, g, r = out[..., 0], out[..., 1], out[..., 2]
    near_white = (r >= threshold) & (g >= threshold) & (b >= threshold)
    out[near_white, 3] = 0  # drop alpha where near-white
    result = QImage(out.tobytes(), img.width(), img.height(), QImage.Format.Format_ARGB32).copy()
    return trim(result)

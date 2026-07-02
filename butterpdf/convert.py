"""Light converters — PDF ⇄ images.

PDF → PNG/JPEG renders each page with QtPdf/PDFium (the same engine the viewer
uses) at a chosen DPI. Images → PDF embeds each picture losslessly with img2pdf
(one page per image). Deliberately light — no editing, just the everyday
"I need this as an image" / "make a PDF from these scans".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtPdf import QPdfDocument


def export_pdf_images(
    doc: QPdfDocument, out_dir: str, stem: str, *, fmt: str = "png", dpi: int = 150
) -> list[Path]:
    """Render every page of ``doc`` to ``out_dir/{stem}-NNN.{fmt}`` at ``dpi``.
    Returns the written paths. ``fmt`` is ``"png"`` or ``"jpeg"``."""
    fmt = fmt.lower()
    ext = "jpg" if fmt in ("jpg", "jpeg") else "png"
    qt_fmt = "JPEG" if ext == "jpg" else "PNG"
    scale = dpi / 72.0
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    count = doc.pageCount()
    width = max(3, len(str(count)))
    for i in range(count):
        size = doc.pagePointSize(i)
        px = QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)))
        image = doc.render(i, px)
        if ext == "jpg":  # JPEG has no alpha — flatten onto white paper
            image = _flatten_white(image)
        path = out / f"{stem}-{i + 1:0{width}d}.{ext}"
        image.save(str(path), qt_fmt, 92 if ext == "jpg" else -1)
        written.append(path)
    return written


def images_to_pdf(image_paths: list[str], dest_path: str) -> None:
    """Combine images into a PDF (one page each), embedded losslessly. Raises on
    failure. Alpha PNGs are flattened onto white (img2pdf rejects transparency)."""
    import img2pdf

    prepared = _prepare_for_img2pdf(image_paths)
    with open(dest_path, "wb") as f:
        f.write(img2pdf.convert(prepared))


# ── internals ─────────────────────────────────────────────────────────


def _flatten_white(image):
    from PySide6.QtGui import QColor, QImage, QPainter

    flat = QImage(image.size(), QImage.Format.Format_RGB888)
    flat.fill(QColor(255, 255, 255))
    p = QPainter(flat)
    p.drawImage(0, 0, image)
    p.end()
    return flat


def _prepare_for_img2pdf(image_paths: list[str]) -> list:
    """img2pdf refuses images with an alpha channel; flatten those onto white and
    hand it the bytes. Non-alpha files are passed through by path (lossless)."""
    import io

    from PySide6.QtGui import QImage

    out: list = []
    for path in image_paths:
        img = QImage(path)
        if not img.isNull() and img.hasAlphaChannel():
            buf = io.BytesIO()
            flat = _flatten_white(img)
            # QImage can't save to BytesIO directly; go via a QBuffer.
            from PySide6.QtCore import QBuffer

            qbuf = QBuffer()
            qbuf.open(QBuffer.OpenModeFlag.ReadWrite)
            flat.save(qbuf, "PNG")
            buf.write(bytes(qbuf.data()))
            out.append(buf.getvalue())
        else:
            out.append(path)
    return out

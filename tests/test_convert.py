"""Tests for the light converters (butterpdf.convert)."""

from __future__ import annotations

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("img2pdf")

from butterpdf import convert  # noqa: E402


def _blank_pdf(path) -> str:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=300)
    w.add_blank_page(width=200, height=300)
    out = path / "two.pdf"
    with open(out, "wb") as f:
        w.write(f)
    return str(out)


def test_export_pages_as_images(qapp, tmp_path):
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    doc.load(_blank_pdf(tmp_path))
    qapp.processEvents()

    for fmt, ext in (("png", "png"), ("jpeg", "jpg")):
        written = convert.export_pdf_images(doc, str(tmp_path / fmt), "pg", fmt=fmt, dpi=96)
        assert len(written) == 2  # two pages
        assert all(p.suffix == f".{ext}" and p.stat().st_size > 0 for p in written)


def test_images_to_pdf(qapp, tmp_path):
    from pypdf import PdfReader
    from PySide6.QtGui import QColor, QImage

    imgs = []
    for i, c in enumerate((QColor("white"), QColor("#eee"))):
        im = QImage(80, 60, QImage.Format.Format_RGB888)
        im.fill(c)
        p = tmp_path / f"img{i}.png"
        im.save(str(p), "PNG")
        imgs.append(str(p))

    out = tmp_path / "out.pdf"
    convert.images_to_pdf(imgs, str(out))
    assert len(PdfReader(str(out)).pages) == 2


def test_images_to_pdf_flattens_alpha(qapp, tmp_path):
    """img2pdf rejects transparency — an alpha PNG must be flattened, not error."""
    from pypdf import PdfReader
    from PySide6.QtGui import QColor, QImage

    im = QImage(40, 40, QImage.Format.Format_RGBA8888)
    im.fill(QColor(0, 0, 0, 0))  # fully transparent
    p = tmp_path / "alpha.png"
    im.save(str(p), "PNG")

    out = tmp_path / "flat.pdf"
    convert.images_to_pdf([str(p)], str(out))  # must not raise
    assert len(PdfReader(str(out)).pages) == 1

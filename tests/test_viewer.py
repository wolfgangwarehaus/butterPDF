"""The PDF viewer opens a real PDF, and degrades gracefully on a bad one."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtPdf import QPdfDocument

from butterpdf.viewer import PdfViewer


def _minimal_pdf() -> bytes:
    """A valid one-page PDF with a computed xref — enough for QtPdf to report Ready."""
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    startxref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, startxref)
    return bytes(out)


def test_opens_a_pdf(qapp, tmp_path: Path) -> None:
    pdf = tmp_path / "good.pdf"
    pdf.write_bytes(_minimal_pdf())
    viewer = PdfViewer()
    viewer.open_path(pdf)
    qapp.processEvents()
    assert viewer._doc.status() == QPdfDocument.Status.Ready
    assert viewer._doc.pageCount() == 1
    assert viewer._stack.currentWidget() is viewer._view  # the document, not the empty state


def test_bad_file_degrades_without_crashing(qapp, tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is plainly not a pdf")
    viewer = PdfViewer()
    viewer.open_path(bad)
    qapp.processEvents()
    assert viewer._doc.status() == QPdfDocument.Status.Error
    assert viewer._stack.currentWidget() is viewer._empty  # falls back to the error/empty state


def test_controls_are_disabled_until_a_doc_loads(qapp, tmp_path: Path) -> None:
    viewer = PdfViewer()
    assert viewer.controls() is viewer._footer
    assert not viewer._next.isEnabled()  # nothing to page through yet
    viewer.open_path(_write(tmp_path, _minimal_pdf()))
    qapp.processEvents()
    assert viewer._next.isEnabled()


def _write(tmp_path: Path, data: bytes) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(data)
    return p


# ── the page context menu + text stamps (2026-07-08 walkthrough asks) ─────────


def test_insert_text_box_types_in_place_and_composites(qapp, tmp_path: Path) -> None:
    """'Insert text here' drops an IN-PLACE text box (no dialog): typing into
    it renders through the same save tracking as signatures."""
    pdf = tmp_path / "good.pdf"
    pdf.write_bytes(_minimal_pdf())
    viewer = PdfViewer()
    viewer.open_path(pdf)
    qapp.processEvents()

    viewer._insert_text_at(0, 60.0, 120.0)
    (page_index, overlay) = viewer._signatures[-1]
    assert page_index == 0
    assert viewer._collect_signatures() == []  # nothing typed → nothing baked

    overlay._edit.setText("2026-07-08")
    ((idx, rect_pt, img),) = viewer._collect_signatures()
    assert idx == 0
    x0, y0, x1, y1 = rect_pt
    assert (x0, y0) == (60.0, 120.0)  # anchored at the clicked spot
    assert abs((y1 - y0) - 14.0) < 0.01  # form-line height
    assert not img.isNull()
    # the composite rect matches the RENDER's aspect (no chrome stretch)
    assert abs((x1 - x0) / (y1 - y0) - img.width() / img.height()) < 0.01


def test_prefilled_date_box_stays_editable(qapp, tmp_path: Path) -> None:
    """'Insert today's date here' is just a prefilled text box."""
    from datetime import date

    pdf = tmp_path / "good.pdf"
    pdf.write_bytes(_minimal_pdf())
    viewer = PdfViewer()
    viewer.open_path(pdf)
    qapp.processEvents()

    viewer._insert_text_at(0, 40.0, 40.0, viewer._today())
    (_, overlay) = viewer._signatures[-1]
    assert overlay._edit.text() == date.today().isoformat()
    ((_, _, img),) = viewer._collect_signatures()
    assert not img.isNull()


def test_empty_text_box_removes_itself_on_focus_out(qapp, tmp_path: Path) -> None:
    pdf = tmp_path / "good.pdf"
    pdf.write_bytes(_minimal_pdf())
    viewer = PdfViewer()
    viewer.open_path(pdf)
    qapp.processEvents()

    viewer._insert_text_at(0, 60.0, 120.0)
    (_, overlay) = viewer._signatures[-1]
    page = viewer._view.page_widget(0)
    assert overlay in page._overlays
    from PySide6.QtCore import QEvent

    overlay.eventFilter(overlay._edit, QEvent(QEvent.Type.FocusOut))
    assert overlay not in page._overlays  # cleaned itself up
    assert viewer._collect_signatures() == []


def test_page_right_click_reaches_the_viewer_handler(qapp, tmp_path: Path) -> None:
    """PageWidget → RenderedPdfView dispatch → the viewer's handler, with the
    click position already converted to page points."""
    pdf = tmp_path / "good.pdf"
    pdf.write_bytes(_minimal_pdf())
    viewer = PdfViewer()
    viewer.open_path(pdf)
    qapp.processEvents()

    got = []
    viewer._view.page_context_handler = lambda *a: got.append(a)
    page = viewer._view.page_widget(0)
    x_pt, y_pt = page.px_to_pt(10.0, 10.0)
    page.context_handler(page.index, x_pt, y_pt, None)
    ((idx, gx, gy, gpos),) = got
    assert idx == 0 and gpos is None
    assert (gx, gy) == (x_pt, y_pt)


def test_parked_text_box_click_reenters_editing(qapp, tmp_path: Path) -> None:
    """Press+release without movement on a parked box = back into the text;
    only an actual drag moves it."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pdf = tmp_path / "good.pdf"
    pdf.write_bytes(_minimal_pdf())
    viewer = PdfViewer()
    viewer.open_path(pdf)
    qapp.processEvents()

    viewer._insert_text_at(0, 60.0, 120.0, "hello")
    (_, overlay) = viewer._signatures[-1]
    entered = []
    overlay.start_editing = lambda: entered.append(True)

    center = QPointF(overlay.width() / 2, overlay.height() / 2)
    gpos = QPointF(overlay.mapToGlobal(center.toPoint()))
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, center, gpos,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, center, gpos,
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.NoModifier)
    overlay.mousePressEvent(press)
    overlay.mouseReleaseEvent(release)
    assert entered == [True]

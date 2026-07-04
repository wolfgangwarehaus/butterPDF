"""Tests for the fill-and-save engine (butterpdf.pdf_save) — the make-or-break:
values persist AND appearance streams are regenerated so they show in Adobe/print.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pypdf")

from butterpdf.pdf_save import save_filled  # noqa: E402


def _form_pdf(path: Path) -> str:
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        FloatObject,
        NameObject,
        NullObject,
        TextStringObject,
    )

    w = PdfWriter()
    page = w.add_blank_page(width=300, height=200)

    def rect(a, b, c, d):
        return ArrayObject([FloatObject(a), FloatObject(b), FloatObject(c), FloatObject(d)])

    text = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Tx"),
        NameObject("/T"): TextStringObject("fullname"),
        NameObject("/Rect"): rect(50, 100, 250, 130),
        NameObject("/V"): TextStringObject(""),
    })
    ap_n = DictionaryObject({NameObject("/Yes"): NullObject(), NameObject("/Off"): NullObject()})
    chk = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Btn"),
        NameObject("/T"): TextStringObject("agree"),
        NameObject("/Rect"): rect(50, 60, 70, 80),
        NameObject("/AS"): NameObject("/Off"),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): ap_n}),
    })
    refs = [w._add_object(text), w._add_object(chk)]
    page[NameObject("/Annots")] = ArrayObject(refs)
    w._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject(refs)}
    )
    src = path / "in.pdf"
    with open(src, "wb") as f:
        w.write(f)
    return str(src)


def test_fill_persists_with_appearances(tmp_path):
    from pypdf import PdfReader

    src = _form_pdf(tmp_path)
    out = tmp_path / "out.pdf"
    save_filled(src, str(out), {"fullname": "Ada Lovelace", "agree": "/Yes"})

    reader = PdfReader(str(out))
    fields = reader.get_fields()
    assert str(fields["fullname"]["/V"]) == "Ada Lovelace"
    assert str(fields["agree"]["/V"]) == "/Yes"
    # every widget got a regenerated appearance stream (Adobe/print correctness)
    assert all(a.get_object().get("/AP") is not None for a in reader.pages[0]["/Annots"])


def test_overwrite_in_place_is_atomic(tmp_path):
    from pypdf import PdfReader

    src = _form_pdf(tmp_path)
    save_filled(src, src, {"fullname": "Grace"})  # overwrite the source
    assert not (tmp_path / "in.pdf.butterpdf.tmp").exists()  # temp cleaned up
    assert str(PdfReader(src).get_fields()["fullname"]["/V"]) == "Grace"


def test_flatten_writes_a_file(tmp_path):
    src = _form_pdf(tmp_path)
    out = tmp_path / "flat.pdf"
    save_filled(src, str(out), {"fullname": "Ada"}, flatten=True)
    assert out.is_file() and out.stat().st_size > 0


def test_signature_is_baked_as_image_xobject(tmp_path):
    pytest.importorskip("pikepdf")
    from PySide6.QtGui import QColor, QImage

    sig = QImage(60, 30, QImage.Format.Format_RGBA8888)
    sig.fill(QColor(0, 0, 0, 0))
    for x in range(10, 50):
        for y in range(10, 20):
            sig.setPixelColor(x, y, QColor(10, 20, 40, 255))  # some opaque "ink"

    src = _form_pdf(tmp_path)
    out = tmp_path / "signed.pdf"
    save_filled(src, str(out), {}, signatures=[(0, (50.0, 50.0, 150.0, 90.0), sig)])

    import pikepdf

    pdf = pikepdf.open(str(out))
    xobjs = pdf.pages[0].get("/Resources", {}).get("/XObject", {})
    images = [v for v in xobjs.values() if str(v.get("/Subtype")) == "/Image"]
    assert images, "no image XObject stamped"
    assert any("/SMask" in v for v in images), "signature lost its transparency mask"


# ── R1: checkbox appearances are repaired at save ────────────────────────────


def _null_ap_checkbox_pdf(path):
    """A form whose checkbox has NULL on-state appearances (the R1 repro shape:
    the value saves, the mark renders nowhere else)."""
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        FloatObject,
        NameObject,
        NullObject,
        TextStringObject,
    )

    w = PdfWriter()
    page = w.add_blank_page(width=300, height=300)
    ap_n = DictionaryObject({NameObject("/Yes"): NullObject(), NameObject("/Off"): NullObject()})
    chk = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Btn"),
        NameObject("/T"): TextStringObject("agree"),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (50, 250, 70, 270)]),
        NameObject("/AS"): NameObject("/Off"),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): ap_n}),
    })
    ref = w._add_object(chk)
    page[NameObject("/Annots")] = ArrayObject([ref])
    w._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([ref])}
    )
    out = path / "nullap.pdf"
    with open(out, "wb") as f:
        w.write(f)
    return str(out)


def test_checked_box_gets_a_real_appearance_when_missing(tmp_path):
    """R1: a checkbox with null on-state appearance gets a baked ✕ form
    XObject at save — so the mark survives into other viewers."""
    from pypdf import PdfReader
    from pypdf.generic import StreamObject

    src = _null_ap_checkbox_pdf(tmp_path)
    dest = str(tmp_path / "out.pdf")
    save_filled(src, dest, {"agree": "/Yes"})
    r = PdfReader(dest)
    annot = r.pages[0]["/Annots"][0].get_object()
    entry = annot["/AP"]["/N"]["/Yes"].get_object()
    assert isinstance(entry, StreamObject)
    ops = entry.get_data().decode("ascii")
    assert ops.count(" l S") == 2, "the baked appearance draws the two ✕ strokes"
    assert str(annot["/V"]) == "/Yes"


def test_existing_good_appearance_is_left_alone(tmp_path):
    """A form that ships a REAL on-state stream keeps it byte-identical."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        FloatObject,
        NameObject,
        TextStringObject,
    )

    w = PdfWriter()
    page = w.add_blank_page(width=300, height=300)
    good = DecodedStreamObject()
    good.set_data(b"q 1 0 0 RG 0 0 m 10 10 l S Q")  # a distinctive stroke
    good[NameObject("/Type")] = NameObject("/XObject")
    good[NameObject("/Subtype")] = NameObject("/Form")
    good[NameObject("/BBox")] = ArrayObject([FloatObject(v) for v in (0, 0, 20, 20)])
    ap_n = DictionaryObject({NameObject("/Yes"): w._add_object(good)})
    chk = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Btn"),
        NameObject("/T"): TextStringObject("agree"),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (50, 250, 70, 270)]),
        NameObject("/AS"): NameObject("/Off"),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): ap_n}),
    })
    ref = w._add_object(chk)
    page[NameObject("/Annots")] = ArrayObject([ref])
    w._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([ref])}
    )
    src = tmp_path / "goodap.pdf"
    with open(src, "wb") as f:
        w.write(f)

    dest = str(tmp_path / "out.pdf")
    save_filled(str(src), dest, {"agree": "/Yes"})
    entry = PdfReader(dest).pages[0]["/Annots"][0].get_object()["/AP"]["/N"]["/Yes"].get_object()
    assert entry.get_data() == b"q 1 0 0 RG 0 0 m 10 10 l S Q"


def test_flatten_strips_the_interactive_layer(tmp_path):
    """R5 (cross-viewer finding): flatten must remove the widgets AND the
    AcroForm — pypdf's flatten flag alone left live, editable fields. The look
    survives as page-content XObject stamps."""
    from pypdf import PdfReader

    src = _form_pdf(tmp_path)
    out = tmp_path / "flat.pdf"
    save_filled(src, str(out), {"fullname": "Ada", "agree": "/Yes"}, flatten=True)
    r = PdfReader(str(out))
    assert not (r.get_fields() or {}), "AcroForm gone — nothing editable anywhere"
    annots = r.pages[0].get("/Annots") or []
    assert len(annots) == 0, "widget annotations stripped"
    content = r.pages[0].get_contents().get_data().decode("latin-1")
    assert " Do " in content or content.rstrip().endswith("Do Q"), (
        "the widgets' appearances were stamped into the page content"
    )


def test_unflattened_save_keeps_fields_editable(tmp_path):
    from pypdf import PdfReader

    src = _form_pdf(tmp_path)
    out = tmp_path / "filled.pdf"
    save_filled(src, str(out), {"fullname": "Ada"})
    r = PdfReader(str(out))
    assert set(r.get_fields() or {}) == {"fullname", "agree"}
    assert len(r.pages[0]["/Annots"]) == 2

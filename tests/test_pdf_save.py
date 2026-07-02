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

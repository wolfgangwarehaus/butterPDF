"""Tests for the AcroForm field reader (butterpdf.pdf_forms)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pypdf")

from butterpdf.pdf_forms import read_fields  # noqa: E402


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
    page = w.add_blank_page(width=300, height=400)

    def rect(a, b, c, d):
        return ArrayObject([FloatObject(a), FloatObject(b), FloatObject(c), FloatObject(d)])

    text = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Tx"),
        NameObject("/T"): TextStringObject("fullname"),
        NameObject("/Rect"): rect(50, 300, 250, 330),
        NameObject("/V"): TextStringObject("Ada"),
    })
    ap_n = DictionaryObject({NameObject("/Yes"): NullObject(), NameObject("/Off"): NullObject()})
    chk = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Btn"),
        NameObject("/T"): TextStringObject("agree"),
        NameObject("/Rect"): rect(50, 250, 70, 270),
        NameObject("/AS"): NameObject("/Yes"),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): ap_n}),
    })
    refs = [w._add_object(text), w._add_object(chk)]
    page[NameObject("/Annots")] = ArrayObject(refs)
    w._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject(refs)}
    )
    out = path / "form.pdf"
    with open(out, "wb") as f:
        w.write(f)
    return str(out)


def test_reads_text_and_checkbox(tmp_path):
    fields = {f.name: f for f in read_fields(_form_pdf(tmp_path))}
    assert set(fields) == {"fullname", "agree"}

    text = fields["fullname"]
    assert text.kind == "text"
    assert text.value == "Ada"
    assert text.page_index == 0
    assert text.rect == (50.0, 300.0, 250.0, 330.0)

    chk = fields["agree"]
    assert chk.kind == "checkbox"
    assert chk.on_value == "Yes"
    assert chk.value == "Yes"  # /AS is /Yes → checked


def test_missing_or_formless_pdf_is_empty(tmp_path):
    assert read_fields(str(tmp_path / "nope.pdf")) == []
    # a valid PDF with no AcroForm → no fields, no error
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    plain = tmp_path / "plain.pdf"
    with open(plain, "wb") as f:
        w.write(f)
    assert read_fields(str(plain)) == []

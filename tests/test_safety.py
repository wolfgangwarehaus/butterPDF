"""Tests for the safe-open baseline (butterpdf.safety) + save-time sanitize."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pypdf")

from butterpdf.safety import inspect  # noqa: E402


def _evil_pdf(path: Path, *, xfa: bool = True) -> str:
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        NameObject,
        TextStringObject,
    )

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    root = w._root_object
    root[NameObject("/OpenAction")] = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("app.alert(1)"),
    })
    root[NameObject("/Names")] = DictionaryObject({
        NameObject("/JavaScript"): DictionaryObject({NameObject("/Names"): ArrayObject([])}),
    })
    acro = DictionaryObject({NameObject("/Fields"): ArrayObject([])})
    if xfa:
        acro[NameObject("/XFA")] = ArrayObject([])
    root[NameObject("/AcroForm")] = acro
    out = path / "evil.pdf"
    with open(out, "wb") as f:
        w.write(f)
    return str(out)


def test_inspect_flags_active_content_and_xfa(tmp_path):
    r = inspect(_evil_pdf(tmp_path))
    assert r.active_content and r.xfa and r.any_notice
    assert "document JavaScript" in r.details


def test_inspect_clean_pdf(tmp_path):
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    clean = tmp_path / "clean.pdf"
    with open(clean, "wb") as f:
        w.write(f)
    r = inspect(str(clean))
    assert not r.any_notice


def test_inspect_never_raises_on_garbage(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.7 not really a pdf \x00\xff")
    r = inspect(str(junk))  # must not raise
    assert not r.any_notice


def test_save_strips_active_content(tmp_path):
    pytest.importorskip("pikepdf")
    import pikepdf

    from butterpdf.pdf_save import save_filled

    src = _evil_pdf(tmp_path, xfa=False)
    out = tmp_path / "saved.pdf"
    save_filled(src, str(out), {})  # a plain save still runs the sanitize pass

    pdf = pikepdf.open(str(out))
    assert "/OpenAction" not in pdf.Root
    assert "/JavaScript" not in (pdf.Root.get("/Names") or {})

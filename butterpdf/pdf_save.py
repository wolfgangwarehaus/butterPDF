"""Write filled AcroForm values back into a PDF — correctly.

The make-or-break of a fill tool: the saved file must show the values in Adobe
and on paper, not just in the app that wrote them. So we regenerate each field's
**appearance stream** (pypdf ``auto_regenerate=False``) rather than leaning on
``/NeedAppearances`` (which many renderers, and most printers, ignore).

``save_filled`` clones the source, applies the values, and writes a new file.
``flatten=True`` bakes the fields into the page content (no longer editable) for
sending. Values: text/choice as strings; a checkbox/radio as its on-state name
(e.g. ``"/Yes"``) or ``"/Off"``.
"""

from __future__ import annotations


def save_filled(
    src_path: str,
    dest_path: str,
    values: dict[str, str],
    *,
    signatures: list | None = None,
    flatten: bool = False,
) -> None:
    """Fill ``src_path``'s fields with ``values``, composite any ``signatures``
    ((page_index, rect_pt, QImage) with rect in points, bottom-left origin), and
    write to ``dest_path``. Appearance streams are regenerated so fields show in
    Adobe/print; signatures are baked as image XObjects. Raises on failure."""
    import io
    import os

    from pypdf import PdfWriter

    # 1. Fill the form (pypdf) into a memory buffer.
    writer = PdfWriter(clone_from=src_path)
    if values:
        writer.update_page_form_field_values(
            list(writer.pages), values, auto_regenerate=False, flatten=flatten,
        )
    buf = io.BytesIO()
    writer.write(buf)
    data = buf.getvalue()

    # 2. Stamp signatures (pikepdf) if any, then atomically replace the target — so
    # an overwrite-in-place can't corrupt the open file on a failure.
    tmp = f"{dest_path}.butterpdf.tmp"
    try:
        _finalize(data, signatures, tmp)
        os.replace(tmp, dest_path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _finalize(pdf_bytes: bytes, signatures: list | None, dest_path: str) -> None:
    """The pikepdf pass every save goes through: **sanitize** the output (strip
    active content — see butterpdf.safety) and **stamp** any signatures as image
    XObjects (soft-masked for transparency), then write."""
    import io

    import pikepdf
    from pikepdf import Name, Stream

    from butterpdf import signature as sig
    from butterpdf.safety import sanitize_pdf

    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        sanitize_pdf(pdf)  # never write a booby-trapped file back out
        for page_index, rect_pt, image in signatures or []:
            if page_index < 0 or page_index >= len(pdf.pages):
                continue
            page = pdf.pages[page_index]
            rgb, alpha, w, h = sig.to_rgb_alpha(image)

            smask = Stream(pdf, alpha)
            smask.Type, smask.Subtype = Name.XObject, Name.Image
            smask.Width, smask.Height = w, h
            smask.ColorSpace, smask.BitsPerComponent = Name.DeviceGray, 8

            xobj = Stream(pdf, rgb)
            xobj.Type, xobj.Subtype = Name.XObject, Name.Image
            xobj.Width, xobj.Height = w, h
            xobj.ColorSpace, xobj.BitsPerComponent = Name.DeviceRGB, 8
            xobj.SMask = smask

            name = page.add_resource(xobj, Name.XObject)
            x0, y0, x1, y1 = rect_pt
            # image space is a unit square; this cm maps it to the target rect (pts)
            cs = f"q {x1 - x0:.3f} 0 0 {y1 - y0:.3f} {x0:.3f} {y0:.3f} cm {name} Do Q"
            page.contents_add(Stream(pdf, cs.encode("ascii")), prepend=False)
        pdf.save(dest_path)
    finally:
        pdf.close()

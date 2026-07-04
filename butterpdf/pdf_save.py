"""Write filled AcroForm values back into a PDF — correctly.

The make-or-break of a fill tool: the saved file must show the values in Adobe
and on paper, not just in the app that wrote them. So we regenerate each field's
**appearance stream** (pypdf ``auto_regenerate=False``) rather than leaning on
``/NeedAppearances`` (which many renderers, and most printers, ignore).

``save_filled`` clones the source, applies the values, and writes a new file.
``flatten=True`` REALLY flattens: each widget's appearance is stamped into the
page content and the interactive layer (widgets + AcroForm) is stripped — a
flattened file must not be editable in ANY viewer. (pypdf's ``flatten=`` flag
alone leaves the live widgets in place — cross-viewer walkthrough finding R5 —
so the true flatten happens in the pikepdf pass.) Values: text/choice as
strings; a checkbox/radio as its on-state name (e.g. ``"/Yes"``) or ``"/Off"``.
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

    # 1. Fill the form (pypdf) into a memory buffer. Checkbox appearances are
    # repaired FIRST (some forms ship empty/null on-state streams — the value
    # would save correctly but render unchecked everywhere else), so the fill
    # and a flatten both see a real appearance to carry.
    writer = PdfWriter(clone_from=src_path)
    if values:
        _ensure_checkbox_appearances(writer, values)
        writer.update_page_form_field_values(
            list(writer.pages), values, auto_regenerate=False,
        )
    buf = io.BytesIO()
    writer.write(buf)
    data = buf.getvalue()

    # 2. Stamp signatures (pikepdf) if any, then atomically replace the target — so
    # an overwrite-in-place can't corrupt the open file on a failure.
    tmp = f"{dest_path}.butterpdf.tmp"
    try:
        _finalize(data, signatures, tmp, flatten=flatten)
        os.replace(tmp, dest_path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _ensure_checkbox_appearances(writer, values: dict[str, str]) -> None:
    """Give every checkbox being set to an on-state a REAL appearance stream.

    A checked box only shows outside butterPDF if its widget's ``/AP /N
    /<on-state>`` entry is a drawable form XObject. Some generators emit null
    or empty entries — the value round-trips, the mark silently vanishes in
    other viewers (walkthrough finding R1). For those widgets we bake the same
    ✕ the on-screen editor shows. Usable existing appearances are left alone.
    """
    from pypdf.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        FloatObject,
        NameObject,
        StreamObject,
    )

    on_states = {
        name: v for name, v in values.items()
        if isinstance(v, str) and v.startswith("/") and v != "/Off"
    }
    if not on_states:
        return

    def _field_name(annot) -> str | None:
        t = annot.get("/T")
        if t is None and annot.get("/Parent") is not None:
            t = annot["/Parent"].get_object().get("/T")
        return str(t) if t is not None else None

    def _usable(entry) -> bool:
        obj = entry.get_object() if entry is not None else None
        return isinstance(obj, StreamObject) and bool(obj.get_data().strip())

    for page in writer.pages:
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/FT") != "/Btn":
                continue
            name = _field_name(annot)
            state = on_states.get(name or "")
            if state is None:
                continue
            ap = annot.get("/AP")
            n = ap.get_object().get("/N") if ap is not None else None
            if n is not None and _usable(n.get_object().get(state)):
                continue  # the form brought a real appearance — keep it
            x1, y1, x2, y2 = (float(v) for v in annot["/Rect"])
            w, h = abs(x2 - x1), abs(y2 - y1)
            inset, lw = 0.20, max(1.2, 0.10 * min(w, h))
            xa, ya, xb, yb = w * inset, h * inset, w * (1 - inset), h * (1 - inset)
            xo = DecodedStreamObject()
            xo.set_data(
                f"q {lw:.2f} w 0.13 0.15 0.19 RG 1 J "
                f"{xa:.2f} {ya:.2f} m {xb:.2f} {yb:.2f} l S "
                f"{xa:.2f} {yb:.2f} m {xb:.2f} {ya:.2f} l S Q".encode("ascii")
            )
            xo[NameObject("/Type")] = NameObject("/XObject")
            xo[NameObject("/Subtype")] = NameObject("/Form")
            xo[NameObject("/BBox")] = ArrayObject(
                [FloatObject(0), FloatObject(0), FloatObject(w), FloatObject(h)]
            )
            stream_ref = writer._add_object(xo)
            if ap is None or not isinstance(ap.get_object(), DictionaryObject):
                annot[NameObject("/AP")] = DictionaryObject()
                ap = annot["/AP"]
            ap_dict = ap.get_object()
            if not isinstance(ap_dict.get("/N"), DictionaryObject):
                ap_dict[NameObject("/N")] = DictionaryObject()
            ap_dict["/N"][NameObject(state)] = stream_ref


def _flatten_widgets(pdf) -> None:
    """The REAL flatten: draw every widget's current appearance into the page
    content (mapped ``/BBox`` → ``/Rect``; appearance ``/Matrix`` is not
    handled — the appearances we generate carry none), then strip the widgets
    and the AcroForm. After this, nothing is editable anywhere."""
    import pikepdf
    from pikepdf import Name, Stream

    for page in pdf.pages:
        annots = page.get(Name.Annots)
        if annots is None:
            continue
        keep, ops = [], []
        for annot in annots:
            if annot.get(Name.Subtype) != Name.Widget:
                keep.append(annot)
                continue
            ap = annot.get(Name.AP)
            n = ap.get(Name.N) if ap is not None else None
            stream = None
            if isinstance(n, pikepdf.Stream):
                stream = n
            elif isinstance(n, pikepdf.Dictionary):
                state = annot.get(Name.AS)
                cand = n.get(state) if state is not None else None
                if isinstance(cand, pikepdf.Stream):
                    stream = cand
            if stream is not None and Name.BBox in stream:
                xs = [float(v) for v in annot[Name.Rect]]
                x0, x1 = sorted((xs[0], xs[2]))
                y0, y1 = sorted((xs[1], xs[3]))
                bx0, by0, bx1, by1 = (float(v) for v in stream[Name.BBox])
                bw, bh = bx1 - bx0, by1 - by0
                if bw > 0 and bh > 0 and x1 > x0 and y1 > y0:
                    sx, sy = (x1 - x0) / bw, (y1 - y0) / bh
                    tx, ty = x0 - bx0 * sx, y0 - by0 * sy
                    name = page.add_resource(stream, Name.XObject)
                    ops.append(
                        f"q {sx:.4f} 0 0 {sy:.4f} {tx:.3f} {ty:.3f} cm {name} Do Q"
                    )
            # the widget is dropped either way — value already lives in the look
        if ops:
            page.contents_add(Stream(pdf, " ".join(ops).encode("ascii")), prepend=False)
        if keep:
            page[Name.Annots] = pdf.make_indirect(pikepdf.Array(keep))
        elif Name.Annots in page:
            del page[Name.Annots]
    if Name.AcroForm in pdf.Root:
        del pdf.Root[Name.AcroForm]


def _finalize(
    pdf_bytes: bytes, signatures: list | None, dest_path: str, *, flatten: bool = False
) -> None:
    """The pikepdf pass every save goes through: **sanitize** the output (strip
    active content — see butterpdf.safety), **stamp** any signatures as image
    XObjects (soft-masked for transparency), optionally **flatten** the form
    (see :func:`_flatten_widgets`), then write."""
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
        if flatten:
            _flatten_widgets(pdf)
        pdf.save(dest_path)
    finally:
        pdf.close()

"""Read a PDF's AcroForm fields — name, page, rect, type, value — so the viewer
can float an editable widget over each one.

Fields live as ``/Widget`` annotations in each page's ``/Annots``; the field
type / name / value may sit on the widget or be inherited from a ``/Parent``
field. Rects are in PDF points (bottom-left origin). This is read-only; writing
values back into the document is the save step.

Best-effort + robust: any malformed field is skipped, never fatal. XFA and
signature fields are intentionally ignored here (out of scope for fill).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FormField:
    name: str
    page_index: int
    rect: tuple[float, float, float, float]  # (x0,y0,x1,y1) points, bottom-left origin
    kind: str  # 'text' | 'checkbox' | 'radio' | 'choice'
    value: str = ""
    on_value: str | None = None  # checkbox/radio 'on' export state (e.g. 'Yes')
    options: list[str] = field(default_factory=list)  # choice options
    readonly: bool = False
    multiline: bool = False


def _inherited(obj, key: str):
    """Value of ``key`` on the widget or any ``/Parent`` up the chain."""
    seen = 0
    while obj is not None and seen < 20:
        if key in obj:
            return obj[key]
        parent = obj.get("/Parent")
        obj = parent.get_object() if parent is not None else None
        seen += 1
    return None


def _name(obj) -> str:
    """Fully-qualified field name (parent.child…), best-effort."""
    parts = []
    seen = 0
    while obj is not None and seen < 20:
        t = obj.get("/T")
        if t is not None:
            parts.append(str(t))
        parent = obj.get("/Parent")
        obj = parent.get_object() if parent is not None else None
        seen += 1
    return ".".join(reversed(parts))


def _ap_on_state(obj) -> str | None:
    """The non-Off appearance state of a button widget (its 'on' export value)."""
    ap = obj.get("/AP")
    if ap is None:
        return None
    normal = ap.get_object().get("/N") if hasattr(ap, "get_object") else ap.get("/N")
    if normal is None:
        return None
    for key in normal.get_object().keys():
        k = str(key).lstrip("/")
        if k != "Off":
            return k
    return None


def read_fields(path: str) -> list[FormField]:
    """All fillable AcroForm fields in the document. Empty on any failure."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
    except Exception:
        return []

    fields: list[FormField] = []
    for pnum, page in enumerate(reader.pages):
        try:
            annots = page.get("/Annots")
        except Exception:
            annots = None
        if not annots:
            continue
        for ref in annots:
            try:
                obj = ref.get_object()
                if obj.get("/Subtype") != "/Widget":
                    continue
                ft = _inherited(obj, "/FT")
                if ft is None:
                    continue
                ft = str(ft)
                raw = [float(v) for v in obj["/Rect"]]
                rect = (min(raw[0], raw[2]), min(raw[1], raw[3]),
                        max(raw[0], raw[2]), max(raw[1], raw[3]))
                flags = int(_inherited(obj, "/Ff") or 0)
                readonly = bool(flags & 1)
                name = _name(obj)
                value = _inherited(obj, "/V")

                if ft == "/Tx":
                    fields.append(FormField(
                        name, pnum, rect, "text",
                        str(value) if value is not None else "",
                        readonly=readonly, multiline=bool(flags & (1 << 12)),
                    ))
                elif ft == "/Btn":
                    on = _ap_on_state(obj) or "Yes"
                    state = obj.get("/AS")
                    cur = str(state).lstrip("/") if state is not None else (
                        str(value).lstrip("/") if value is not None else "Off")
                    kind = "radio" if (flags & (1 << 15)) else "checkbox"
                    fields.append(FormField(
                        name, pnum, rect, kind,
                        on if cur == on else "Off", on_value=on, readonly=readonly,
                    ))
                elif ft == "/Ch":
                    opts = []
                    raw_opts = _inherited(obj, "/Opt") or []
                    for o in raw_opts:
                        o = o.get_object() if hasattr(o, "get_object") else o
                        opts.append(str(o[1]) if isinstance(o, (list, tuple)) else str(o))
                    fields.append(FormField(
                        name, pnum, rect, "choice",
                        str(value) if value is not None else "",
                        options=opts, readonly=readonly,
                    ))
            except Exception:
                continue
    return fields

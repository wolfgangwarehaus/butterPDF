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
    flatten: bool = False,
) -> None:
    """Fill ``src_path``'s fields with ``values`` and write to ``dest_path`` with
    regenerated appearance streams. Raises on failure (caller shows a toast)."""
    import os

    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=src_path)
    if values:
        # A list of all pages so fields are matched wherever they live. Appearance
        # streams are regenerated (auto_regenerate=False) → correct in Adobe/print.
        writer.update_page_form_field_values(
            list(writer.pages), values, auto_regenerate=False, flatten=flatten,
        )
    # Write to a sibling temp then atomically replace, so an overwrite-in-place
    # (Save over the currently-open file) can't truncate/corrupt it on a failure.
    tmp = f"{dest_path}.butterpdf.tmp"
    try:
        with open(tmp, "wb") as f:
            writer.write(f)
        os.replace(tmp, dest_path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

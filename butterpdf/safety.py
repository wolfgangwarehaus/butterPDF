"""Treat every PDF as hostile.

butterPDF renders with PDFium, which never executes document JavaScript or launch
actions — so *opening* a file can't run its active content. This module adds the
rest of the baseline:

* **inspect** — on open, flag active content (auto-run OpenAction, document
  JavaScript, additional-actions, embedded files) and XFA forms, so the user is
  told rather than silently exposed / silently unable to fill.
* **sanitize_pdf** — on save, strip those dangerous constructs from the *output*
  so butterPDF never writes a booby-trapped file back out.

Malformed input is handled upstream (QtPdf degrades to the error state); every
call here is best-effort and never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SafetyReport:
    active_content: bool = False  # JS / OpenAction / AA / launch / embedded files
    xfa: bool = False             # an XFA form (butterPDF fills AcroForm, not XFA)
    details: list[str] = field(default_factory=list)

    @property
    def any_notice(self) -> bool:
        return self.active_content or self.xfa


def inspect(path: str) -> SafetyReport:
    """Flag active content + XFA in ``path``. Never raises."""
    report = SafetyReport()
    try:
        from pypdf import PdfReader

        root = PdfReader(path).trailer["/Root"]
        if "/OpenAction" in root:
            report.active_content = True
            report.details.append("an auto-run action")
        if "/AA" in root:
            report.active_content = True
            report.details.append("document additional-actions")
        names = root.get("/Names")
        names = names.get_object() if names is not None else {}
        if "/JavaScript" in names:
            report.active_content = True
            report.details.append("document JavaScript")
        if "/EmbeddedFiles" in names:
            report.active_content = True
            report.details.append("embedded files")
        acro = root.get("/AcroForm")
        if acro is not None and "/XFA" in acro.get_object():
            report.xfa = True
    except Exception:
        pass
    return report


def sanitize_pdf(pdf) -> None:
    """Strip dangerous constructs from an open pikepdf ``pdf`` in place: auto-run /
    additional actions, document JavaScript + embedded-file name trees, and any
    annotation whose action is JavaScript or Launch. Navigation links (GoTo) and
    normal form logic are left intact. Best-effort."""
    from pikepdf import Name

    try:
        root = pdf.Root
        for key in ("/OpenAction", "/AA"):
            if key in root:
                del root[key]
        names = root.get("/Names")
        if names is not None:
            for key in ("/JavaScript", "/EmbeddedFiles"):
                if key in names:
                    del names[key]
        dangerous = {Name.JavaScript, Name.Launch}
        for page in pdf.pages:
            if "/AA" in page:
                del page["/AA"]
            annots = page.get("/Annots")
            if annots is None:
                continue
            for annot in annots:
                for key in ("/A", "/AA"):
                    act = annot.get(key)
                    if act is not None and act.get("/S") in dangerous:
                        del annot[key]
    except Exception:
        pass

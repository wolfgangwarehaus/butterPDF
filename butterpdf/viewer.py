"""butterPDF's PDF viewer — the foundation feature.

Renders a PDF on the frosted chrome with Qt's built-in engine (QtPdf / PDFium):
open (dialog, drag-drop, or a path on the command line), continuous-scroll render,
zoom, and page navigation. The fill + sign layers — the real point of butterPDF —
build on top of this view.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from butterpdf import ui_helpers
from butterpdf.bus import AppBus
from butterpdf.design_tokens import TYPE_BODY, TYPE_DISPLAY, type_qss
from butterpdf.page_view import RenderedPdfView
from butterpdf.settings import get_settings
from butterpdf.top_bar import CenteredBar

_ZOOM_STEP = 1.25

# Document-background modes → (paper, recolor). paper is the fill behind the page
# (None = frosted see-through); recolor is (invert, floor, ceil) for
# page_view.recolor, or None for a straight render. The dark modes invert +
# re-level the grayscale content (text/paper) while leaving colour images natural.
_DOC_BG = {
    "white": (QColor(255, 255, 255), None),
    "light_grey": (QColor(202, 202, 202), (False, 0, 202)),
    "dark_grey": (QColor(32, 32, 32), (True, 32, 220)),
    "oled": (QColor(0, 0, 0), (True, 0, 255)),
    "transparent": (None, None),
}
# The selector's user-facing options, in order (value, label).
DOC_BG_OPTIONS = [
    ("auto", "Auto (match theme)"),
    ("white", "White"),
    ("light_grey", "Light grey"),
    ("dark_grey", "Dark grey"),
    ("oled", "OLED black"),
    ("transparent", "Transparent"),
]


def _resolve_doc_bg(mode: str, dark: bool) -> tuple:
    """(paper, recolor) for a mode. 'auto' follows the app theme: a light theme →
    white, a dark theme → dark grey."""
    if mode == "auto":
        mode = "dark_grey" if dark else "white"
    return _DOC_BG.get(mode, _DOC_BG["white"])


class PdfViewer(QWidget):
    """The document view plus a control bar (returned by :meth:`controls`, meant for
    the window footer). Open a PDF via :meth:`open_path`, :meth:`open_dialog`, or by
    dropping a file onto it."""

    document_changed = Signal(str)  # basename when a doc opens; "" when cleared/failed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._path: str | None = None

        # butterPDF renders pages itself (page_view.RenderedPdfView) rather than
        # using QPdfView — the fill + sign layers need exact page geometry to anchor
        # overlay widgets, which QPdfView doesn't expose. The frost, even 8px
        # gutters, and 10px page spacing live in RenderedPdfView.
        self._doc = QPdfDocument(self)
        self._view = RenderedPdfView(self)  # installs its own slim auto-fade scrollbar
        self._view.set_document(self._doc)

        self._empty = self._make_empty_state()
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._empty)  # 0
        self._stack.addWidget(self._view)  # 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._footer = self._make_footer()
        self._doc.statusChanged.connect(self._on_status_changed)
        self._view.current_page_changed.connect(lambda _p: self._update_page_label())
        # The page paper follows the app theme (+ the frosted-document setting), and
        # re-applies live when either changes — theme_changed carries both.
        AppBus.get().theme_changed.connect(self._apply_document_display)
        self._apply_document_display()
        self._refresh()

        # Ctrl+S save (over the open file) / Ctrl+Shift+S save-as. App-wide so it
        # fires regardless of which field has focus.
        from PySide6.QtGui import QKeySequence, QShortcut

        save_sc = QShortcut(QKeySequence.StandardKey.Save, self)
        save_sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        save_sc.activated.connect(self.save)
        save_as_sc = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        save_as_sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        save_as_sc.activated.connect(lambda: self.save_as())

    # ── public ───────────────────────────────────────────────────────────────
    def controls(self) -> QWidget:
        """The control bar, for ``window.set_footer(...)``."""
        return self._footer

    def open_path(self, path: str | Path) -> None:
        self._path = str(path)
        # Image placements (for dark-mode image protection) come from the file
        # itself via pypdf; lazy + best-effort, independent of the QtPdf render.
        from butterpdf.pdf_images import ImageBoxes

        self._images = ImageBoxes(self._path)
        self._doc.load(self._path)

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF documents (*.pdf)")
        if path:
            self.open_path(path)

    def _build_form_fields(self) -> None:
        """Read the AcroForm fields and float an editable widget over each, on its
        page, so they can be filled in place. Best-effort — a doc with no fields
        (or an unreadable form) simply adds nothing."""
        from butterpdf.form_layer import make_field_widget
        from butterpdf.pdf_forms import read_fields

        self._field_widgets = []
        for fld in read_fields(self._path or ""):
            page = self._view.page_widget(fld.page_index)
            if page is None:
                continue
            widget = make_field_widget(fld)
            if widget is None:
                continue
            page.add_field(widget, fld.rect)
            self._field_widgets.append(widget)

    # ── signatures ───────────────────────────────────────────────────────────
    def can_edit(self) -> bool:
        return self._doc.status() == QPdfDocument.Status.Ready and self._doc.pageCount() > 0

    def begin_sign(self) -> None:
        """Create a signature (dialog) and drop it on the current page to place."""
        if not self.can_edit():
            return
        from PySide6.QtWidgets import QDialog

        from butterpdf.sign_dialog import SignatureDialog

        dlg = SignatureDialog(self.window())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            img = dlg.signature_image()
            if img is not None and not img.isNull():
                self.place_signature(img)

    def place_signature(self, image) -> None:
        """Drop ``image`` onto the current page at a comfortable default size, ready
        to drag/resize. Tracked for compositing on save."""
        from butterpdf.sign_overlay import SignatureOverlay

        idx = self._view.current_page()
        page = self._view.page_widget(idx)
        if page is None:
            return
        pw, ph = page.page_size_pt()
        width_pt = min(220.0, pw * 0.42)
        aspect = image.height() / image.width() if image.width() else 0.4
        height_pt = width_pt * aspect
        x0, y0 = pw * 0.10, ph * 0.12  # lower-left-ish, a natural sign spot
        rect_pt = (x0, y0, x0 + width_pt, y0 + height_pt)
        overlay = SignatureOverlay(page, image, rect_pt)
        page.add_overlay(overlay)
        self._signatures = getattr(self, "_signatures", [])
        self._signatures.append((idx, overlay))

    def _collect_signatures(self) -> list:
        """(page_index, rect_pt points, QImage) for each placed signature still
        alive — for compositing into the saved PDF."""
        out = []
        for idx, ov in getattr(self, "_signatures", []):
            try:
                out.append((idx, ov.rect_pt, ov.image))
            except RuntimeError:
                continue  # deleted overlay
        return out

    # ── form save ──────────────────────────────────────────────────────────
    def has_form(self) -> bool:
        return bool(getattr(self, "_field_widgets", None))

    def _collect_values(self) -> dict:
        """Current field values keyed by field name: text/choice as strings, a
        checkbox/radio as its on-state name (``/Yes``) or ``/Off``."""
        from butterpdf.form_layer import field_value

        values = {}
        for widget in getattr(self, "_field_widgets", ()):
            fld = getattr(widget, "_field", None)
            if fld is None:
                continue
            val = field_value(widget)
            if fld.kind in ("checkbox", "radio"):
                values[fld.name] = "/" + (val or "Off")
            else:
                values[fld.name] = val if val is not None else ""
        return values

    def save_document(self, dest_path: str, *, flatten: bool = False) -> None:
        """Write the filled form to ``dest_path`` (regenerated appearance streams).
        Raises on failure — the caller surfaces it."""
        from butterpdf.pdf_save import save_filled

        save_filled(
            self._path or "", dest_path, self._collect_values(),
            signatures=self._collect_signatures(), flatten=flatten,
        )

    def save(self) -> None:
        """Save over the currently-open file (atomic). No-op without a document."""
        if self._path:
            self._save_to(self._path)

    def save_as(self, *, flatten: bool = False) -> None:
        """Prompt for a destination and save (optionally flattened for sending)."""
        if not self._path:
            return
        from pathlib import Path

        stem = Path(self._path).stem
        suffix = "-flattened" if flatten else "-filled"
        suggested = str(Path(self._path).with_name(f"{stem}{suffix}.pdf"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", suggested, "PDF documents (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self._save_to(path, flatten=flatten)

    def _save_to(self, path: str, *, flatten: bool = False) -> None:
        from butterpdf.frosted_dialog import frosted_warning

        try:
            self.save_document(path, flatten=flatten)
        except Exception as exc:  # surface, never crash
            frosted_warning(self, "Couldn't save", f"Saving the PDF failed:\n{exc}")

    def _apply_document_display(self) -> None:
        """Resolve the page paper + recolor from the 'Document background' setting
        (which may follow the app theme) and push it to the view."""
        from butterpdf.theme import get_active_theme

        paper, recolor = _resolve_doc_bg(get_settings().document_bg, get_active_theme().dark)
        self._view.set_display(paper, recolor)

    # ── drag & drop ──────────────────────────────────────────────────────────
    def _dropped_pdf(self, event) -> str | None:
        if not event.mimeData().hasUrls():
            return None
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local.lower().endswith(".pdf"):
                return local
        return None

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._dropped_pdf(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        local = self._dropped_pdf(event)
        if local:
            self.open_path(local)
            event.acceptProposedAction()

    # ── view actions ─────────────────────────────────────────────────────────
    def _zoom_by(self, factor: float) -> None:
        self._view.zoom_by(factor)
        self._update_zoom_label()

    def _fit_width(self) -> None:
        self._view.set_fit_width()
        self._update_zoom_label()

    def _go(self, delta: int) -> None:
        if self._doc.pageCount() <= 0:
            return
        self._view.jump_to_page(self._view.current_page() + delta)

    # ── state ────────────────────────────────────────────────────────────────
    def _on_status_changed(self, status) -> None:
        if status == QPdfDocument.Status.Ready:
            self._view.rebuild()  # build page widgets now the doc has pages
            images = getattr(self, "_images", None)
            if images is not None:
                self._view.set_image_boxes(images.boxes_pt)
            self._build_form_fields()
            self._stack.setCurrentWidget(self._view)
            self.document_changed.emit(Path(self._path).name if self._path else "")
        elif status == QPdfDocument.Status.Error:
            if self._doc.error() == QPdfDocument.Error.IncorrectPassword:
                self._set_empty_text("That PDF is password-protected — not supported yet.")
            else:
                self._set_empty_text("Couldn't open that file as a PDF.")
            self._stack.setCurrentWidget(self._empty)
            self.document_changed.emit("")
        self._refresh()

    def _refresh(self) -> None:
        ready = self._doc.status() == QPdfDocument.Status.Ready and self._doc.pageCount() > 0
        for control in (self._prev, self._next, self._zoom_out, self._zoom_in, self._fit_btn):
            control.setEnabled(ready)
        self._update_page_label()
        self._update_zoom_label()

    def _update_page_label(self) -> None:
        count = self._doc.pageCount()
        current = self._view.current_page()
        self._page_label.setText(f"{current + 1} / {count}" if count > 0 else "—")
        footer = getattr(self, "_footer", None)
        if isinstance(footer, CenteredBar):
            footer.recenter()  # the page label changed width

    def _update_zoom_label(self) -> None:
        fit = self._view.is_fit()
        self._fit_btn.setText("Fit" if fit else f"{round(self._view.zoom_factor() * 100)}%")

    # ── widgets ──────────────────────────────────────────────────────────────
    def _make_empty_state(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(widget)
        lay.addStretch(1)
        title = QLabel("Open a PDF")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {ui_helpers.TEXT}; {type_qss(TYPE_DISPLAY)}")
        self._empty_sub = QLabel("Drop a file here, or hit Open below.")
        self._empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_sub.setStyleSheet(f"color: {ui_helpers.TEXT_DIM}; {type_qss(TYPE_BODY)}")
        lay.addWidget(title)
        lay.addWidget(self._empty_sub)
        lay.addStretch(2)
        return widget

    def _set_empty_text(self, text: str) -> None:
        self._empty_sub.setText(text)

    def _make_footer(self) -> QWidget:
        bar = CenteredBar()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 5, 14, 5)
        row.setSpacing(6)
        row.addStretch(1)

        # zoom group — tucked in the right corner: −  [Fit]  +  where the middle button
        # shows the zoom % AND is the fit control (one "Fit", not two).
        self._zoom_out = self._tool("−", lambda: self._zoom_by(1 / _ZOOM_STEP))
        self._fit_btn = self._tool("Fit", self._fit_width)
        self._zoom_in = self._tool("+", lambda: self._zoom_by(_ZOOM_STEP))
        for control in (self._zoom_out, self._fit_btn, self._zoom_in):
            row.addWidget(control)

        # page navigation — floats truly centered over the whole footer
        nav = QWidget(bar)
        nav_lay = QHBoxLayout(nav)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(6)
        self._prev = self._tool("◀", lambda: self._go(-1))
        self._page_label = self._label("—")
        self._next = self._tool("▶", lambda: self._go(1))
        nav_lay.addWidget(self._prev)
        nav_lay.addWidget(self._page_label)
        nav_lay.addWidget(self._next)
        bar.set_centered(nav)
        return bar

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {ui_helpers.TEXT}; {type_qss(TYPE_BODY)}")
        return label

    def _tool(self, text: str, on_click) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color: {ui_helpers.TEXT}; background: transparent; border: none;"
            f" padding: 4px 12px; border-radius: 8px; {type_qss(TYPE_BODY)} }}"
            f" QPushButton:hover {{ background: rgba(255,255,255,0.10); }}"
            f" QPushButton:disabled {{ color: {ui_helpers.TEXT_DIM}; }}"
        )
        btn.clicked.connect(on_click)
        return btn

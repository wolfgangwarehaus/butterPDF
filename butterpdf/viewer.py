"""butterPDF's PDF viewer — the foundation feature.

Renders a PDF on the frosted chrome with Qt's built-in engine (QtPdf / PDFium):
open (dialog, drag-drop, or a path on the command line), continuous-scroll render,
zoom, and page navigation. The fill + sign layers — the real point of butterPDF —
build on top of this view.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
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
from butterpdf.design_tokens import TYPE_BODY, TYPE_DISPLAY, type_qss
from butterpdf.top_bar import CenteredBar

_ZOOM_STEP = 1.25
_ZOOM_MIN = 0.1
_ZOOM_MAX = 8.0


class PdfViewer(QWidget):
    """The document view plus a control bar (returned by :meth:`controls`, meant for
    the window footer). Open a PDF via :meth:`open_path`, :meth:`open_dialog`, or by
    dropping a file onto it."""

    document_changed = Signal(str)  # basename when a doc opens; "" when cleared/failed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._fit = True  # track ZoomMode ourselves (QPdfView has no public getter)
        self._path: str | None = None

        self._doc = QPdfDocument(self)
        self._view = QPdfView(self)
        self._view.setDocument(self._doc)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._nav = self._view.pageNavigator()
        self._frost_view()

        self._empty = self._make_empty_state()
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._empty)  # 0
        self._stack.addWidget(self._view)  # 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._footer = self._make_footer()
        self._doc.statusChanged.connect(self._on_status_changed)
        self._nav.currentPageChanged.connect(lambda _p: self._update_page_label())
        self._refresh()

    # ── public ───────────────────────────────────────────────────────────────
    def controls(self) -> QWidget:
        """The control bar, for ``window.set_footer(...)``."""
        return self._footer

    def open_path(self, path: str | Path) -> None:
        self._path = str(path)
        self._doc.load(self._path)

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF documents (*.pdf)")
        if path:
            self.open_path(path)

    def _frost_view(self) -> None:
        """Let the window's frost show through the page gutters + margins instead of
        QtPdf's default opaque grey — uniform frosted glass is a dough hallmark."""
        view = self._view
        view.setStyleSheet("QPdfView { background: transparent; border: none; }")
        viewport = view.viewport()
        viewport.setAutoFillBackground(False)
        clear = QColor(0, 0, 0, 0)
        pal = view.palette()
        for role in (
            QPalette.ColorRole.Base,
            QPalette.ColorRole.Dark,
            QPalette.ColorRole.Mid,
            QPalette.ColorRole.Window,
            QPalette.ColorRole.Button,
        ):
            pal.setColor(role, clear)
        view.setPalette(pal)
        viewport.setPalette(pal)

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
        self._fit = False
        self._view.setZoomMode(QPdfView.ZoomMode.Custom)
        target = max(_ZOOM_MIN, min(_ZOOM_MAX, self._view.zoomFactor() * factor))
        self._view.setZoomFactor(target)
        self._update_zoom_label()

    def _fit_width(self) -> None:
        self._fit = True
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._update_zoom_label()

    def _go(self, delta: int) -> None:
        count = self._doc.pageCount()
        if count <= 0:
            return
        page = max(0, min(count - 1, self._nav.currentPage() + delta))
        self._nav.jump(page, QPointF(0, 0), 0)

    # ── state ────────────────────────────────────────────────────────────────
    def _on_status_changed(self, status) -> None:
        if status == QPdfDocument.Status.Ready:
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
        self._page_label.setText(f"{self._nav.currentPage() + 1} / {count}" if count > 0 else "—")
        footer = getattr(self, "_footer", None)
        if isinstance(footer, CenteredBar):
            footer.recenter()  # the page label changed width

    def _update_zoom_label(self) -> None:
        self._zoom_label.setText("Fit" if self._fit else f"{round(self._view.zoomFactor() * 100)}%")

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

        # zoom group — right-aligned in the normal layout
        self._zoom_out = self._tool("−", lambda: self._zoom_by(1 / _ZOOM_STEP))
        self._zoom_label = self._label("Fit")
        self._zoom_in = self._tool("+", lambda: self._zoom_by(_ZOOM_STEP))
        self._fit_btn = self._tool("Fit", self._fit_width)
        for control in (self._zoom_out, self._zoom_label, self._zoom_in, self._fit_btn):
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

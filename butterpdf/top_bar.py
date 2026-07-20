"""TopBar — butterPDF's top bar, which doubles as the titlebar in borderless mode.

Left: a document menu (Open / Edit / Sign). Center: the app name + the open
document's name — TRULY centered over the window (via :class:`CenteredBar`), not just
between the side groups. Right: settings + minimize / maximize / close. Dragging the
bar moves the window; double-click toggles maximize.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from butterpdf import ui_helpers
from butterpdf.bus import AppBus
from butterpdf.design_tokens import TYPE_BODY, TYPE_SUBHEAD, type_qss
from butterpdf.icon_button import IconButton
from butterpdf.icons import icon


class CenteredBar(QWidget):
    """A horizontal bar that keeps ONE child truly centered over the full bar width —
    not merely between its side groups — and re-centers it on every resize. Side
    content lives in the normal layout; the centered child floats on top. This is the
    "balanced regardless of what's on the sides" behaviour a polished titlebar wants.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._centered: QWidget | None = None

    def set_centered(self, widget: QWidget) -> None:
        self._centered = widget
        self.recenter()

    def recenter(self) -> None:
        c = self._centered
        if c is None:
            return
        c.adjustSize()
        c.move(max(0, (self.width() - c.width()) // 2), max(0, (self.height() - c.height()) // 2))
        c.raise_()

    def resizeEvent(self, event):  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.recenter()


class TopBar(CenteredBar):
    HEIGHT = 40

    def __init__(self, window, *, titlebar_mode: bool, title: str = "butterpdf"):
        super().__init__(window)
        self._window = window
        self._titlebar_mode = titlebar_mode
        self._viewer = None
        self.setFixedHeight(self.HEIGHT)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        # ── left: the document menu (Open / Sign / Save) + settings gear ───
        self.menu_btn = self._chrome_button("menu", "Menu")
        self.menu_btn.clicked.connect(self._show_menu)
        lay.addWidget(self.menu_btn)
        self.settings_btn = self._chrome_button("settings", "Settings")
        self.settings_btn.clicked.connect(lambda: AppBus.get().show_settings.emit())
        lay.addWidget(self.settings_btn)
        lay.addStretch(1)

        # Update-available chip — invisible until butterpdf.updates finds a
        # newer release (AppBus.update_available); Download / What's-new /
        # Dismiss. Sits just left of the window controls, clear of the
        # centered doc name.
        from butterpdf.update_chip import UpdateChip

        self.update_chip = UpdateChip(self)
        lay.addWidget(self.update_chip)

        # ── right: window controls ─────────────────────────────────────────
        if titlebar_mode:
            self.min_btn = self._chrome_button("win_minimize", "Minimize")
            self.min_btn.clicked.connect(window.showMinimized)
            self.max_btn = self._chrome_button("win_maximize", "Maximize")
            self.max_btn.clicked.connect(self._toggle_max)
            self.close_btn = self._chrome_button("win_close", "Close")
            self.close_btn.clicked.connect(window.close)
            for b in (self.min_btn, self.max_btn, self.close_btn):
                lay.addWidget(b)

        # ── center: app name + open document — floats, truly centered ──────
        self._center = QWidget(self)
        self._center.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # drag passes through
        center_lay = QHBoxLayout(self._center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(8)
        self.title = QLabel(title)
        self.doc_label = QLabel("")
        self.doc_label.hide()
        center_lay.addWidget(self.title)
        center_lay.addWidget(self.doc_label)
        self.set_centered(self._center)

        self.restyle()

    # ── viewer wiring ───────────────────────────────────────────────────────
    def bind_viewer(self, viewer) -> None:
        """Wire the document menu's Open + the centered doc name to the viewer."""
        self._viewer = viewer
        viewer.document_changed.connect(self.set_document_name)

    def set_document_name(self, name: str) -> None:
        if name:
            self.doc_label.setText(f"·  {name}")
            self.doc_label.show()
        else:
            self.doc_label.clear()
            self.doc_label.hide()
        self.recenter()  # the centered group changed width

    def _show_menu(self) -> None:
        menu = ui_helpers.opaque_menu(self, blur_corner_radius=8)  # frosted, readable
        menu.addAction("Open…").triggered.connect(self._open)

        can_edit = self._viewer is not None and self._viewer.can_edit()
        sign = menu.addAction("Sign…")
        sign.setEnabled(can_edit)
        sign.triggered.connect(lambda: self._viewer.begin_sign())

        has_form = self._viewer is not None and self._viewer.has_form()
        menu.addSeparator()
        save = menu.addAction("Save")
        save.setEnabled(has_form)
        save.triggered.connect(lambda: self._viewer.save())
        save_as = menu.addAction("Save As…")
        save_as.setEnabled(has_form)
        save_as.triggered.connect(lambda: self._viewer.save_as())
        flatten = menu.addAction("Flatten && Save As…")  # && = literal & in Qt menus
        flatten.setEnabled(has_form)
        flatten.triggered.connect(lambda: self._viewer.save_as(flatten=True))

        menu.addSeparator()
        export_png = menu.addAction("Export pages as PNG…")
        export_png.setEnabled(can_edit)
        export_png.triggered.connect(lambda: self._viewer.export_images("png"))
        export_jpg = menu.addAction("Export pages as JPEG…")
        export_jpg.setEnabled(can_edit)
        export_jpg.triggered.connect(lambda: self._viewer.export_images("jpeg"))
        make_pdf = menu.addAction("Create PDF from images…")
        make_pdf.triggered.connect(lambda: self._viewer.images_to_pdf())

        menu.addSeparator()
        soon = menu.addAction("Edit  (soon)")
        soon.setEnabled(False)  # MVP fast-follow
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _open(self) -> None:
        if self._viewer is not None:
            self._viewer.open_dialog()

    def _chrome_button(self, icon_name: str, tip: str) -> IconButton:
        # accessible_name passed explicitly (the preferred pattern) even
        # though the tooltip would fall back to the same string — a call site
        # that later reworks its tooltip wording keeps a stable announced name.
        b = IconButton(accessible_name=tip)
        b.setIcon(icon(icon_name))
        b.setToolTip(tip)
        b.setFixedSize(32, 28)
        return b

    def restyle(self) -> None:
        """Re-read theme colors (call on AppBus.theme_changed) + refresh icons."""
        self.title.setStyleSheet(f"color: {ui_helpers.TEXT}; {type_qss(TYPE_SUBHEAD)}")
        self.doc_label.setStyleSheet(f"color: {ui_helpers.TEXT_DIM}; {type_qss(TYPE_BODY)}")
        self.recenter()
        for name, btn in (
            ("menu", getattr(self, "menu_btn", None)),
            ("settings", getattr(self, "settings_btn", None)),
            ("win_minimize", getattr(self, "min_btn", None)),
            ("win_maximize", getattr(self, "max_btn", None)),
            ("win_close", getattr(self, "close_btn", None)),
        ):
            if btn is not None:
                btn.setIcon(icon(name))

    def _toggle_max(self) -> None:
        w = self._window
        w.showNormal() if w.isMaximized() else w.showMaximized()

    # ── Drag-to-move / double-click maximize (titlebar) ────────────────────
    def mousePressEvent(self, e):
        if self._titlebar_mode and e.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._titlebar_mode and e.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
            return
        super().mouseDoubleClickEvent(e)

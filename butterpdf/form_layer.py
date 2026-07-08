"""Build an editable Qt widget for a PDF form field.

The viewer anchors these over the rendered page (page_view.PageWidget.add_field)
so a user can fill the real AcroForm fields in place. Widgets are deliberately
styled as obvious inputs — a near-opaque light field with an accent border — so a
fillable area reads clearly over either a light or a dark (inverted) page. On a
DARK page the fill is a soft light grey rather than plain white (user call:
avoid pure white on dark) — still unmistakably an input, less glare. The
originating :class:`~butterpdf.pdf_forms.FormField` is stashed on ``._field`` for
the save step, and ``.value_str()`` reads the current widget value uniformly.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QWidget

from butterpdf import ui_helpers


class TextField(QLineEdit):
    """A text input whose context menu is the app's frosted ``opaque_menu`` —
    Qt's default QLineEdit popup is a raw un-themed QMenu (the one place the
    stock chrome leaked through, caught in the 2026-07-08 walkthrough) — plus
    the two form niceties: insert today's date, and sign the document here.
    ``sign_here`` is wired by the viewer (``fn(field)``) when signing is
    possible; unwired, the action simply doesn't appear."""

    def __init__(self, field, dark_page: bool = False) -> None:
        super().__init__(field.value)
        self._field = field
        self.sign_here = None  # viewer-wired: fn(field) → the sign-at flow

    def _build_context_menu(self):
        menu = ui_helpers.opaque_menu(self)

        def act(text, slot, enabled=True, shortcut=None):
            a = menu.addAction(text)
            a.triggered.connect(slot)
            a.setEnabled(enabled)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            return a

        has_sel = self.hasSelectedText()
        act("Undo", self.undo, self.isUndoAvailable(), QKeySequence.StandardKey.Undo)
        act("Redo", self.redo, self.isRedoAvailable(), QKeySequence.StandardKey.Redo)
        menu.addSeparator()
        act("Cut", self.cut, has_sel, QKeySequence.StandardKey.Cut)
        act("Copy", self.copy, has_sel, QKeySequence.StandardKey.Copy)
        act("Paste", self.paste,
            bool(QGuiApplication.clipboard().text()), QKeySequence.StandardKey.Paste)
        act("Select All", self.selectAll, bool(self.text()),
            QKeySequence.StandardKey.SelectAll)
        menu.addSeparator()
        act("Insert today's date", self._insert_today)
        if callable(self.sign_here):
            act("Sign document here…", lambda: self.sign_here(self._field))
        return menu

    def _insert_today(self) -> None:
        """ISO date (2026-07-08) at the cursor — unambiguous on any form,
        replaces a selection like normal typed input."""
        from datetime import date

        self.insert(date.today().isoformat())

    def contextMenuEvent(self, e) -> None:  # noqa: N802 (Qt override)
        self._build_context_menu().exec(e.globalPos())


class CheckField(QPushButton):
    """A checkable box that stamps an ✕ when checked (how a paper checkbox is
    filled), not a plain fill."""

    MARK = "✕"

    def __init__(self, field, dark_page: bool = False) -> None:
        super().__init__()
        self._field = field
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setChecked(bool(field.on_value) and field.value == field.on_value)
        self.setStyleSheet(_check_qss(dark_page))
        self.toggled.connect(self._update_mark)
        self._update_mark()

    def _update_mark(self, *_) -> None:
        self.setText(self.MARK if self.isChecked() else "")

    def resizeEvent(self, e) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(e)
        f = self.font()  # size the glyph to the box
        f.setPixelSize(max(6, int(self.height() * 0.78)))
        self.setFont(f)


def _paper(dark_page: bool) -> tuple[str, str, str]:
    """(base, focus, disabled) input fills. Light page → near-white; dark page →
    the soft light-grey family (same paper as the signature canvas)."""
    if dark_page:
        return "rgba(233,235,239,0.96)", "#eef0f3", "rgba(233,235,239,0.55)"
    return "rgba(255,255,255,0.94)", "#ffffff", "rgba(255,255,255,0.55)"


def _text_qss(dark_page: bool = False) -> str:
    a = ui_helpers.ACCENT
    base, focus, dis = _paper(dark_page)
    return (
        f"QLineEdit{{background:{base};border:1px solid {a};"
        f"border-radius:2px;color:#111;padding:0 4px;selection-background-color:{a};}}"
        f"QLineEdit:focus{{border:2px solid {a};background:{focus};}}"
        f"QLineEdit:disabled{{background:{dis};color:#555;}}"
    )


def _check_qss(dark_page: bool = False) -> str:
    a = ui_helpers.ACCENT
    base, _focus, dis = _paper(dark_page)
    return (
        f"QPushButton{{background:{base};border:1px solid {a};"
        f"border-radius:2px;color:{a};font-weight:bold;padding:0;}}"
        f"QPushButton:disabled{{background:{dis};color:#888;}}"
    )


def _combo_qss(dark_page: bool = False) -> str:
    a = ui_helpers.ACCENT
    base, _focus, _dis = _paper(dark_page)
    return (
        f"QComboBox{{background:{base};border:1px solid {a};"
        f"border-radius:2px;color:#111;padding:0 4px;}}"
        f"QComboBox:focus{{border:2px solid {a};}}"
    )


def restyle_field_widget(w: QWidget, dark_page: bool) -> None:
    """Re-stamp a field widget's QSS for the current page darkness — called when
    the document background (or the theme driving 'auto') changes live."""
    if isinstance(w, QLineEdit):
        w.setStyleSheet(_text_qss(dark_page))
    elif isinstance(w, QComboBox):
        w.setStyleSheet(_combo_qss(dark_page))
    elif isinstance(w, QPushButton):
        w.setStyleSheet(_check_qss(dark_page))


def make_field_widget(field, dark_page: bool = False, sign_here=None) -> QWidget | None:
    """An editable widget for ``field`` (or None for a kind we don't fill yet).
    Carries ``._field``; read the current value with :func:`field_value`.
    ``sign_here`` (``fn(field)``) enables the text fields' context-menu
    "Sign document here…" action."""
    if field.kind == "text":
        w: QWidget = TextField(field, dark_page)
        w.sign_here = sign_here
        w.setStyleSheet(_text_qss(dark_page))
    elif field.kind in ("checkbox", "radio"):
        w = CheckField(field, dark_page)
    elif field.kind == "choice":
        w = QComboBox()
        w.addItems(field.options or [])
        if field.value:
            i = w.findText(field.value)
            if i >= 0:
                w.setCurrentIndex(i)
        w.setStyleSheet(_combo_qss(dark_page))
    else:
        return None

    w._field = field
    if field.readonly:
        w.setEnabled(False)
    return w


def field_value(widget: QWidget):
    """Current value of a field widget: str for text/choice, the field's on-value
    or ``'Off'`` for a checkbox/radio."""
    field = getattr(widget, "_field", None)
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, CheckField):
        on = getattr(field, "on_value", None) or "Yes"
        return on if widget.isChecked() else "Off"
    return None

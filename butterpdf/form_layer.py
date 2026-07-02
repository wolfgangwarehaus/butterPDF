"""Build an editable Qt widget for a PDF form field.

The viewer anchors these over the rendered page (page_view.PageWidget.add_field)
so a user can fill the real AcroForm fields in place. Widgets are deliberately
styled as obvious inputs — a near-opaque light field with an accent border — so a
fillable area reads clearly over either a light or a dark (inverted) page. The
originating :class:`~butterpdf.pdf_forms.FormField` is stashed on ``._field`` for
the save step, and ``.value_str()`` reads the current widget value uniformly.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QWidget

from butterpdf import ui_helpers


class CheckField(QPushButton):
    """A checkable box that stamps a mark when checked — a ✓ or ✕ per the
    ``checkbox_mark`` setting (how people fill a paper checkbox), not a plain
    fill. Call :meth:`refresh_mark` to re-read the setting live."""

    def __init__(self, field) -> None:
        super().__init__()
        self._field = field
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setChecked(bool(field.on_value) and field.value == field.on_value)
        self.setStyleSheet(_check_qss())
        self.toggled.connect(lambda _on: self.refresh_mark())
        self.refresh_mark()

    def refresh_mark(self) -> None:
        from butterpdf.settings import get_settings

        mark = "✕" if get_settings().checkbox_mark == "cross" else "✓"  # ✕ / ✓
        self.setText(mark if self.isChecked() else "")

    def resizeEvent(self, e) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(e)
        f = self.font()  # size the glyph to the box
        f.setPixelSize(max(6, int(self.height() * 0.78)))
        self.setFont(f)


def _text_qss() -> str:
    a = ui_helpers.ACCENT
    return (
        f"QLineEdit{{background:rgba(255,255,255,0.94);border:1px solid {a};"
        f"border-radius:2px;color:#111;padding:0 4px;selection-background-color:{a};}}"
        f"QLineEdit:focus{{border:2px solid {a};background:#ffffff;}}"
        f"QLineEdit:disabled{{background:rgba(255,255,255,0.55);color:#555;}}"
    )


def _check_qss() -> str:
    a = ui_helpers.ACCENT
    return (
        f"QPushButton{{background:rgba(255,255,255,0.94);border:1px solid {a};"
        f"border-radius:2px;color:{a};font-weight:bold;padding:0;}}"
        f"QPushButton:disabled{{background:rgba(255,255,255,0.55);color:#888;}}"
    )


def _combo_qss() -> str:
    a = ui_helpers.ACCENT
    return (
        f"QComboBox{{background:rgba(255,255,255,0.94);border:1px solid {a};"
        f"border-radius:2px;color:#111;padding:0 4px;}}"
        f"QComboBox:focus{{border:2px solid {a};}}"
    )


def make_field_widget(field) -> QWidget | None:
    """An editable widget for ``field`` (or None for a kind we don't fill yet).
    Carries ``._field``; read the current value with :func:`field_value`."""
    if field.kind == "text":
        w: QWidget = QLineEdit(field.value)
        w.setStyleSheet(_text_qss())
    elif field.kind in ("checkbox", "radio"):
        w = CheckField(field)
    elif field.kind == "choice":
        w = QComboBox()
        w.addItems(field.options or [])
        if field.value:
            i = w.findText(field.value)
            if i >= 0:
                w.setCurrentIndex(i)
        w.setStyleSheet(_combo_qss())
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

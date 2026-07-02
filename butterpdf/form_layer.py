"""Build an editable Qt widget for a PDF form field.

The viewer anchors these over the rendered page (page_view.PageWidget.add_field)
so a user can fill the real AcroForm fields in place. Widgets are deliberately
styled as obvious inputs — a near-opaque light field with an accent border — so a
fillable area reads clearly over either a light or a dark (inverted) page. The
originating :class:`~butterpdf.pdf_forms.FormField` is stashed on ``._field`` for
the save step, and ``.value_str()`` reads the current widget value uniformly.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QWidget

from butterpdf import ui_helpers


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
        f"QCheckBox{{background:transparent;}}"
        f"QCheckBox::indicator{{width:100%;height:100%;border:1px solid {a};"
        f"border-radius:2px;background:rgba(255,255,255,0.94);}}"
        f"QCheckBox::indicator:checked{{background:{a};}}"
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
        w = QCheckBox()
        w.setChecked(bool(field.on_value) and field.value == field.on_value)
        w.setStyleSheet(_check_qss())
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
    if isinstance(widget, QCheckBox):
        on = getattr(field, "on_value", None) or "Yes"
        return on if widget.isChecked() else "Off"
    return None

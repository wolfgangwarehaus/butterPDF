"""Field-widget styling — the dark-page input-fill contract (user call: no
plain white on a dark page; the soft light-grey family instead)."""

from __future__ import annotations

import pytest

pytest.importorskip("pypdf")

from butterpdf.form_layer import (  # noqa: E402
    _check_qss,
    _combo_qss,
    _text_qss,
    make_field_widget,
    restyle_field_widget,
)
from butterpdf.pdf_forms import FormField  # noqa: E402


def _field(kind="text", **kw):
    base = dict(name="f", kind=kind, rect=(0, 0, 10, 10), page_index=0,
                value="", options=None, on_value="Yes", readonly=False)
    base.update(kw)
    return FormField(**base)


@pytest.mark.parametrize("qss", [_text_qss, _check_qss, _combo_qss])
def test_dark_page_fills_avoid_plain_white(qss):
    dark = qss(True)
    assert "255,255,255" not in dark and "#ffffff" not in dark
    assert "233,235,239" in dark  # the light-grey paper family
    light = qss(False)
    assert "255,255,255" in light  # the light page keeps its near-white


@pytest.mark.usefixtures("qapp")
def test_restyle_switches_fill_live():
    w = make_field_widget(_field("text"))
    assert "255,255,255" in w.styleSheet()
    restyle_field_widget(w, dark_page=True)
    assert "233,235,239" in w.styleSheet()
    restyle_field_widget(w, dark_page=False)
    assert "255,255,255" in w.styleSheet()


@pytest.mark.usefixtures("qapp")
def test_checkbox_created_dark_starts_grey():
    w = make_field_widget(_field("checkbox"), dark_page=True)
    assert "233,235,239" in w.styleSheet()


# ── the frosted context menu (2026-07-08 walkthrough: Qt's default black
# QLineEdit popup was the one un-themed surface; opaque_menu is the convention)


@pytest.mark.usefixtures("qapp")
def test_text_field_context_menu_is_frosted_with_form_actions():
    w = make_field_widget(_field("text", value="hello"))
    menu = w._build_context_menu()
    labels = [a.text() for a in menu.actions() if a.text()]
    for expected in ("Undo", "Redo", "Cut", "Copy", "Paste", "Select All",
                     "Insert today's date"):
        assert expected in labels
    # unwired sign_here → no dangling action
    assert not any("Sign document here" in t for t in labels)
    # the opaque_menu treatment actually applied (never a raw QMenu)
    assert menu.styleSheet()


@pytest.mark.usefixtures("qapp")
def test_sign_here_action_appears_when_wired_and_passes_the_field():
    got = []
    w = make_field_widget(_field("text"), sign_here=got.append)
    menu = w._build_context_menu()
    (sign,) = [a for a in menu.actions() if "Sign document here" in a.text()]
    sign.trigger()
    assert got == [w._field]


@pytest.mark.usefixtures("qapp")
def test_insert_today_inserts_an_iso_date_at_the_cursor():
    from datetime import date

    w = make_field_widget(_field("text", value="signed on "))
    w.setCursorPosition(len(w.text()))
    w._insert_today()
    assert w.text() == f"signed on {date.today().isoformat()}"

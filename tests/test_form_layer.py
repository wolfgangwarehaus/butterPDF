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

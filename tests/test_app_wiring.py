"""run_app's subsystem wiring — autostart reconcile + the notify bus route.

These cover the two P1-leftover wirings without running the event loop: the
helpers are module-level so they're testable in isolation, and every OS-facing
call is monkeypatched (a test must never write a real autostart entry or pop a
real notification).
"""

from __future__ import annotations

import pytest

from butterpdf import app as app_mod
from butterpdf import autostart, notifications
from butterpdf.bus import AppBus


@pytest.fixture
def fresh_bus():
    """A private AppBus instance per test — the process singleton would
    accumulate ``_wire_notifications`` connections across tests (each emit
    would then fan out to every prior test's slot)."""
    saved = AppBus._instance
    AppBus._instance = None
    try:
        yield AppBus.get()
    finally:
        AppBus._instance = saved


def test_reconcile_autostart_reasserts_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "is_supported", lambda: True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: True)
    monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
    app_mod._reconcile_autostart()
    assert calls == ["enable"]


@pytest.mark.parametrize(
    ("supported", "enabled"),
    [(False, True), (True, False), (False, False)],
)
def test_reconcile_autostart_is_opt_in(monkeypatch, supported, enabled):
    """butterpdf never turns autostart ON — off or unsupported means no enable()."""
    calls = []
    monkeypatch.setattr(autostart, "is_supported", lambda: supported)
    monkeypatch.setattr(autostart, "is_enabled", lambda: enabled)
    monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
    app_mod._reconcile_autostart()
    assert calls == []


def test_reconcile_autostart_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(autostart, "is_supported", boom)
    app_mod._reconcile_autostart()  # must not raise


@pytest.mark.usefixtures("qapp")
def test_notify_signal_reaches_backend(monkeypatch, fresh_bus):
    got = []
    monkeypatch.setattr(
        notifications, "notify", lambda title, body="", **kw: got.append((title, body))
    )
    app_mod._wire_notifications(fresh_bus)
    fresh_bus.notify.emit("Saved", "form.pdf written")
    assert got == [("Saved", "form.pdf written")]


@pytest.mark.usefixtures("qapp")
def test_notify_backend_failure_is_swallowed(monkeypatch, fresh_bus):
    def boom(*a, **kw):
        raise RuntimeError("no notification daemon")

    monkeypatch.setattr(notifications, "notify", boom)
    app_mod._wire_notifications(fresh_bus)
    fresh_bus.notify.emit("still fine", "")  # must not raise through the signal


@pytest.mark.usefixtures("qapp")
def test_settings_dialog_autostart_toggle(monkeypatch):
    """The toggle appears when supported, reads the OS truth, and writes
    enable()/disable() — no QSettings mirror."""
    state = {"enabled": False}
    monkeypatch.setattr(autostart, "is_supported", lambda: True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: state["enabled"])
    monkeypatch.setattr(
        autostart, "enable", lambda: state.__setitem__("enabled", True) or True
    )
    monkeypatch.setattr(
        autostart, "disable", lambda: state.__setitem__("enabled", False) or True
    )

    from butterpdf.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    try:
        assert hasattr(dlg, "autostart_check")
        assert not dlg.autostart_check.isChecked()
        dlg.autostart_check.setChecked(True)
        assert state["enabled"] is True
        dlg.autostart_check.setChecked(False)
        assert state["enabled"] is False
    finally:
        dlg.deleteLater()


@pytest.mark.usefixtures("qapp")
def test_settings_dialog_hides_autostart_when_unsupported(monkeypatch):
    monkeypatch.setattr(autostart, "is_supported", lambda: False)

    from butterpdf.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    try:
        assert not hasattr(dlg, "autostart_check")
    finally:
        dlg.deleteLater()


# ── Second-launch file forwarding → the viewer ──────────────────────────────
class _StubWindow:
    """Just enough window for _build_content: a footer slot + a bare top_bar
    (no bind_viewer, so the menu wiring is skipped)."""

    def __init__(self):
        self.top_bar = object()
        self.footer = None

    def set_footer(self, w):
        self.footer = w


def test_files_received_opens_forwarded_pdf(qapp, fresh_bus, tmp_path, minimal_pdf):
    """Round-trip for the second-launch path: run_app re-emits the forwarded
    argv as AppBus.files_received; _build_content binds it to the viewer, so
    a `butterpdf doc.pdf` against a running instance opens the document."""
    pdf = tmp_path / "forwarded.pdf"
    pdf.write_bytes(minimal_pdf)

    viewer = app_mod._build_content(_StubWindow())
    try:
        fresh_bus.files_received.emit([str(pdf)])
        qapp.processEvents()
        from PySide6.QtPdf import QPdfDocument

        assert viewer._doc.status() == QPdfDocument.Status.Ready
        assert viewer._path == str(pdf)
    finally:
        viewer.deleteLater()


def test_files_received_ignores_non_pdfs(qapp, fresh_bus, tmp_path):
    """The forwarded payload is unfiltered argv — same .pdf-and-exists filter
    as the first-launch loop, so a stray text file never reaches the engine."""
    txt = tmp_path / "notes.txt"
    txt.write_text("not a pdf")

    viewer = app_mod._build_content(_StubWindow())
    try:
        fresh_bus.files_received.emit([str(txt), str(tmp_path / "gone.pdf")])
        qapp.processEvents()
        assert viewer._path is None  # nothing opened; the empty state stays
    finally:
        viewer.deleteLater()
